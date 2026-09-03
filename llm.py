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
# Surchargeable pour que PLUSIEURS mesures tournent en même temps : chacune se
# donne une copie du catalogue, la patche, et ne dérange personne. Sans ça, deux
# mesures concurrentes se disputent `locales/fr.toml` et l'une des deux évalue
# un prompt qu'elle n'a pas écrit.
LOCALES = os.environ.get("MICROTURN_LOCALES") or os.path.join(ICI, "locales")
# Banc « détection seule » : retirer "r" du SCHÉMA, et pas seulement du prompt.
# Sans ça la consigne « ne rends que le marqueur » reste facultative — mesuré le
# 02/09/2026 : le modèle a quand même produit une réponse dans 23 décisions sur
# 39, et la variante ne mesurait donc pas ce qu'elle prétendait mesurer.
SANS_R = bool(os.environ.get("MICROTURN_SANS_R"))

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
# La longueur de la réponse est suggérée par le SCHÉMA, plus par `max_tokens`.
#
# `max_tokens` était à 60 et il coupait pour de vrai : la troncature casse le
# JSON, donc c'est la DÉCISION entière qui est perdue, pas seulement la fin de
# la phrase. Onze fois sur 897 chez gemini, et en session le 03/09 sur une
# réponse de 250 caractères. Il compte tout, en plus — accolades, noms de
# champs, marqueur : `<|user finish talking|>` en mange une douzaine à lui
# seul. Il est retiré, il n'y en a plus du tout.
#
# `maxLength` a été essayé le 03/09 puis retiré. Il n'est PAS respecté à la
# lettre — à limite de 200 la réponse fait 4 231 caractères — mais il influence
# fortement (aucun → 7 995 car, 200 → 4 231, 80 → 1 515), et sans jamais casser
# le JSON. C'est donc un levier utilisable, gardé ici comme information : on ne
# limite plus rien du tout.
#
# Les chercheurs ne limitent rien : chez eux la longueur est apprise des
# données. L'autre levier mesuré est le PROMPT — la consigne « courte » tenait
# les réponses à 57 caractères contre 77 sans elle.
#
# Le garde-fou contre une génération qui s'emballe reste `TIMEOUT`, qui limite
# le TEMPS. C'est la bonne grandeur dans une boucle à 1,2 s, et il ne casse
# rien : un appel coupé est une erreur franche, pas un JSON tronqué.



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
                           ("divers", ("silence", "silence_repete", "bruit_sans_texte", "tour_en_cours",
                                       "whisper", "espeak"))):
        manque = [c for c in clefs if c not in cat.get(section, {})]
        if manque:
            raise SystemExit(f"{chemin} : [{section}] — clé(s) manquante(s) : "
                             f"{', '.join(manque)}")
    # `systeme` est le prompt par défaut ; `systeme_<moteur>` le remplace quand ce
    # moteur tourne. Tous les prompts vivent dans le catalogue, aucun n'est
    # assemblé par le code : une phrase vraie pour un moteur est fausse pour un
    # autre (mesuré : +0,063 avec sherpa, −0,103 avec whisper), et c'est une
    # donnée, pas une règle métier.
    for clef in [c for c in cat if c == "systeme" or c.startswith("systeme_")]:
        if not cat.get(clef, "").strip():
            raise SystemExit(f"{chemin} : `{clef}` vide")
        if "{exemples}" not in cat[clef]:
            raise SystemExit(f"{chemin} : `{clef}` doit contenir {{exemples}} — les "
                             f"exemples vivent dans le prompt, sans ancre ils "
                             f"disparaîtraient sans un mot")
        cat[clef] = cat[clef].strip()
    if not cat.get("systeme", "").strip():
        raise SystemExit(f"{chemin} : `systeme` vide ou absent")
    # `silence_repete` peut valoir le même marqueur que `silence` : c'est le
    # design de DuplexCascade, qui n'a qu'un seul <|no voice|> et ne compte pas
    # les silences. La contrainte sur {n} ne vaut donc que si les deux diffèrent.
    rep = cat["divers"]["silence_repete"]
    if rep != cat["divers"]["silence"] and "{n}" not in rep:
        raise SystemExit(f"{chemin} : `silence_repete` doit contenir {{n}} ou "
                         f"valoir `silence`, sinon le compte est perdu en route")
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


def rendre_exemples(langue="fr"):
    """Les exemples en texte, tels qu'ils apparaissent DANS le message système."""
    return "\n".join(f"  utilisateur: {u}\n  assistant: {a}"
                     for u, a in catalogue(langue)["exemples"])


def systeme(langue="fr", tick=1.2, moteur=None):
    """Le prompt de la langue, avec la vraie période d'horloge — l'écrire en dur
    ferait mentir le prompt dès qu'on la change pour une expérience.

    Les exemples sont DANS ce texte, pas envoyés comme messages : en messages
    alternés, le modèle les voit au même niveau que la vraie conversation et
    croit qu'elle a commencé par eux. Observé — il relançait « Salut ! Comment
    puis-je t'aider ? » en plein milieu d'une session déjà entamée."""
    virgule = "," if langue == "fr" else "."
    # .replace et non .format : `.format` interprète TOUTES les accolades, donc
    # un « { » littéral dans le catalogue (un exemple JSON, une notation {mot})
    # faisait planter au démarrage sur un KeyError nu. La présence de {tick} est
    # déjà garantie par la validation du catalogue.
    cat = catalogue(langue)
    # `systeme_sherpa` s'il existe, `systeme` sinon. Le choix est une lecture de
    # clé, pas une construction : le catalogue reste la seule source du prompt.
    brut = cat.get(f"systeme_{moteur}") or cat["systeme"]
    return (brut
            .replace("{tick}", str(tick).replace(".", virgule))
            .replace("{exemples}", rendre_exemples(langue)))


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
    # Sortie contrainte : {"m": "<jeton>", "r": "réponse"}. On la reconnaît
    # avant tout le reste ; le parsing texte demeure pour les cas où la
    # contrainte n'a pas pu s'appliquer (modèle sans schéma, rejeu d'anciennes
    # traces), et il ne doit jamais devenir le chemin normal.
    if t.startswith("{"):
        try:
            d = json.loads(t)
        except ValueError:
            d = None
        if isinstance(d, dict) and d.get("m"):
            j = catalogue(langue)["jetons"]
            reponse = (d.get("r") or "").strip()
            for cle in ("parler", "reflechit", "coupe", "parle"):
                if d["m"] == j.get(cle):
                    if cle == "parler":
                        return ("parler", reponse) if reponse else ("parler_sans_texte", "")
                    return cle, ""
            # Les DEUX backchannel sont dans l'enum du schéma, donc le modèle a
            # le droit de les choisir — et il le fait. Ne pas les mapper les
            # faisait tomber en « hors format » et JETAIT la décision, alors que
            # le catalogue promet qu'ils sont « ramenés à ne prends pas la
            # parole ». Vu en session le 03/09 :
            #   ⚠ malformed: {"m": "<|user backchannel|>", "r": "Hello!"}
            # Un signal d'écoute n'est pas une prise de parole : c'est bien
            # « attends », soit exactement `reflechit`.
            if d["m"] in (j.get("backchannel"), j.get("mhm")):
                return "reflechit", ""
            return "format", t
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
        if any(mot.startswith(j[k]) for k in ("backchannel", "mhm") if j.get(k)):
            return "reflechit", ""
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

class Simule:
    """Décideur factice, déterministe, hors ligne. Aucun appel réseau.

    Sert à deux choses que le vrai modèle ne permet pas :

    - **Isoler le bruit de mesure.** Sur le banc, l'écart entre deux passes
      identiques mêle le non-déterminisme du modèle distant, la latence réseau
      et le cadencement temps réel. Avec ce décideur, la part du modèle tombe à
      zéro : ce qui reste est le bruit de la mécanique. On sait alors ce qu'une
      amélioration doit dépasser pour être réelle.
    - **Tester la mécanique gratuitement.** Le rendu, l'horloge audio, la
      troncature au barge-in, l'assemblage du WAV : rien de tout cela n'a besoin
      d'un modèle intelligent, et il serait absurde de payer des milliers
      d'appels pour vérifier qu'un fichier fait la bonne longueur.

    Ses règles sont volontairement bêtes et explicites — c'est un étalon, pas un
    concurrent. Il ne doit JAMAIS servir à juger la qualité du tour de parole.
    """

    def __init__(self, model="simule", timeout=None, trace=None, langue="fr",
                 tick=1.2):
        self.model, self.trace, self.langue = model, trace, langue
        cat = catalogue(langue)
        self.jetons = cat["jetons"]
        self.silence = cat["divers"]["silence"]
        self.bruit = cat["divers"]["bruit_sans_texte"]
        self.etats = cat["etats"]

    def decide(self, transcript, history=None):
        t0 = time.time()
        nu = transcript
        for marqueur in self.etats.values():
            if nu.startswith(marqueur):
                nu = nu[len(marqueur):].strip()
                break
        if not nu or nu.startswith("(") :
            action, texte = "parle", ""
        elif nu.rstrip().endswith(("?", ".", "!")):
            action, texte = "parler", "D'accord."
        else:
            action, texte = "parle", ""
        dt = time.time() - t0
        if self.trace is not None:
            self.trace.ev("decision", action=action, texte=texte,
                          source="simule", transcript=transcript,
                          latence=round(dt, 4))
        return action, texte, dt


class Decideur:
    """Une connexion HTTPS réutilisée, protégée par un verrou (un appel à la fois)."""

    def __init__(self, model=MODEL, timeout=TIMEOUT, trace=None, langue="fr",
                 tick=1.2, moteur=None):
        self.model, self.timeout, self.trace = model, timeout, trace
        self.langue = langue
        self.systeme = systeme(langue, tick, moteur)
        self.exemples = catalogue(langue)["exemples"]
        self.jetons = catalogue(langue)["jetons"]
        self.conn = None
        self.lock = threading.Lock()
        self.niveau = 0                 # index dans NIVEAUX : contrainte courante
        self.non_conformes = 0          # ce que le garde-fou a refusé

    # Du plus contraint au moins contraint. Tous les modèles n'acceptent pas le
    # schéma strict : `gpt-4o-mini` répond 400, et on perdrait alors 100 % des
    # décisions. On descend d'un cran à chaque refus et on retient ce qui passe.
    NIVEAUX = ("schema_strict", "schema_souple", "json_libre", "aucune")

    def contrainte(self, jetons):
        """Le `response_format` du niveau courant, ou None."""
        n = self.NIVEAUX[self.niveau]
        if n == "aucune":
            return None
        if n == "json_libre":
            return {"type": "json_object"}
        return {"type": "json_schema", "json_schema": {
            "name": "tour", "strict": n == "schema_strict", "schema": {
                "type": "object",
                "properties": {"m": {"type": "string", "enum": jetons},
                               "r": {"type": "string"}},
                "required": ["m"], "additionalProperties": False}}}

    def _degrade(self, raison):
        """Descend d'un cran, une seule fois par niveau."""
        if self.niveau + 1 >= len(self.NIVEAUX):
            return False
        avant = self.NIVEAUX[self.niveau]
        self.niveau += 1
        self._tracer("contrainte_degradee", de=avant,
                     vers=self.NIVEAUX[self.niveau], raison=str(raison)[:120])
        return True

    def conforme(self, brut):
        """Le garde-fou. Sous le schéma strict il ne peut rien refuser ; dès
        qu'on dégrade, c'est la seule chose qui sépare une vraie décision d'un
        texte libre qui y ressemble.

        Rend (ok, motif). Le motif part dans la trace ET dans le résumé de
        session : une dérive de format doit se voir dans la mesure, pas se
        cacher dans le score."""
        jetons = set(dict.fromkeys(self.jetons.values()))
        try:
            o = json.loads(brut)
        except (ValueError, TypeError):
            return False, "pas du JSON"
        if not isinstance(o, dict):
            return False, "pas un objet"
        if o.get("m") not in jetons:
            return False, f"marqueur inconnu : {str(o.get('m'))[:40]}"
        if "r" in o and not isinstance(o["r"], str):
            return False, "champ r non textuel"
        return True, ""

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
        # Les exemples sont dans le système (cf. `systeme()`), pas ici : ce qui
        # suit est la conversation RÉELLE, et rien d'autre.
        msgs = [{"role": "system", "content": self.systeme}]
        msgs += (history or [])
        msgs.append({"role": "user", "content": transcript})
        # `stop` interdit structurellement une sortie multi-lignes ; `temperature`
        # à 0 parce qu'à 0,3 dix décisions sur vingt-et-une changeaient d'une
        # passe à l'autre, ce qui rendait tout rejeu incomparable.
        # Le format n'est plus ESPÉRÉ, il est IMPOSÉ au décodage. Un enum sur
        # les jetons du catalogue : le modèle ne peut structurellement pas en
        # inventer un, ni sortir du format. C'est notre équivalent de ce que
        # leur fine-tuning garantit — eux apprennent le format, nous le
        # contraignons.
        # Mesuré cette nuit : 122 décisions sur 122 perdues parce que le
        # parseur découpait sur le premier mot, alors que le modèle répondait
        # parfaitement. Coût : environ dix tokens de sortie en plus, soit 0,2 s.
        jetons = list(dict.fromkeys(self.jetons.values()))
        props = {"m": {"type": "string", "enum": jetons}}
        if not SANS_R:
            props["r"] = {"type": "string"}
        # Aucune limite de longueur, ni ici ni dans le schéma : cf. en tête.
        corps = {"model": self.model, "messages": msgs, "temperature": 0,
                 "response_format": {"type": "json_schema", "json_schema": {
                     "name": "tour", "strict": True, "schema": {
                         "type": "object", "properties": props,
                         "required": ["m"], "additionalProperties": False}}}}
        # Le prompt exact part dans la trace, système et historique compris : c'est
        # la seule façon de comprendre APRÈS COUP pourquoi le modèle a mal tranché.
        # La clé, elle, ne voyage que dans les en-têtes et n'est jamais écrite.
        self._tracer("llm_appel", modele=self.model, langue=self.langue,
                     messages=msgs, temperature=0,
                     contraint=True)
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
            # Un modèle qui refuse la contrainte répond 400 : on descend d'un
            # cran plutôt que de perdre 100 % des décisions. Mesuré sur
            # `gpt-4o-mini`, qui rejette le schéma strict.
            msg = str(out.get("error", out))
            if ("400" in msg or "schema" in msg.lower()
                    or "response_format" in msg.lower()) and self._degrade(msg):
                return "error", "contrainte dégradée, on réessaie", dt
            return "error", msg[:90], dt
        # Le cache de prompt est IMPLICITE sur gemini-2.5 (automatique au-delà
        # de 1024 tokens, lecture facturée 0,25x). Notre préfixe — système et
        # exemples — est constant et représente l'essentiel de l'entrée, donc il
        # devrait être servi depuis le cache. « Devrait » ne suffit pas : on
        # trace ce que l'API dit vraiment, et le résumé de session en donne le
        # taux. Sans ça, « le cache est activé » resterait une croyance.
        u = out.get("usage") or {}
        detail = u.get("prompt_tokens_details") or {}
        # `finish_reason` dit POURQUOI la génération s'est arrêtée. Le schéma
        # contraint garantit la grammaire de chaque jeton, pas que la génération
        # aille au bout : si le serveur l'interrompt, on reçoit un préfixe de
        # JSON valide en cours de route. Mesuré le 03/09 en session — trois
        # réponses sur quarante-cinq coupées à `{"m": "<|user`, avec un `usage`
        # à zéro des deux côtés. Sans ce champ, on ne pouvait qu'émettre des
        # hypothèses.
        fin = (out["choices"][0].get("finish_reason")
               or out["choices"][0].get("native_finish_reason"))
        self._tracer("llm_reponse", brut=brut, latence=round(dt, 3),
                     fin=fin,
                     tokens_entree=u.get("prompt_tokens"),
                     tokens_caches=detail.get("cached_tokens"),
                     tokens_sortie=u.get("completion_tokens"))
        # Le garde-fou : sous le schéma strict il ne peut rien refuser, mais dès
        # qu'on dégrade, c'est la seule chose qui distingue une vraie décision
        # d'un texte libre qui y ressemble.
        ok, motif = self.conforme(brut)
        if not ok:
            self.non_conformes += 1
            self._tracer("format_invalide", motif=motif, brut=brut[:120],
                         niveau=self.NIVEAUX[self.niveau],
                         total=self.non_conformes)
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
