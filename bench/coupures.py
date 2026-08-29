#!/usr/bin/env python3
"""Quelles phrases ont été coupées, et à quel endroit.

Une coupure est légitime quand l'utilisateur reprend vraiment la parole, et
parasite quand elle vient de l'écho ou d'un artefact. On ne peut pas trancher
sans savoir OÙ dans la phrase elle tombe : couper au premier mot, c'est ne rien
avoir dit ; couper au dernier, c'est presque avoir fini.

On estime la position par le temps écoulé rapporté à la durée attendue de la
phrase (14 caractères par seconde, mesuré sur piper).

    python bench/coupures.py sessions/<date>
"""
import json, os, sys

DEBIT_CAR_S = 14.0
ATTAQUE_S = 0.95


def main():
    d = sys.argv[1].rstrip("/")
    ev = [json.loads(l) for l in open(os.path.join(d, "session.jsonl"),
                                      encoding="utf-8") if l.strip()]
    stt = [(e["t"], e.get("texte", "")) for e in ev if e["type"] == "partial"]
    paroles = []
    for i, e in enumerate(ev):
        if e["type"] != "parole_debut":
            continue
        txt = e.get("texte", "")
        duree = ATTAQUE_S + len(txt) / DEBIT_CAR_S
        # la coupure qui suit, avant la prochaine prise de parole
        suite = [x for x in ev[i + 1:] if x["type"] in ("coupure", "parole_debut")]
        coupe = suite[0] if suite and suite[0]["type"] == "coupure" else None
        paroles.append((e["t"], txt, duree, coupe["t"] if coupe else None))

    print(f"{len(paroles)} prises de parole · "
          f"{sum(1 for *_, c in paroles if c)} coupées\n")
    print(f"{'début':>7} {'durée':>6} {'coupée à':>9} {'avancement':>11}   texte")
    tot = []
    for t, txt, duree, c in paroles:
        if c is None:
            print(f"{t:7.1f} {duree:5.1f}s {'—':>9} {'entière':>11}   {txt[:44]}")
            continue
        dt = c - t
        pct = min(100, 100 * dt / duree)
        tot.append(pct)
        # ce qui a été entendu juste avant la coupure
        avant = [x for s, x in stt if t <= s <= c]
        cause = avant[-1][-28:] if avant else "(rien entendu)"
        print(f"{t:7.1f} {duree:5.1f}s {dt:8.1f}s {pct:10.0f}%   {txt[:44]}")
        print(f"{'':>36}↳ entendu : {cause}")
    if tot:
        tot.sort()
        print(f"\n  avancement médian à la coupure : {tot[len(tot)//2]:.0f} %")
        print(f"  coupées avant la moitié : {sum(1 for x in tot if x < 50)}/{len(tot)}")


if __name__ == "__main__":
    main()
