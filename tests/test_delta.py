#!/usr/bin/env python3
"""`Session._delta` et `Session._cle` — les deux fonctions PURES du pipeline.

Elles décident ce que le modèle reçoit à chaque tick. Elles ne touchent ni au
micro, ni au réseau, ni à l'horloge : elles se testent en mémoire, et c'est la
seule partie du projet dont on peut prouver le comportement sans enregistrer
un son. Le banc, lui, lance `pipeline.py` en sous-processus — il teste une CLI,
pas ces deux fonctions.

    .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

Ce fichier complète `tests/delta.py` (qui épingle les pièges historiques) sur
un point qu'il ne couvrait pas : l'ANCRAGE lui-même.

Le contrat d'entrée. `transcript` est le texte cumulatif du TOUR rendu par
`stt.py` — c'est-à-dire `fige + segment courant`, où `fige` ne fait que
croître (les segments clos y sont concaténés, jamais réécrits) et où seul le
segment courant est révisable par le décodeur. Le préfixe commun entre deux
transcripts successifs couvre donc tout `fige` puis la part stable du segment :
s'ancrer sur ce préfixe, c'est s'ancrer sur le préfixe DU SEGMENT, exprimé dans
les coordonnées que `pipeline` a sous la main.

Deux cas interdisent cet ancrage, et ils ont chacun leur classe de tests :

  - la RÉVISION EN TÊTE — whisper re-transcrit toute sa fenêtre, donc il peut
    corriger son premier mot (« LA » → « L HEURE ») ou halluciner un générique
    devant. Le préfixe commun retombe alors à zéro, et le publier voudrait dire
    renvoyer la phrase entière comme si elle venait d'être dite ;
  - la CROISSANCE INTERNE — un mot inséré au milieu sans que rien ne s'ajoute
    à la fin (« je peux venir » → « je ne peux pas venir »). Le préfixe rendrait
    toute la queue déjà envoyée.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pipeline                                          # noqa: E402

SILENCE = "<|no voice|>"


class Faux(pipeline.Session):
    """Une `Session` réduite à ce que `_delta` lit.

    `pipeline.Session.__init__` démarre le moteur STT, le TTS et le décideur :
    on ne l'appelle pas. `_delta` ne lit que `vu`, `transcript`, et la porte de
    volume — neutralisée ici, le corpus d'un test n'a pas de crête audio."""

    def __init__(self):
        self.silence = SILENCE

    def _muet_mesure(self):
        return False

    def _rien(self):
        return self.silence


def delta(vu, courant):
    s = Faux()
    s.vu, s.transcript = vu, courant
    return s._delta()


class TestCle(unittest.TestCase):
    """`_cle` — la forme comparable d'un mot.

    Sans elle, la ponctuation et la capitalisation que whisper refait à chaque
    passe cassent l'ancrage : « Bonjour, » et « bonjour » deviennent deux mots
    différents, le préfixe commun tombe à zéro, et tout le tour repart comme
    neuf. C'est le préalable des deux ancrages, pas un détail de confort."""

    def test_capitalisation(self):
        self.assertEqual(pipeline.Session._cle("Bonjour"), "bonjour")

    def test_ponctuation_aux_deux_bouts(self):
        # Un seul JETON à chaque fois : `_delta` appelle `_cle` sur le résultat
        # d'un `split()`, jamais sur une phrase.
        for brut in ("bonjour,", "bonjour.", "bonjour!", "bonjour?",
                     "bonjour…", "«bonjour»", '"bonjour"', "(bonjour)"):
            self.assertEqual(pipeline.Session._cle(brut), "bonjour", msg=brut)

    def test_meme_mot_reponctue(self):
        self.assertEqual(pipeline.Session._cle("Bonjour,"),
                         pipeline.Session._cle("bonjour"))

    def test_apostrophe_interne_conservee(self):
        # L'apostrophe INTERNE porte du sens (« m'entends » n'est pas
        # « mentends ») ; seule celle des bouts est du décor.
        self.assertEqual(pipeline.Session._cle("M'ENTENDS"), "m'entends")

    def test_apostrophe_finale_retiree(self):
        # « M' » est une élision que le décodeur va compléter : sa clé est le
        # radical, sinon un mot en cours d'écriture ne s'aligne sur rien.
        self.assertEqual(pipeline.Session._cle("M'"), "m")

    def test_mot_vide(self):
        self.assertEqual(pipeline.Session._cle(""), "")

    def test_ponctuation_seule(self):
        self.assertEqual(pipeline.Session._cle("..."), "")


class TestDeltaCasDeBase(unittest.TestCase):
    """Ce que le tick doit rendre quand rien de subtil ne se passe."""

    def test_premier_mot_du_tour(self):
        self.assertEqual(delta("", "SALUT"), "SALUT")

    def test_rien_de_neuf_est_un_silence(self):
        # Rendre à nouveau « SALUT » ferait lire au modèle une répétition ;
        # le marqueur dit la vérité — il ne s'est rien ajouté.
        self.assertEqual(delta("SALUT", "SALUT"), SILENCE)

    def test_transcript_vide(self):
        self.assertEqual(delta("BONJOUR", ""), SILENCE)

    def test_vu_ne_contient_que_du_blanc(self):
        self.assertEqual(delta("   ", "BONJOUR"), "BONJOUR")

    def test_ajout_en_queue(self):
        self.assertEqual(delta("EST CE QUE TU PEUX",
                               "EST CE QUE TU PEUX ME DIRE"), "ME DIRE")

    def test_transcript_raccourci(self):
        # L'ASR a retiré des mots. Rien n'est neuf : ne rien renvoyer.
        self.assertEqual(delta("BONJOUR JE VOUDRAIS SAVOIR",
                               "BONJOUR JE VOUDRAIS"), SILENCE)


class TestDeltaRevisionDeQueue(unittest.TestCase):
    """Le décodeur allonge et corrige SA QUEUE — le régime ordinaire.

    Un transducteur en flux écrit son dernier mot caractère par caractère
    (« VOU » → « VOUDRAIS ») et le corrige jusqu'au dernier moment. Le mot
    révisé doit repartir : ne pas le renvoyer, c'est laisser le modèle sur une
    troncature, et c'est ce qui rendait le système sourd pour le reste du tour
    (quarante secondes mesurées en session le 03/09)."""

    def test_dernier_mot_complete(self):
        self.assertEqual(delta("SALUT TU M'", "SALUT TU M'ENTENDS"),
                         "M'ENTENDS")

    def test_complete_puis_suivi_de_mots_neufs(self):
        self.assertEqual(delta("BONJOUR JE VOU", "BONJOUR JE VOUDRAIS SAVOIR"),
                         "VOUDRAIS SAVOIR")

    def test_complete_en_changeant_d_orthographe(self):
        self.assertEqual(delta("JE VAIS AU", "JE VAIS AUX TOILETTES"),
                         "AUX TOILETTES")

    def test_plusieurs_mots_partiels_recolles(self):
        self.assertEqual(delta("peux me dire s y l",
                               "peux me dire si le train"), "si le train")


class TestDeltaRepetitions(unittest.TestCase):
    """Un mot qui revient ne doit pas piéger l'ancre.

    L'ancrage cherché EN PARTANT DE LA FIN s'accrochait à la mauvaise
    occurrence et rendait zéro. Ces cas-là restent verts quel que soit
    l'ancrage retenu — ils sont là pour qu'on s'en aperçoive s'ils tombent."""

    def test_repetition_pure(self):
        self.assertEqual(delta("oui oui", "oui oui oui"), "oui")

    def test_groupe_repete(self):
        self.assertEqual(delta("je veux je", "je veux je veux"), "veux")


class TestDeltaRevisionEnTete(unittest.TestCase):
    """L'ASR réécrit sa TÊTE — le cas qui interdit l'ancrage naïf par préfixe.

    Whisper n'est pas causal : il re-transcrit toute la fenêtre à chaque passe,
    donc il corrige aussi son premier mot, et sa fenêtre finit par glisser.
    Le préfixe commun retombe alors à zéro. Publier `mc[0:]` renverrait la
    phrase ENTIÈRE comme neuve : le modèle la lit comme un énoncé complet et
    répond au milieu du propos. Mesuré deux fois en vingt secondes.

    Ces tests sont la contrepartie de `TestDeltaAncrageParLePrefixe` : ils
    fixent la limite au-delà de laquelle le préfixe n'est plus une ancre."""

    def test_mot_du_debut_corrige(self):
        # « BONJOUR » → « BONSOIR » : seul « SAVOIR » est neuf.
        self.assertEqual(delta("BONJOUR JE VOUDRAIS",
                               "BONSOIR JE VOUDRAIS SAVOIR"), "SAVOIR")

    def test_la_devient_l_heure(self):
        # Le cas nommé dans la consigne, avec de la parole derrière l'ancre.
        # Un préfixe nu rendrait tout le tour ; ici on ne veut que le neuf.
        self.assertEqual(delta("IL EST LA", "IL EST L HEURE"), "L HEURE")

    def test_parole_neuve_devant_une_ancre_d_un_mot(self):
        self.assertEqual(delta("OUI", "JE NE SAIS PAS OUI"), "JE NE SAIS PAS")

    def test_ancre_en_dernier_mot(self):
        self.assertEqual(delta("LA", "JE SUIS LA"), "JE SUIS")

    def test_un_seul_mot_insere_en_tete(self):
        self.assertEqual(delta("NON", "MAIS NON"), "MAIS")

    def test_hallucination_de_generique_en_tete(self):
        # « Sous-titrage… » n'est pas de la parole : le filtre d'artefacts le
        # distingue d'une vraie insertion en tête, la position ne le peut pas.
        self.assertEqual(delta("merci beaucoup",
                               "sous-titrage merci beaucoup"), SILENCE)


class TestDeltaCroissanceInterne(unittest.TestCase):
    """Un mot apparaît AU MILIEU sans que rien ne s'ajoute à la fin.

    Le préfixe s'arrête à l'insertion, mais toute la queue derrière a déjà été
    envoyée : la publier serait un doublon pur. On ne rend que l'inséré."""

    def test_insertions_au_milieu(self):
        self.assertEqual(delta("je peux venir", "je ne peux pas venir"),
                         "ne pas")

    def test_insertion_avant_un_mot_identique(self):
        self.assertEqual(delta("de sept heures p", "de sept heures pour p"),
                         "pour")

    def test_mot_d_ancrage_repete_plus_loin(self):
        self.assertEqual(delta("correspondance ou", "correspondance oui ou"),
                         "oui")


class TestDeltaAncrageParLePrefixe(unittest.TestCase):
    """LE défaut corrigé : une révision AU MILIEU suivie de texte neuf.

    L'ancrage par la QUEUE prend la fin du dernier bloc aligné entre `vu` et le
    transcript courant, et ne rend que ce qui vient après. Quand le décodeur
    révise un mot déjà envoyé ET ajoute derrière, le mot révisé se retrouve
    AVANT ce dernier bloc : il n'est jamais envoyé. Le modèle garde la version
    fausse pour tout le reste du tour.

    L'ancrage par le préfixe du segment n'a pas ce trou : dès qu'un mot change,
    tout ce qui suit repart. On paie la republication de quelques mots déjà
    vus — un doublon se relit, un mot manquant ne se devine pas."""

    def test_revision_au_milieu_puis_ajout(self):
        # « VAI » corrigé en « VAIS », et « BIEN » arrive dans le même tick.
        self.assertEqual(delta("JE VAI TRES", "JE VAIS TRES BIEN"),
                         "VAIS TRES BIEN")

    def test_revision_loin_de_la_queue(self):
        self.assertEqual(delta("TU AS UN TRAIN", "TU AS EU UN TRAIN DIRECT"),
                         "EU UN TRAIN DIRECT")

    def test_revision_sans_ajout_reste_minimale(self):
        # Rien de neuf en queue : la croissance est interne, on ne republie
        # pas la queue. C'est la frontière entre les deux régimes.
        self.assertEqual(delta("JE VAI TRES BIEN", "JE VAIS TRES BIEN"),
                         "VAIS")


class TestDeltaFrontiereDeSegment(unittest.TestCase):
    """Ce que la fermeture d'un segment fait au transcript.

    `stt.py` concatène le segment clos dans `fige`, avec un espace en général,
    SANS espace quand le décodeur écrivait encore au bloc précédent (règle 3 de
    sherpa, qui coupe sur une durée d'énoncé). Le tour vu par `_delta` change
    donc de forme à la frontière, sans qu'un mot n'ait été prononcé."""

    def test_fermeture_ne_change_rien_au_texte(self):
        # Cas ordinaire : le segment rejoint `fige` avec un espace, le
        # transcript est identique — aucun mot neuf, donc silence.
        self.assertEqual(delta("BONJOUR CA VA", "BONJOUR CA VA"), SILENCE)

    def test_segment_suivant_s_ajoute_normalement(self):
        self.assertEqual(delta("BONJOUR CA VA", "BONJOUR CA VA ET TOI"),
                         "ET TOI")

    def test_recollage_sans_espace_republie_le_mot_ressoude(self):
        # « SUMMARISE » coupé en plein mot laisse « SUM » figé, puis « ARISE »
        # revient au segment suivant : `stt.py` les ressoude en « SUMARISE ».
        # Le mot ressoudé DOIT repartir, sinon le modèle garde « SUM ».
        self.assertEqual(delta("PLEASE SUM", "PLEASE SUMARISE OUR DIALOGUE"),
                         "SUMARISE OUR DIALOGUE")

    def test_recollage_en_tete_de_tour(self):
        # Même chose quand le mot ressoudé est le premier du tour : le préfixe
        # est nul, c'est l'alignement qui doit s'en sortir.
        self.assertEqual(delta("SUM", "SUMARISE OUR DIALOGUE"),
                         "SUMARISE OUR DIALOGUE")


class TestDeltaPorteAudio(unittest.TestCase):
    """La mesure du son prime sur ce que le décodeur a rendu.

    Sur un tick réellement silencieux, un ASR invente des phrases plausibles
    qu'aucune liste d'artefacts ne peut prévoir. La crête, elle, est une
    mesure : sous le seuil, il ne s'est rien dit."""

    def test_tick_mesure_muet(self):
        s = Faux()
        s._muet_mesure = lambda: True
        s.vu, s.transcript = "", "UNE PHRASE INVENTEE"
        self.assertEqual(s._delta(), SILENCE)


if __name__ == "__main__":
    unittest.main()
