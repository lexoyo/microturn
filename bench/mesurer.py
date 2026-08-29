#!/usr/bin/env python3
"""Une mesure complète sur Full-Duplex-Bench : rendu, alignement, évaluation.

Enchaîne les trois étapes sur un ou plusieurs corpus et rend un tableau de
chiffres comparables d'une itération à l'autre.

    python bench/mesurer.py --taches pause,turn --echantillon 15
    python bench/mesurer.py --taches pause --echantillon 15 --passes 3

`--passes` répète la mesure à l'identique pour établir le BRUIT DE MESURE.
C'est la première chose à faire avant toute optimisation : le décideur est un
modèle distant, la lecture est en temps réel, la latence réseau varie du simple
au quadruple. Sans écart-type, on ne sait pas si un gain de 0,05 est un progrès
ou du hasard — et on passe la nuit à courir après du bruit.
"""
import argparse, json, os, statistics, subprocess, sys, time

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.expanduser("~/_/fdbench-data")
EVAL = os.path.expanduser("~/_/fdbench/v1_v1.5/evaluation")
PY_ = sys.executable

# nom court -> (dossier du corpus, script d'évaluation, sens de la métrique)
TACHES = {
    "pause":       ("candor_pause_handling",       "eval_pause_handling.py",   "bas"),
    "pause_synth": ("synthetic_pause_handling",    "eval_pause_handling.py",   "bas"),
    "turn":        ("candor_turn_taking",          "eval_smooth_turn_taking.py", "haut"),
    # notre adaptateur, pas le leur : le leur exige un client OpenAI pour une
    # note GPT-4o hors périmètre (cf. bench/eval_interrupt.py)
    "interrupt":   ("synthetic_user_interruption", "@eval_interrupt.py",       "haut"),
    "backchannel": ("icc_backchannel",             "eval_backchannel.py",      "bas"),
}


def lancer(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def chiffres(sortie):
    """Extrait les nombres d'un rapport d'évaluation, par ligne étiquetée."""
    out = {}
    for ligne in sortie.splitlines():
        if ":" not in ligne or "[" in ligne:
            continue
        cle, _, val = ligne.partition(":")
        try:
            out[cle.strip()] = float(val.strip())
        except ValueError:
            pass
    return out


def une_passe(tache, n, refaire, modele=None):
    dossier, script, _ = TACHES[tache]
    corpus = os.path.join(DATA, dossier)
    if not os.path.isdir(corpus):
        return {"erreur": f"corpus absent : {corpus}"}

    cmd = [PY_, os.path.join(ICI, "bench", "lancer.py"), "--corpus", corpus]
    if n:
        cmd += ["--echantillon", str(n)]
    if refaire:
        cmd += ["--refaire"]
    if modele:
        cmd += ["--modele", modele]
    r = lancer(cmd, cwd=ICI)
    if r.returncode != 0:
        return {"erreur": f"rendu: {r.stderr.strip()[:200]}"}

    r = lancer([PY_, os.path.join(ICI, "bench", "asr_whisper.py"),
                "--root_dir", corpus], cwd=ICI)
    if r.returncode != 0:
        return {"erreur": f"alignement: {r.stderr.strip()[:200]}"}

    # un script préfixé « @ » est l'un des nôtres, dans bench/
    if script.startswith("@"):
        chemin, dossier = os.path.join(ICI, "bench", script[1:]), ICI
    else:
        chemin, dossier = os.path.join(EVAL, script), EVAL
    r = lancer([PY_, chemin, "--root_dir", corpus], cwd=dossier)
    if r.returncode != 0:
        return {"erreur": f"évaluation: {r.stderr.strip()[:200]}"}
    return chiffres(r.stdout)


def accuracy(resultats):
    """La « Averaged Turn-Taking Accuracy » de DuplexCascade (arXiv 2603.09180).

    Le TOR change de sens d'une tâche à l'autre : bas est bon pour les pauses et
    le backchannel, haut est bon pour la prise de parole et l'interruption.
    Surveiller deux nombres qui se contredisent rend toute optimisation
    ambiguë — on ne sait jamais si on progresse ou si on déplace le problème.
    Eux définissent donc la justesse comme 1-TOR là où bas est bon, TOR là où
    haut est bon, et en prennent la moyenne non pondérée.

    On adopte leur définition telle quelle : c'est le seul moyen de se comparer
    à eux, et ils sont le point de comparaison le plus juste qui existe (même
    architecture en cascade, même principe de micro-tours ; ils entraînent leur
    modèle là où nous faisons du prompting). Leur chiffre : 0,858.

    Rendue à None si une seule tâche manque. Une moyenne partielle publiée sous
    le même nom serait un piège — c'est exactement le défaut relevé dans
    tests/evaluer.py.
    """
    parts = {}
    for tache, d in resultats.items():
        tor = None
        for cle, v in d["valeurs"].items():
            if "take turn" in cle.lower():
                tor = v["moyenne"]
        if tor is None:
            continue
        parts[tache] = (1 - tor) if d["sens_favorable"] == "bas" else tor
    if len(parts) < len(resultats) or not parts:
        return None
    return {"par_tache": {k: round(v, 4) for k, v in parts.items()},
            "moyenne": round(sum(parts.values()) / len(parts), 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--taches", default="pause",
                    help="séparées par des virgules : " + ", ".join(TACHES))
    ap.add_argument("--echantillon", type=int, default=15)
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--note", default="", help="ce qu'on teste, pour le journal")
    ap.add_argument("--modele", default=None,
                    help="modèle du décideur ; « simule » pour le décideur "
                         "déterministe hors ligne, qui donne le bruit de la "
                         "mécanique seule")
    a = ap.parse_args()

    taches = [t.strip() for t in a.taches.split(",") if t.strip()]
    inconnues = [t for t in taches if t not in TACHES]
    if inconnues:
        raise SystemExit(f"tâche(s) inconnue(s) : {inconnues} — parmi {list(TACHES)}")

    empreinte = lancer(["git", "rev-parse", "--short", "HEAD"], cwd=ICI).stdout.strip()
    sale = bool(lancer(["git", "status", "--porcelain"], cwd=ICI).stdout.strip())
    t0 = time.time()
    print(f"code {empreinte}{' + modifications non commitées' if sale else ''}")
    if a.note:
        print(f"note : {a.note}")
    print()

    resultats = {}
    for tache in taches:
        sens = TACHES[tache][2]
        passes = []
        for i in range(a.passes):
            # TOUJOURS refaire. Ne refaire qu'à partir de la 2e passe était un
            # piège : à la première passe d'une NOUVELLE itération, lancer.py
            # retrouvait les output.wav de l'itération précédente, les gardait,
            # et on évaluait l'ancien code en croyant mesurer le nouveau. Dix
            # itérations auraient donné dix fois le même chiffre.
            r = une_passe(tache, a.echantillon, refaire=True, modele=a.modele)
            if "erreur" in r:
                print(f"  {tache:12} ÉCHEC — {r['erreur']}")
                break
            passes.append(r)
            vals = ", ".join(f"{k}={v:.3f}" for k, v in r.items())
            print(f"  {tache:12} passe {i+1}/{a.passes}  {vals}")
        if not passes:
            continue
        agrege = {}
        for cle in passes[0]:
            vs = [p[cle] for p in passes if cle in p]
            agrege[cle] = {"moyenne": round(statistics.mean(vs), 4),
                           "ecart_type": round(statistics.stdev(vs), 4)
                           if len(vs) > 1 else None,
                           "passes": vs}
        resultats[tache] = {"sens_favorable": sens, "valeurs": agrege}

    print(f"\n--- {time.time()-t0:.0f} s ---")
    justesse = accuracy(resultats)
    for tache, d in resultats.items():
        fleche = "↓ mieux" if d["sens_favorable"] == "bas" else "↑ mieux"
        for cle, v in d["valeurs"].items():
            et = f" ± {v['ecart_type']}" if v["ecart_type"] is not None else ""
            print(f"  {tache:12} {cle:24} {v['moyenne']:.3f}{et}   ({fleche})")

    if justesse:
        print(f"\n  JUSTESSE MOYENNE  {justesse['moyenne']:.3f}"
              f"   (DuplexCascade : 0.858, sur les 4 tâches)")
        for k, v in justesse["par_tache"].items():
            print(f"    {k:12} {v:.3f}")
    else:
        print("\n  justesse moyenne : non calculée — il manque des tâches. "
              "Une moyenne partielle sous ce nom serait trompeuse.")

    rapport = {"code": empreinte, "modifie": sale, "note": a.note,
               "modele": a.modele, "justesse": justesse,
               "echantillon": a.echantillon, "passes": a.passes,
               "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "resultats": resultats}
    chemin = os.path.join(ICI, "bench", "derniere_mesure.json")
    with open(chemin, "w") as f:
        json.dump(rapport, f, indent=2, ensure_ascii=False)
    print(f"\n{chemin}")


if __name__ == "__main__":
    main()
