#!/usr/bin/env python3
"""L'interruption déduite par l'hôte, et les deux backchannel.

    .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

Ce que ces tests épinglent (PLAN-REPRO § 3.1 à 3.3, 04/09/2026) :

  - `<user is interrupting>` n'existe plus. Il était défini « pendant que tu
    parles » alors que rien ne dit au modèle qu'il parle, et il n'a jamais été
    émis : 0 fois sur 897 décisions. À la place, un ET logique dans l'hôte —
    un `parle` reçu pendant qu'on lit une réponse EST une interruption ;
  - `<user backchannel>` ne coupe PAS. C'est ce qui sépare les deux moitiés de
    leur démo 2 : « Okay », « Yes », puis « Okay, please summarize in one
    sentence » — le même mot, deux rôles, tous les trois pendant qu'on parle ;
  - `<system backchannel>` déclenche un clip pré-synthétisé, pas du TTS.

Aucun réseau, aucun son, aucune horloge réelle : tout est en mémoire. La
`Session` n'est jamais construite (son `__init__` démarre le STT, le TTS et le
décideur) — on n'instancie que ce que `_appliquer` lit vraiment.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import llm        # noqa: E402
import pipeline   # noqa: E402
import tts        # noqa: E402


class Voix:
    """Un locuteur factice : il dit s'il parle, et note qu'on l'a coupé."""

    def __init__(self, parle=False):
        self._parle = parle
        self.coupures = 0

    def speaking(self):
        return self._parle

    def stop(self):
        self.coupures += 1
        self._parle = False


class ClipsFactices:
    def __init__(self, chemins=("clips/fr/00.wav",)):
        self.actif = True
        self.joues = []
        self.chemins = list(chemins)

    def jouer(self):
        if not self.chemins:
            return None
        self.joues.append(self.chemins[len(self.joues) % len(self.chemins)])
        return self.joues[-1]


class Hote(pipeline.Session):
    """Une `Session` réduite à ce que `_appliquer` lit."""

    def __init__(self, langue="fr", parle=False):
        cat = llm.catalogue(langue)
        self.langue = langue
        self.jetons = cat["jetons"]
        self.etats = cat["etats"]
        self.silence = cat["divers"]["silence"]
        self.bruit_sans_texte = cat["divers"]["bruit_sans_texte"]
        self.voix = Voix(parle)
        self.clips = ClipsFactices()
        self.robot_parle = parle
        self.texte_dit = ""
        self.micro_tours = []
        self.stats = []
        self.silences = 0
        self.seq = 1
        self.en_vol = True
        self.trace = None
        self.lignes = []

    def log(self, s):
        self.lignes.append(s)


def appliquer(hote, action, texte="", delta="d'accord et le samedi"):
    hote._appliquer(action, texte, delta, 0.1, hote.seq)
    return hote


class TestJetonRetire(unittest.TestCase):
    """§ 3.1 — le jeton d'interruption a quitté les deux catalogues."""

    def test_absent_des_catalogues(self):
        for lg in ("fr", "en"):
            self.assertNotIn("coupe", llm.catalogue(lg)["jetons"], lg)

    def test_absent_des_quatre_prompts(self):
        for lg in ("fr", "en"):
            for moteur in (None, "sherpa"):
                p = llm.systeme(lg, tick=1.2, moteur=moteur)
                self.assertNotIn("interrupting", p, f"{lg}/{moteur}")

    def test_marqueur_inconnu_reste_hors_format(self):
        """Reçu quand même — vieille trace, modèle têtu — il ne doit pas être
        silencieusement pris pour autre chose."""
        a, _ = llm.lire_controle('{"m": "<user is interrupting>"}', "fr")
        self.assertEqual(a, "format")


class TestDeductionHote(unittest.TestCase):
    """§ 3.1 — l'ET logique : `parle` ET on parle."""

    def test_parle_pendant_qu_on_parle_coupe(self):
        h = appliquer(Hote(parle=True), "parle")
        self.assertEqual(h.voix.coupures, 1)

    def test_parle_alors_qu_on_se_tait_ne_coupe_pas(self):
        h = appliquer(Hote(parle=False), "parle")
        self.assertEqual(h.voix.coupures, 0)

    def test_silence_pendant_qu_on_parle_ne_coupe_pas(self):
        """L'écho passe toujours un peu la porte : sans cette garde, quatre
        prises de parole sur quatre étaient coupées par notre propre voix."""
        h = appliquer(Hote(parle=True), "parle",
                      delta=llm.catalogue("fr")["divers"]["silence"])
        self.assertEqual(h.voix.coupures, 0)

    def test_notre_propre_voix_ne_coupe_pas(self):
        h = Hote(parle=True)
        h.texte_dit = "Le samedi, c'est la même cadence."
        appliquer(h, "parle", delta="le samedi c'est la même cadence")
        self.assertEqual(h.voix.coupures, 0)

    def test_robot_parle_suit_le_locuteur(self):
        """Le rejeu déterministe ne rafraîchissait jamais cet état : il restait
        vrai pour toujours après la première réponse."""
        h = Hote(parle=False)
        h.robot_parle = True
        h._je_parle()
        self.assertFalse(h.robot_parle)


class TestBackchannelUtilisateur(unittest.TestCase):
    """§ 3.2 — « ne prends pas la parole ET ne t'interromps pas »."""

    def test_decode_comme_action_propre(self):
        for lg in ("fr", "en"):
            jeton = llm.catalogue(lg)["jetons"]["backchannel"]
            a, _ = llm.lire_controle('{"m": "%s"}' % jeton, lg)
            self.assertEqual(a, "backchannel", lg)

    def test_ne_coupe_pas_meme_pendant_qu_on_parle(self):
        h = appliquer(Hote(parle=True), "backchannel", delta="d'accord")
        self.assertEqual(h.voix.coupures, 0)

    def test_la_sequence_de_la_demo_2(self):
        """« Okay », « Yes », puis « Okay, please summarize in one sentence » :
        les deux premiers ne coupent pas, le troisième coupe."""
        h = Hote("en", parle=True)
        appliquer(h, "backchannel", delta="okay")
        appliquer(h, "backchannel", delta="yes")
        self.assertEqual(h.voix.coupures, 0)
        appliquer(h, "parle", delta="okay please summarize in one sentence")
        self.assertEqual(h.voix.coupures, 1)

    def test_ecrit_son_propre_marqueur_dans_l_historique(self):
        h = appliquer(Hote(parle=True), "backchannel", delta="d'accord")
        self.assertIn(h.jetons["backchannel"], h.micro_tours[-1]["content"])


class TestBackchannelSysteme(unittest.TestCase):
    """§ 3.3 — le marqueur déclenche enfin quelque chose."""

    def test_decode_comme_action_propre(self):
        for lg in ("fr", "en"):
            jeton = llm.catalogue(lg)["jetons"]["mhm"]
            a, _ = llm.lire_controle('{"m": "%s"}' % jeton, lg)
            self.assertEqual(a, "mhm", lg)

    def test_joue_un_clip(self):
        h = appliquer(Hote(), "mhm", delta="comment on va de Paris à Lyon")
        self.assertEqual(len(h.clips.joues), 1)

    def test_ne_touche_pas_au_locuteur(self):
        """Le clip ne doit ni retarder la réponse ni couper l'écoute : il ne
        passe pas par le locuteur, donc il ne pose pas l'état « je parle »."""
        h = appliquer(Hote(parle=True), "mhm", delta="et pour le retour")
        self.assertEqual(h.voix.coupures, 0)
        self.assertTrue(h.voix.speaking())


class TestClips(unittest.TestCase):
    """La mécanique de tirage, sans jamais lancer `aplay`."""

    def test_dossier_vide_ne_leve_pas(self):
        c = tts.Clips("fr", dossier="/nexistepas", actif=False)
        self.assertIsNone(c.jouer())

    def test_les_clips_du_depot_sont_la(self):
        for lg in ("fr", "en"):
            c = tts.Clips(lg, actif=False)
            self.assertTrue(c.fichiers, f"clips/{lg} vide — clips/generer.py")

    def test_jamais_deux_fois_le_meme_d_affilee(self):
        c = tts.Clips("fr", actif=False)
        if len(c.fichiers) < 2:
            self.skipTest("moins de deux clips")
        tires = [c.jouer() for _ in range(40)]
        self.assertFalse(any(a == b for a, b in zip(tires, tires[1:])))

    def test_inactif_tire_mais_ne_joue_rien(self):
        c = tts.Clips("fr", actif=False)
        self.assertIsNotNone(c.jouer())
        self.assertEqual(c._procs, [])


class TestExemplesParMoteur(unittest.TestCase):
    """Les exemples suivent le moteur, comme les prompts.

    `systeme_sherpa` annonce « majuscules sans ponctuation » à sa première
    ligne ; montrer en dessous sept exemples en minuscules ponctuées revenait à
    se contredire dans la zone du prompt qui vaut +0,063 de justesse."""

    PONCTUATION = set(".,;:!?'’«»")

    def test_les_entrees_sherpa_sont_nues(self):
        silence = None
        for lg in ("fr", "en"):
            silence = llm.catalogue(lg)["divers"]["silence"]
            for entree, _ in llm.exemples(lg, "sherpa"):
                if entree == silence:
                    continue
                self.assertEqual(entree, entree.upper(), f"{lg}: {entree}")
                self.assertFalse(self.PONCTUATION & set(entree),
                                 f"{lg}: {entree}")

    def test_les_reponses_parlees_restent_du_texte_normal(self):
        """`r` part au TTS : piper insère deux faux silences au milieu d'un
        « J.K. Rowling ». Les majuscules n'ont rien à y faire."""
        for lg in ("fr", "en"):
            for _, sortie in llm.exemples(lg, "sherpa"):
                if '"r"' not in sortie:
                    continue
                import json
                r = json.loads(sortie)["r"]
                self.assertNotEqual(r, r.upper(), f"{lg}: {r}")

    def test_le_prompt_whisper_garde_ses_exemples_ponctues(self):
        for lg in ("fr", "en"):
            entrees = [e for e, _ in llm.exemples(lg, None)]
            self.assertNotEqual(entrees, [e for e, _ in llm.exemples(lg, "sherpa")])
            self.assertTrue(any(e != e.upper() for e in entrees), lg)

    def test_le_bon_jeu_atterrit_dans_le_bon_prompt(self):
        for lg in ("fr", "en"):
            sherpa = llm.systeme(lg, 1.2, "sherpa")
            defaut = llm.systeme(lg, 1.2, None)
            for entree, _ in llm.exemples(lg, "sherpa"):
                self.assertIn(entree, sherpa, f"{lg}: {entree}")
            for entree, _ in llm.exemples(lg, None):
                self.assertIn(entree, defaut, f"{lg}: {entree}")

    def test_aucun_placeholder_residuel(self):
        import re
        for lg in ("fr", "en"):
            for moteur in (None, "sherpa"):
                p = llm.systeme(lg, tick=1.2, moteur=moteur)
                self.assertEqual(re.findall(r"\{(?:tick|exemples)\}", p), [],
                                 f"{lg}/{moteur}")


class TestExemplesMontrentLesBackchannel(unittest.TestCase):
    """§ 3.2 — le levier le plus fort du prompt : il n'y en avait AUCUN."""

    def test_les_deux_marqueurs_apparaissent_en_sortie(self):
        for lg in ("fr", "en"):
            j = llm.catalogue(lg)["jetons"]
            for moteur in (None, "sherpa"):
                sorties = " ".join(s for _, s in llm.exemples(lg, moteur))
                self.assertIn(j["backchannel"], sorties, f"{lg}/{moteur}")
                self.assertIn(j["mhm"], sorties, f"{lg}/{moteur}")

    def test_le_prompt_dit_quand_les_emettre(self):
        for lg in ("fr", "en"):
            for moteur in (None, "sherpa"):
                p = llm.systeme(lg, 1.2, moteur).lower()
                # le mot-clé du « ne juge pas sur le premier mot »
                self.assertTrue("entière" in p or "whole line" in p,
                                f"{lg}/{moteur}")


if __name__ == "__main__":
    unittest.main()
