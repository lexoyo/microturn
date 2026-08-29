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

# UNE seule constante de temps, et c'est tout le turn-taking.
#
# Avant : six seuils (silence, mots nouveaux, intervalle, relance…) qui décidaient
# de la fin de tour AVANT le modèle, en aveugle — un VAD déguisé, exactement ce
# que DuplexCascade supprime. Pire, on n'appelait le décideur QUE sur du texte
# nouveau : le modèle ne voyait jamais les silences, donc ne pouvait pas juger
# une fin de tour.
#
# Maintenant : on consulte à intervalle fixe, quoi qu'il arrive, et le silence
# est une donnée qu'on lui transmet. 1,2 s est leur optimum mesuré d'exactitude
# (0,934 contre 0,858 à 0,6 s) ; ils ont retenu 0,6 s pour la latence, mais notre
# problème est la justesse, pas la réactivité — et ça divise les appels par deux.
TICK_S = 1.2
SILENCE = "(silence)"      # ce qu'on envoie quand rien n'a été dit depuis le tick
MICRO_TOURS = 24         # historique gardé ; au-delà le prompt gonfle sans fin
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
                 muet=False, modele=None, **kw):
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
                "llm": modele or llm.MODEL,
                "tts": self.voix.engine, "voix": self.voix.voice,
                "source": path or f"micro {mic}", "muet": muet,
                "parametres": {
                    "TICK_S": TICK_S, "MICRO_TOURS": MICRO_TOURS,
                    "porte_facteur": porte,
                    "porte_facteur_bruit": audio.FACTEUR_BRUIT,
                    "llm_TIMEOUT": llm.TIMEOUT, "stt_PLAFOND_S": stt.PLAFOND_S,
                    "stt_PAS_S": stt.PAS_S, "audio_CHUNK": audio.CHUNK},
                "version_code": _empreinte_code(),
                "machine": _machine()})
        self.porte = audio.Porte(porte, self.trace) if porte > 0 else None
        self.decideur = llm.Decideur(model=modele or llm.MODEL, trace=self.trace)
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

        self.transcript = ""        # fenêtre courante rendue par le STT
        self.vu = ""                # ce qui avait déjà été envoyé au décideur
        self.parle_depuis = None    # début de notre propre parole
        self.parle_fin = 0.0        # quand on a fini de parler
        self.texte_dit = ""         # ce qu'on est en train de prononcer
        self.en_vol = False         # un appel réseau est en cours
        self.t_vol = 0.0            # depuis quand
        self.micro_tours = []       # historique alterné vu par le modèle
        self.stats = []

    def log(self, s):
        if self.verbose:
            print(f"{time.time()-self.t0:6.2f}s  {s}", flush=True)

    # ---------- parole ----------
    def _dire(self, texte):
        if not texte:
            return
        self.log(f"▶  {texte}")
        self.voix.say(texte)                 # ne bloque pas
        self.parle_depuis = time.time()
        self.texte_dit = texte
        self.robot_parle = True
        if self.trace:
            self.trace.ev("parole_debut", texte=texte)
        # Ferme le tour côté STT : sans ça le prochain transcript recontiendrait
        # tout ce à quoi on vient de répondre.
        self.eng.reset()
        self.transcript = ""
        self.vu = ""

    # ---------- l'horloge ----------
    @staticmethod
    def _cle(mot):
        """Forme comparable d'un mot : whisper re-ponctue et re-capitalise toute
        la fenêtre à chaque passe, donc « bonjour » et « Bonjour, » sont le même
        mot. Comparer les formes brutes faisait tomber le préfixe commun à zéro
        et renvoyait la phrase entière comme si elle venait d'être dite — le
        modèle la lisait alors comme un énoncé neuf et complet, et répondait au
        milieu de la phrase."""
        return mot.lower().strip(".,;:!?…\"'«»()")

    def _delta(self):
        """Ce qui est arrivé DEPUIS le tick précédent, ou SILENCE.

        Le modèle a besoin de la dynamique (« ce qui vient de se dire »), pas de
        l'état (« voilà tout le tour »). Whisper re-transcrit toute la fenêtre et
        peut se corriger rétroactivement : on prend donc ce qui dépasse du
        préfixe commun, comparé sur une forme normalisée."""
        mc = self.transcript.split()
        mv = self.vu.split()
        if not mc:
            return SILENCE
        k = 0
        while k < len(mc) and k < len(mv) and self._cle(mc[k]) == self._cle(mv[k]):
            k += 1
        reste = " ".join(mc[k:]).strip()
        return reste or SILENCE

    def _interroger(self, delta):
        """Tourne dans son thread. Ne DOIT jamais mourir sans reposer sa réponse :
        sinon `en_vol` reste vrai pour toujours, plus aucune décision n'est prise,
        et le système se tait définitivement — sans le moindre message."""
        try:
            action, texte, dt = self.decideur.decide(delta, list(self.micro_tours))
        except Exception as e:
            action, texte, dt = "error", f"{type(e).__name__}: {e}"[:90], 0.0
        self.q.put(("decision", (action, texte, delta, dt), time.time() - self.t0))

    def _tick(self):
        """Un tour d'horloge : on consulte le modèle, quoi qu'il se soit passé."""
        if self.en_vol:
            # Ceinture : un mutisme définitif ne doit pas dépendre de
            # l'exhaustivité d'un `except`.
            if time.time() - self.t_vol > 4 * TICK_S:
                self.log("⚠  appel sans réponse, on repart")
                self.en_vol = False
            else:
                return              # un seul appel en vol ; le texte s'accumule
        delta = self._delta()
        # Sans ça, COUPE est indécidable : le prompt le définit comme « elle se
        # remet à parler alors que je suis en train de parler », information
        # qu'on ne transmettait jamais. C'est aussi la première source de
        # contexte du système — les suivantes (caméra, capteurs) viendront ici.
        # THINKING n'est décidable que si le modèle sait s'il vient de parler —
        # même oubli que pour COUPE, corrigé plus tôt. Sans cette information il
        # prend n'importe quel silence pour une réflexion post-réponse : observé
        # 54 fois pour 4 réponses, et dans cet état il n'écoute plus rien.
        if self.robot_parle:
            delta = "[I am speaking] " + delta
        elif self.parle_fin and time.time() - self.parle_fin < 6.0:
            delta = "[I just answered] " + delta
        else:
            delta = "[I have not spoken] " + delta
        self.vu = self.transcript
        self.en_vol = True
        self.t_vol = time.time()
        threading.Thread(target=self._interroger, args=(delta,), daemon=True).start()

    def _appliquer(self, action, texte, delta, dt):
        """L'action découle mécaniquement de l'état perçu."""
        self.en_vol = False
        self.stats.append((action, dt))
        if action == "error":
            # Traité AVANT d'écrire l'historique : sinon la troncature à
            # MICRO_TOURS s'applique d'abord et le retrait des deux entrées
            # fantômes emporte deux vrais micro-tours avec lui.
            self.log(f"⚠  réseau ({dt:.2f}s) {texte}")
            self.vu = ""            # l'énoncé n'est pas perdu : il repartira
            return
        self.micro_tours += [{"role": "user", "content": delta},
                             {"role": "assistant",
                              # Les mêmes labels que le prompt : l'historique en montrait
                              # d'autres, en français, plus nombreux et plus récents que
                              # les exemples — la configuration mesurée comme la pire.
                              "content": {"parler": "DONE " + texte, "parle": "SPEAKING",
                                          "reflechit": "THINKING",
                                          "coupe": "INTERRUPTING"}.get(action, "SPEAKING")}]
        self.micro_tours[:] = self.micro_tours[-MICRO_TOURS:]

        if action == "parler":
            self._dire(texte)
        elif action in ("coupe", "parle"):
            # Comme DuplexCascade : n'importe quel tick où elle parle pendant
            # qu'on parle coupe la synthèse. Faire dépendre l'interruption du
            # seul label INTERRUPTING la rendait impossible — il n'a jamais été
            # émis une seule fois sur 153 décisions.
            if self.voix.speaking() and not delta.strip().endswith(SILENCE):
                self.voix.stop()
                self.log("✂  coupé, tu reprends la parole")
                if self.trace:
                    self.trace.ev("coupure")
        elif action == "reflechit":
            self.log(f"…  ({dt:.2f}s) elle réfléchit")
        elif action == "parler_sans_texte":
            # Une décision de parler dont la réponse manque. La confondre avec
            # l'attente rendait le système muet ET faussait le ratio, en silence.
            self.log(f"⚠  ({dt:.2f}s) a décidé de répondre, sans réponse")
        elif action == "format":
            self.log(f"⚠  ({dt:.2f}s) hors format : {texte[:50]}")
        else:
            self.log(f"⏳ ({dt:.2f}s) elle parle encore")

    # ---------- boucle principale ----------
    def run(self):
        prochain = time.time() + TICK_S
        try:
            while True:
                try:
                    kind, payload, t = self.q.get(timeout=0.05)
                except queue.Empty:
                    kind = None
                now = time.time()

                if kind == "eof":
                    break
                elif kind == "decision":
                    self._appliquer(*payload)
                elif kind in ("partial", "final"):
                    if payload and payload != self.transcript:
                        self.transcript = payload
                        self.log(f"…  {payload[-70:]}")

                # Barge-in local, sans réseau : la porte a mesuré une vraie voix
                # par-dessus notre parole. Passer par le modèle coûterait un tick
                # plus un aller-retour, soit plus d'une seconde et demie.
                if (self.porte is not None and self.porte.barge_in
                        and self.voix.speaking()):
                    self.voix.stop()
                    self.porte.barge_in = False
                    self.log("✂  coupé, tu reprends la parole")
                    if self.trace:
                        self.trace.ev("coupure", origine="porte")

                self.robot_parle = self.voix.speaking()
                if not self.robot_parle and self.parle_depuis is not None:
                    if self.trace:
                        self.trace.ev("parole_fin", texte=self.texte_dit)
                    self.parle_depuis = None
                    self.parle_fin = now

                if now >= prochain:
                    # horloge ponctuelle avec rattrapage, mais SANS rafale : si un
                    # tick a débordé, le suivant part tout de suite, on n'empile pas
                    # les ticks manqués.
                    prochain = max(now, prochain + TICK_S)
                    self._tick()
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
    ap.add_argument("--moteur", default="whisper",
                    choices=["whisper", "vosk", "rejeu"],
                    help="rejeu : relit les transcriptions d'une session tracée, "
                         "pour comparer deux réglages sur des entrées identiques")
    ap.add_argument("--modele", default=None, metavar="NOM",
                    help="modèle de décision (défaut : %s)" % llm.MODEL)
    ap.add_argument("--vitesse", type=float, default=1.0,
                    help="rejeu accéléré ; au-delà de 1.0 les latences mesurées "
                         "ne veulent plus rien dire")
    ap.add_argument("--mic", default="default")
    ap.add_argument("--tts", default=None, choices=["piper", "espeak"])
    ap.add_argument("--muet", action="store_true", help="ne pas prononcer (mesure seule)")
    ap.add_argument("--trace", metavar="DOSSIER",
                    help="enregistre la session (audio, événements, méta) pour la rejouer")
    ap.add_argument("--porte", type=float, default=audio.FACTEUR_ECHO, metavar="FACTEUR",
                    help="porte de volume anti-écho : seuil = niveau d'écho mesuré "
                         f"× FACTEUR (défaut {audio.FACTEUR_ECHO}, 0 = désactivée)")
    a = ap.parse_args()

    kw = {}
    if a.moteur == "rejeu":
        if not a.fichier:
            raise SystemExit("--moteur rejeu attend un dossier de session")
        kw = {"session": a.fichier, "vitesse": a.vitesse}
        a.fichier = None
    s = Session(a.moteur, a.fichier, a.mic, engine=a.tts, trace_dir=a.trace,
                porte=a.porte, muet=a.muet, modele=a.modele, **kw)
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
