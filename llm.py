#!/usr/bin/env python3
"""Étage décision de microturn — le LLM tient lieu de détecteur de tour de parole.

Toutes les `TICK_S` secondes, on lui envoie ce qui vient d'être transcrit, ou le
marqueur SILENCE si rien n'a été dit. Il répond par l'état qu'il perçoit chez la
personne — elle parle, elle a fini, elle réfléchit, elle me coupe — et seulement
dans le deuxième cas par une phrase à prononcer.

L'idée vient de DuplexCascade (arXiv 2603.09180) : plutôt qu'un détecteur de
parole qui tranche sur un seuil de silence, c'est le modèle qui juge, à partir du
texte. Eux l'obtiennent par fine-tuning, nous par prompting — d'où le format
imposé et les exemples déséquilibrés de FEWSHOT.

Deux choix de mise en œuvre qui comptent :
  - la connexion HTTPS reste ouverte : sur un Cortex-A53, rouvrir TLS coûterait
    150 à 250 ms par décision, à comparer aux ~400 ms de l'appel lui-même ;
  - une erreur est renvoyée telle quelle, jamais confondue avec « attends » :
    l'appelant doit pouvoir réessayer au lieu de perdre l'énoncé.
"""
import http.client, json, os, threading, time

# Mesuré sur 12 cas, les deux classes séparées : les Llama 3.2 (1b comme 3b) ne
# disent JAMAIS « elle a fini » — 0 question détectée sur 5, quel que soit le
# prompt. Ils tiennent parfaitement les silences (7/7) et c'est tout : un modèle
# qui répond toujours « elle parle encore » obtient un bon score global sur une
# conversation réelle, où neuf ticks sur dix sont effectivement des silences.
# C'est pourquoi il faut mesurer les deux classes séparément.
#   gemini-2.5-flash-lite  9/12, questions 4/5, 0,52 s  <- retenu
#   gpt-4o-mini           10/12, questions 4/5, 0,87 s  (trop lent pour le tick)
#   nova-micro-v1          7/12, questions 1/5, 0,48 s
#   llama-3.2-3b / 1b      7/12, questions 0/5
MODEL = os.environ.get("MICROTURN_MODEL", "google/gemini-2.5-flash-lite")
HOST, PATH = "openrouter.ai", "/api/v1/chat/completions"
TIMEOUT = float(os.environ.get("MICROTURN_TIMEOUT", "1.5"))   # au-delà, la décision est périmée

# Les jetons décrivent l'ÉTAT DE LA PERSONNE, pas l'action à faire. C'est le
# choix de DuplexCascade et il est meilleur qu'il n'en a l'air : on demande au
# modèle une perception (« où en est-elle ? »), pas une décision de politique
# (« dois-je parler ? »). Un modèle générique s'en sort beaucoup mieux, et ça
# sépare deux cas que notre ancien <WAIT> confondait — elle parle encore, contre
# elle ne dit rien après ma réponse.
# Le système et les labels sont en ANGLAIS, la réponse reste en français.
# Ce n'est pas une coquetterie : des labels français font s'effondrer les petits
# Llama sur une seule classe (Enomoto et al., NAACL 2025 — 89,7 → 33,7 de F1 en
# français), et on l'a reproduit ici : 2 bonnes décisions sur 21 avec le prompt
# français sur le 1B, contre 16 avec celui-ci. `PARLE` était le pire mot possible,
# un impératif adressé au modèle pour le label censé le faire taire.
# La langue de sortie, elle, est ancrée par l'entrée française et les exemples —
# le few-shot est la meilleure parade connue à la dérive linguistique
# (Marchisio et al., EMNLP 2024). Mesuré : 0 réponse en anglais sur 21.
SYSTEM = """You are listening to someone speaking French. Every 1.2 seconds you \
receive the words transcribed since the last check, or (silence) if she said nothing.

Your first word is always one of these four:

SPEAKING      her turn is still going: she is talking, or pausing mid-sentence to \
breathe or find a word
DONE          her turn is over and she is waiting for an answer
THINKING      she is silent because you have just answered her
INTERRUPTING  she starts talking while you are still talking

After DONE, and only after DONE, continue on the same line with what to say out \
loud, in French, one short spoken sentence. DONE always carries an answer.

DONE is for a complete question or request — something she is clearly waiting for an \
answer to. SPEAKING is for everything that could still continue: a fragment, a \
subject with no verb, a sentence cut mid-way.

Most checks fall in the middle of her turn, so SPEAKING is the common answer. People \
breathe, hesitate and hunt for their words; several (silence) in a row are still one \
single turn. But when she has clearly finished asking something, say DONE and answer \
her — leaving a real question unanswered is just as wrong as cutting her off.

The text comes from an error-prone speech recognizer and is often wrong. You do not \
need to understand the words to do your job. When they make no sense, that is a \
recognition error: answer SPEAKING.

If the fragment could continue, SPEAKING. If she has finished asking, DONE."""

# Quatre exemples, et ils portent le FORMAT à eux seuls : sans eux, 14 sorties sur
# 21 sont invalides et le modèle repart en assistant serviable. Ils ne servent pas
# à installer le ratio — ça, c'est la phrase « nine times out of ten », qui coûte
# 12 jetons au lieu de 200.
# L'exemple DONE porte une VRAIE réponse : quand tous les exemples s'arrêtent après
# le label, le modèle apprend à s'arrêter après le label. C'était la cause des 15
# « FINI » nus sur 16 observés dans les traces.
# Le troisième est du bruit whisper réel : le prompt parlait de transcription
# fausse sans jamais en montrer une.
FEWSHOT = [
    ("[I have not spoken] est-ce que tu peux", "SPEAKING"),
    ("[I have not spoken] (silence)", "SPEAKING"),
    ("[I have not spoken] un an et plus en t'es non assez fan ce fil", "SPEAKING"),
    ("[I have not spoken] allumer la lumière du salon", "DONE C'est allumé."),
    ("[I just answered] (silence)", "THINKING"),
    ("[I have not spoken] quelle heure il est", "DONE Il est bientôt minuit."),
]


def _key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    raise SystemExit("pas de clé OpenRouter : mets OPENROUTER_API_KEY dans .env")


KEY = _key()                     # lue une fois, pas à chaque décision


class Decideur:
    """Une connexion HTTPS réutilisée, protégée par un verrou (un appel à la fois)."""

    def __init__(self, model=MODEL, timeout=TIMEOUT, trace=None):
        self.model, self.timeout = model, timeout
        self.trace = trace
        self.conn = None
        self.lock = threading.Lock()

    def _post(self, body):
        for essai in (1, 2):                 # une reconnexion si le serveur a fermé
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(HOST, timeout=self.timeout)
                self.conn.request("POST", PATH, body, {
                    "Authorization": f"Bearer {KEY}",
                    "Content-Type": "application/json",
                    "Connection": "keep-alive"})
                return json.loads(self.conn.getresponse().read())
            except Exception:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None
                if essai == 2:
                    raise
        return {}

    def decide(self, transcript, history=None):
        """Rend (action, texte, latence).

        action ∈ {parle, parler, reflechit, coupe, error}.

        Une erreur est renvoyée telle quelle, JAMAIS confondue avec 'parle' :
        l'appelant doit pouvoir réessayer au lieu de perdre l'énoncé."""
        # Plus de porte locale : elle supprimait des appels, donc des occasions de
        # décider, et elle tranchait le tour de parole AVANT le modèle — le VAD
        # déguisé qu'on cherche justement à supprimer. Le modèle est désormais
        # consulté à chaque tick, y compris sur du silence.
        msgs = [{"role": "system", "content": SYSTEM}]
        for u, a in FEWSHOT:
            msgs += [{"role": "user", "content": u},
                     {"role": "assistant", "content": a}]
        msgs += (history or [])
        msgs.append({"role": "user", "content": transcript})
        body = json.dumps({"model": self.model, "messages": msgs,
                           "max_tokens": 40, "temperature": 0, "stop": ["\n"]})
        # Le prompt exact part dans la trace, système et historique compris :
        # c'est la seule façon de comprendre APRÈS COUP pourquoi le modèle a mal
        # tranché. La clé, elle, ne voyage que dans les en-têtes (`_post`) et
        # n'est donc jamais écrite.
        self._tracer("llm_appel", modele=self.model, messages=msgs,
                     max_tokens=40, temperature=0)
        t0 = time.time()
        try:
            with self.lock:
                out = self._post(body)
        except Exception as e:
            dt = time.time() - t0
            err = f"{type(e).__name__}: {e}"[:90]
            self._tracer("llm_reponse", brut=None, erreur=err, latence=round(dt, 3))
            self._tracer("decision", action="error", texte=err, source="reseau",
                         transcript=transcript, latence=round(dt, 3))
            return "error", err, dt
        dt = time.time() - t0
        try:
            txt = (out["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            err = str(out.get("error", out))[:90]
            self._tracer("llm_reponse", brut=None, corps=out, erreur=err,
                         latence=round(dt, 3))
            self._tracer("decision", action="error", texte=err, source="reseau",
                         transcript=transcript, latence=round(dt, 3))
            return "error", err, dt
        # `brut` est le texte du modèle AVANT `_lire_controle` : on veut pouvoir
        # relire ce qu'il a réellement écrit, pas ce qu'on en a compris.
        self._tracer("llm_reponse", brut=txt, corps=out, latence=round(dt, 3))
        action, texte = _lire_controle(txt)
        self._tracer("decision", action=action, texte=texte, source="reseau",
                     transcript=transcript, latence=round(dt, 3))
        return action, texte, dt

    def _tracer(self, type, **champs):
        if self.trace is not None:
            self.trace.ev(type, **champs)


def _lire_controle(txt):
    """Rend (action, texte). Le premier mot est l'état perçu, le reste la réponse.

    Trois cas étaient auparavant confondus dans un même « elle parle encore » :
    un vrai SPEAKING, un DONE sans réponse, et une sortie hors format. Les deux
    derniers sont des pannes — les taire rendait le système muet ET faussait le
    ratio, les deux en silence."""
    t = (txt or "").strip().strip("`*\"'")
    if not t:
        return "format", ""
    parts = t.split(None, 1)        # blancs et non " " : un \n avalait la réponse
    etat = parts[0].strip(":.,!?<>[]()").upper()
    reste = parts[1].strip() if len(parts) > 1 else ""
    if etat.startswith("DONE") or etat.startswith("FINI"):
        # Un DONE nu n'est PAS « elle parle encore » : c'est une décision de
        # parler dont la réponse manque.
        return ("parler", reste) if reste else ("parler_sans_texte", "")
    if etat.startswith("SPEAK") or etat.startswith("PARLE"):
        return "parle", ""
    if etat.startswith("THINK") or etat.startswith("REFLECH"):
        return "reflechit", ""
    if etat.startswith("INTERRUPT") or etat.startswith("COUPE"):
        return "coupe", ""
    return "format", t              # tracé comme tel, jamais noyé dans « parle »



if __name__ == "__main__":
    import sys
    cas = sys.argv[1:] or [
        "bonjour",
        "bonjour est-ce que tu peux",
        "bonjour est-ce que tu peux allumer la lumière du salon",
        "il est vingt-trois heures et je voudrais écouter de la musique douce",
        "quelle heure il est",
    ]
    d = Decideur()
    for t in cas:
        a, txt, dt = d.decide(t)
        marque = "gratuit" if dt == 0 else f"{dt:5.2f}s"
        print(f"{marque}  {a:6s}  « {t[:50]} » -> {txt}")
