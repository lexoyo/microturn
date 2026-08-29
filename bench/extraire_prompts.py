#!/usr/bin/env python3
"""Sort d'une trace de rejeu les prompts RÉELLEMENT envoyés au modèle.

Le prompt qu'on lit dans `locales/` n'est pas celui que le modèle reçoit : il
faut y ajouter les exemples, l'historique accumulé et le dernier tour. Ce script
va chercher les événements `llm_appel` d'une trace et les rend lisibles, pour
qu'on discute du vrai prompt et pas de son intention.

    python bench/extraire_prompts.py /tmp/rejeu_<session> --combien 3

La clé d'API ne voyage que dans les en-têtes HTTP : elle n'est pas dans la trace,
donc pas ici non plus.
"""
import argparse, glob, json, os, sys


def appels(trace):
    for f in sorted(glob.glob(os.path.join(trace, "*", "session.jsonl"))) or \
             sorted(glob.glob(os.path.join(trace, "session.jsonl"))):
        with open(f, encoding="utf-8") as fh:
            for ligne in fh:
                try:
                    ev = json.loads(ligne)
                except ValueError:
                    continue
                if ev.get("type") == "llm_appel":
                    yield ev


def rendre(ev, n):
    msgs = ev.get("messages") or []
    out = [f"{'='*72}", f"APPEL {n} — {len(msgs)} messages, modèle {ev.get('modele')}",
           f"{'='*72}"]
    for m in msgs:
        role = m.get("role", "?")
        contenu = (m.get("content") or "")
        if role == "system":
            out.append("┌─ system ────────────────────────────────────────────")
            out += ["│ " + l for l in contenu.split("\n")]
            out.append("└─────────────────────────────────────────────────────")
        else:
            out.append(f"{role:>9}: {contenu}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--combien", type=int, default=3,
                    help="nombre d'appels à rendre, répartis sur la session")
    ap.add_argument("--sortie", default="PROMPTS-ENVOYES.txt")
    a = ap.parse_args()

    tous = list(appels(a.trace))
    if not tous:
        sys.exit(f"aucun llm_appel dans {a.trace}")
    # Répartis, pas les N premiers : le début de session n'a pas d'historique et
    # ne montre donc jamais à quoi ressemble un prompt en cours de conversation.
    if a.combien >= len(tous):
        choisis = list(enumerate(tous, 1))
    else:
        pas = len(tous) / a.combien
        choisis = [(int(i * pas) + 1, tous[int(i * pas)]) for i in range(a.combien)]

    txt = (f"Prompts réellement envoyés au modèle\n"
           f"trace : {a.trace}\n"
           f"{len(tous)} appels dans la session, {len(choisis)} rendus ici\n\n"
           + "\n\n".join(rendre(ev, n) for n, ev in choisis) + "\n")
    with open(a.sortie, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"{len(tous)} appels — {len(choisis)} écrits dans {a.sortie}")


if __name__ == "__main__":
    main()
