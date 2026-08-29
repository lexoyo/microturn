#!/usr/bin/env python3
"""Transcrit une session avec sherpa-onnx et en fait une session mesurable.

Un transducteur n'a pas de fenêtre : il consomme l'audio par blocs et garde son
état. On l'alimente donc au même rythme que le pipeline (300 ms), et on note le
texte À CHAQUE FOIS qu'il change — c'est ça, le streaming, et c'est ce qu'on veut
comparer à la re-transcription de whisper.

    python bench/session_sherpa.py sessions/20260829-073852
"""
import json, os, shutil, subprocess, sys, time
import numpy as np

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = os.path.join(ICI, "models", "sherpa-onnx-streaming-zipformer-fr-2023-04-14")
BLOC = 4800          # 300 ms à 16 kHz, le pas du pipeline


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    import sherpa_onnx
    src = sys.argv[1].rstrip("/")
    dst = src + "-sherpa"

    rec = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=f"{M}/tokens.txt",
        encoder=f"{M}/encoder-epoch-29-avg-9-with-averaged-model.int8.onnx",
        decoder=f"{M}/decoder-epoch-29-avg-9-with-averaged-model.int8.onnx",
        joiner=f"{M}/joiner-epoch-29-avg-9-with-averaged-model.int8.onnx",
        num_threads=3, sample_rate=16000, feature_dim=80,
        enable_endpoint_detection=True, rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=1.2, rule3_min_utterance_length=20)

    raw = subprocess.run(["ffmpeg", "-loglevel", "quiet", "-i",
                          os.path.join(src, "entree.wav"),
                          "-f", "s16le", "-ar", "16000", "-ac", "1", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768

    s = rec.create_stream()
    evts, vu, fige, t0 = [], "", "", time.time()
    for i in range(0, len(a), BLOC):
        s.accept_waveform(16000, a[i:i + BLOC])
        while rec.is_ready(s):
            rec.decode_stream(s)
        t = (i + BLOC) / 16000.0
        # La détection de fin d'énoncé fige le texte et repart : sans elle le
        # transducteur accumule tout depuis le début et le delta n'a plus de sens.
        if rec.is_endpoint(s):
            fige = (fige + " " + rec.get_result(s)).strip()
            rec.reset(s)
            vu = ""
            continue
        txt = rec.get_result(s)
        if txt != vu:
            vu = txt
            entier = (fige + " " + txt).strip()
            if entier:
                evts.append({"t": round(t, 3), "type": "partial", "texte": entier})
    cpu = time.time() - t0

    os.makedirs(dst, exist_ok=True)
    for f in ("entree.wav", "reference.json"):
        c = os.path.join(src, f)
        if os.path.exists(c):
            shutil.copy2(c, os.path.join(dst, f))
    meta = json.load(open(os.path.join(src, "meta.json"), encoding="utf-8"))
    meta.update({"stt": "sherpa-onnx", "modele_stt": os.path.basename(M),
                 "derive_de": src, "rtf": round(cpu / (len(a) / 16000), 3)})
    json.dump(meta, open(os.path.join(dst, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    with open(os.path.join(dst, "session.jsonl"), "w", encoding="utf-8") as f:
        for e in evts:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"{len(evts)} événements · RTF {cpu/(len(a)/16000):.3f} → {dst}")
    if evts:
        print(f"  fin : ...{evts[-1]['texte'][-140:]}")


if __name__ == "__main__":
    main()
