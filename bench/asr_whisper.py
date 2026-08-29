#!/usr/bin/env python3
"""Remplaçant de `get_transcript/asr.py` de Full-Duplex-Bench, sans GPU.

Leur chaîne aligne les transcriptions avec `nvidia/parakeet-tdt-0.6b-v2` sous
NeMo, qui exige CUDA. Cette machine n'a pas de GPU. On produit donc le même
`output.json` avec whisper.cpp, qui sait horodater au mot
(`token_timestamps` + `max_len=1` + `split_on_word`).

**Ce que ça change, et il faut le dire dans tout résultat publié** : nos
chiffres ne sont plus directement comparables à ceux du papier, puisque
l'aligneur diffère. Ils restent parfaitement comparables ENTRE NOS VERSIONS,
ce qui est l'usage principal — mesurer une progression et attraper une
régression. Le modèle est fixé par défaut à `small` : plus lent que le `tiny`
du temps réel, mais c'est une passe hors ligne, et l'aligneur ne doit pas être
le maillon faible de la mesure.

Interface identique à la leur, pour pouvoir enchaîner sans adaptation :

    python bench/asr_whisper.py --root_dir DOSSIER [--task user_interruption]
                                [--audio_name output.wav] [--modele ...]
"""
import argparse, json, os, sys
from glob import glob

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ICI)
MODELE = os.path.join(ICI, "models", "ggml-small-q5_1.bin")
# Amplitude crête en dessous de laquelle une tranche est considérée muette
# (sur 32768). Un TTS produit des milliers ; le silence numérique produit zéro.
SEUIL_MUET = 200


def aligner(m, chemin, offset=0.0, depuis=0.0):
    """Transcription mot à mot d'un WAV, bornes décalées de `offset`."""
    import wave
    import numpy as np
    with wave.open(chemin, "rb") as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        if w.getnchannels() > 1:
            pcm = pcm.reshape(-1, w.getnchannels()).mean(axis=1).astype(np.int16)
    if depuis > 0:
        pcm = pcm[int(depuis * rate):]
    audio = pcm.astype(np.float32) / 32768
    chunks, texte = [], []
    for s in m.transcribe(audio):
        mot = s.text.strip()
        if not mot:
            continue
        # Whisper hallucine sur du silence : sur un output.wav où le système
        # n'avait RIEN dit, il a produit un mot, et le banc a conclu que le
        # système avait pris la parole (TOR = 1.0 au lieu de 0). Un mot dont la
        # tranche audio est muette n'existe pas — on le jette. Le seuil est
        # volontairement très bas : il ne s'agit pas de juger le volume, mais
        # de distinguer du son de son absence.
        d0, d1 = int(s.t0 / 100 * rate), int(s.t1 / 100 * rate)
        tranche = pcm[max(0, d0):max(d0 + 1, d1)]
        if len(tranche) == 0 or np.abs(tranche).max() < SEUIL_MUET:
            continue
        # whisper.cpp compte en centisecondes
        chunks.append({"text": " " + mot,
                       "timestamp": [round(s.t0 / 100 + offset, 3),
                                     round(s.t1 / 100 + offset, 3)]})
        texte.append(mot)
    return {"text": " ".join(texte), "chunks": chunks}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root_dir", required=True)
    ap.add_argument("--task", default="default",
                    choices=["default", "user_interruption"])
    ap.add_argument("--audio_name", default="output.wav")
    ap.add_argument("--modele", default=MODELE)
    ap.add_argument("--langue", default="en")
    a = ap.parse_args()

    audios = sorted(glob(f"{a.root_dir}/*/{a.audio_name}"))
    if not audios:
        raise SystemExit(f"aucun {a.audio_name} sous {a.root_dir}/*/")
    if not os.path.exists(a.modele):
        raise SystemExit(
            f"modèle absent : {a.modele}\n"
            f"  il sert d'aligneur de référence, pas au temps réel — le prendre "
            f"gros est délibéré.\n"
            f"  télécharger : https://huggingface.co/ggerganov/whisper.cpp/"
            f"resolve/main/ggml-small-q5_1.bin")

    from pywhispercpp.model import Model
    m = Model(a.modele, language=a.langue, print_progress=False,
              print_realtime=False, token_timestamps=True, max_len=1,
              split_on_word=True)

    nom_json = a.audio_name.rsplit(".", 1)[0] + ".json"
    for chemin in audios:
        offset = depuis = 0.0
        if a.task == "user_interruption":
            # Comme chez eux : on ne transcrit que ce qui suit l'interruption,
            # et on rétablit ensuite les bornes absolues.
            meta = os.path.join(os.path.dirname(chemin), "interrupt.json")
            with open(meta) as f:
                depuis = offset = json.load(f)[0]["timestamp"][1]
        res = aligner(m, chemin, offset, depuis)
        sortie = os.path.join(os.path.dirname(chemin), nom_json)
        with open(sortie, "w") as f:
            json.dump(res, f, indent=4, ensure_ascii=False)
        print(f"  {sortie}  ({len(res['chunks'])} mots)")


if __name__ == "__main__":
    main()
