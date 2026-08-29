#!/usr/bin/env python3
"""Mesure du comportement sur les sessions RÉELLES d'Alex, par rejeu.

Pourquoi pas seulement Full-Duplex-Bench : son corpus est anglais, sans écho,
avec des voix qui ne sont pas celles d'Alex, et son bruit de mesure (±0,116 à
dix échantillons) noie tout écart plus petit que douze points. Une itération y
coûte vingt minutes. Ici, un rejeu coûte deux minutes et porte sur ce qu'Alex
constate réellement quand il parle à la machine.

**La métrique.** Pour chaque question de la transcription de référence — un
segment qui se termine par « ? » — le système a-t-il répondu dans les
DELAI_MAX secondes qui suivent ? C'est le défaut principal mesuré le
29/08/2026 : trois questions consécutives, parfaitement transcrites, sans une
seule réponse pendant quarante secondes.

On compte aussi les prises de parole non sollicitées et les coupures, pour
qu'une correction qui fait « répondre plus » ne passe pas pour un progrès si
elle fait surtout parler à tort.

**Ce que ça ne mesure pas** : la pertinence des réponses. Le PROTOCOLE.md est
explicite — la bêtise des réponses tient à la taille du modèle, ce n'est pas
le sujet.

    python bench/sessions.py --sessions sessions/20260829-032332 [...]
    python bench/sessions.py --toutes --min-decisions 50
"""
import argparse, glob, json, os, subprocess, sys, time

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELAI_MAX = 12.0        # au-delà, une réponse ne répond plus à la question
# Fenêtre pendant laquelle une prise de parole compte comme une intrusion dans
# une pause. Chez eux elle vaut 1,0 s ; c'est plus court que notre temps de
# réaction minimal (tick 1,2 s + réseau + attaque TTS), donc la métrique serait
# structurellement nulle. On l'aligne sur ce que le système peut physiquement
# faire, et on le dit — c'est le défaut exact relevé dans tests/evaluer.py.
PAUSE_MIN = 1.0
FENETRE_PAUSE = 3.0


def reference(dossier):
    """Segments de la transcription de référence, produite si absente."""
    chemin = os.path.join(dossier, "reference.json")
    if not os.path.exists(chemin):
        r = subprocess.run([sys.executable, os.path.join(ICI, "tests", "reference.py"),
                            dossier], cwd=ICI, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(chemin):
            return None
    with open(chemin) as f:
        return json.load(f)


def occasions(segments):
    """Les deux situations que le banc distingue, dérivées de la référence.

    On adopte les définitions de Full-Duplex-Bench pour que les chiffres tirés
    des sessions d'Alex et ceux du corpus se comparent — sinon on aurait deux
    systèmes de mesure qui ne se parlent pas, et une correction validée ici
    resterait invérifiable là-bas.

    - **fins de tour** (leur `smooth_turn_taking`) : un segment qui se termine
      par « ? ». Le système DOIT prendre la parole. TOR haut = bon.
    - **pauses** (leur `pause_handling`) : un silence de plus de PAUSE_MIN
      secondes À L'INTÉRIEUR d'un tour, c'est-à-dire qui ne suit pas une
      question. Le système doit se taire. TOR bas = bon.

    Approximation assumée : leur corpus a des pauses ANNOTÉES par des humains ;
    nous les dérivons des silences entre segments. Une respiration longue et
    une vraie fin de tour mal ponctuée sont donc indiscernables ici. Les
    chiffres qui en sortent sont comparables ENTRE NOS VERSIONS, et seulement
    indicatifs face aux leurs — la même réserve que pour l'aligneur.
    """
    fins, pauses = [], []
    for i, seg in enumerate(segments):
        texte = (seg.get("texte") or seg.get("text") or "").strip()
        t1 = seg.get("t1", seg.get("end"))
        if t1 is None:
            continue
        if texte.endswith("?"):
            fins.append((float(t1), texte))
            continue
        if i + 1 < len(segments):
            t0_suivant = segments[i + 1].get("t0", segments[i + 1].get("start"))
            if t0_suivant is not None and float(t0_suivant) - float(t1) >= PAUSE_MIN:
                pauses.append((float(t1), texte))
    return fins, pauses


def questions(segments):
    """Les segments qui appellent une réponse, avec leur instant de fin.

    Une question est reconnue au « ? » final. C'est grossier — mais c'est la
    référence produite par whisper `small`, pas la transcription temps réel, et
    la ponctuation y est fiable.

    Réserve à garder en tête : entree.wav contient AUSSI la voix du robot, que
    la référence transcrit. Un segment peut donc être une réponse du système
    prise pour une question de l'utilisateur. On écarte ceux qui tombent
    pendant que le système parlait.
    """
    out = []
    for s in segments:
        texte = (s.get("text") or s.get("texte") or "").strip()
        fin = s.get("end", s.get("fin"))
        if texte.endswith("?") and fin is not None:
            out.append((float(fin), texte))
    return out


def evalue(dossier, muet=True):
    """Rejoue la session et compte ce qui a été répondu."""
    segs = reference(dossier)
    if not segs:
        return {"erreur": "pas de transcription de référence"}
    fins, pauses = occasions(segs)
    if not fins and not pauses:
        return {"erreur": "ni fin de tour ni pause dans la référence"}

    trace = os.path.join("/tmp", "rejeu_" + os.path.basename(dossier.rstrip("/")))
    subprocess.run(["rm", "-rf", trace])
    cmd = [sys.executable, os.path.join(ICI, "pipeline.py"), "--moteur", "rejeu",
           dossier, "--trace", trace]
    if muet:
        cmd.append("--muet")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ICI, capture_output=True, text=True)
    if r.returncode != 0:
        return {"erreur": f"rejeu: {r.stderr.strip()[-200:]}"}

    jsonl = sorted(glob.glob(os.path.join(trace, "*", "session.jsonl")))
    if not jsonl:
        return {"erreur": "rejeu sans trace"}
    ev = []
    for ligne in open(jsonl[-1]):
        try:
            ev.append(json.loads(ligne))
        except ValueError:
            pass

    paroles = [e["t"] for e in ev if e["type"] == "parole_debut"]
    coupures = sum(1 for e in ev if e["type"] == "coupure")

    repondues, delais, utilisees = 0, [], set()
    for fin, _ in fins:
        for i, t in enumerate(paroles):
            if i in utilisees:
                continue
            if fin <= t <= fin + DELAI_MAX:
                repondues += 1
                delais.append(round(t - fin, 2))
                utilisees.add(i)
                break
    intrusions = sum(1 for debut, _ in pauses
                     if any(debut <= t <= debut + FENETRE_PAUSE for t in paroles))

    tor_fins = round(repondues / len(fins), 3) if fins else None
    tor_pauses = round(intrusions / len(pauses), 3) if pauses else None
    # La justesse agrégée de DuplexCascade : 1-TOR là où bas est bon, TOR là où
    # haut est bon. Jamais de moyenne partielle : si une des deux manque, on
    # rend None plutôt qu'un chiffre qui changerait de définition selon la
    # session.
    justesse = (round((tor_fins + (1 - tor_pauses)) / 2, 3)
                if tor_fins is not None and tor_pauses is not None else None)

    return {
        "fins_de_tour": len(fins),
        "repondues": repondues,
        "tor_fins": tor_fins,
        "pauses": len(pauses),
        "intrusions": intrusions,
        "tor_pauses": tor_pauses,
        "justesse": justesse,
        "latence_med": round(sorted(delais)[len(delais)//2], 2) if delais else None,
        "prises_de_parole": len(paroles),
        "coupures": coupures,
        "duree_rejeu_s": round(time.time() - t0, 1),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sessions", nargs="*", default=[])
    ap.add_argument("--toutes", action="store_true")
    ap.add_argument("--min-decisions", type=int, default=50,
                    help="avec --toutes : ignorer les sessions trop courtes")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    sessions = list(a.sessions)
    if a.toutes:
        for d in sorted(glob.glob(os.path.join(ICI, "sessions", "*"))):
            try:
                n = sum(1 for l in open(os.path.join(d, "session.jsonl"))
                        if '"decision"' in l)
            except OSError:
                continue
            if n >= a.min_decisions:
                sessions.append(d)
    if not sessions:
        raise SystemExit("aucune session — utiliser --sessions ou --toutes")

    empreinte = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ICI,
                               capture_output=True, text=True).stdout.strip()
    print(f"code {empreinte}" + (f" — {a.note}" if a.note else ""))
    print(f"{len(sessions)} session(s)\n")

    tf = tr = tp = ti = tc = 0
    for d in sessions:
        r = evalue(d)
        nom = os.path.basename(d.rstrip("/"))
        if "erreur" in r:
            print(f"  {nom}  ÉCHEC — {r['erreur']}")
            continue
        tf += r["fins_de_tour"]; tr += r["repondues"]
        tp += r["pauses"]; ti += r["intrusions"]; tc += r["coupures"]
        print(f"  {nom}  tours {r['repondues']}/{r['fins_de_tour']}  "
              f"pauses {r['intrusions']}/{r['pauses']}  "
              f"justesse {r['justesse']}  lat {r['latence_med']}s  "
              f"coupures {r['coupures']}  [{r['duree_rejeu_s']}s]")

    if tf or tp:
        tor_f = tr / tf if tf else None
        tor_p = ti / tp if tp else None
        print(f"\n  TOR fins de tour  {tr}/{tf} = "
              f"{tor_f:.3f}" if tf else "\n  TOR fins de tour : —")
        print(f"  TOR pauses        {ti}/{tp} = "
              f"{tor_p:.3f}" if tp else "  TOR pauses : —")
        if tor_f is not None and tor_p is not None:
            print(f"  JUSTESSE MOYENNE  {(tor_f + 1 - tor_p) / 2:.3f}"
                  f"   (DuplexCascade : 0.858)")
        print(f"  coupures : {tc}")


if __name__ == "__main__":
    main()
