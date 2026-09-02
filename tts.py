#!/usr/bin/env python3
"""Étage TTS de microturn — parole non bloquante et interruptible.

`say()` rend la main immédiatement : la synthèse et la lecture tournent dans des
processus fils. `stop()` les tue net — c'est le geste du barge-in.

Deux moteurs, choisis par MICROTURN_TTS :
  piper   : voix naturelle. Le modèle est rechargé à chaque phrase, donc coûteux
            (~0,7 s ici, plusieurs secondes sur un Pi) : ne pas découper en phrases.
  espeak  : 5 Mo, ~70 ms. Le mode dégradé assumé pour petite machine.

Aucun shell n'est utilisé : les processus sont chaînés directement, ce qui évite
le quoting, un /bin/sh par phrase, et les surprises de `echo` sous dash (Pi OS).
"""
import json, os, subprocess, threading, time, wave

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


class Speaker:
    def __init__(self, engine=ENGINE, voice=VOICE, langue="fr"):
        self.engine = engine
        self.voice = voice
        self.langue = langue                 # code espeak-ng, pas le nom du fichier
        self.rate = voice_rate(voice)
        self.procs = []                      # tous les fils vivants, pas seulement le dernier
        self.lock = threading.RLock()
        self._synth = None                   # piper, résident
        self._sortie = None                  # l'`aplay` du moment
        self._gen = 0                        # phrase courante
        self._purger = False                 # jeter le PCM d'une phrase coupée
        # Le chargement du modèle coûte 8 s sur un Pi. Sans préchauffage il
        # tombe sur la PREMIÈRE réponse de la conversation, celle qui donne le
        # ton. On le paie au démarrage, pendant qu'il ne se passe rien.
        if self.engine != "espeak":
            threading.Thread(target=self._prechauffer, daemon=True).start()

    # -- piper RÉSIDENT --------------------------------------------------
    # Mesuré sur le Pi 3B : relancer piper à chaque phrase coûte 8 s, dont la
    # quasi-totalité en chargement du modèle. Gardé en vie, il rend le premier
    # échantillon en moins de 10 ms. C'est huit secondes de latence par réponse,
    # soit plus que tout le reste de la chaîne réuni.
    #
    # Le prix à payer : on ne peut plus tuer piper pour couper la parole, car il
    # sert aussi la phrase suivante. On tue donc `aplay` seul, et un compteur de
    # génération fait jeter au lecteur le PCM devenu sans objet.

    def _prechauffer(self):
        """Démarre piper et lui fait produire du son qu'on jette."""
        try:
            synth = self._piper()
            synth.stdin.write(b"a\n")       # une syllabe, juste pour charger
            synth.stdin.flush()
        except Exception:
            pass                             # le préchauffage ne doit rien casser

    def _piper(self):
        """Le processus résident, démarré à la première phrase."""
        if self._synth is not None and self._synth.poll() is None:
            return self._synth
        self._synth = subprocess.Popen(
            [PIPER, "-m", self.voice, "--output-raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True)
        th = threading.Thread(target=self._lire, args=(self._synth,), daemon=True)
        th.start()
        return self._synth

    # Sans PCM pendant ce délai, piper a fini sa phrase et on ferme `aplay`.
    #
    # Le réglage a deux bords, et les deux s'entendent :
    #   trop court, il se déclenche ENTRE deux morceaux d'une même phrase et la
    #     coupe en tranches (« bonjour ceci … est un test ») ;
    #   trop long, le robot reste « en train de parler » après avoir fini, donc
    #     il ne se laisse pas interrompre et son état ment au décideur.
    # 0,35 s tient sur ce PC ; le Pi synthétise plus lentement et pourra
    # demander davantage. `MICROTURN_FIN_PHRASE` pour l'ajuster sans recompiler.
    FIN_PHRASE_S = float(os.environ.get("MICROTURN_FIN_PHRASE", "0.35"))

    def _lire(self, synth):
        """Draine piper en continu et route le PCM vers l'`aplay` du moment.

        piper ne marque pas la fin d'une phrase : on la déduit d'un silence de
        lecture, et on FERME alors l'entrée d'`aplay`.

        Cette fermeture n'est pas un détail. `aplay` ne se termine que quand son
        entrée se ferme ; tant qu'il tourne, `speaking()` répond vrai. Sans elle,
        le système se croit en train de parler pour le reste de la session :
        mesuré en session réelle, neuf « coupures » sur treize prises de parole,
        dont huit tombaient APRÈS la fin de la phrase — une phrase de 3,4 s
        « coupée » 18,5 s après son début. Et l'état « je parle » envoyé au
        décideur était faux tout du long."""
        import select
        ecrit = False                        # du PCM a-t-il été servi ?
        while synth.poll() is None:
            pret = select.select([synth.stdout], [], [], self.FIN_PHRASE_S)[0]
            if not pret:
                # Ne fermer QUE si cette phrase a déjà produit du son. piper met
                # de 0,8 à 2,9 s avant son premier échantillon : fermer avant
                # rendrait `speaking()` faux pendant qu'on parle — l'exact
                # symétrique du défaut qu'on corrige.
                with self.lock:
                    self._purger = False     # le silence clôt la purge
                if ecrit:
                    with self.lock:
                        if self._sortie is not None:
                            try:
                                self._sortie.stdin.close()   # `aplay` peut finir
                            except (BrokenPipeError, ValueError, OSError):
                                pass
                            self._sortie = None
                    ecrit = False
                continue
            try:
                bloc = synth.stdout.read(4096)
            except (BrokenPipeError, ValueError, OSError):
                break                        # processus fermé sous nos pieds
            if not bloc:
                break
            with self.lock:
                sortie, purger = self._sortie, self._purger
            if purger:
                # Une phrase a été coupée : piper garde son PCM en tube et le
                # servirait à la phrase SUIVANTE. On le jette jusqu'au silence
                # qui marque sa fin. Sans ça, on entend la fin de la phrase
                # interrompue, puis la nouvelle ne sort jamais — c'est le
                # « ça coupe au milieu » entendu en session.
                continue
            if sortie is None:
                continue                     # rien à servir
            try:
                sortie.stdin.write(bloc)
                sortie.stdin.flush()
                ecrit = True
            except (BrokenPipeError, ValueError, OSError):
                pass                         # `aplay` tué par stop()

    # -- interne : lance la chaîne de processus, verrou déjà tenu --
    def _spawn(self, text):
        if self.engine == "espeak":
            p = subprocess.Popen(["espeak-ng", "-v", self.langue, "-s", "165", text],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            return [p]
        synth = self._piper()
        cmd = ["aplay", "-q", "-r", str(self.rate), "-f", "S16_LE", "-c", "1"]
        if APLAY:
            cmd += ["-D", APLAY]
        if APLAY_BUFFER_US:
            cmd += ["--buffer-time", str(APLAY_BUFFER_US),
                    "--period-time", str(max(1000, APLAY_BUFFER_US // 4))]
        play = subprocess.Popen(cmd + ["-"],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        self._sortie = play
        self._gen += 1
        threading.Thread(target=self._feed, args=(synth, text), daemon=True).start()
        return [play]                        # piper N'EST PAS dans la liste : on ne
                                             # le tue jamais, c'est tout l'intérêt

    # Premier morceau court, suivants plus longs. Mesuré sur le Pi : piper ne
    # diffuse RIEN au fil de la synthèse — il fabrique la phrase entière puis la
    # Le découpage en morceaux a été RETIRÉ le 03/09. Il divisait la latence
    # avant le premier son par 2,5 (2890 → 1135 ms), mais il a produit les trois
    # bugs les plus coûteux du projet : la phrase sortie en tranches (« bonjour
    # ceci … est un test un peu plus long »), le silence de fin de phrase qui se
    # déclenchait entre deux morceaux, et la comptabilité des morceaux restants
    # à tenir sous interruption. On envoie désormais la phrase d'un bloc.
    def _feed(self, proc, text):
        """Envoie la phrase à piper, d'un seul bloc.

        `flush()` et NON `close()` : le processus est résident et resservira."""
        with self.lock:
            gen = self._gen
        try:
            with self.lock:
                if self._gen != gen:
                    return               # déjà coupé : ne rien envoyer
            proc.stdin.write((text.strip() + "\n").encode())
            proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass                         # coupé par stop() entre-temps

    def say(self, text):
        """Parle sans bloquer. Coupe ce qui était en cours. Atomique."""
        text = text.strip()
        if not text:
            return
        with self.lock:                      # kill + spawn dans UNE section critique,
            self._stop_locked()              # sinon deux appels concurrents laissent
            self.procs = self._spawn(text)   # des processus orphelins increvables

    def _stop_locked(self):
        self._gen += 1
        self._sortie = None
        # piper continue de produire la phrase coupée : tout ce qui sort du tube
        # jusqu'au prochain silence appartient au passé et doit être jeté.
        if self.procs:
            self._purger = True
        for p in self.procs:
            if p.poll() is None:
                try:
                    # start_new_session garantit pgid == pid : pas de getpgid(),
                    # qui renverrait le groupe d'un autre si le PID a été recyclé.
                    os.killpg(p.pid, 9)
                except (ProcessLookupError, PermissionError):
                    pass
            try:
                p.wait(timeout=0.5)          # reaping déterministe, et aplay rend ALSA
            except subprocess.TimeoutExpired:
                pass
        self.procs = []

    def stop(self):
        with self.lock:
            self._stop_locked()

    def speaking(self):
        with self.lock:
            return any(p.poll() is None for p in self.procs)

    def wait(self):
        """Attend la fin de la parole. Ne tient pas le verrou pendant l'attente,
        sinon stop() — donc le barge-in — serait bloqué tout du long."""
        with self.lock:
            procs = list(self.procs)
        for p in procs:
            try:
                p.wait()
            except Exception:
                pass


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
    Les deux valeurs sont des mesures (cf. RESULTATS.md), pas des estimations de
    confort — elles sont tracées dans meta.json pour rester discutables.
    """
    ATTAQUE_S = 0.95        # piper : du retour de say() au premier échantillon
    DEBIT_CAR_S = 14.0      # voix fr_FR-siwis-medium, lecture normale

    def __init__(self, engine="muet", voice=VOICE, langue="fr"):
        # Même surface que Speaker : `meta.json` lit `engine` et `voice`, et une
        # trace qui ne dit pas qu'elle est muette n'est pas comparable.
        self.engine = engine
        self.voice = voice
        self.langue = langue
        self.rate = voice_rate(voice)
        self.fin = 0.0
        self.lock = threading.RLock()

    def duree(self, text):
        return self.ATTAQUE_S + len(text.strip()) / self.DEBIT_CAR_S

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
