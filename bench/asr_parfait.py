#!/usr/bin/env python3
"""Fabrique une session où la reconnaissance vocale est PARFAITE.

But : la borne haute. Si la justesse ne monte pas quand l'ASR est irréprochable,
le prompt n'est plus le problème — et l'inverse vaut aussi. On a mesuré que 80 %
de la latence vient du délai de whisper ; reste à savoir ce que ce délai, et les
fautes qui vont avec, coûtent en JUSTESSE.

On part de la transcription de référence (whisper `small`, hors ligne, sans
contrainte de temps) et on la ré-émet comme un flux : les mots d'un segment sont
répartis linéairement entre son début et sa fin, et chaque mot produit un
`partial` cumulatif. Le texte est donc juste ET disponible au moment où il est
prononcé.

C'est une approximation par le haut sur deux points, tous deux dans le sens de
la borne : la répartition linéaire ignore le débit réel, et `small` n'est pas la
vérité terrain — c'est le meilleur ASR qu'on ait sous la main.

    python bench/asr_parfait.py sessions/20260829-073852
    → sessions/20260829-073852-parfait/
"""
import json, os, shutil, sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1].rstrip("/")
    dst = src + "-parfait"
    ref = json.load(open(os.path.join(src, "reference.json"), encoding="utf-8"))

    os.makedirs(dst, exist_ok=True)
    for f in ("entree.wav", "reference.json"):
        chemin = os.path.join(src, f)
        if os.path.exists(chemin):
            shutil.copy2(chemin, os.path.join(dst, f))
    meta = json.load(open(os.path.join(src, "meta.json"), encoding="utf-8"))
    meta["stt"] = "parfait (référence ré-émise)"
    meta["derive_de"] = src
    json.dump(meta, open(os.path.join(dst, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # Le transcript est CUMULATIF, comme celui de whisper : le pipeline calcule
    # son delta par différence, il attend donc un texte qui s'allonge.
    evts, cumul = [], []
    for seg in ref["segments"]:
        mots = seg["texte"].split()
        if not mots:
            continue
        t0, t1 = float(seg["t0"]), float(seg["t1"])
        pas = (t1 - t0) / len(mots)
        for i, mot in enumerate(mots):
            cumul.append(mot)
            evts.append({"t": round(t0 + (i + 1) * pas, 3), "type": "partial",
                         "texte": " ".join(cumul)})
    with open(os.path.join(dst, "session.jsonl"), "w", encoding="utf-8") as f:
        for e in evts:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"{len(evts)} événements, {len(cumul)} mots → {dst}")


if __name__ == "__main__":
    main()
