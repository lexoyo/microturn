#!/usr/bin/env python3
"""Étage décision de microturn — le LLM tient lieu de détecteur de tour de parole.

L'idée vient de DuplexCascade : au lieu d'un VAD qui décide « la personne s'est
tue », c'est le modèle qui tranche à partir du texte qui arrive :

  <WAIT>   la phrase n'est pas finie — on se tait et on continue d'écouter
  <HMM>    un simple signe d'écoute suffit
  autre    la réponse à prononcer

Deux garde-fous avant tout appel réseau, qui coûtent zéro :
  - `porte_locale()` renvoie `wait` sans rien demander quand la transcription se
    termine par un mot-outil ("je voudrais que...") — la phrase est manifestement
    en suspens. C'est un prior sur le texte, pas une mesure de silence.
  - la connexion HTTPS est gardée ouverte : sur un Cortex-A53, rouvrir TLS à
    chaque décision coûterait 150 à 250 ms, à comparer aux ~500 ms de l'appel.
"""
import http.client, json, os, threading, time, urllib.parse

MODEL = os.environ.get("MICROTURN_MODEL", "meta-llama/llama-3.2-3b-instruct")
HOST, PATH = "openrouter.ai", "/api/v1/chat/completions"
TIMEOUT = float(os.environ.get("MICROTURN_TIMEOUT", "1.5"))   # au-delà, la décision est périmée

SYSTEM = """Tu es un compagnon vocal. Tu reçois une transcription EN COURS, qui peut être \
incomplète ou mal transcrite.

Réponds par EXACTEMENT une de ces trois choses :
- `<WAIT>` si la personne n'a manifestement pas fini sa phrase, ou si tu n'as pas assez \
pour répondre utilement.
- `<HMM>` si elle parle depuis un moment et qu'un simple signe d'écoute suffit.
- sinon, ta réponse parlée : UNE phrase courte, orale, sans ponctuation décorative.

Règles importantes :
- La transcription est automatique et souvent FAUSSE. Si elle est incompréhensible, tronquée, ou si tu n'es pas sûr de ce qui a été dit, réponds `<WAIT>`. Ne devine pas, n'invente pas une question sur un mot que tu n'as pas compris.
- Ne demande pas « ça veut dire quoi ? » sur un mot bizarre : c'est presque toujours une erreur de transcription, pas un vrai mot.
- Une phrase qui commence par « alors je vais », « je voudrais », « est-ce que tu peux » sans suite est INACHEVÉE : attends.

N'explique jamais ton choix. Ne répète pas ce qu'on t'a dit."""

# Mots qui appellent une suite : si la transcription s'arrête là, inutile de demander.
_EN_SUSPENS = {
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "que", "qui", "quoi",
    "de", "du", "des", "le", "la", "les", "un", "une", "et", "ou", "mais", "donc",
    "car", "à", "au", "aux", "en", "dans", "sur", "sous", "pour", "par", "avec",
    "sans", "chez", "vers", "est-ce", "c'est", "j'ai", "tu", "me", "te", "se",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "ce", "cet",
    "cette", "très", "plus", "moins", "si", "quand", "comme", "parce",
}


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


def porte_locale(transcript, mots_min=3):
    """Décide sans réseau quand c'est évident. Rend 'wait' ou None."""
    mots = transcript.split()
    if len(mots) < mots_min:
        return "wait"
    if mots[-1].lower().strip(",") in _EN_SUSPENS:
        return "wait"
    return None


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
        """Rend (action, texte, latence). action ∈ {wait, hmm, speak, error}.

        Une erreur est renvoyée telle quelle, JAMAIS confondue avec 'wait' :
        l'appelant doit pouvoir réessayer au lieu de perdre l'énoncé."""
        gratuit = porte_locale(transcript)
        if gratuit:
            self._tracer("decision", action=gratuit, texte="", source="locale",
                         transcript=transcript, latence=0.0)
            return gratuit, "", 0.0
        msgs = [{"role": "system", "content": SYSTEM}] + (history or [])
        msgs.append({"role": "user", "content": transcript})
        body = json.dumps({"model": self.model, "messages": msgs,
                           "max_tokens": 60, "temperature": 0.4})
        # Le prompt exact part dans la trace, système et historique compris :
        # c'est la seule façon de comprendre APRÈS COUP pourquoi le modèle a mal
        # tranché. La clé, elle, ne voyage que dans les en-têtes (`_post`) et
        # n'est donc jamais écrite.
        self._tracer("llm_appel", modele=self.model, messages=msgs,
                     max_tokens=60, temperature=0.4)
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
        except (KeyError, IndexError):
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
    """Reconnaît un token de contrôle, avec ou sans chevrons.

    Les petits modèles renvoient souvent `HMM` nu, ou `<WAIT>` entouré de
    guillemets ou de ponctuation. Les chercher tels quels ferait prononcer
    « hmm » à voix haute — observé en vrai."""
    nu = txt.strip().strip('`"\'*.!? \n').upper()
    if nu in ("WAIT", "<WAIT>", "ATTENDRE") or "<WAIT>" in txt.upper():
        return "wait", ""
    if nu in ("HMM", "<HMM>", "MHM", "MMH") or "<HMM>" in txt.upper():
        return "hmm", ""
    return ("speak", txt) if txt else ("wait", "")


_defaut = None


def decide(transcript, history=None, model=MODEL):
    global _defaut
    if _defaut is None or _defaut.model != model:
        _defaut = Decideur(model)
    return _defaut.decide(transcript, history)


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
