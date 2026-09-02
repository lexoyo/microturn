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
PLAFOND_S = 10.0                # au-delà, on coupe le tour de force. 10 s et non
                                # 20 : `audio_ctx` suit, et le coût par passe
                                # tombe de 1,35 s à 0,81 s (4,3 s sur le Pi
                                # contre 7 à 12,3). Ne sert plus qu'au repli
                                # whisper : le défaut est sherpa.
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
# `[ée]` et non `é` : un moteur qui rend le texte sans accents (sherpa écrit
# « REALISES ») échappait au filtre, qui ne cherchait que la forme accentuée.
_GENERIQUE = re.compile(r"sous[- ]titr\w*\s+(r[ée]alis|par|fait)", re.I)
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

    @staticmethod
    def _suffixe(path):
        """Déduit le nom commun des trois fichiers du modèle.

        On cherche l'encodeur — il n'y en a qu'un — et on retire son préfixe.
        Les variantes int8 sont préférées : c'est ce que le projet mesure, et
        c'est trois fois plus léger sur le Pi."""
        import glob
        cands = sorted(glob.glob(os.path.join(path, "encoder-*.int8.onnx"))
                       or glob.glob(os.path.join(path, "encoder-*.onnx")))
        if not cands:
            raise SystemExit(f"aucun encodeur sherpa dans {path}")
        return os.path.basename(cands[0])[len("encoder-"):]

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



# Un modèle par langue. `MICROTURN_SHERPA` l'emporte : c'est un réglage de la
# machine, la table n'est qu'un défaut. Les noms de fichiers diffèrent d'un
# modèle à l'autre, ils sont déduits du dossier (cf. `Sherpa._suffixe`).
SHERPA_MODELES = {
    "fr": "models/sherpa-onnx-streaming-zipformer-fr-2023-04-14",
    "en": "models/sherpa-onnx-streaming-zipformer-en-2023-06-26",
}
SHERPA_DIR = os.environ.get("MICROTURN_SHERPA", "")


class Sherpa:
    """Transducteur zipformer streaming — l'inverse de la fenêtre glissante.

    Whisper est un encodeur-décodeur NON CAUSAL : pour obtenir le texte à
    l'instant T il faut lui redonner tout l'audio du tour, et le coût monte avec
    la durée. Mesuré sur le Pi 3B : 4,3 s par passe, et jusqu'à 12,3 s sur un
    tour long, pour un budget de 1,2 s. Un transducteur garde son état — il
    consomme l'audio par blocs et ne re-décode jamais rien. Mesuré sur la même
    machine : 244 ms par bloc de 300 ms, à DEUX threads (le Pi throttle à 83 °C
    dès trois, et perd en fréquence plus qu'il ne gagne en parallélisme).

    Ce qu'on perd : la ponctuation et la casse. Whisper rend « Ça va ? », sherpa
    rend « ÇA VA ». Le point d'interrogation est justement ce qui aide le modèle
    à trancher une fin de tour — d'où `systeme_sherpa` dans le catalogue, qui le
    prévient. Mesuré : +0,063 de justesse avec cette phrase, et −0,103 si on la
    donne à tort à whisper.
    """

    dernier_cout = 0.0

    def __init__(self, path=None, langue="fr", threads=2):
        import sherpa_onnx
        t0 = time.time()
        path = path or SHERPA_DIR or SHERPA_MODELES.get(langue) or SHERPA_MODELES["fr"]
        if not os.path.isdir(path):
            raise SystemExit(
                f"pas de modele sherpa pour « {langue} » dans {path}.\n"
                f"  Modeles connus : {', '.join(SHERPA_MODELES)}\n"
                f"  Ou pose MICROTURN_SHERPA sur un dossier de modele.")
        # Le nom des fichiers change d'un modèle à l'autre : le français de
        # 2023-04-14 est en `epoch-29-avg-9-with-averaged-model`, l'anglais de
        # 2023-06-26 en `epoch-99-avg-1-chunk-16-left-128`. Le coder en dur
        # n'autorisait qu'UN modèle au monde. On le déduit du dossier.
        suffixe = self._suffixe(path)
        self.reglages = {"modele": path, "threads": threads, "int8": True,
                         "bloc_ms": 300, "endpoint": True}
        self.rec = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=os.path.join(path, "tokens.txt"),
            encoder=os.path.join(path, f"encoder-{suffixe}"),
            decoder=os.path.join(path, f"decoder-{suffixe}"),
            joiner=os.path.join(path, f"joiner-{suffixe}"),
            num_threads=threads, sample_rate=audio.RATE, feature_dim=80,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=1.2,
            # La règle 3 force un endpoint après N secondes d'énoncé continu,
            # SANS ÉGARD AU CONTENU — donc tôt ou tard au milieu d'un mot. Et
            # ce qui est figé échappe définitivement à la révision de sherpa :
            # « SUMMARISE » coupé pendant qu'il s'écrivait a donné « SUM » dans
            # le figé, puis « ARISE » au segment suivant, et le transcript
            # portait « PLEASE SUM ARISE OUR DIALOGUE ». Vu en session le
            # 03/09, et reproduit hors de notre code : sherpa seul, en flux par
            # blocs de 300 ms, révise correctement SUM → SUMMARI → SUMMARISE.
            #
            # Cette règle ne nous sert à rien : notre tour se ferme quand on
            # prend la parole, pas sur une durée. À 60 s elle ne garantit plus
            # qu'une chose — qu'un tour d'une minute finisse par se fermer.
            rule3_min_utterance_length=float(
                os.environ.get("MICROTURN_SHERPA_TOUR_MAX", "60")))
        self.flux = self.rec.create_stream()
        self.fige = ""
        self.recolles = 0                # coupures recollées sans espace
        self.charge_s = time.time() - t0

    @staticmethod
    def _suffixe(path):
        """Déduit le nom commun des trois fichiers du modèle.

        On cherche l'encodeur — il n'y en a qu'un — et on retire son préfixe.
        Les variantes int8 sont préférées : c'est ce que le projet mesure, et
        c'est trois fois plus léger sur le Pi."""
        import glob
        cands = sorted(glob.glob(os.path.join(path, "encoder-*.int8.onnx"))
                       or glob.glob(os.path.join(path, "encoder-*.onnx")))
        if not cands:
            raise SystemExit(f"aucun encodeur sherpa dans {path}")
        return os.path.basename(cands[0])[len("encoder-"):]

    _raz = False

    def run(self, cap, q, stop):
        """Deux threads, pour la même raison que `Whisper` — et je l'avais oublié.

        Un seul thread qui lit PUIS décode cesse de vider le tube pendant tout le
        décodage. Sur ce PC il dure 49 ms et rien ne se voit ; sur le Pi il en
        dure 267, soit deux blocs de 125 ms accumulés à chaque tour. Mesuré en
        session réelle : **38 % de l'audio perdu** (33,1 s enregistrées pour 53 s
        de conversation), des trous de plusieurs secondes dans la transcription,
        et un système qui semble ramer alors qu'il n'entend qu'une phrase sur
        deux.
        """
        t0 = time.time()
        # 16 blocs de 125 ms = 2 s de tampon, pas plus. Une file profonde ne perd
        # rien mais accumule du retard qui ne se résorbe jamais : mesuré en
        # session réelle, le délai entre la parole et son affichage grandissait
        # tout au long de la conversation. En temps réel, du son vieux de huit
        # secondes ne vaut rien — mieux vaut le sacrifier que le servir en retard.
        tampon = queue.Queue(maxsize=16)
        self.sacrifies = 0

        def lecteur():
            """Ne fait QUE vider le tube. Jamais de calcul ici."""
            while not stop.is_set():
                data = cap.lire()
                if data is None:
                    break
                if not data:
                    continue           # jeté par la porte
                try:
                    tampon.put_nowait(data)
                except queue.Full:
                    # Le décodeur est distancé : on jette le PLUS ANCIEN et on
                    # garde le neuf. L'inverse conservait du vieil audio et
                    # jetait ce que l'utilisateur venait de dire.
                    try:
                        tampon.get_nowait()
                        tampon.put_nowait(data)
                        self.sacrifies += 1
                    except (queue.Empty, queue.Full):
                        pass
            tampon.put(None)

        th = threading.Thread(target=lecteur, daemon=True)
        th.start()

        vu = ""
        dit_encore = False               # le segment s'allongeait-il encore ?
        _seg_vu = ""
        while not stop.is_set():
            if self._raz:
                # Fin de tour : on repart à vide, sinon le transcript
                # recontiendrait ce à quoi on vient de répondre.
                self.rec.reset(self.flux)
                self.fige, vu, self._raz = "", "", False
            try:
                data = tampon.get(timeout=0.5)
            except queue.Empty:
                continue
            if data is None:
                break
            t1 = time.time()
            self.flux.accept_waveform(
                audio.RATE,
                np.frombuffer(data, np.int16).astype(np.float32) / 32768)
            while self.rec.is_ready(self.flux):
                self.rec.decode_stream(self.flux)
            self.dernier_cout = time.time() - t1
            # La détection de fin d'énoncé fige le texte et relance le décodeur :
            # sans elle le transducteur accumule tout depuis le début, et le
            # delta envoyé au modèle n'a plus de sens.
            if self.rec.is_endpoint(self.flux):
                bout = self.rec.get_result(self.flux)
                if bout:
                    # Toutes les coupures ne se valent pas. Les règles 1 et 2
                    # de sherpa se déclenchent sur un SILENCE : le mot est fini,
                    # un espace le sépare légitimement du suivant. La règle 3 se
                    # déclenche sur une DURÉE, sans égard au contenu — donc tôt
                    # ou tard en plein milieu d'un mot. Et ce qui est figé
                    # échappe définitivement à la révision de sherpa.
                    #
                    # Mesuré le 03/09 : « SUMMARISE » coupé pendant qu'il
                    # s'écrivait a laissé « SUM » dans le figé puis « ARISE »
                    # au segment suivant, et le transcript portait « PLEASE SUM
                    # ARISE OUR DIALOGUE ». Reproduit hors de notre code :
                    # sherpa seul, en flux, révise correctement SUM → SUMMARI →
                    # SUMMARISE. C'est bien la coupure qui gèle une hypothèse
                    # transitoire.
                    #
                    # On ne peut pas demander à sherpa quelle règle a tranché.
                    # Mais la règle 3 est la seule qui puisse couper SANS
                    # silence, donc la seule qui coupe alors que le décodeur
                    # produisait encore des jetons : c'est exactement ce que
                    # `dit_encore` observe.
                    self.fige = ((self.fige + bout) if dit_encore
                                 else (self.fige + " " + bout)).strip()
                    if dit_encore:
                        self.recolles += 1
                self.rec.reset(self.flux)
                vu = ""
                dit_encore = False
                continue
            # Le décodeur a-t-il allongé le segment courant à ce tour ? Si oui
            # et qu'un endpoint tombe au prochain, il tombe en pleine parole.
            _seg = self.rec.get_result(self.flux)
            dit_encore = bool(_seg) and _seg != _seg_vu
            _seg_vu = _seg
            txt = (self.fige + " " + self.rec.get_result(self.flux)).strip()
            if txt and txt != vu:
                vu = txt
                if cap.trace is not None:
                    cap.trace.ev("partial", texte=txt,
                                 cout=round(self.dernier_cout, 3),
                                 attente=tampon.qsize(),
                                 sacrifies=self.sacrifies)
                q.put(("partial", txt, time.time() - t0))
        th.join(timeout=1)
        q.put(("eof", "", time.time() - t0))

    def reset(self):
        self._raz = True


def moteur(nom, **kw):
    if nom == "rejeu":
        return Rejeu(**kw)
    if nom == "sherpa":
        return Sherpa(**kw)
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
