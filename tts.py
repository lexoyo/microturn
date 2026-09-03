#!/usr/bin/env python3
"""Étage TTS de microturn — parole non bloquante et interruptible.

`say()` rend la main immédiatement : la synthèse et la lecture tournent dans des
processus fils. `stop()` les tue net — c'est le geste du barge-in.

Deux moteurs, choisis par MICROTURN_TTS :
  piper   : voix naturelle. **Résident depuis le 03/09** — le modèle n'est plus
            rechargé à chaque phrase, ce qui économisait ~8 s par réponse sur un
            Pi 3B. Il écrit un WAV par phrase, qu'`aplay` joue d'un bloc.
  espeak  : 5 Mo, ~70 ms. Le mode dégradé assumé pour petite machine.

Prix de ce choix, assumé et partagé par wyoming-piper, rhasspy3 et pipecat : le
premier son attend la fin de la synthèse. L'attaque n'est donc plus une
constante, elle croît avec la longueur du texte — voir `duree_parole()` et
`Silencieux.attaque()`.

Aucun shell n'est utilisé : les processus sont chaînés directement, ce qui évite
le quoting, un /bin/sh par phrase, et les surprises de `echo` sous dash (Pi OS).
"""
import atexit, glob, json, os, random, shutil, signal, subprocess, tempfile
import threading, time, wave

ENGINE = os.environ.get("MICROTURN_TTS", "piper")
PIPER = os.path.expanduser(os.environ.get("MICROTURN_PIPER", "~/.local/bin/piper"))
# Le périphérique de SORTIE. `aplay` sans `-D` cherche un « default » qui
# n'existe pas sur une image Raspberry Pi Lite : il échoue, et comme son stderr
# part dans DEVNULL, le robot parle dans le vide sans un message. Trouvé en
# session réelle, invisible en rejeu.
APLAY = os.environ.get("MICROTURN_APLAY", "")
# Taille du tampon de sortie ALSA, en microsecondes. Par défaut `aplay` en prend
# un très large — mesuré ~2 s sur la sortie HDMI du Pi, entre la décision de
# parler et le premier son. C'est de la latence pure, invisible dans nos traces
# puisqu'elle se produit après tout ce qu'on mesure.
# 0 = laisser ALSA choisir (comportement d'avant).
APLAY_BUFFER_US = int(os.environ.get("MICROTURN_APLAY_BUFFER", "0"))
VOICE = os.path.expanduser(os.environ.get(
    "MICROTURN_VOICE", "~/.local/share/piper/fr_FR-siwis-medium.onnx"))


def voix_pour(nom, defaut=VOICE):
    """Chemin du modèle piper pour un nom de voix de catalogue (« en_US-amy-medium »).

    Une voix posée explicitement dans MICROTURN_VOICE l'emporte : c'est un
    réglage de la machine, le catalogue n'est qu'un défaut par langue.
    Si le fichier n'existe pas on garde le défaut — mieux vaut la mauvaise
    langue qu'un système muet sans un mot d'explication."""
    if os.environ.get("MICROTURN_VOICE") or not nom:
        return defaut
    chemin = os.path.join(os.path.dirname(defaut), nom + ".onnx")
    return chemin if os.path.exists(chemin) else defaut


def voice_rate(voice=VOICE, default=22050):
    """Taux d'échantillonnage déclaré par la voix. Les voix `low` sont à 16 kHz :
    le coder en dur ferait parler le robot 35 % trop vite après un changement."""
    try:
        with open(voice + ".json") as f:
            return int(json.load(f)["audio"]["sample_rate"])
    except Exception:
        return default


ICI = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.environ.get("MICROTURN_CLIPS") or os.path.join(ICI, "clips")


class Clips:
    """Les backchannels de l'ASSISTANT : des WAV courts, tirés au hasard.

    Comme les chercheurs (papier § 3.2, et les « Mhmm. » / « Sure. » /
    « Uh-huh. » / « Gotcha. » de leur démo 3) : le clip est **pré-synthétisé**,
    pas produit à la volée. La raison est la seule qui vaille ici — un signal
    d'écoute qui arrive en retard n'est plus un signal d'écoute. Sur un Pi 3B,
    une passe de piper coûte de une à trois secondes ; le tick en dure 1,2.

    Trois propriétés que le reste du système attend de cette classe :

    - **elle ne retarde rien** : `jouer()` lance `aplay` et rend la main. Aucune
      attente, aucune synthèse, aucun verrou partagé avec `Speaker` ;
    - **elle ne coupe pas l'écoute** : elle ne touche ni à `speaking()`, ni à
      `robot_parle`, ni à la porte anti-écho. Le clip dure moins d'une seconde,
      donc l'hôte ne se croit pas en train de « parler » — et un `parle` qui
      tombe pendant ne se transforme pas en interruption ;
    - **elle ne casse rien quand le dossier est vide** : sans clip on ne joue
      rien et on le dit (None), on ne lève pas.

    Les fichiers se régénèrent avec `clips/generer.py` — jamais de binaire
    opaque sans le moyen de le refaire.
    """

    def __init__(self, langue="fr", dossier=None, actif=True):
        self.langue = langue
        self.dossier = os.path.join(dossier or CLIPS, langue)
        self.actif = actif                 # faux en --muet et en --rendu
        self.fichiers = sorted(glob.glob(os.path.join(self.dossier, "*.wav")))
        self._dernier = None
        self._procs = []

    def tirer(self):
        """Un clip au hasard, jamais deux fois le même d'affilée — quatre clips
        dont deux « Mhm. » de suite s'entendent comme un bégaiement."""
        if not self.fichiers:
            return None
        choix = [f for f in self.fichiers if f != self._dernier] or self.fichiers
        self._dernier = random.choice(choix)
        return self._dernier

    def jouer(self):
        """Tire un clip et le lance SANS BLOQUER. Rend le chemin, ou None s'il
        n'y a aucun clip installé.

        `actif=False` (mesure muette, rendu au format du banc) tire quand même :
        la trace dit alors ce qui AURAIT été joué, et deux sessions restent
        comparables."""
        chemin = self.tirer()
        if chemin is None or not self.actif:
            return chemin
        cmd = ["aplay", "-q"]
        if APLAY:
            cmd += ["-D", APLAY]
        try:
            self._procs = [p for p in self._procs if p.poll() is None]
            self._procs.append(subprocess.Popen(
                cmd + [chemin], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True))
        except OSError:
            return None                    # pas d'aplay : le reste continue
        return chemin

    def stop(self):
        """Tue un clip en cours. Utile au barge-in, pas obligatoire : un clip
        dure moins d'une seconde."""
        for p in self._procs:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    pass
        self._procs = []


# --- durée de parole et attaque : des MESURES, pas des estimations ---------
#
# Mesuré le 04/09/2026 sur `shiao` (2 cœurs), piper RÉSIDENT écrivant UN WAV PAR
# PHRASE — l'architecture du 03/09. Dix phrases de 6 à 197 caractères par voix ;
# la durée lue est celle du WAV produit (`wave` : getnframes()/getframerate()),
# c'est-à-dire la durée de PAROLE (le son une fois joué), et non la durée de
# SYNTHÈSE (le temps que piper met à produire le fichier). Ce sont deux
# grandeurs différentes : la parole ne dépend que du texte et de la voix, la
# synthèse dépend de la machine. Ce qu'il faut ici pour savoir jusqu'à quand le
# canal est occupé, c'est la première — plus l'attaque, ci-dessous.
#
#   voix                 parole ≈ a + n/débit      résidu    débit brut
#   fr_FR-siwis-medium   0,53 s + n / 20,9 car/s   rms 0,32 s   18,6 car/s
#   en_US-amy-medium     0,88 s + n / 18,5 car/s   rms 0,22 s   15,6 car/s
#
# L'ancien `DEBIT_CAR_S = 14` unique SURESTIMAIT la parole de ~45 % (100
# caractères : 7,14 s annoncées contre 4,78 s réelles en français). Le « facteur
# 3 » des passations n'est pas là — cf. RTF_SYNTHESE_ITEM plus bas.
#
# Les deux voix s'écartent de ~18 % à 100 caractères (5,3 s contre 6,3 s), soit
# trois fois le résidu : une valeur unique ne peut pas couvrir les deux, d'où la
# table. Les autres voix du dossier (`tom`, `upmc`) n'ont pas été mesurées.
#
# Plancher de précision : piper échantillonne du bruit (noise_scale 0,667,
# noise_w 0,8), la même phrase ne dure pas deux fois pareil — ±0,16 s sur 5
# répétitions, à 17 comme à 76 caractères. Viser mieux que ~0,3 s n'a pas de
# sens ; c'est aussi pourquoi la durée EXACTE, quand elle existe, vaut mieux que
# n'importe quelle régression (cf. `Speaker.audio_s`).
PAROLE_PAR_VOIX = {
    "fr_FR-siwis-medium": (0.53, 20.9),
    "en_US-amy-medium":   (0.88, 18.5),
}
PAROLE_DEFAUT = PAROLE_PAR_VOIX["fr_FR-siwis-medium"]

# ATTAQUE : de `say()` au PREMIER échantillon.
#
# Depuis que le TTS est résident et écrit un WAV par phrase (03/09), le premier
# son n'arrive qu'APRÈS LA FIN DE LA SYNTHÈSE. L'attaque vaut donc
#     synthèse complète + démarrage d'ALSA
# et ce n'est donc PAS une constante : elle croît avec la longueur du texte, et
# le terme de synthèse dépend de la machine.
#
# Deux valeurs qui circulent et qui ne veulent plus rien dire ici :
#   — le « 0,01 s » des vieilles notes est un DÉLAI AVANT LE PREMIER SON de
#     l'architecture par tube, où `aplay` était alimenté au fil de l'eau ;
#   — l'ancien `ATTAQUE_S = 0,95` vient des 0,97 s de `RESULTATS.md` §6, qui
#     mesuraient un piper RELANCÉ à chaque phrase (rechargement du modèle de
#     63 Mo). piper étant résident depuis le 03/09, ce coût a disparu du chemin
#     normal.
#
# Démarrage d'ALSA — mesuré le 04/09 sur `shiao` : 0,25 s. (Surcoût d'`aplay`
# sur des WAV de silence de 0,5 / 1 / 3 s : 0,25 s médian, constant, donc
# indépendant de la durée du fichier.) Cohérent avec les ~0,3 s mesurés sur la
# sortie HDMI du Pi (`ARTICLE-NOTES.md`).
ATTAQUE_ALSA_S = float(os.environ.get("MICROTURN_TTS_ATTAQUE", "0.25"))

# RTF_SYNTHESE_ITEM : rapport parole / synthèse, le SEUL terme dépendant de la
# machine — et c'est là qu'est le facteur 3 des passations.
#   `shiao`, 04/09/2026 : 9,0 (fr) et 9,2 (en) — 5,3 s de synthèse pour 47 s de
#     parole, sur les 10 phrases ci-dessus.
#   Pi 3B : ~3 — `README.md` donne ~2,9 s de synthèse pour une longue phrase
#     (≈ 9,9 s de parole), et `ARTICLE-NOTES.md` chiffre à ~3 le rapport de
#     puissance entre `shiao` et le Pi.
# UNE constante ne peut pas être juste sur les deux machines : le rapport se
# pose sur la cible, `MICROTURN_TTS_RTF=3` sur un Pi 3B.
#
# ⚠️ Le « ×3,0 » de `RESULTATS-PI.md` § 4 a été mesuré via `--rendu`, donc via
# `Enregistreur._pcm`, qui relance piper à chaque phrase (~8 s de chargement sur
# le Pi). Il mesure ce rechargement autant que le débit, et ne s'applique pas au
# chemin livré, où piper est résident. À remesurer sur le Pi avant d'y croire.
RTF_SYNTHESE = float(os.environ.get("MICROTURN_TTS_RTF", "9.0"))


def duree_parole(text, voice=VOICE):
    """Durée du SON UNE FOIS JOUÉ, en secondes. Estimation par caractères.

    C'est un REPLI, pour l'instant où le WAV n'existe pas encore (mode muet, ou
    avant la synthèse). Dès que le fichier est écrit, sa durée est EXACTE et se
    lit dans son en-tête — c'est ce que fait `Speaker.audio_s`, et c'est
    toujours mieux que cette régression."""
    nom = os.path.basename(voice or "")
    if nom.endswith(".onnx"):
        nom = nom[:-len(".onnx")]
    amorce, debit = PAROLE_PAR_VOIX.get(nom, PAROLE_DEFAUT)
    n = len(" ".join((text or "").split()))
    return amorce + n / debit if n else 0.0


class Speaker:
    """Parole non bloquante et interruptible, par FICHIER et non par tube.

    Chaque phrase est synthétisée dans un WAV complet, puis jouée d'un bloc.
    C'est ce que font tous les projets sérieux qui intègrent piper —
    wyoming-piper (Home Assistant), rhasspy3, pipecat, le serveur HTTP de
    piper : **aucun n'utilise `--output-raw`**.

    Pourquoi : `--output-raw` ne rend que des octets concaténés, sans le moindre
    marqueur de fin de phrase. On en était réduit à déduire la fin d'un silence
    de 0,35 s dans le tube — faux dès que piper met plus longtemps entre deux
    blocs, ce qui arrive dès qu'il partage le CPU avec l'ASR. On fermait alors
    `aplay` en pleine phrase, et le reste du son sortait **avec la phrase
    suivante**. Mesuré le 03/09 : « Bonjour. » servait 1,58 s pour 0,38 s
    attendues, et la phrase d'après n'en recevait aucune.

    Avec un fichier, la frontière est explicite : piper écrit le WAV, rend son
    chemin sur stdout, et on le joue. Plus de tube partagé, plus de purge, plus
    de compteur de génération dans le flux audio, plus de sous-alimentation
    d'`aplay` — le fichier est complet avant le premier son.

    Le prix : le premier son attend la fin de la synthèse (~0,2 s ici, ~2,9 s
    sur un Pi 3B pour une longue phrase). C'est l'arbitrage que tous les autres
    ont fait.

    piper reste RÉSIDENT : le relancer coûte ~8 s sur le Pi. Résident et tube
    sont deux choses distinctes, et c'est le tube qui posait problème."""

    def __init__(self, engine=ENGINE, voice=VOICE, langue="fr"):
        self.engine = engine
        self.voice = voice
        self.langue = langue
        self.rate = voice_rate(voice)
        self.lock = threading.RLock()
        self._synth = None                   # piper résident
        self._sortie = None                  # l'`aplay` du moment
        self._gen = 0                        # invalide une phrase en vol
        self._parlant = False                # de `say()` à la fin d'`aplay`
        self._dossier = tempfile.mkdtemp(prefix="microturn-tts-")
        self.audio_s = 0.0                   # durée du WAV de la phrase en cours
        self._ferme = False
        # Chaque WAV est effacé après lecture ; ceci n'est que la ceinture pour
        # un arrêt brutal, où le `finally` de `_parler` ne passe pas.
        atexit.register(shutil.rmtree, self._dossier, True)
        if engine == "piper":
            threading.Thread(target=self._prechauffer, daemon=True).start()

    # -- piper résident, protocole « une ligne in, un chemin out » ----------

    def _prechauffer(self):
        """Charge le modèle sans rien faire entendre.

        La synthèse va dans un fichier qu'on efface : rien ne peut fuir vers le
        haut-parleur, contrairement au tube où la syllabe de chauffe sortait
        devant la première phrase.

        On chauffe sur une PONCTUATION SEULE, pas sur un mot. La chauffe tient
        le verrou de synthèse : une vraie phrase arrivée pendant attend qu'elle
        finisse. Chauffer sur « Bonjour. » ajoutait donc la synthèse d'un mot
        réel devant la première réponse — sur le Pi, les huit secondes de
        chargement PLUS une seconde de parole inutile, soit exactement ce que
        le préchauffage devait éviter."""
        try:
            chemin = self._synthetiser(".")
            if chemin:
                os.unlink(chemin)
        except Exception:
            pass                             # la chauffe ne doit rien casser

    def _piper(self):
        """Le processus résident. `--output_dir` : un WAV par ligne d'entrée."""
        if self._ferme:
            # Sans ce garde, un `say()` après `close()` ressuscite piper sur un
            # `--output_dir` qui n'existe plus, et personne ne le tuera jamais.
            return None
        if self._synth is not None and self._synth.poll() is None:
            return self._synth
        self._synth = subprocess.Popen(
            [PIPER, "-m", self.voice, "--output_dir", self._dossier, "-q"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True)
        return self._synth

    def _synthetiser(self, text):
        """Une phrase → un fichier WAV complet. Rend son chemin, ou None.

        Bloquant : appelé depuis le thread de `_parler`, jamais depuis `say()`.
        Sérialisé par `_verrou_synth` — piper est un seul processus, et deux
        écritures concurrentes mélangeraient les réponses de son stdout."""
        # UNE ligne = UN wav = UNE ligne sur stdout. Un saut de ligne dans le
        # texte produit donc deux fichiers pour un `say()`, et toutes les
        # phrases suivantes lisent le chemin de la précédente : le décalage est
        # DÉFINITIF pour la session. `strip()` n'ôte que les bords ; une réponse
        # JSON du modèle peut très bien contenir un `\n` au milieu.
        text = " ".join(text.split())
        with self._verrou_synth:
            try:
                p = self._piper()
                if p is None:
                    return None              # fermé
                p.stdin.write((text + "\n").encode())
                p.stdin.flush()
                ligne = p.stdout.readline().decode().strip()
            except (BrokenPipeError, ValueError, OSError):
                return None
        return ligne if ligne and os.path.exists(ligne) else None

    _verrou_synth = threading.Lock()

    # -- parler ------------------------------------------------------------

    def say(self, text):
        """Parle sans bloquer. Coupe ce qui était en cours. Atomique."""
        text = text.strip()
        if not text:
            return
        with self.lock:
            self._stop_locked()
            self.audio_s = 0.0               # compteur de CETTE prise de parole
            self._gen += 1
            gen = self._gen
            # `speaking()` doit être vrai DÈS MAINTENANT, pas au premier son :
            # sinon le décideur croit qu'on s'est tu pendant qu'on synthétise,
            # et le barge-in comme l'écho reposent sur cet état.
            self._parlant = True
        threading.Thread(target=self._parler, args=(text, gen),
                         daemon=True).start()

    def _parler(self, text, gen):
        chemin = None
        try:
            if self.engine == "espeak":
                self._jouer_espeak(text, gen)
                return
            chemin = self._synthetiser(text)
            # Ce qui a RÉELLEMENT été produit, en regard du texte demandé. Un
            # écart net signale une phrase tronquée ou un reste de la
            # précédente — invisible autrement qu'à l'oreille. Le WAV est
            # complet ici, donc la mesure est exacte : c'est mieux que le
            # comptage d'octets qu'elle remplace, qui n'a jamais survécu à la
            # réécriture du 03/09 et écrivait `None` dans chaque trace.
            if chemin:
                try:
                    with wave.open(chemin) as w:
                        self.audio_s = round(w.getnframes() / w.getframerate(), 2)
                except Exception:
                    self.audio_s = 0.0
            with self.lock:
                if self._gen != gen:
                    return                   # coupé pendant la synthèse
                if chemin is None:
                    self._parlant = False
                    return
                cmd = ["aplay", "-q"]
                if APLAY:
                    cmd += ["-D", APLAY]
                if APLAY_BUFFER_US:
                    cmd += ["--buffer-time", str(APLAY_BUFFER_US),
                            "--period-time", str(max(1000, APLAY_BUFFER_US // 4))]
                play = subprocess.Popen(cmd + [chemin], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                self._sortie = play
            play.wait()
        except Exception:
            pass
        finally:
            with self.lock:
                if self._gen == gen:         # personne n'a parlé depuis
                    self._parlant = False
                    self._sortie = None
            if chemin:
                try:
                    os.unlink(chemin)
                except OSError:
                    pass

    def _jouer_espeak(self, text, gen):
        """Mode dégradé : espeak parle tout seul, rien à cadrer."""
        p = subprocess.Popen(["espeak-ng", "-v", self.langue, "-s", "165", text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        with self.lock:
            if self._gen != gen:
                p.kill()
                return
            self._sortie = p
        p.wait()

    # -- couper ------------------------------------------------------------

    def _stop_locked(self):
        """Invalide la phrase en vol et tue le lecteur. Verrou déjà tenu.

        Rien à purger : le WAV appartient à cette phrase et à elle seule. Le
        compteur de génération suffit — s'il a bougé, le thread qui synthétise
        encore jettera son fichier au lieu de le jouer."""
        self._gen += 1
        self._parlant = False
        p, self._sortie = self._sortie, None
        if p is not None and p.poll() is None:
            try:
                # start_new_session garantit pgid == pid : pas de getpgid(),
                # qui échouerait si le processus vient de mourir.
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    p.kill()
                except OSError:
                    pass

    def stop(self):
        with self.lock:
            self._stop_locked()

    def speaking(self):
        with self.lock:
            return self._parlant

    def pret(self):
        """piper a-t-il fini de charger ? L'hôte peut attendre avant le premier
        tick plutôt que de payer le chargement sur la première réponse."""
        with self.lock:
            return self._synth is not None and self._synth.poll() is None

    def wait(self, timeout=30.0):
        t0 = time.time()
        while self.speaking() and time.time() - t0 < timeout:
            time.sleep(0.02)

    def close(self):
        self.stop()
        self._ferme = True
        with self.lock:
            if self._synth is not None and self._synth.poll() is None:
                try:
                    os.killpg(self._synth.pid, signal.SIGKILL)
                except OSError:
                    pass
        shutil.rmtree(self._dossier, ignore_errors=True)


class Enregistreur:
    """Locuteur qui écrit dans un tampon au lieu de jouer, pour un banc d'essai.

    Full-Duplex-Bench attend, pour chaque `input.wav`, un `output.wav` de MÊME
    DURÉE : silence là où le système se tait, sa réponse exactement là où il l'a
    prononcée. Ni `--muet` (qui ne produit rien) ni `--moteur rejeu` (qui ne lit
    aucun son) ne peuvent le faire — d'où ce troisième mode.

    Deux choix qui décident de l'honnêteté du résultat :

    - Les positions sont comptées en ÉCHANTILLONS D'ENTRÉE, pas en secondes
      d'horloge murale. Sinon la latence réseau du moment déplace les réponses
      et deux passes sur le même corpus ne se comparent plus.
    - Le segment commence quand piper a fini de produire son PCM, pas quand
      `say()` rend la main. piper ne diffuse pas au fil de l'eau : entre les
      deux il y a près d'une seconde ici, et cinq à huit sur un Pi. Placer le
      son au retour de `say()` avancerait toutes les réponses d'autant, et
      donnerait une latence flatteuse et fausse.
    """

    def __init__(self, horloge, voice=VOICE, langue="fr", rate_sortie=16000,
                 engine=ENGINE):
        self.horloge = horloge          # -> position courante, en échantillons
        self.engine = engine
        self.voice = voice
        self.langue = langue
        self.rate = voice_rate(voice)
        self.rate_sortie = rate_sortie
        self.segments = []              # (debut_echantillon, pcm int16)
        self.lock = threading.RLock()
        self._en_synthese = False
        self._courant = None            # index du segment en train d'être « dit »

    # -- synthèse hors ligne, rendue à la cadence de l'entrée --
    def _pcm(self, text):
        if self.engine == "espeak":
            p = subprocess.run(["espeak-ng", "-v", self.langue, "-s", "165",
                                "--stdout", text],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            brut = p.stdout
            return brut[44:] if brut[:4] == b"RIFF" else brut   # saute l'en-tête
        p = subprocess.run([PIPER, "-m", self.voice, "--output-raw"],
                           input=(text + "\n").encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return p.stdout

    def _reechantillonne(self, pcm):
        """Du taux de la voix vers celui de l'entrée, en linéaire.

        Les voix piper sont à 22 050 Hz (16 000 pour les `low`), l'entrée à
        16 000 : coller le PCM tel quel décalerait toute la suite du fichier.
        """
        import numpy as np
        a = np.frombuffer(pcm, dtype=np.int16)
        if self.rate == self.rate_sortie or len(a) == 0:
            return a
        n = int(len(a) * self.rate_sortie / self.rate)
        pos = np.linspace(0, len(a) - 1, n)
        return np.interp(pos, np.arange(len(a)), a).astype(np.int16)

    def say(self, text):
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self._tronquer_locked()      # une nouvelle phrase coupe la précédente
            self._en_synthese = True
        threading.Thread(target=self._synthese, args=(text,), daemon=True).start()

    def _synthese(self, text):
        try:
            son = self._reechantillonne(self._pcm(text))
        except Exception:
            son = None
        with self.lock:
            self._en_synthese = False
            if son is None or len(son) == 0:
                return
            # le son commence MAINTENANT : la synthèse vient de se terminer
            self.segments.append([self.horloge(), son])
            self._courant = len(self.segments) - 1

    def _tronquer_locked(self):
        """Coupe le segment en cours à la position courante — c'est le barge-in.

        Sans ça, `output.wav` contiendrait une réponse que le système n'a
        jamais fini de dire, et le banc mesurerait une parole qui n'a pas eu
        lieu."""
        if self._courant is None:
            return
        debut, son = self.segments[self._courant]
        garde = max(0, self.horloge() - debut)
        if garde < len(son):
            self.segments[self._courant][1] = son[:garde]
        self._courant = None

    def stop(self):
        with self.lock:
            self._en_synthese = False
            self._tronquer_locked()

    def speaking(self):
        with self.lock:
            if self._en_synthese:
                return True              # piper travaille : on « parle » déjà
            if self._courant is None:
                return False
            debut, son = self.segments[self._courant]
            if self.horloge() < debut + len(son):
                return True
            self._courant = None
            return False

    def wait(self):
        while self.speaking():
            time.sleep(0.02)

    def rendre(self, chemin, total):
        """Écrit un WAV de `total` échantillons, aux positions mesurées."""
        import numpy as np
        piste = np.zeros(total, dtype=np.int32)
        for debut, son in self.segments:
            if len(son) == 0 or debut >= total:
                continue
            fin = min(total, debut + len(son))
            piste[debut:fin] += son[:fin - debut]
        piste = np.clip(piste, -32768, 32767).astype(np.int16)
        with wave.open(chemin, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate_sortie)
            w.writeframes(piste.tobytes())
        return len([s for _, s in self.segments if len(s)])


class Silencieux:
    """Locuteur qui ne produit aucun son mais dure le temps qu'il faut.

    Neutraliser `say` en `lambda t: None` — ce que faisait `--muet` — rendait
    `speaking()` toujours faux. Conséquence : l'état « je parle » n'était jamais
    transmis au modèle, la coupure devenait structurellement impossible, et la
    fenêtre « je viens de répondre » démarrait trop tôt. Une session en `--muet`
    n'exerçait donc pas le même système que celle qu'on livre, alors que le
    protocole s'en sert pour comparer deux versions du code.

    Ici la parole a une durée simulée : attaque du moteur, puis débit de lecture.
    Les deux termes sont des mesures — celles de l'en-tête de ce fichier, datées
    et attribuées à une machine et à une voix — pas des estimations de confort ;
    elles sont tracées dans meta.json pour rester discutables.

    C'est la SEULE classe qui estime. `Speaker` n'estime rien : `speaking()` y
    suit la vie d'`aplay`, et `audio_s` est lu dans l'en-tête du WAV. Le mode
    muet, lui, ne synthétise jamais — c'est sa raison d'être (sur un Pi, une
    synthèse coûte des secondes) — donc aucune durée exacte n'y est disponible.
    """
    # Part FIXE de l'attaque, le démarrage d'ALSA. La part variable, la synthèse,
    # dépend du texte : elle est dans `attaque(texte)`.
    # ⚠️ `pipeline.py` trace aujourd'hui cet attribut sous le nom `attaque` ; il
    # ne couvre donc plus que le démarrage d'ALSA. C'est `attaque(texte)` qu'il
    # faudrait y appeler.
    ATTAQUE_S = ATTAQUE_ALSA_S
    RTF_SYNTHESE = RTF_SYNTHESE

    def __init__(self, engine="muet", voice=VOICE, langue="fr"):
        # Même surface que Speaker : `meta.json` lit `engine` et `voice`, et une
        # trace qui ne dit pas qu'elle est muette n'est pas comparable.
        self.engine = engine
        self.voice = voice
        self.langue = langue
        self.rate = voice_rate(voice)
        self.fin = 0.0
        self.lock = threading.RLock()

    def attaque(self, text, parole=None):
        """De `say()` au premier échantillon : synthèse complète, puis ALSA."""
        if parole is None:
            parole = duree_parole(text, self.voice)
        return self.ATTAQUE_S + parole / self.RTF_SYNTHESE

    def duree(self, text):
        """Jusqu'à quand le canal est occupé : attaque, puis parole."""
        parole = duree_parole(text, self.voice)
        if not parole:
            return 0.0
        return self.attaque(text, parole) + parole

    def say(self, text):
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self.fin = time.monotonic() + self.duree(text)

    def stop(self):
        with self.lock:
            self.fin = 0.0

    def speaking(self):
        with self.lock:
            return time.monotonic() < self.fin

    def wait(self):
        while self.speaking():
            time.sleep(0.02)


if __name__ == "__main__":
    import sys
    txt = " ".join(sys.argv[1:]) or "Bonjour Alex, je suis microturn, et je parle en local."
    for eng in ("espeak", "piper"):
        if eng == "piper" and not os.path.exists(PIPER):
            print(f"{eng:7s} absent"); continue
        s = Speaker(eng); t0 = time.time(); s.say(txt); lance = time.time() - t0
        s.wait()
        print(f"{eng:7s} lancement {lance*1000:5.0f} ms | fin {time.time()-t0:.2f} s "
              f"| {s.rate} Hz")
