#!/usr/bin/env python3
"""microturn — conversation en flux continu, sans détecteur de parole.

    ┌─ thread audio ─┐      ┌─ boucle d'état ─┐      ┌─ thread décideur ─┐
    │ lit le micro   │─────▶│ tient l'état    │─────▶│ 1 appel en vol    │
    │ transcrit      │ queue│ décide QUAND    │ queue│ jamais bloquant   │
    └────────────────┘      └─────────────────┘      └───────────────────┘

Trois threads et une queue, pour une raison précise : la boucle ne doit JAMAIS
bloquer sur de l'I/O. Si elle attend la fin de la parole ou une réponse HTTP,
l'audio s'accumule dans le tube (2,048 s de capacité), ALSA déborde, et on perd
ce que la personne dit — puis on transcrit l'écho de sa propre voix.

La décision est SPÉCULATIVE, et c'est là qu'est l'idée de DuplexCascade : on
interroge le modèle pendant que la personne parle, on garde la réponse au chaud,
et on la prononce dès qu'elle s'arrête. La latence perçue devient le temps de
détection de la fin, pas le temps de l'aller-retour réseau.
"""
import argparse, hashlib, os, platform, queue, subprocess, sys, threading, time
import audio, llm, stt, tts

PAUSE_FIN = 0.35      # sans mot nouveau -> on considère que le tour est fini
DELTA_MOTS = 3        # mots nouveaux avant de redemander au décideur
ENTRE_APPELS = 0.4    # s minimum entre deux appels réseau
RELANCE_S = 2.5       # filet : redemander si le texte change sans grandir
# Il n'y a plus de GRACE_ECHO : ignorer le micro pendant 0,4 s ne servait à rien
# face à une réponse de 3 à 5 s, et l'allonger aurait tué le barge-in. C'est
# `audio.Porte` qui traite l'écho maintenant, en le mesurant au lieu de parier
# sur une durée (sa calibration joue le rôle de la grâce, mais seulement le
# temps d'entendre trois blocs sonores, et une seule fois par session).


def _empreinte_code():
    """Identifie la version exacte du code. Le dépôt n'a pas encore de commit,
    donc un hash du contenu des sources : sans ça, deux traces ne sont pas
    comparables — on ne saurait pas si un écart vient du réglage ou du code."""
    h = hashlib.sha256()
    ici = os.path.dirname(os.path.abspath(__file__))
    for nom in sorted(("audio.py", "stt.py", "llm.py", "tts.py",
                       "pipeline.py", "journal.py")):
        try:
            with open(os.path.join(ici, nom), "rb") as f:
                h.update(f.read())
        except FileNotFoundError:
            pass
    infos = {"sources_sha256": h.hexdigest()[:16]}
    try:
        infos["git"] = subprocess.run(
            ["git", "-C", ici, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2).stdout.strip() or None
    except Exception:
        infos["git"] = None
    return infos


def _machine():
    """Une trace prise sur un laptop et une prise sur le Pi ne se comparent pas
    sans savoir laquelle est laquelle."""
    return {"hote": platform.node(), "arch": platform.machine(),
            "python": platform.python_version(), "coeurs": os.cpu_count()}


class Session:
    def __init__(self, moteur="whisper", path=None, mic="default",
                 engine=None, verbose=True, trace_dir=None, porte=audio.FACTEUR_ECHO,
                 muet=False, **kw):
        self.voix = tts.Speaker(engine or tts.ENGINE)
        self.muet = muet
        if muet:
            self.voix.say = lambda t: None   # mesure seule : rien ne sort, donc
        self.robot_parle = False             # rien ne peut nous revenir non plus
        self.trace = None
        if trace_dir:
            # importé seulement ici : sans --trace, pas de module, pas de thread,
            # pas de fichier ouvert.
            import journal
            self.trace = journal.Journal(trace_dir, {
                "stt": moteur,
                "modele_stt": stt.WHISPER_MODEL if moteur == "whisper" else stt.VOSK_DIR,
                "llm": llm.MODEL,
                "tts": self.voix.engine, "voix": self.voix.voice,
                "source": path or f"micro {mic}", "muet": muet,
                "parametres": {
                    "PAUSE_FIN": PAUSE_FIN, "DELTA_MOTS": DELTA_MOTS,
                    "ENTRE_APPELS": ENTRE_APPELS, "porte_facteur": porte,
                    "porte_facteur_bruit": audio.FACTEUR_BRUIT,
                    "llm_TIMEOUT": llm.TIMEOUT, "stt_PLAFOND_S": stt.PLAFOND_S,
                    "stt_PAS_S": stt.PAS_S, "audio_CHUNK": audio.CHUNK},
                "version_code": _empreinte_code(),
                "machine": _machine()})
        self.porte = audio.Porte(porte, self.trace) if porte > 0 else None
        self.decideur = llm.Decideur(trace=self.trace)
        self.q, self.stop_evt, self.stream, self.eng = stt.start(
            moteur, path, mic, porte=self.porte, trace=self.trace,
            robot_parle=lambda: self.robot_parle, **kw)
        if self.trace is not None and hasattr(self.eng, "reglages"):
            # les réglages du moteur ne sont connus qu'après sa construction, et
            # ce sont eux qui font varier le RTF du simple au double (audio_ctx,
            # best_of, threads) : sans eux, deux traces ne se comparent pas.
            self.trace.meta["reglages_stt"] = self.eng.reglages
            self.trace.meta["charge_stt_s"] = round(self.eng.charge_s, 3)
        self.verbose = verbose
        self.t0 = time.time()

        self.transcript = ""        # ce que la personne dit dans ce tour
        self.dernier_mot = 0.0      # quand le transcript a bougé
        self.mots_vus = 0           # au dernier appel réseau
        self.dernier_appel = 0.0
        self.dernier_soumis = ""
        self.parle_depuis = None    # début de notre propre parole
        self.texte_dit = ""         # ce qu'on est en train de prononcer

        self.pret = None            # (réponse, transcript_source) — la spéculation
        self.en_vol = False
        self.sale = False           # un nouveau transcript est arrivé pendant l'appel
        self.histoire = []
        self.stats = []

    def log(self, s):
        if self.verbose:
            print(f"{time.time()-self.t0:6.2f}s  {s}", flush=True)

    # ---------- thread décideur : ne bloque jamais la boucle ----------
    def _interroger(self, transcript):
        action, texte, dt = self.decideur.decide(transcript, self.histoire)
        self.q.put(("decision", (action, texte, transcript, dt), time.time() - self.t0))

    def _peut_interroger(self, now):
        """Décide s'il vaut la peine de payer un appel réseau.

        Le compteur de mots ne suffit pas : le tampon STT glisse quand un tour
        dépasse PLAFOND_S, donc le transcript RACCOURCIT. `mots_vus` restait
        alors au-dessus du compte courant, la différence ne repassait jamais
        au-dessus du seuil, et le système devenait muet DÉFINITIVEMENT
        (observé : 2 décisions et aucune réponse en 68 s). D'où deux garde-fous :
        on remet le compteur à zéro dès qu'il devient incohérent, et une relance
        au temps prend le relais quand le texte change sans grandir."""
        if self.en_vol or not self.transcript:
            return False
        if now - self.dernier_appel < ENTRE_APPELS:
            return False
        if self.transcript == self.dernier_soumis:
            return False                       # rien de neuf : inutile de payer
        n = len(self.transcript.split())
        if n < self.mots_vus:                  # le tampon a glissé
            self.mots_vus = 0
        return (n - self.mots_vus >= DELTA_MOTS
                or now - self.dernier_appel >= RELANCE_S)

    def _lancer(self, now):
        self.en_vol, self.sale = True, False
        self.mots_vus = len(self.transcript.split())
        self.dernier_soumis = self.transcript
        self.dernier_appel = now
        threading.Thread(target=self._interroger, args=(self.transcript,),
                         daemon=True).start()

    # ---------- parole ----------
    def _dire(self, texte):
        self.log(f"▶  {texte}")
        self.histoire += [{"role": "user", "content": self.transcript},
                          {"role": "assistant", "content": texte}]
        self.histoire[:] = self.histoire[-8:]
        self.voix.say(texte)                 # ne bloque pas
        self._debut_parole(texte)
        self.parle_depuis = time.time()
        self.eng.reset()                     # borne le segment : sinon le transcript
        self.transcript = ""                 # suivant recontient tout depuis le début
        self.mots_vus = 0
        self.pret = None

    def _debut_parole(self, texte):
        """Ouvre la fenêtre où le seul son attendu au micro est notre écho.

        On lit l'état réel des processus plutôt qu'un booléen posé à la main :
        en `--muet` rien n'a été lancé, et fermer la porte pour un son qui ne
        sortira jamais rendrait le robot sourd. L'audio de sortie n'est PAS
        enregistré dans la trace : piper est déterministe, on le régénère du
        texte, et ça doublerait le volume écrit."""
        self.robot_parle = self.voix.speaking()
        self.texte_dit = texte
        if self.trace:
            self.trace.ev("parole_debut", texte=texte, audible=self.robot_parle)
            if not self.robot_parle:     # --muet : la paire début/fin reste
                self.trace.ev("parole_fin", texte=texte, duree=0.0)  # complète

    # ---------- boucle principale ----------
    def run(self):
        try:
            while True:
                try:
                    kind, payload, t = self.q.get(timeout=0.1)
                except queue.Empty:
                    kind = None
                now = time.time()

                if self.robot_parle and not self.voix.speaking():
                    self.robot_parle = False
                    if self.trace:
                        self.trace.ev("parole_fin", texte=self.texte_dit,
                                      duree=round(now - self.parle_depuis, 2))

                if kind == "eof":
                    break

                elif kind == "decision":
                    action, texte, source, dt = payload
                    self.en_vol = False
                    self.stats.append((action, dt))
                    if action == "error":
                        self.log(f"⚠  réseau ({dt:.2f}s) {texte}")
                        self.mots_vus = 0        # l'énoncé n'est PAS perdu : on réessaiera
                    elif action == "speak":
                        self.pret = (texte, source)
                        self.log(f"✓  prêt ({dt:.2f}s) {texte[:60]}")
                    elif action == "hmm":
                        self.log(f"~  ({dt:.2f}s) mhm")
                        self.voix.say("mmh")
                        self._debut_parole("mmh")
                        self.parle_depuis = now
                    else:
                        self.log(f"⏳ ({dt:.2f}s) j'attends la suite")

                elif kind in ("partial", "final"):
                    txt = payload
                    # L'écho est arrêté en amont, au niveau du bloc audio, par
                    # audio.Porte : ce qui arrive ici a déjà passé la porte.
                    if txt and txt != self.transcript:
                        nouveaux = len(txt.split()) - len(self.transcript.split())
                        self.transcript, self.dernier_mot = txt, now
                        self.log(f"…  {txt[-70:]}")
                        # barge-in : on parle et la personne repart -> on se tait
                        if self.voix.speaking() and nouveaux >= 2:
                            self.voix.stop()
                            self.robot_parle = False
                            self.log("✂  coupé, tu reprends la parole")
                            if self.trace:
                                self.trace.ev("coupure", motif="barge-in",
                                              texte_coupe=self.texte_dit,
                                              transcript=txt)

                # la personne s'est arrêtée et la réponse est déjà calculée
                if self.pret and self.dernier_mot and now - self.dernier_mot >= PAUSE_FIN:
                    texte, source = self.pret
                    if source == self.transcript:
                        self._dire(texte)
                    else:
                        self.pret = None         # le transcript a changé : périmé
                        self.mots_vus = 0

                if self._peut_interroger(now):
                    self._lancer(now)
        except KeyboardInterrupt:
            self.log("[arrêt]")
        finally:
            self.close()
        return self.stats

    def close(self):
        self.stop_evt.set()
        self.voix.stop()
        audio.close_stream(self.stream)
        if self.trace:
            dossier = self.trace.close(
                bruit_final=round(self.porte.bruit or 0, 1) if self.porte else None,
                echo_final=round(self.porte.echo, 1) if self.porte else None)
            self.trace = None            # close() est idempotent vu d'ici
            self.log(f"trace: {dossier}")


def main():
    ap = argparse.ArgumentParser(description="microturn — conversation en flux continu")
    ap.add_argument("fichier", nargs="?", help="WAV à rejouer (sinon micro)")
    ap.add_argument("--moteur", default="whisper", choices=["whisper", "vosk"])
    ap.add_argument("--mic", default="default")
    ap.add_argument("--tts", default=None, choices=["piper", "espeak"])
    ap.add_argument("--muet", action="store_true", help="ne pas prononcer (mesure seule)")
    ap.add_argument("--trace", metavar="DOSSIER",
                    help="enregistre la session (audio, événements, méta) pour la rejouer")
    ap.add_argument("--porte", type=float, default=audio.FACTEUR_ECHO, metavar="FACTEUR",
                    help="porte de volume anti-écho : seuil = niveau d'écho mesuré "
                         f"× FACTEUR (défaut {audio.FACTEUR_ECHO}, 0 = désactivée)")
    a = ap.parse_args()

    s = Session(a.moteur, a.fichier, a.mic, engine=a.tts,
                trace_dir=a.trace, porte=a.porte, muet=a.muet)
    st = s.run()
    if st:
        par = {}
        for act, dt in st:
            par.setdefault(act, []).append(dt)
        resume = "  ".join(f"{k}:{len(v)}" for k, v in sorted(par.items()))
        reseau = [d for a_, d in st if d > 0]
        print(f"\n--- {len(st)} décisions | {resume} | "
              f"latence réseau moy {sum(reseau)/len(reseau):.2f}s "
              f"sur {len(reseau)} appels" if reseau else
              f"\n--- {len(st)} décisions | {resume} | aucun appel réseau",
              file=sys.stderr)


if __name__ == "__main__":
    main()
