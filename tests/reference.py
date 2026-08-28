#!/usr/bin/env python3
"""Transcription de RÉFÉRENCE d'une session — ce qui a vraiment été dit.

Le système tourne avec `tiny` pour être temps réel sur un Pi ; il se trompe.
Pour juger ses décisions il faut d'abord savoir ce qui a réellement été dit :
on repasse donc l'audio dans un modèle bien plus gros, hors ligne, sans
contrainte de temps. C'est la première étape du protocole d'analyse.

    python tests/reference.py sessions/20260829-005246
"""
import json, os, subprocess, sys
import numpy as np

MODELE = "models/ggml-small-q5_1.bin"


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    d = sys.argv[1].rstrip("/")
    wav = os.path.join(d, "entree.wav")
    if not os.path.exists(wav):
        raise SystemExit(f"pas de {wav}")

    from pywhispercpp.model import Model
    raw = subprocess.run(["ffmpeg", "-loglevel", "quiet", "-i", wav,
                          "-f", "s16le", "-ar", "16000", "-ac", "1", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    print(f"{len(a)/16000:.1f} s d'audio, modèle {MODELE}", file=sys.stderr)

    # Ici on veut la MEILLEURE transcription, pas la plus rapide : contexte
    # complet, segments naturels, pas de troncature.
    m = Model(MODELE, language="fr", n_threads=os.cpu_count(),
              print_progress=False, print_realtime=False)
    segs = m.transcribe(a)

    out = []
    for s in segs:
        # pywhispercpp donne les temps en centisecondes
        t0, t1 = s.t0 / 100.0, s.t1 / 100.0
        out.append({"t0": round(t0, 2), "t1": round(t1, 2), "texte": s.text.strip()})
        print(f"[{t0:6.2f} → {t1:6.2f}]  {s.text.strip()}")

    chemin = os.path.join(d, "reference.json")
    with open(chemin, "w") as f:
        json.dump({"modele": MODELE, "segments": out}, f, ensure_ascii=False, indent=2)
    print(f"\n→ {chemin}  ({len(out)} segments)", file=sys.stderr)


if __name__ == "__main__":
    main()
