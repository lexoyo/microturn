#!/usr/bin/env python3
"""Source audio unique de microturn — micro ou fichier, même contrat.

Un seul endroit qui sait produire du PCM 16 kHz mono, pour que le banc de mesure
et le pipeline mesurent exactement la même chose.
"""
import subprocess
import numpy as np

RATE = 16000
BYTES_PER_S = RATE * 2
CHUNK = 4000                    # 125 ms


def open_stream(path=None, mic="default", realtime=True):
    """Rend un Popen dont stdout est du PCM 16 kHz mono signé 16 bits.

    `default` et non `hw:` : `hw:` court-circuite la conversion ALSA et échoue sur
    les micros qui n'exposent que 44,1/48 kHz stéréo, et surtout il ignore le
    routage de PipeWire — un casque Bluetooth branché en cours de route ne serait
    jamais entendu. `default` suit le périphérique choisi par le système.
    `realtime` cadence la lecture d'un fichier à la vitesse réelle, pour que le
    rejeu reproduise les contraintes du direct.
    """
    if path:
        cmd = ["ffmpeg", "-loglevel", "quiet"]
        if realtime:
            cmd += ["-re"]
        cmd += ["-i", path, "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-"]
    else:
        cmd = ["arecord", "-D", mic, "-f", "S16_LE", "-r", str(RATE),
               "-c", "1", "-t", "raw", "-q"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


def close_stream(proc):
    """Arrêt propre : pas de descripteur qui fuit, pas d'enfant non attendu."""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=1)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass


# --- niveau, porte de volume, capteur -------------------------------------
#
# Sans casque, le micro réentend le robot : whisper transcrit sa propre réponse
# et le robot finit par se répondre à lui-même. Une garde de temps ne suffit pas
# (une réponse dure 3 à 5 s), et couper l'écoute pendant qu'il parle tuerait le
# barge-in — qui est tout l'intérêt d'un compagnon en flux continu.
#
# On garde donc l'écoute, et on ne transmet au STT que ce qui dépasse nettement
# le niveau de l'écho. Ce niveau, on le MESURE au lieu de le régler : pendant
# que le robot parle, le seul son possible est justement son propre écho. Zéro
# réglage manuel, et la mesure suit la pièce et le volume du haut-parleur.

FACTEUR_ECHO = 2.0     # voix directe / écho, en RMS. Voir Porte.juge().
FACTEUR_BRUIT = 2.0    # voix / bruit de fond. Mesuré sur samples/ : le plancher
                       # est à 9 (01-normal) et 8 (02-loin) pour une médiane de
                       # parole à 109 et 49 — un facteur 2 ne coupe donc que du
                       # vrai silence, même sur l'enregistrement lointain.
CALIB_BLOCS = 8        # 1 s pendant laquelle on laisse tout passer : on ne sait
                       # encore rien, jeter serait pire que transcrire du silence.
ECHO_BLOCS_MIN = 3     # blocs SONORES à entendre avant de croire la mesure d'écho
DECROISSANCE = 0.98    # oubli du pic d'écho, par bloc de parole robot : demi-vie
                       # 4,3 s, soit la durée d'une réponse. L'estimation suit
                       # donc le pic RÉCENT et pas le pic de la session, sinon un
                       # claquement de porte fermerait la porte pour de bon.
# Nombre de blocs consécutifs au-dessus du seuil qui signent une VRAIE voix
# pendant que le robot parle. 3 blocs = 375 ms : assez pour ne pas déclencher
# sur un choc, assez court pour couper avant d'être pénible.
# arecord démarre par du silence NUMÉRIQUE : sans plancher, `bruit` tombe à 0 et
# ne peut jamais remonter (min d'une valeur positive et de 0 vaut 0). La porte
# reste alors grande ouverte, se calibre sur la seconde de silence où piper
# charge son modèle, et prend ensuite notre propre écho pour une voix — observé
# en session réelle : trois auto-coupures, chacune une seconde après le début
# d'une réponse.
PLANCHER_BRUIT = 1.0

BARGE_IN_BLOCS = 3
# Au-delà, c'est que le niveau d'écho a changé (volume monté, micro déplacé) et
# qu'il faut le remesurer. Il DOIT rester bien au-dessus de BARGE_IN_BLOCS,
# sinon un barge-in réussi serait pris pour une dérive et refermerait la porte
# sur la personne qui vient de parler.
RECALIBRE_BLOCS = 24   # 3 s de porte ouverte d'affilée pendant que le robot parle
                       # ne peut PAS être un barge-in : la boucle l'aurait coupé
                       # au bout de 100 ms. C'est donc que l'écho a changé de
                       # niveau (volume monté, enceinte déplacée) — on remesure.
QUEUE_BLOCS = 3        # ~375 ms après le dernier bloc retenu : les fins de mot
                       # sont à peine plus fortes que le silence, les couper
                       # ferait manger la dernière syllabe par le STT.
PERIODE_NIVEAUX = 8    # une ligne de trace par seconde, pas par bloc


def rms(data):
    """Niveau efficace d'un bloc PCM S16, en unités int16 (0 à 32768)."""
    x = np.frombuffer(data, np.int16)
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))


class Porte:
    """Porte de volume auto-calibrée : laisse passer la voix, retient l'écho.

    Deux estimations, toutes deux en O(1) — pas de fenêtre glissante à garder en
    RAM sur une machine à 905 Mio :

      `bruit` : plancher de la pièce, suivi quand personne ne parle, avec une
                descente rapide et une montée lente (un tracker de bruit
                classique : le minimum récent est un bien meilleur estimateur du
                fond qu'une moyenne, que la parole tire vers le haut).
      `echo`  : maximum glissant du niveau reçu PENDANT que le robot parle. On
                prend le maximum et non une moyenne parce qu'il suffit d'UN bloc
                d'écho transmis pour que whisper écrive une phrase et que le
                robot se réponde ; c'est donc le pire bloc qu'il faut couvrir,
                pas le bloc moyen. Corollaire : la référence étant déjà le pic,
                le facteur n'a pas à absorber la dynamique de l'écho, et 2,0
                (+6 dB) suffit — la voix directe arrive bien plus fort que le
                même son après un aller-retour dans la pièce.
    """

    def __init__(self, facteur=FACTEUR_ECHO, trace=None):
        self.facteur = facteur
        self.trace = trace
        self.bruit = None
        self.echo = 0.0
        self.n_calib = 0
        self.n_echo = 0          # blocs sonores mesurés pendant la parole robot
        self.n_ouverts = 0       # blocs consécutifs laissés passer pendant qu'il parle
        self.barge_in = False    # une vraie voix couvre notre propre parole
        self.bloc = 0
        self.jusqua = 0          # fin de la queue de garde, en numéro de bloc
        self.ouverte = True      # pour ne tracer que les changements d'état
        self._raz_fenetre()

    def _raz_fenetre(self):
        self.f_pic, self.f_somme, self.f_transmis, self.f_jetes, self.f_n = 0.0, 0.0, 0, 0, 0

    def juge(self, data, robot_parle):
        """Rend True si le bloc doit aller au STT. Met à jour les estimations.

        Le bloc est lu et compté dans tous les cas : refuser un bloc n'autorise
        JAMAIS à cesser de lire le tube, qui déborderait en 2 s.
        """
        n = rms(data)
        self.bloc += 1

        if self.n_calib < CALIB_BLOCS:
            # On n'a pas encore de plancher : tout passe, et on retient le moins
            # fort de ces huit blocs comme point de départ.
            self.n_calib += 1
            n = max(n, PLANCHER_BRUIT)   # sinon le silence numérique cloue le plancher à 0
            self.bruit = n if self.bruit is None else min(self.bruit, n)
            ouvre = True
        elif robot_parle:
            pret = self.n_echo >= ECHO_BLOCS_MIN
            ouvre = pret and n > self.echo * self.facteur
            if ouvre:
                self.n_ouverts += 1
                # Se taire est la seule action qui doit être instantanée. La
                # faire décider par le modèle coûterait un tick plus un
                # aller-retour réseau, soit plus d'une seconde et demie.
                if self.n_ouverts >= BARGE_IN_BLOCS:
                    self.barge_in = True
                if self.n_ouverts >= RECALIBRE_BLOCS:
                    self._recalibrer(n)     # ce n'était pas une voix, c'est l'écho
                    ouvre = False           # qui a changé : on repart de sa mesure
            else:
                self.n_ouverts = 0
            if not ouvre:
                # Seuls les blocs qu'on n'a PAS pris pour de la voix nourrissent
                # l'estimation : sinon un barge-in réussi ferait monter le seuil
                # et refermerait la porte juste derrière lui.
                self.echo = max(n, self.echo * DECROISSANCE)
                if n > self.bruit * FACTEUR_BRUIT:
                    self.n_echo += 1   # piper met ~1 s à sortir son premier son :
                                       # on compte les blocs SONORES, pas le temps
                                       # écoulé, sinon on calibrerait sur du vide.
        else:
            self.n_ouverts = 0
            # Désarmer ICI, et pas seulement quand la boucle constate la coupure :
            # sinon le drapeau survit à la fin d'une réponse et tue la SUIVANTE
            # dès sa première milliseconde, sans qu'aucune trace n'en dise la
            # raison.
            self.barge_in = False
            self._suivre_bruit(n)
            ouvre = n > self.bruit * FACTEUR_BRUIT

        if ouvre:
            self.jusqua = self.bloc + QUEUE_BLOCS
        passe = ouvre or self.bloc <= self.jusqua
        self._tracer(n, passe, robot_parle)
        return passe

    def _recalibrer(self, n):
        """Repart de zéro sur l'écho : porte fermée le temps de remesurer.

        Le prix est d'environ une seconde d'écho transmis avant qu'on s'en
        aperçoive — mais l'alternative, garder une estimation figée trop basse,
        c'est le robot qui se répond à lui-même pour le reste de la session."""
        self.echo = n
        self.n_echo = 0
        self.n_ouverts = 0
        if self.trace is not None:
            self.trace.ev("recalibrage", echo=round(n, 1))

    def _suivre_bruit(self, n):
        """Descente rapide, montée lente, et RIEN au-dessus du seuil.

        Suivre aussi les blocs de parole faisait dériver le plancher de 9 à 32
        sur samples/01-normal.wav (20 s de parole quasi continue) : le seuil
        montait avec la voix et finissait par couper les fins de phrase. On ne
        met donc à jour que sur ce qu'on tient pour du fond. Si le fond réel
        passe un jour au-dessus du seuil (une hotte qui démarre), l'estimation
        se fige et tout passe : on retombe sur le comportement d'avant la porte,
        ce qui est la bonne façon d'échouer."""
        if n < self.bruit:
            self.bruit += 0.25 * (n - self.bruit)
        elif n <= self.bruit * FACTEUR_BRUIT:
            self.bruit += 0.05 * (n - self.bruit)

    def _tracer(self, n, passe, robot_parle):
        if self.trace is None:
            return
        if robot_parle and passe != self.ouverte:
            self.trace.ev("porte", ouverte=passe, rms=round(n, 1),
                          echo=round(self.echo, 1),
                          seuil=round(self.echo * self.facteur, 1))
        self.ouverte = passe if robot_parle else True
        self.f_n += 1
        self.f_somme += n
        self.f_pic = max(self.f_pic, n)
        self.f_transmis += passe
        self.f_jetes += not passe
        if self.f_n >= PERIODE_NIVEAUX:
            self.trace.ev("niveaux", rms_moy=round(self.f_somme / self.f_n, 1),
                          rms_pic=round(self.f_pic, 1),
                          bruit=round(self.bruit or 0, 1), echo=round(self.echo, 1),
                          transmis=self.f_transmis, jetes=self.f_jetes,
                          robot=bool(robot_parle))
            self._raz_fenetre()


class Capteur:
    """Le seul objet qui lit le tube audio : copie de trace, puis porte.

    Les deux moteurs STT passent par lui pour que la trace, la porte et le
    « ne jamais cesser de lire » soient écrits une fois, pas deux.
    """

    def __init__(self, stream, porte=None, trace=None, robot_parle=None):
        self.stream = stream
        self.porte = porte
        self.trace = trace
        self.robot_parle = robot_parle or (lambda: False)

    def lire(self):
        """Rend le prochain bloc PCM, b'' si la porte l'a jeté, None à la fin."""
        data = self.stream.stdout.read(CHUNK)
        if not data:
            return None
        if self.trace is not None:
            self.trace.pcm(data)         # avant la porte : entree.wav doit être
        if self.porte is None:           # le flux réel, pour pouvoir le rejouer
            return data                  # et rerégler le facteur après coup
        return data if self.porte.juge(data, self.robot_parle()) else b""
