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

MODEL = os.environ.get("MICROTURN_MODEL", "meta-llama/llama-3.2-3b-instruct")
HOST, PATH = "openrouter.ai", "/api/v1/chat/completions"
TIMEOUT = float(os.environ.get("MICROTURN_TIMEOUT", "1.5"))   # au-delà, la décision est périmée

# Les jetons décrivent l'ÉTAT DE LA PERSONNE, pas l'action à faire. C'est le
# choix de DuplexCascade et il est meilleur qu'il n'en a l'air : on demande au
# modèle une perception (« où en est-elle ? »), pas une décision de politique
# (« dois-je parler ? »). Un modèle générique s'en sort beaucoup mieux, et ça
# sépare deux cas que notre ancien <WAIT> confondait — elle parle encore, contre
# elle ne dit rien après ma réponse.
SYSTEM = """Tu écoutes quelqu'un parler. Toutes les 1,2 seconde, tu reçois ce qui vient d'être transcrit — parfois quelques mots, parfois SILENCE si la personne n'a rien dit.

Ton premier mot est TOUJOURS un de ces quatre états :

PARLE      elle est en train de parler, ou elle marque une pause au milieu de sa phrase
FINI       elle a fini de parler et attend une réponse
REFLECHIT  elle ne dit rien, mais je viens de lui répondre : elle réfléchit
COUPE      elle se remet à parler alors que je suis en train de parler

Après FINI seulement, ajoute ta réponse sur la même ligne : UNE phrase courte et orale.
Après PARLE, REFLECHIT ou COUPE, n'écris rien d'autre.

Ce qui compte le plus : une pause n'est pas une fin de phrase. Les gens respirent, hésitent, cherchent leurs mots. Tant que la phrase n'est pas terminée, c'est PARLE — même après plusieurs SILENCE d'affilée.

La transcription est automatique et souvent fausse. Si c'est incompréhensible, c'est PARLE : ne devine pas, ne demande pas ce qu'un mot bizarre veut dire, c'est une erreur de transcription."""

# Le ratio est la clé. Dans une vraie conversation, « elle parle encore » est émis
# une dizaine de fois pour une seule prise de parole — c'est structurel. Un modèle
# instruction-tuné n'a aucun prior là-dessus : il VEUT répondre. Ces exemples
# reproduisent ce déséquilibre, faute de pouvoir l'entraîner.
FEWSHOT = [
    ("est-ce que tu peux", "PARLE"),
    ("SILENCE", "PARLE"),
    ("est-ce que tu peux allumer", "PARLE"),
    ("la lumière du salon", "FINI c'est fait"),
    ("SILENCE", "REFLECHIT"),
    ("SILENCE", "REFLECHIT"),
    ("alors je voudrais", "PARLE"),
    ("SILENCE", "PARLE"),
    ("SILENCE", "PARLE"),
    ("te demander un truc", "PARLE"),
    ("SILENCE", "PARLE"),
    ("c'est quoi la capitale du Japon", "FINI Tokyo"),
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
                           "max_tokens": 40, "temperature": 0.3})
        # Le prompt exact part dans la trace, système et historique compris :
        # c'est la seule façon de comprendre APRÈS COUP pourquoi le modèle a mal
        # tranché. La clé, elle, ne voyage que dans les en-têtes (`_post`) et
        # n'est donc jamais écrite.
        self._tracer("llm_appel", modele=self.model, messages=msgs,
                     max_tokens=40, temperature=0.3)
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

    Le modèle s'engage sur l'état AVANT de rédiger : ça permet d'arrêter là quand
    il ne doit pas parler, et surtout ça l'empêche de se convaincre de répondre en
    générant d'abord du texte."""
    t = (txt or "").strip().strip("`*\"'")
    if not t:
        return "parle", ""
    premier, _, reste = t.partition(" ")
    etat = premier.strip(":.,!?<>[]()").upper()
    reste = reste.strip()
    if etat.startswith("FINI"):
        return ("parler", reste) if reste else ("parle", "")
    if etat.startswith("REFLECH"):
        return "reflechit", ""
    if etat.startswith("COUPE"):
        return "coupe", ""
    if etat.startswith("PARLE"):
        return "parle", ""
    # Le modèle a répondu sans jeton : il a désobéi au format. On ne prend pas
    # le risque de parler sur une sortie qu'on ne comprend pas.
    return "parle", ""


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
