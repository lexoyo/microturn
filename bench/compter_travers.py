#!/usr/bin/env python3
"""Compte ce que la justesse ne voit pas : les travers de FORME des réponses.

Trois défauts relevés en session réelle — les relances vides, le tic « je suis
un grand modèle linguistique », l'alternance tutoiement/vouvoiement — ne
déplacent aucun marqueur, donc n'apparaissent pas dans la justesse. Les variantes
55, 57 et 58 les visent : il faut donc les compter, pas les scorer.

    python bench/compter_travers.py /tmp/rejeu_<session>
"""
import glob, json, os, re, sys

RELANCES = re.compile(
    r"^(je t'écoute|vas-y|je suis prêt|dis-moi|continue|je vous écoute"
    r"|allez-y|je suis à ton écoute|je t'entends)\b", re.I)
TIC = re.compile(r"grand mod[èe]le|mod[èe]le linguistique|entraîné par", re.I)
VOUS = re.compile(r"\b(vous|votre|vos)\b", re.I)


def travers(trace):
    f = sorted(glob.glob(os.path.join(trace, "*", "session.jsonl")))
    if not f:
        f = [os.path.join(trace, "session.jsonl")]
    rep = []
    for ligne in open(f[-1], encoding="utf-8"):
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        if e.get("type") == "llm_reponse" and e.get("brut"):
            try:
                o = json.loads(e["brut"])
            except ValueError:
                continue
            if o.get("r"):
                rep.append(o["r"].strip())
    return rep


def main():
    rep = travers(sys.argv[1])
    if not rep:
        sys.exit("aucune réponse dans cette trace")
    r = sum(1 for x in rep if RELANCES.match(x))
    t = sum(1 for x in rep if TIC.search(x))
    v = sum(1 for x in rep if VOUS.search(x))
    print(f"  {len(rep):3} réponses · {sum(len(x) for x in rep)//len(rep)} car en moyenne")
    print(f"  relances vides        {r:3}  ({100*r//len(rep)} %)")
    print(f"  tic « grand modèle »  {t:3}  ({100*t//len(rep)} %)")
    print(f"  vouvoiement           {v:3}  ({100*v//len(rep)} %)")


if __name__ == "__main__":
    main()
