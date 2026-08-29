#!/usr/bin/env python3
"""Étage décision de microturn — le modèle tient lieu de détecteur de tour de parole.

Toutes les `TICK_S` secondes, on lui envoie ce qui vient d'être transcrit, ou le
marqueur de silence si rien n'a été dit. Il répond par l'état qu'il perçoit — ça
parle encore, c'est fini, ça réfléchit, ça me coupe — et seulement dans le
deuxième cas par une phrase à prononcer.

L'idée vient de DuplexCascade (arXiv 2603.09180) : plutôt qu'un détecteur de
parole qui tranche sur un seuil de silence, c'est le modèle qui juge, à partir du
texte. Eux l'obtiennent par fine-tuning, nous par prompting — d'où le format
imposé et les exemples de `locales/`.

Deux choix de mise en œuvre qui comptent :
  - la connexion HTTPS reste ouverte : sur un Cortex-A53, rouvrir TLS coûterait
    150 à 250 ms par décision, à comparer aux ~400 ms de l'appel lui-même ;
  - une erreur est renvoyée telle quelle, jamais confondue avec « ça parle » :
    l'appelant doit pouvoir réessayer au lieu de perdre l'énoncé.
"""
import http.client, json, os, threading, time

ICI = os.path.dirname(os.path.abspath(__file__))
LOCALES = os.path.join(ICI, "locales")

# Mesuré sur 12 cas, les deux classes comptées séparément : les Llama 3.2 (1b
# comme 3b) ne disent JAMAIS « c'est fini » — 0 question détectée sur 5, quel que
# soit le prompt. Ils tiennent les silences (7/7) et c'est tout. Or dans une vraie
# conversation neuf ticks sur dix sont des silences : un modèle qui répond
# toujours « ça parle encore » obtient donc mécaniquement un bon score global.
# C'est pourquoi il faut mesurer les deux classes séparément.
#   gemini-2.5-flash-lite  9/12, questions 4/5, 0,52 s  <- retenu
#   gpt-4o-mini           10/12, questions 4/5, 0,87 s  (trop lent pour le tick)
#   nova-micro-v1          7/12, questions 1/5, 0,48 s
#   llama-3.2-3b et 1b     7/12, questions 0/5
MODEL = os.environ.get("MICROTURN_MODEL", "google/gemini-2.5-flash-lite")
HOST, PATH = "openrouter.ai", "/api/v1/chat/completions"
TIMEOUT = float(os.environ.get("MICROTURN_TIMEOUT", "1.5"))


# ---------------------------------------------------------------- catalogues

def _lire_catalogue(langue):
    """Charge `locales/<langue>.toml`.

    TOML plutôt qu'un format maison : il est dans la bibliothèque standard depuis
    Python 3.11, gère nativement les chaînes multi-lignes, et évite d'écrire un
    parseur — donc de le déboguer. Une nouvelle langue ne demande qu'un fichier,
    relisible sans ouvrir le code.
    """
    import tomllib
    chemin = os.path.join(LOCALES, langue + ".toml")
    try:
        with open(chemin, "rb") as f:
            cat = tomllib.load(f)
    except FileNotFoundError:
        raise SystemExit(f"catalogue absent : {chemin} (langues : {', '.join(langues())})")
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"catalogue illisible, {chemin} : {e}")
    # Un catalogue incomplet doit échouer AU DÉMARRAGE, pas au premier silence
    # d'une conversation : une clé manquante donnerait sinon un KeyError au
    # milieu d'une session, ou pire, un marqueur vide que le prompt ne décrit pas.
    for section, clefs in (("jetons", ("parle", "parler", "reflechit", "coupe")),
                           ("etats", ("parle", "vient", "muet")),
                           ("divers", ("silence", "whisper", "espeak"))):
        manque = [c for c in clefs if c not in cat.get(section, {})]
        if manque:
            raise SystemExit(f"{chemin} : [{section}] — clé(s) manquante(s) : "
                             f"{', '.join(manque)}")
    if not cat.get("systeme", "").strip():
        raise SystemExit(f"{chemin} : `systeme` vide ou absent")
    if "{tick}" not in cat["systeme"]:
        raise SystemExit(f"{chemin} : `systeme` doit contenir {{tick}}, sinon le "
                         f"prompt ment sur la période d'horloge")
    if not cat.get("exemples"):
        raise SystemExit(f"{chemin} : aucun exemple — sans eux la sortie du modèle "
                         f"devient invalide dans les deux tiers des cas")
    cat["exemples"] = [(e["entree"], e["sortie"]) for e in cat["exemples"]]
    cat["systeme"] = cat["systeme"].strip()
    return cat


CATALOGUES = {}


def catalogue(langue="fr"):
    if langue not in CATALOGUES:
        CATALOGUES[langue] = _lire_catalogue(langue)
    return CATALOGUES[langue]


def langues():
    return sorted(f[:-5] for f in os.listdir(LOCALES) if f.endswith(".toml"))


def systeme(langue="fr", tick=1.2):
    """Le prompt de la langue, avec la vraie période d'horloge — l'écrire en dur
    ferait mentir le prompt dès qu'on la change pour une expérience."""
    virgule = "," if langue == "fr" else "."
    return catalogue(langue)["systeme"].format(tick=str(tick).replace(".", virgule))


# ------------------------------------------------------------------ décodage

def lire_controle(txt, langue="fr"):
    """Rend (action, texte). Le premier mot est l'état perçu, le reste la réponse.

    Trois cas étaient autrefois confondus dans un même « ça parle encore » : un
    vrai `parle`, une décision de répondre dont la réponse manque, et une sortie
    hors format. Les deux derniers sont des pannes — les taire rendait le système
    muet ET faussait le ratio, les deux en silence.
    """
    t = (txt or "").strip().strip("`*\"'")
    if not t:
        return "format", ""
    parts = t.split(None, 1)      # blancs, et non " " : un saut de ligne avalait
    mot = parts[0].strip(":.,!?<>[]()").upper()   # la réponse
    reste = parts[1].strip() if len(parts) > 1 else ""
    # On accepte les jetons de TOUTES les langues : le modèle répond parfois dans
    # une autre que celle demandée, et perdre la décision pour ça serait absurde.
    ordre = [langue] + [l for l in CATALOGUES if l != langue]
    for lg in ordre:
        j = catalogue(lg)["jetons"]
        if mot.startswith(j["parler"]):
            return ("parler", reste) if reste else ("parler_sans_texte", "")
        if mot.startswith(j["reflechit"]):
            return "reflechit", ""
        if mot.startswith(j["coupe"]):
            return "coupe", ""
        if mot.startswith(j["parle"]):
            return "parle", ""
    return "format", t            # tracé comme tel, jamais noyé dans « ça parle »


# --------------------------------------------------------------------- clé

def _key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    try:
        with open(os.path.join(ICI, ".env")) as f:
            for ligne in f:
                if ligne.startswith("OPENROUTER_API_KEY="):
                    return ligne.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    raise SystemExit("pas de clé OpenRouter : mets OPENROUTER_API_KEY dans .env")


KEY = _key()          # lue une fois, pas à chaque décision


# ---------------------------------------------------------------- décideur

class Decideur:
    """Une connexion HTTPS réutilisée, protégée par un verrou (un appel à la fois)."""

    def __init__(self, model=MODEL, timeout=TIMEOUT, trace=None, langue="fr",
                 tick=1.2):
        self.model, self.timeout, self.trace = model, timeout, trace
        self.langue = langue
        self.systeme = systeme(langue, tick)
        self.exemples = catalogue(langue)["exemples"]
        self.conn = None
        self.lock = threading.Lock()

    def _tracer(self, type, **champs):
        if self.trace is not None:
            self.trace.ev(type, **champs)

    def _post(self, body):
        for essai in (1, 2):      # une reconnexion si le serveur a fermé
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

    def decide(self, transcript, history=None):
        """Rend (action, texte, latence).

        action ∈ {parle, parler, parler_sans_texte, reflechit, coupe, format, error}.
        Une erreur est renvoyée telle quelle, JAMAIS confondue avec « ça parle » :
        l'appelant doit pouvoir réessayer au lieu de perdre l'énoncé.
        """
        msgs = [{"role": "system", "content": self.systeme}]
        for u, a in self.exemples:
            msgs += [{"role": "user", "content": u},
                     {"role": "assistant", "content": a}]
        msgs += (history or [])
        msgs.append({"role": "user", "content": transcript})
        # `stop` interdit structurellement une sortie multi-lignes ; `temperature`
        # à 0 parce qu'à 0,3 dix décisions sur vingt-et-une changeaient d'une
        # passe à l'autre, ce qui rendait tout rejeu incomparable.
        corps = {"model": self.model, "messages": msgs, "max_tokens": 40,
                 "temperature": 0, "stop": ["\n"]}
        # Le prompt exact part dans la trace, système et historique compris : c'est
        # la seule façon de comprendre APRÈS COUP pourquoi le modèle a mal tranché.
        # La clé, elle, ne voyage que dans les en-têtes et n'est jamais écrite.
        self._tracer("llm_appel", modele=self.model, langue=self.langue,
                     messages=msgs, max_tokens=40, temperature=0)
        t0 = time.time()
        try:
            with self.lock:
                out = self._post(json.dumps(corps))
        except Exception as e:
            dt = time.time() - t0
            self._tracer("llm_reponse", erreur=f"{type(e).__name__}: {e}"[:200],
                         latence=round(dt, 3))
            return "error", f"{type(e).__name__}: {e}"[:90], dt
        dt = time.time() - t0
        try:
            brut = (out["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            self._tracer("llm_reponse", erreur=str(out)[:200], latence=round(dt, 3))
            return "error", str(out.get("error", out))[:90], dt
        self._tracer("llm_reponse", brut=brut, latence=round(dt, 3))
        action, texte = lire_controle(brut, self.langue)
        self._tracer("decision", action=action, texte=texte, source="reseau",
                     transcript=transcript, latence=round(dt, 3))
        return action, texte, dt


if __name__ == "__main__":
    import sys
    lg = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in langues() else "fr"
    e = catalogue(lg)["etats"]
    cas = sys.argv[2:] or [
        f"{e['muet']} bonjour",
        f"{e['muet']} est-ce que tu peux",
        f"{e['muet']} {catalogue(lg)['divers']['silence']}",
        f"{e['muet']} quelle heure il est",
        f"{e['vient']} {catalogue(lg)['divers']['silence']}",
        f"{e['parle']} non attends stop",
    ]
    d = Decideur(langue=lg)
    print(f"[{lg} · {d.model} · jetons {list(catalogue(lg)['jetons'].values())}]")
    for t in cas:
        a, txt, dt = d.decide(t)
        print(f"  {dt:5.2f}s  {a:20s} « {t[:46]} » {txt[:34]}")
