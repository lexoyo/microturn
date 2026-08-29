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
import argparse, glob, hashlib, json, os, platform, queue, subprocess, sys, threading, time
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
# Au-delà de ce silence à l'écran, la boucle dit qu'elle est vivante et ce
# qu'elle attend. Assez long pour ne pas noyer les vraies lignes, assez court
# pour qu'un blocage se voie tout de suite.
BATTEMENT_S = 3.0
# Amplitude crête au-dessus de laquelle on considère qu'il y a eu du son pendant
# le tick. 328 sur 32768, soit -40 dBFS : le seuil par défaut de `ffmpeg
# silencedetect`, choisi pour ne dépendre d'aucune constante maison. En dessous,
# c'est un vrai silence ; au-dessus sans texte, la reconnaissance a échoué.
SEUIL_VOIX = 328
# Le marqueur de silence et les états viennent de la langue choisie : ils doivent
# être EXACTEMENT ceux que le prompt décrit, sinon le modèle voit des marqueurs
# qu'on ne lui a jamais présentés (c'est arrivé : « SILENCE » envoyé 53 fois
# quand le prompt annonçait « (silence) »).
# 24 tours, c'est douze échanges, soit QUATORZE SECONDES d'horizon. Mesuré le
# 29/08/2026 : une question posée en quarante secondes en sortait entièrement,
# et le modèle ne pouvait pas y répondre puisqu'il ne la voyait plus. 48 porte
# l'horizon à une demi-minute. Le surcoût en tokens est en grande partie servi
# par le cache implicite, le préfixe étant constant.
MICRO_TOURS = 20
# Il n'y a plus de GRACE_ECHO : ignorer le micro pendant 0,4 s ne servait à rien
# face à une réponse de 3 à 5 s, et l'allonger aurait tué le barge-in. C'est
# `audio.Porte` qui traite l'écho maintenant, en le mesurant au lieu de parier
# sur une durée (sa calibration joue le rôle de la grâce, mais seulement le
# temps d'entendre trois blocs sonores, et une seule fois par session).


def _empreinte_code():
    """Identifie la version exacte du code ET des catalogues.

    Hash du contenu plutôt que le seul commit : on trace couramment un dépôt
    modifié, et sans ça deux traces ne sont pas comparables — on ne saurait pas
    si un écart vient du réglage ou du code. Les catalogues en font partie : le
    prompt système, les jetons et les exemples sont le principal levier de
    comportement du système, et deux prompts différents donnaient jusqu'ici la
    même empreinte."""
    h = hashlib.sha256()
    ici = os.path.dirname(os.path.abspath(__file__))
    fichiers = [os.path.join(ici, nom) for nom in
                sorted(("audio.py", "stt.py", "llm.py", "tts.py",
                        "pipeline.py", "journal.py"))]
    fichiers += sorted(glob.glob(os.path.join(ici, "locales", "*.toml")))
    for chemin in fichiers:
        try:
            with open(chemin, "rb") as f:
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


class HorlogeVirtuelle:
    """Le temps du rejeu déterministe : il n'avance que d'un tick à l'autre.

    En temps réel, un appel réseau lent fait sauter des ticks. C'est le
    comportement authentique du système, mais il rend deux mesures
    incomparables : la même session rejouée deux fois, sur le même code, a donné
    118 puis 123 décisions et 0,762 puis 0,691 de justesse. On mesurait le
    réseau, pas le prompt.

    Ici l'horloge n'avance que quand on le décide : le nombre de ticks et leur
    contenu sont fixes, et deux rejeux du même code donnent le même résultat.
    En contrepartie ce chronomètre ne voit plus la latence — elle se mesure
    ailleurs, en conditions réelles (`llm.py` garde la vraie horloge).
    """

    def __init__(self, vrai):
        self.t = 0.0
        self._vrai = vrai

    def time(self):
        return self.t

    def monotonic(self):
        return self.t

    def sleep(self, _s):
        """Le temps ne passe pas tout seul : dormir ne fait rien avancer."""

    def __getattr__(self, nom):
        """Tout le reste — `strftime`, `struct_time`… — vient du vrai module."""
        return getattr(self._vrai, nom)


class Session:
    def __init__(self, moteur="whisper", path=None, mic="default",
                 engine=None, verbose=True, trace_dir=None, porte=audio.FACTEUR_ECHO,
                 muet=False, modele=None, langue="fr", rendu=None, **kw):
        self.langue = langue
        cat = llm.catalogue(langue)
        self.silence = cat["divers"]["silence"]
        self.repete = cat["divers"]["silence_repete"]
        self.bruit_sans_texte = cat["divers"]["bruit_sans_texte"]
        self.tour_en_cours = cat["divers"]["tour_en_cours"]
        self.silences = 0           # longueur de la série de silences en cours
        self.jetons = cat["jetons"]
        self.etats = cat["etats"]
        # En muet on garde un locuteur qui DURE : sans lui `speaking()` reste
        # faux, l'état « je parle » n'est jamais envoyé et la coupure devient
        # impossible — on mesurerait un autre système que celui qu'on livre.
        # La voix suit la langue demandée : sans ça `--langue en` faisait lire
        # l'anglais par une voix française, et les deux clés du catalogue
        # (`voix_piper`, `espeak`) n'étaient lues par personne.
        _voix = tts.voix_pour(cat["divers"].get("voix_piper"))
        _lg = cat["divers"].get("espeak", langue)
        self.rendu = rendu
        if rendu:
            # Banc d'essai : on synthétise dans un tampon pour produire un
            # output.wav aligné sur l'entrée, au lieu de jouer.
            self.voix = tts.Enregistreur(self._horloge, voice=_voix, langue=_lg,
                                         rate_sortie=audio.RATE,
                                         engine=engine or tts.ENGINE)
        elif muet:
            self.voix = tts.Silencieux(voice=_voix, langue=_lg)
        else:
            self.voix = tts.Speaker(engine or tts.ENGINE, voice=_voix, langue=_lg)
        self.muet = muet
        self.robot_parle = False
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
                "source": path or f"micro {mic}", "muet": muet, "langue": langue,
                "parametres": {
                    "TICK_S": TICK_S, "MICRO_TOURS": MICRO_TOURS,
                    "porte_facteur": porte,
                    "porte_facteur_bruit": audio.FACTEUR_BRUIT,
                    "llm_TIMEOUT": llm.TIMEOUT, "stt_PLAFOND_S": stt.PLAFOND_S,
                    "stt_PAS_S": stt.PAS_S, "audio_CHUNK": audio.CHUNK},
                "version_code": _empreinte_code(),
                "machine": _machine()})
        self.porte = audio.Porte(porte, self.trace) if porte > 0 else None
        # `--modele simule` : décideur déterministe hors ligne. Il ne juge rien,
        # il sert d'étalon — il donne le bruit de mesure de la mécanique seule,
        # sans le non-déterminisme du modèle distant ni la latence réseau.
        fabrique = llm.Simule if (modele or "") == "simule" else llm.Decideur
        # Le prompt ne dépend QUE de la langue (arbitrage d'Alex, 29/08). Une
        # phrase décrivant ce que rend le moteur — « le texte est en majuscules
        # sans ponctuation », vraie pour sherpa — vaut +0,063 avec lui et coûte
        # 0,103 avec whisper, qui ponctue. Plutôt qu'un prompt à deux visages,
        # le défaut est whisper et le prompt est écrit pour lui.
        self.decideur = fabrique(model=modele or llm.MODEL, trace=self.trace,
                                 langue=langue, tick=TICK_S)
        self.q, self.stop_evt, self.stream, self.eng = stt.start(
            moteur, path, mic, porte=self.porte, trace=self.trace,
            robot_parle=lambda: self.robot_parle,
            **({"langue": cat["divers"]["whisper"]}
               if moteur == "whisper" else {}), **kw)
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
        self.seq = 0                # numéro de l'appel en cours
        self.t_log = time.time()    # dernière ligne affichée, pour le battement
        self.micro_tours = []       # historique alterné vu par le modèle
        self.stats = []

    def _horloge(self):
        """Position courante en échantillons d'entrée. Zéro avant le démarrage
        du moteur — `self.eng` n'existe pas encore quand le locuteur est
        construit, d'où l'indirection."""
        cap = getattr(getattr(self, "eng", None), "cap", None)
        return cap.lus if cap is not None else 0

    def log(self, s):
        self.t_log = time.time()
        if self.verbose:
            print(f"{time.time()-self.t0:6.2f}s  {s}", flush=True)

    def battement(self):
        """Signe de vie quand aucune action ne produit de ligne.

        Un écran muet est indistinguable d'un plantage. C'est arrivé pour de
        bon : trente-trois secondes sans une ligne alors que le décideur
        répondait toutes les 1,2 s. La boucle dit donc où elle en est, même
        quand il ne se passe rien — c'est le seul moyen de faire la différence
        entre « il réfléchit » et « il est mort »."""
        if time.time() - self.t_log < BATTEMENT_S:
            return
        etat = "appel en cours" if self.en_vol else "en attente"
        vu = self.transcript[-40:] if self.transcript else "rien entendu"
        self.log(f"·  {etat} — transcript stt : {vu!r}")

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
            # `parole_debut` est l'instant où on DEMANDE la parole ; le premier
            # son sort plus tard — le temps que le moteur attaque. Sans cette
            # durée dans la trace, la latence mesurée est plus courte que celle
            # qu'on entend, et c'est celle qu'on entend qui compte.
            self.trace.ev("parole_debut", texte=texte,
                          attaque=round(getattr(self.voix, "ATTAQUE_S", 0.0), 3))
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

    def _envoye(self, delta):
        """Ce qui est PARTI au modèle, rendu lisible pour l'écran.

        Les lignes `…` montrent le transcript complet de whisper ; le modèle,
        lui, ne reçoit que le delta. L'écart entre les deux a trompé Alex et
        moi le même soir : on lisait une question entière à l'écran et on en
        concluait qu'il refusait d'y répondre, alors qu'on lui envoyait
        « (silence) ». Une ligne de décision doit montrer son entrée."""
        e = self.etats
        court = {e["parle"]: "il parle", e["vient"]: "a répondu",
                 e["muet"]: "muet"}
        for marqueur, abrege in court.items():
            if delta.startswith(marqueur):
                reste = delta[len(marqueur):].strip()
                return f"[{abrege}] {reste[:58]}"
        return delta[:70]

    def _rien(self):
        """Le marqueur qui décrit HONNÊTEMENT un tick sans texte neuf.

        On envoyait « (silence) » dans les deux cas, ce qui est faux la moitié
        du temps : whisper redonne souvent la même chaîne pendant que la
        personne parle encore. Mesuré sur une session réelle — vingt secondes de
        « (silence) » d'affilée alors qu'elle disait « Allo ? Allo ? ».

        La porte, elle, sait s'il y a eu du son : c'est une mesure, pas une
        heuristique. Sans porte (ou en rejeu) l'information n'existe pas, et on
        retombe sur le silence — le seul cas où l'ambiguïté est inévitable."""
        cap = getattr(getattr(self, "eng", None), "cap", None)
        if cap is not None and cap.crete > SEUIL_VOIX:
            return self.bruit_sans_texte
        return self.silence

    def _muet_mesure(self):
        """Vrai si le son de ce tick est sous le seuil de silence.

        Sans porte (rejeu, ou capture sans mesure) l'information n'existe pas :
        on ne peut alors rien affirmer, donc on ne bloque rien."""
        cap = getattr(getattr(self, "eng", None), "cap", None)
        return cap is not None and cap.crete <= SEUIL_VOIX

    def _delta(self):
        """Ce qui est arrivé DEPUIS le tick précédent, ou SILENCE.

        Le modèle a besoin de la dynamique (« ce qui vient de se dire »), pas de
        l'état (« voilà tout le tour »). Whisper re-transcrit toute la fenêtre et
        peut se corriger rétroactivement : on prend donc ce qui dépasse du
        préfixe commun, comparé sur une forme normalisée.

        Deux sources décident de <|no voice|>, pas une : la reconnaissance qui
        ne rend rien, ET la mesure du son. Le filtre lexical de `stt.utile` ne
        rattrape que les artefacts CONNUS (génériques de sous-titres, mots de
        bruitage) ; sur un tick réellement silencieux, whisper invente aussi des
        phrases plausibles qu'aucune liste ne peut prévoir. La crête, elle, est
        une mesure : sous le seuil, il ne s'est rien dit, quoi qu'ait rendu le
        décodeur."""
        if self._muet_mesure():
            return self.silence
        mc = self.transcript.split()
        mv = self.vu.split()
        if not mc:
            return self._rien()
        if not mv:
            return " ".join(mc).strip() or self._rien()
        # Ancrage par la QUEUE, pas par la tête. Un préfixe commun tombe à zéro
        # dès que whisper corrige un mot du début, insère une hésitation ou fait
        # glisser sa fenêtre au-delà de PLAFOND_S — et on renvoyait alors toute
        # la phrase comme si elle venait d'être dite. Mesuré deux fois en 20 s.
        # Les derniers mots déjà vus, eux, restent stables : on les retrouve et
        # on coupe juste après.
        cv = [self._cle(m) for m in mv]
        cc = [self._cle(m) for m in mc]
        for taille in (3, 2, 1):
            if len(cv) < taille:
                continue
            queue = cv[-taille:]
            for i in range(len(cc) - taille, -1, -1):
                if cc[i:i + taille] == queue:
                    return " ".join(mc[i + taille:]).strip() or self._rien()
        # Plus aucun repère : la fenêtre a entièrement changé. Ne jamais rendre
        # plus de mots qu'il n'en est apparu depuis le tick précédent, sinon on
        # présente au modèle un énoncé ancien comme s'il était neuf.
        neufs = max(0, len(mc) - len(mv))
        return " ".join(mc[len(mc) - neufs:]).strip() or self._rien()

    def _est_echo(self, delta):
        """Reconnaît sa propre voix dans ce que le STT vient de rendre.

        Sans casque, le micro reprend le haut-parleur : whisper transcrit la
        phrase du robot, le modèle voit du texte pendant qu'il parle et répond
        ME_COUPE. Observé deux fois sur deux — il ne finissait aucune phrase.
        La porte ne suffit pas : elle laisse passer environ une seconde d'écho
        après chaque recalibrage, et c'est assez.

        On ne coupe donc que si le delta apporte des mots qui ne sont PAS dans
        ce qu'on est en train de prononcer. Une vraie interruption en apporte
        toujours ; un écho, jamais."""
        if not self.texte_dit:
            return False
        dit = {self._cle(m) for m in self.texte_dit.split()}
        dit.discard("")
        # Le marqueur d'état est notre propre préfixe, pas de la parole entendue.
        nu = delta
        for marqueur in self.etats.values():
            if nu.startswith(marqueur):
                nu = nu[len(marqueur):]
                break
        mots = [self._cle(m) for m in nu.split()]
        mots = [m for m in mots if m and m != self._cle(self.silence)]
        if not mots:
            return False
        inconnus = [m for m in mots if m not in dit]
        return len(inconnus) <= len(mots) // 2

    def _interroger(self, delta, seq):
        """Tourne dans son thread. Ne DOIT jamais mourir sans reposer sa réponse :
        sinon `en_vol` reste vrai pour toujours, plus aucune décision n'est prise,
        et le système se tait définitivement — sans le moindre message."""
        try:
            action, texte, dt = self.decideur.decide(delta, list(self.micro_tours))
        except Exception as e:
            action, texte, dt = "error", f"{type(e).__name__}: {e}"[:90], 0.0
        self.q.put(("decision", (action, texte, delta, dt, seq), time.time() - self.t0))

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
        cap = getattr(getattr(self, "eng", None), "cap", None)
        if cap is not None:
            cap.crete = 0
        # Sans ça, COUPE est indécidable : le prompt le définit comme « elle se
        # remet à parler alors que je suis en train de parler », information
        # qu'on ne transmettait jamais. C'est aussi la première source de
        # contexte du système — les suivantes (caméra, capteurs) viendront ici.
        # THINKING n'est décidable que si le modèle sait s'il vient de parler —
        # même oubli que pour COUPE, corrigé plus tôt. Sans cette information il
        # prend n'importe quel silence pour une réflexion post-réponse : observé
        # 54 fois pour 4 réponses, et dans cet état il n'écoute plus rien.
        # Le modèle ne reçoit que le DELTA — les quelques mots apparus depuis le
        # tick précédent. Il ne voit donc jamais la phrase entière : « Allo ? »
        # tout seul, jamais « comment tu t'appelles, tu me dis ? Allo ? ». Il
        # applique alors la règle du fragment et se tait. Mesuré : trois
        # questions consécutives sans réponse pendant quarante secondes.
        # On lui rappelle le tour en cours quand il apporte plus que le delta.
        # Le rappel vient APRÈS le delta, et SANS parenthèses. Première version :
        # « (depuis le début de son tour : …) » placé devant. Résultat mesuré,
        # 3/9 inchangé — et la trace montre pourquoi : tous les marqueurs entre
        # parenthèses du système veulent dire « rien entendu » ((silence),
        # (toujours rien…), (ça parle mais je ne comprends pas)). Le modèle a
        # appris cette forme et lisait le rappel comme un marqueur de silence,
        # donc répondait REFLECHIT alors que la question entière était sous ses
        # yeux. Deux sens opposés ne doivent pas avoir la même apparence.
        vu_mots = self.transcript.split()
        # Le rappel vaut SURTOUT quand le delta est un marqueur de silence :
        # c'est là que le modèle n'a rien d'autre à se mettre sous la dent. La
        # condition qui l'excluait a fait tomber le score de 3/9 à 2/9.
        if len(vu_mots) > len(delta.split()) + 2:
            delta = delta + " " + self.tour_en_cours.replace(
                "{texte}", " ".join(vu_mots[-60:]))
        e = self.etats
        if self.robot_parle:
            delta = e["parle"] + " " + delta
        elif self.parle_fin and time.time() - self.parle_fin < 6.0:
            delta = e["vient"] + " " + delta
        else:
            delta = e["muet"] + " " + delta
        self.vu = self.transcript
        self.en_vol = True
        self.t_vol = time.time()
        self.seq += 1
        if getattr(self, "synchrone", False):
            # Rejeu déterministe : l'appel bloque, donc aucun tick ne saute et
            # aucune décision n'arrive en retard. C'est toute la différence.
            self._interroger(delta, self.seq)
            return
        threading.Thread(target=self._interroger, args=(delta, self.seq),
                         daemon=True).start()

    def _appliquer(self, action, texte, delta, dt, seq):
        """L'action découle mécaniquement de l'état perçu."""
        # Le chien de garde relance sans pouvoir annuler le thread parti : sa
        # réponse arrive quand même, décrivant une phrase vieille de plusieurs
        # secondes. L'appliquer faisait parler par-dessus le tour en cours,
        # écrivait l'historique dans le désordre, et remettait `en_vol` à faux
        # alors qu'un appel plus récent était encore en vol — d'où un troisième
        # appel, une file derrière le verrou, et le chien de garde en cascade.
        if seq != self.seq:
            self.log(f"⌛ ({dt:.2f}s) périmée, ignorée · {self._envoye(delta)}")
            return
        self.en_vol = False
        self.stats.append((action, dt))
        if action == "error":
            # Traité AVANT d'écrire l'historique : sinon la troncature à
            # MICRO_TOURS s'applique d'abord et le retrait des deux entrées
            # fantômes emporte deux vrais micro-tours avec lui.
            self.log(f"⚠  réseau ({dt:.2f}s) {texte}")
            self.vu = ""            # l'énoncé n'est pas perdu : il repartira
            return
        # Une série de silences est REPLIÉE en un seul tour qui porte leur
        # nombre, au lieu d'occuper une ligne chacun. Mesuré : à 147 s, douze
        # `(silence)` consécutifs avaient chassé la question d'Alex hors d'un
        # historique qui ne tient que douze tours — il ne pouvait pas y
        # répondre, il ne la voyait plus. L'horizon utile tombait à quatorze
        # secondes. Compter plutôt que jeter garde l'information de durée, qui
        # est justement ce qui distingue une respiration d'un tour fini.
        muet = action == "parle" and delta.strip().endswith(
            (self.silence, self.bruit_sans_texte))
        if muet and self.silences and len(self.micro_tours) >= 2:
            self.silences += 1
            n = self.silences
            marqueur = (self.bruit_sans_texte
                        if delta.strip().endswith(self.bruit_sans_texte)
                        else self.silence)
            self.micro_tours[-2]["content"] = delta[:-len(marqueur)] + \
                self.repete.replace("{n}", str(n))
            self.stats.append(("silence_replie", 0.0))
            self.log(f"⏳ ({dt:.2f}s) parle encore · {self._envoye(delta)}"
                     f"  [replié ×{n}]")
            return
        self.silences = 1 if muet else 0
        # Le MÊME format que les exemples et que la sortie contrainte. L'historique
        # était resté en texte brut (`<|user finish talking|> Ça va bien`) alors que
        # les exemples sont en JSON : le modèle lisait deux conventions pour la même
        # chose, et la mauvaise était la plus proche de sa réponse. Vu dans
        # PROMPTS-ENVOYES.txt, invisible depuis le prompt seul.
        rep = ({"m": self.jetons["parler"], "r": texte} if action == "parler"
               else {"m": self.jetons.get(action, self.jetons["parle"])})
        self.micro_tours += [{"role": "user", "content": delta},
                             {"role": "assistant",
                              "content": json.dumps(rep, ensure_ascii=False)}]
        self.micro_tours[:] = self.micro_tours[-MICRO_TOURS:]

        if action == "parler":
            self._dire(texte)
        elif action in ("coupe", "parle"):
            # Comme DuplexCascade : n'importe quel tick où elle parle pendant
            # qu'on parle coupe la synthèse. Faire dépendre l'interruption du
            # seul label INTERRUPTING la rendait impossible — il n'a jamais été
            # émis une seule fois sur 153 décisions.
            # Les DEUX marqueurs de « rien de neuf » protègent de la coupure.
            # N'en tester qu'un a suffi à casser le système : le jour où
            # `bruit_sans_texte` a été ajouté, il n'était couvert par aucune
            # garde, et comme la porte laisse toujours filtrer un peu d'écho
            # pendant qu'on parle, il apparaissait à chaque réponse. Résultat :
            # quatre coupures sur quatre prises de parole, moins d'une seconde
            # après le début, sans qu'Alex ait dit un mot.
            if (self.voix.speaking()
                    and not delta.strip().endswith(
                        (self.silence, self.bruit_sans_texte))
                    and not self._est_echo(delta)):
                self.voix.stop()
                self.log("✂  coupé, tu reprends la parole")
                if self.trace:
                    self.trace.ev("coupure")
            else:
                # Sans cette ligne l'écran devient AVEUGLE : `parle` est l'action
                # de très loin la plus fréquente, et depuis qu'elle a rejoint la
                # branche de coupure elle ne passait plus par le `else` final.
                # Trente-trois secondes d'affilée sans qu'aucune ligne ne sorte,
                # alors que le décideur répondait toutes les 1,2 s — impossible
                # de distinguer ça d'un plantage.
                self.log(f"⏳ ({dt:.2f}s) parle encore · {self._envoye(delta)}")
        elif action == "reflechit":
            self.log(f"⋯  ({dt:.2f}s) réfléchit · {self._envoye(delta)}")
        elif action == "parler_sans_texte":
            # Une décision de parler dont la réponse manque. La confondre avec
            # l'attente rendait le système muet ET faussait le ratio, en silence.
            self.log(f"⚠  ({dt:.2f}s) a décidé de répondre, sans réponse "
                     f"· {self._envoye(delta)}")
        elif action == "format":
            self.log(f"⚠  ({dt:.2f}s) hors format : {texte[:50]}")
        else:
            self.log(f"⏳ ({dt:.2f}s) parle encore · {self._envoye(delta)}")

    # ---------- boucle principale ----------
    def run_deterministe(self):
        """Rejoue une session tick par tick, hors du temps réel.

        Les transcriptions sont figées (`stt.Rejeu`), l'horloge est virtuelle et
        l'appel au modèle est bloquant : à code égal, deux exécutions donnent
        exactement les mêmes décisions. C'est ce qui permet d'attribuer un écart
        de score à ce qu'on a changé, et à rien d'autre.
        """
        global time
        journal = sys.modules.get("journal")
        evts = sorted(getattr(self.eng, "evts", []))
        if not evts:
            raise SystemExit("--deterministe : uniquement avec --moteur rejeu")
        self.synchrone = True
        fin = evts[-1][0] + 2 * TICK_S
        vrai_temps = time
        horloge = HorlogeVirtuelle(vrai_temps)
        # Trois modules à convertir, pas un seul :
        #   pipeline — les ticks et les fenêtres temporelles ;
        #   tts      — la durée simulée de la parole. Sans lui, `speaking()`
        #              compte en temps réel pendant que la conversation avance
        #              en temps virtuel : le rejeu va 2,4× plus vite, donc le
        #              robot « parle » 2,4× plus longtemps. Mesuré : 8 coupures
        #              au lieu de 3, et la justesse qui tombe de 0,634 à 0,551.
        #   journal  — l'horodatage de la trace, que la métrique compare aux
        #              instants de la référence. Compressé, il décalait tout.
        # `llm` garde le VRAI temps : la latence réseau, elle, est réelle.
        time = horloge
        modules = [tts, journal] if journal is not None else [tts]
        anciens = [(m, m.time) for m in modules]
        for m in modules:
            m.time = horloge
        if self.trace is not None:
            self.trace.t0 = 0.0
        try:
            i, k = 0, 1
            while horloge.t < fin:
                horloge.t = k * TICK_S
                # Tout ce qui a été entendu jusqu'ici, et rien de plus tard.
                while i < len(evts) and evts[i][0] <= horloge.t:
                    _, genre, txt = evts[i]
                    if txt and txt != self.transcript:
                        self.transcript = txt
                        self.log(f"stt {txt[-70:]}")
                        # La trace doit rester rejouable : sans ces événements,
                        # un rejeu de rejeu n'a plus rien à lire, et l'analyse
                        # de latence ne peut plus dire quand le texte est arrivé.
                        if self.trace:
                            self.trace.ev(genre, texte=txt)
                    i += 1
                self._tick()
                # La décision est déjà dans la file : l'appel était bloquant.
                while True:
                    try:
                        kind, payload, _t = self.q.get_nowait()
                    except queue.Empty:
                        break
                    if kind == "decision":
                        self._appliquer(*payload)
                k += 1
        finally:
            time = vrai_temps
            for m, vrai in anciens:
                m.time = vrai
            self.close()
        return self.stats

    def run(self):
        prochain = time.time() + TICK_S
        # Sur `eof` on sortait immédiatement : le dernier tick n'était pas joué
        # et l'appel en vol était abandonné (17 appels pour 16 réponses sur un
        # audio de 20 s). Sur les clips courts d'un banc, le tour final est
        # justement celui qu'on mesure. On se donne deux ticks pour finir.
        echeance = None
        try:
            while True:
                if echeance is not None and (time.time() > echeance
                                             or not self.en_vol):
                    break
                try:
                    kind, payload, t = self.q.get(timeout=0.05)
                except queue.Empty:
                    kind = None
                now = time.time()

                self.battement()

                if kind == "eof":
                    if echeance is None:
                        echeance = time.time() + 2 * TICK_S
                    continue
                elif kind == "decision":
                    self._appliquer(*payload)
                elif kind in ("partial", "final"):
                    if payload and payload != self.transcript:
                        self.transcript = payload
                        # préfixe explicite : c'est ce que WHISPER entend, à ne
                        # pas confondre avec ce qui part au modèle (le delta)
                        self.log(f"stt {payload[-70:]}")

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
        # Attendre la fin de la passe en cours AVANT de rendre la main : le
        # thread de décodage est dans du C qui tient une référence au modèle,
        # et l'interpréteur qui sort le libère sous ses pieds. Le temps d'une
        # passe suffit (1 à 2 s ici, davantage sur un Pi), on laisse de la marge
        # sans jamais bloquer pour de bon.
        if self.rendu:
            total = self._horloge()
            n = self.voix.rendre(self.rendu, total)
            self.log(f"rendu: {self.rendu} — {total/audio.RATE:.2f} s, "
                     f"{n} prise(s) de parole")
        th = getattr(self.eng, "th", None)
        if th is not None:
            th.join(timeout=8)
            if th.is_alive():
                self.log("⚠  le moteur STT n'a pas rendu la main")
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
    ap.add_argument("--langue", default="fr", choices=["fr", "en"],
                    help="langue de la conversation : change les jetons, le prompt, "
                         "whisper et la voix. `en` sert au banc des chercheurs")
    ap.add_argument("--modele", default=None, metavar="NOM",
                    help="modèle de décision (défaut : %s)" % llm.MODEL)
    ap.add_argument("--vitesse", type=float, default=1.0,
                    help="rejeu accéléré ; au-delà de 1.0 les latences mesurées "
                         "ne veulent plus rien dire")
    ap.add_argument("--mic", default="default")
    ap.add_argument("--tts", default=None, choices=["piper", "espeak"])
    ap.add_argument("--modele-simule", dest="modele", action="store_const",
                    const="simule",
                    help="décideur déterministe hors ligne : ni réseau ni coût, "
                         "pour mesurer le bruit de la mécanique seule")
    ap.add_argument("--rendu", metavar="SORTIE.wav",
                    help="écrit un WAV de la même durée que l'entrée, avec les "
                         "réponses à leur place — le format attendu par "
                         "Full-Duplex-Bench")
    ap.add_argument("--muet", action="store_true", help="ne pas prononcer (mesure seule)")
    ap.add_argument("--deterministe", action="store_true",
                    help="rejeu hors temps réel : horloge virtuelle et appel "
                         "bloquant, donc deux exécutions identiques à code égal")
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
                porte=a.porte, muet=a.muet, rendu=a.rendu, modele=a.modele,
                langue=a.langue, **kw)
    st = s.run_deterministe() if a.deterministe else s.run()
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
