#!/usr/bin/env python3
"""Étage STT de microturn — produit des événements de transcription dans une queue.

Deux moteurs derrière le même contrat. Chacun tourne dans SON thread et ne fait
que lire l'audio et poser des événements ; il ne bloque jamais sur autre chose.

    ("partial", texte, t)   hypothèse révisable, peut changer au mot suivant
    ("final",   texte, t)   segment figé
    ("eof",     "",    t)   la source est épuisée

  whisper : le plus rapide et le plus léger sur Pi 3B (RTF 1,21 contre 1,86 pour
            Vosk sur le même audio, 130 Mo contre 241). Il ne sait pas produire de
            partiels : on re-transcrit une fenêtre glissante, ce qui revient au même
            du point de vue du consommateur — une hypothèse qui se révise.
  vosk    : partiels natifs mot à mot, mais mono-thread, donc un seul des quatre
            cœurs du Pi. Gardé pour comparaison.

Usage direct (banc de mesure) :
    python stt.py samples/01-normal.wav            # whisper
    python stt.py --moteur vosk samples/01.wav
"""
import json, os, queue, threading, time
import numpy as np
import audio

# Exactement le modèle mesuré sur le Pi. Surchargeable pour comparer deux
# tailles sur le même audio : `MICROTURN_WHISPER=models/ggml-base-q5_1.bin`.
WHISPER_MODEL = os.environ.get("MICROTURN_WHISPER", "models/ggml-tiny-q5_1.bin")
VOSK_DIR = "models/vosk-model-small-fr-0.22"

# whisper n'a pas de transcription incrémentale : on lui redonne tout le tour à
# chaque passe, et on remet le tampon à zéro après chaque réponse (`reset()`).
# Une fenêtre GLISSANTE serait moins chère mais perdrait le début de la phrase —
# le décideur ne verrait qu'une lucarne mouvante et ne pourrait pas trancher.
# Coût d'une passe = RTF × durée du tour, d'où PLAFOND_S qui borne le pire cas.
PLAFOND_S = 20.0                # au-delà, on coupe le tour de force
PAS_S = 0.5                     # plancher ; la vraie cadence est celle du décodage

# Sur du silence ou du souffle, whisper invente des balises de sous-titrage.
# Observé en vrai : « (musique) », « [Rire] », « (crisse) (crisse) », « ... ... ».
# Non filtrées, elles comptent comme du texte et déclenchent des réponses.
import re
from collections import Counter

_BALISE = re.compile(r"[\(\[\*][^\)\]\*]{0,40}[\)\]\*]")
_MOT = re.compile(r"[a-zà-öø-ÿ]{2,}", re.I)
# Générique de fin de sous-titres : whisper l'a appris de ses données
# d'entraînement et le recrache sur du silence prolongé.
_GENERIQUE = re.compile(r"sous[- ]titr\w*\s+(réalis|par|fait)", re.I)
# Ces mots-là ne sont JAMAIS du contenu utile quand ils forment tout le texte.
_VIDES = {"musique", "music", "applaudissements", "rires", "rire", "silence",
          "sous", "titres", "titrage", "générique", "bruit", "bruits", "soupir",
          "crisse", "crisses", "toux", "vent", "cliquetis", "sifflement"}


def utile(texte):
    """Faux si le texte n'est qu'un artefact du décodeur, pas de la parole.

    Trois familles, toutes observées sur de vraies sessions :
      - les balises de sous-titrage inventées sur du silence ;
      - un texte sans aucun mot réel (« ... ... ... ») ;
      - le bégaiement, quand le décodeur part en boucle sur un signal dégradé.
    """
    t = (texte or "").strip()
    if not t:
        return False

    if _GENERIQUE.search(t):
        return False
    # 1. balises retirées ; s'il ne reste aucun mot, c'était du décor
    sans_balises = _BALISE.sub(" ", t)
    mots = [m.lower() for m in _MOT.findall(sans_balises)]
    if not mots:
        return False
    # ... ou uniquement des mots qui ne décrivent qu'un bruit
    if all(m in _VIDES for m in mots):
        return False

    # 2. bégaiement : un motif qui revient et couvre l'essentiel du texte.
    # Fenêtre GLISSANTE : « à la fin de la fin de la fin » décale le motif d'un
    # mot, un découpage par blocs le manquerait.
    if len(mots) >= 6:
        for n in range(1, 7):
            grammes = [tuple(mots[i:i + n]) for i in range(len(mots) - n + 1)]
            if len(grammes) < 3:
                break
            occurrences = Counter(grammes).most_common(1)[0][1]
            if occurrences >= 3 and occurrences * n >= len(mots) * 0.5:
                return False
    return True


class Whisper:
    """Fenêtre glissante re-transcrite : le modèle reste chargé, seul l'audio bouge."""

    def __init__(self, model=WHISPER_MODEL, langue="fr", threads=3):
        from pywhispercpp.model import Model
        t0 = time.time()
        self.reglages = {"modele": model, "langue": langue, "threads": threads,
                         "audio_ctx": 1152, "best_of": 1, "temperature_inc": 0.0,
                         "single_segment": True, "no_context": True,
                         "PLAFOND_S": PLAFOND_S, "PAS_S": PAS_S}
        # audio_ctx=1152 : whisper remplit sinon 30 s de contexte quel que soit
        # l'audio réel, et paie l'encodeur pour du vide. 1152 ≈ 23 s, juste
        # au-dessus de PLAFOND_S. Mesuré +31 % ici, transcription identique.
        # best_of=1 et temperature_inc=0 suppriment le ré-échantillonnage et le
        # repli de température : sans effet sur un audio propre, mais ils évitent
        # des passes supplémentaires imprévisibles quand la transcription patine.
        self.m = Model(model, language=langue, n_threads=threads,
                       print_progress=False, print_realtime=False,
                       single_segment=True, no_context=True,
                       audio_ctx=1152, greedy={"best_of": 1}, temperature_inc=0.0)
        self.charge_s = time.time() - t0

    def run(self, cap, q, stop):
        """Deux threads : un lecteur qui ne fait QUE vider le tube, et le décodage.

        Si le même thread lisait et transcrivait, il cesserait de lire pendant
        toute la passe (plus d'une seconde) ; le tube déborderait et ALSA
        perdrait de l'audio."""
        t0 = time.time()
        buf = np.empty(0, dtype=np.float32)
        garde = threading.Lock()
        fini = threading.Event()

        def lecteur():
            nonlocal buf
            while not stop.is_set():
                data = cap.lire()
                if data is None:
                    break
                # Le drapeau est consommé AVANT tout `continue` : sinon un tour
                # fermé pendant que la porte jette (ce qui est le cas normal —
                # elle jette pendant qu'on parle) ne vide jamais le tampon. La
                # phrase à laquelle on venait de répondre y restait, whisper la
                # re-transcrivait, on y répondait encore : boucle infinie qui
                # survivait au micro coupé.
                raz = self._raz
                if raz:
                    self._raz = False
                if not data:               # jeté par la porte (écho ou silence) —
                    if raz:                # le tube, lui, a bien été vidé
                        with garde:
                            buf = np.empty(0, dtype=np.float32)
                    continue
                bloc = np.frombuffer(data, np.int16).astype(np.float32) / 32768
                with garde:
                    if raz:
                        # Le vidage se fait ICI, dans le lecteur, et pas dans le
                        # thread de décodage : celui-ci est presque toujours au
                        # milieu d'une passe (plus d'une seconde ici, plusieurs
                        # secondes sur un Pi) et vidait alors tout le tampon —
                        # y compris l'audio arrivé PENDANT la passe. C'était
                        # jeter la parole de l'utilisateur juste au moment où il
                        # est le plus susceptible de couper.
                        buf = bloc
                    else:
                        buf = np.concatenate([buf, bloc])
                    trop = len(buf) - int(PLAFOND_S * audio.RATE)
                    if trop > 0:               # garde-fou : un tour interminable
                        buf = buf[trop:]       # ne doit pas faire exploser le coût
            fini.set()

        th = threading.Thread(target=lecteur, daemon=True)
        th.start()

        dernier = ""
        gen_vu = self._gen
        while not stop.is_set():
            if fini.is_set():
                break
            if gen_vu != self._gen:      # un tour s'est fermé entre-temps
                gen_vu = self._gen
                dernier = ""
            with garde:
                fenetre = buf.copy()
            if len(fenetre) < audio.RATE // 2:
                time.sleep(PAS_S)
                continue
            gen = self._gen                # pour repérer un reset() pendant la passe
            t_passe = time.time()
            txt = " ".join(s.text for s in self.m.transcribe(fenetre)).strip()
            self.dernier_cout = time.time() - t_passe
            # Une passe dure plus d'une seconde. Si on a répondu entre-temps,
            # son résultat décrit un tour déjà traité : le publier ferait
            # répondre une deuxième fois à la même phrase.
            perime = gen != self._gen
            # Le `continue` d'avant sautait la pause de cadencement : sur du
            # silence, whisper hallucine à chaque passe, donc on repartait
            # aussitôt. Trois cœurs à fond alors que personne ne parle — 80 °C
            # en 25 s sur un Pi 3B. La pause doit être payée dans TOUS les cas.
            if txt and not perime and utile(txt) and txt != dernier:
                dernier = txt
                if cap.trace is not None:
                    cap.trace.ev("partial", texte=txt, cout=round(self.dernier_cout, 3))
                q.put(("partial", txt, time.time() - t0))
            reste = PAS_S - self.dernier_cout
            if reste > 0:
                time.sleep(reste)

        th.join(timeout=1)
        q.put(("eof", "", time.time() - t0))

    dernier_cout = 0.0
    _raz = False
    _gen = 0

    def reset(self):
        """Ferme le tour : le tampon repart de zéro, donc le prochain transcript
        ne recontient pas ce à quoi on vient déjà de répondre.

        Le compteur invalide aussi une passe DÉJÀ EN COURS, dont le résultat
        décrirait un tour auquel on vient de répondre."""
        self._gen += 1
        self._raz = True


class Vosk:
    def __init__(self, path=VOSK_DIR):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        t0 = time.time()
        self.model = Model(path)               # gardé en attribut : évite la question
        self.rec = KaldiRecognizer(self.model, audio.RATE)
        self.charge_s = time.time() - t0

    _raz = False

    def run(self, cap, q, stop):
        import json
        t0 = time.time()
        while not stop.is_set():
            if self._raz:
                self.rec.Reset()
                self._raz = False
            data = cap.lire()
            if data is None:
                break
            if not data:
                continue               # jeté par la porte ; ne pas le donner au
                                       # treillis, qui y verrait un mot
            if self.rec.AcceptWaveform(data):
                txt = json.loads(self.rec.Result()).get("text", "")
                if txt:
                    if cap.trace is not None:
                        cap.trace.ev("final", texte=txt)
                    q.put(("final", txt, time.time() - t0))
            else:
                txt = json.loads(self.rec.PartialResult()).get("partial", "")
                if txt:
                    if cap.trace is not None:
                        cap.trace.ev("partial", texte=txt)
                    q.put(("partial", txt, time.time() - t0))
        q.put(("eof", "", time.time() - t0))

    def reset(self):
        """Borne le segment : sans ça le treillis grossit et le transcript renvoyé
        contient tout depuis le début, y compris ce à quoi on a déjà répondu.

        Appelé depuis la boucle d'état, donc d'un AUTRE thread : on lève un
        drapeau au lieu d'appeler `Reset()` ici. Le décodeur n'est pas réentrant
        et le faire à chaud pendant un `AcceptWaveform` corrompt le tas — plantage
        systématique du processus à la première réponse (`malloc(): unaligned
        fastbin chunk`). Même geste que `Whisper.reset()`, pour la même raison."""
        self._raz = True


class Rejeu:
    """Rejoue les transcriptions d'une session tracée, au lieu de les recalculer.

    C'est la condition d'un banc de mesure honnête. Rejouer un WAV refait tourner
    whisper, dont le coût par passe varie d'une exécution à l'autre : les découpes
    de fenêtre changent, donc les deltas, donc les prompts. Comparer deux modèles
    ainsi reviendrait à comparer deux bruits.

    Ici les entrées sont figées : mêmes textes, mêmes instants, à la milliseconde.
    Tout écart observé vient de ce qu'on fait varier, et de rien d'autre.

    `vitesse` accélère le rejeu (2.0 = deux fois plus vite). Attention : le
    décideur, lui, tourne toujours en temps réel — au-delà de 1.0 les latences
    mesurées ne veulent plus rien dire, c'est bon pour dégrossir, pas pour publier.
    """

    charge_s = 0.0
    dernier_cout = 0.0

    def __init__(self, session, vitesse=1.0):
        chemin = os.path.join(session, "session.jsonl")
        if not os.path.exists(chemin) and session.endswith(".jsonl"):
            chemin = session
        self.vitesse = max(0.01, float(vitesse))
        self.evts = []
        with open(chemin) as f:
            for ligne in f:
                try:
                    e = json.loads(ligne)
                except ValueError:
                    continue
                if e.get("type") in ("partial", "final") and e.get("texte"):
                    self.evts.append((float(e["t"]), e["type"], e["texte"]))
        self.evts.sort()
        self.source = chemin
        self.reglages = {"source": chemin, "evenements": len(self.evts),
                         "vitesse": self.vitesse}

    def run(self, cap, q, stop):
        t0 = time.time()
        for t, genre, txt in self.evts:
            if stop.is_set():
                break
            attente = t / self.vitesse - (time.time() - t0)
            if attente > 0:
                time.sleep(attente)
            q.put((genre, txt, time.time() - t0))
        q.put(("eof", "", time.time() - t0))

    def reset(self):
        """Rien à vider : les événements sont figés, on ne les recalcule pas."""


def moteur(nom, **kw):
    if nom == "rejeu":
        return Rejeu(**kw)
    return Whisper(**kw) if nom == "whisper" else Vosk(**kw)


def start(nom, path=None, mic="default", porte=None, trace=None,
          robot_parle=None, **kw):
    """Démarre le producteur dans son thread. Rend (queue, stop, stream, moteur).

    `porte` (audio.Porte) et `trace` (journal.Journal) sont optionnels : à None,
    le capteur se réduit à un `read` sur le tube et ne coûte rien de plus qu'avant.
    `robot_parle` est le callable qui dit à la porte quand le seul son attendu
    est notre propre écho.
    """
    eng = moteur(nom, **kw)
    # Le rejeu ne lit aucun son : ouvrir un flux allumerait le micro pour rien,
    # et appliquerait la porte une seconde fois sur des textes déjà produits.
    stream = None if nom == "rejeu" else audio.open_stream(path, mic)
    cap = audio.Capteur(stream, porte, trace, robot_parle) if stream else None
    q, stop = queue.Queue(), threading.Event()
    th = threading.Thread(target=eng.run, args=(cap, q, stop), daemon=True)
    th.start()
    # Le thread est exposé pour pouvoir être JOINT à la fermeture. Sans ça, la
    # sortie de l'interpréteur libère le modèle whisper.cpp pendant qu'une passe
    # tourne encore dedans : « Segmentation fault (core dumped) » après un
    # Ctrl-C, une fois la trace correctement écrite.
    eng.th = th
    eng.cap = cap        # porte l'horloge audio (échantillons lus), pour --rendu
    return q, stop, stream, eng


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("fichier", nargs="?")
    ap.add_argument("--moteur", default="whisper", choices=["whisper", "vosk"])
    ap.add_argument("--mic", default="default")
    ap.add_argument("--porte", type=float, default=0.0,
                    help="facteur de la porte de volume (0 = désactivée)")
    a = ap.parse_args()

    porte = audio.Porte(a.porte) if a.porte > 0 else None
    q, stop, stream, eng = start(a.moteur, a.fichier, a.mic, porte=porte)
    print(f"[{a.moteur} chargé en {eng.charge_s:.2f} s]", file=sys.stderr)
    premier, n = None, 0
    t0 = time.time()
    try:
        while True:
            kind, txt, t = q.get()
            if kind == "eof":
                break
            n += 1
            if premier is None:
                premier = t
                print(f"{t:6.2f}s  [premier mot]", file=sys.stderr)
            print(f"{t:6.2f}s  {kind:7s} {txt}")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); audio.close_stream(stream)
    print(f"\n--- {n} événements | premier mot à {premier if premier else -1:.2f} s "
          f"| {time.time()-t0:.1f} s de traitement", file=sys.stderr)
