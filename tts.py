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
import json, os, subprocess, threading

ENGINE = os.environ.get("MICROTURN_TTS", "piper")
PIPER = os.path.expanduser(os.environ.get("MICROTURN_PIPER", "~/.local/bin/piper"))
VOICE = os.path.expanduser(os.environ.get(
    "MICROTURN_VOICE", "~/.local/share/piper/fr_FR-siwis-medium.onnx"))


def voice_rate(voice=VOICE, default=22050):
    """Taux d'échantillonnage déclaré par la voix. Les voix `low` sont à 16 kHz :
    le coder en dur ferait parler le robot 35 % trop vite après un changement."""
    try:
        with open(voice + ".json") as f:
            return int(json.load(f)["audio"]["sample_rate"])
    except Exception:
        return default


class Speaker:
    def __init__(self, engine=ENGINE, voice=VOICE):
        self.engine = engine
        self.voice = voice
        self.rate = voice_rate(voice)
        self.procs = []                      # tous les fils vivants, pas seulement le dernier
        self.lock = threading.RLock()

    # -- interne : lance la chaîne de processus, verrou déjà tenu --
    def _spawn(self, text):
        if self.engine == "espeak":
            p = subprocess.Popen(["espeak-ng", "-v", "fr", "-s", "165", text],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            return [p]
        synth = subprocess.Popen([PIPER, "-m", self.voice, "--output-raw"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        play = subprocess.Popen(["aplay", "-q", "-r", str(self.rate),
                                 "-f", "S16_LE", "-c", "1", "-"],
                                stdin=synth.stdout, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        synth.stdout.close()                 # seul `aplay` garde l'extrémité de lecture
        threading.Thread(target=self._feed, args=(synth, text), daemon=True).start()
        return [synth, play]

    @staticmethod
    def _feed(proc, text):
        try:
            proc.stdin.write((text + "\n").encode())
            proc.stdin.close()
        except (BrokenPipeError, ValueError):
            pass                             # coupé par stop() entre-temps

    def say(self, text):
        """Parle sans bloquer. Coupe ce qui était en cours. Atomique."""
        text = text.strip()
        if not text:
            return
        with self.lock:                      # kill + spawn dans UNE section critique,
            self._stop_locked()              # sinon deux appels concurrents laissent
            self.procs = self._spawn(text)   # des processus orphelins increvables

    def _stop_locked(self):
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


if __name__ == "__main__":
    import sys, time
    txt = " ".join(sys.argv[1:]) or "Bonjour Alex, je suis microturn, et je parle en local."
    for eng in ("espeak", "piper"):
        if eng == "piper" and not os.path.exists(PIPER):
            print(f"{eng:7s} absent"); continue
        s = Speaker(eng); t0 = time.time(); s.say(txt); lance = time.time() - t0
        s.wait()
        print(f"{eng:7s} lancement {lance*1000:5.0f} ms | fin {time.time()-t0:.2f} s "
              f"| {s.rate} Hz")
