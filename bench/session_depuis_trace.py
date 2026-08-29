#!/usr/bin/env python3
"""Fabrique une session mesurable à partir d'une trace de transcription.

Pourquoi ce détour : le rejeu lit les transcriptions FIGÉES d'une session, donc
changer de modèle whisper n'a aucun effet sur lui. Pour comparer deux ASR il
faut repasser l'audio dans chacun, capturer ce qu'ils rendent ET quand, puis
mesurer les deux flux ainsi obtenus — en déterministe, sinon on compare deux
cadencements au lieu de deux modèles.

    python bench/session_depuis_trace.py /tmp/stt_base sessions/20260829-073852 base
    → sessions/20260829-073852-base/
"""
import glob, json, os, shutil, sys


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    trace, origine, nom = sys.argv[1], sys.argv[2].rstrip("/"), sys.argv[3]
    dst = f"{origine}-{nom}"
    fichiers = sorted(glob.glob(os.path.join(trace, "*", "session.jsonl")))
    if not fichiers:
        raise SystemExit(f"aucune trace dans {trace}")

    os.makedirs(dst, exist_ok=True)
    for f in ("entree.wav", "reference.json"):
        chemin = os.path.join(origine, f)
        if os.path.exists(chemin):
            shutil.copy2(chemin, os.path.join(dst, f))
    meta = json.load(open(os.path.join(origine, "meta.json"), encoding="utf-8"))
    src_meta = json.load(open(os.path.join(os.path.dirname(fichiers[-1]),
                                           "meta.json"), encoding="utf-8"))
    meta["modele_stt"] = src_meta.get("modele_stt", nom)
    meta["derive_de"] = origine
    json.dump(meta, open(os.path.join(dst, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    n = 0
    with open(os.path.join(dst, "session.jsonl"), "w", encoding="utf-8") as out:
        for ligne in open(fichiers[-1], encoding="utf-8"):
            try:
                e = json.loads(ligne)
            except ValueError:
                continue
            if e.get("type") in ("partial", "final") and e.get("texte"):
                out.write(json.dumps(e, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} événements → {dst}  ({meta['modele_stt']})")


if __name__ == "__main__":
    main()
