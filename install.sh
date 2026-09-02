#!/usr/bin/env bash
# Installe ce que microturn attend : l'environnement Python et les modèles.
#
# Idempotent : ce qui est déjà là n'est pas retéléchargé. Sûr à relancer.
#
# Pourquoi un script et pas un paragraphe de README : la section « Installation »
# du README a passé deux jours à documenter whisper alors que le défaut était
# devenu sherpa. Une doc d'install ne survit pas aux changements, un script si.
set -euo pipefail
cd "$(dirname "$0")"

TOUT=${MICROTURN_INSTALL_TOUT:-0}       # 1 = aussi l'anglais et les voix en plus

dit() { printf '  %s\n' "$*"; }
titre() { printf '\n== %s\n' "$*"; }

recupere() {                             # recupere <destination> <url>
    if [ -s "$1" ]; then dit "déjà là   $(basename "$1")"; return; fi
    mkdir -p "$(dirname "$1")"
    dit "télécharge $(basename "$1")"
    curl -fsSL -o "$1.part" "$2" && mv "$1.part" "$1"
}

titre "Python"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q numpy sherpa-onnx pywhispercpp
dit "$(.venv/bin/python -c 'import sherpa_onnx, numpy; print("sherpa-onnx", sherpa_onnx.__version__, "· numpy", numpy.__version__)')"

titre "Reconnaissance vocale — sherpa-onnx (le défaut)"
# Transducteur zipformer en flux : causal, coût constant, 244 ms par bloc de
# 300 ms sur un Pi 3B à deux threads. Les fichiers int8 seulement : c'est ce
# que le projet mesure, et c'est trois fois plus léger.
FR=models/sherpa-onnx-streaming-zipformer-fr-2023-04-14
B=https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-fr-2023-04-14/resolve/main
S=epoch-29-avg-9-with-averaged-model.int8.onnx
for f in encoder-$S decoder-$S joiner-$S tokens.txt; do recupere "$FR/$f" "$B/$f"; done

if [ "$TOUT" = 1 ]; then
    titre "Reconnaissance vocale — anglais"
    EN=models/sherpa-onnx-streaming-zipformer-en-2023-06-26
    B=https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26/resolve/main
    S=epoch-99-avg-1-chunk-16-left-128.int8.onnx
    for f in encoder-$S decoder-$S joiner-$S tokens.txt; do recupere "$EN/$f" "$B/$f"; done
fi

titre "Reconnaissance vocale — whisper (repli, et seul moteur multilingue)"
recupere models/ggml-tiny-q5_1.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q5_1.bin

titre "Voix — piper"
# Le binaire piper n'est PAS installé ici : il est distribué en archive par
# plateforme. Sans lui, `--tts espeak` fonctionne (5 Mo, qualité moindre).
if [ -x "${MICROTURN_PIPER:-$HOME/.local/bin/piper}" ]; then
    dit "binaire piper présent"
    V=$HOME/.local/share/piper
    B=https://huggingface.co/rhasspy/piper-voices/resolve/main
    recupere "$V/fr_FR-siwis-medium.onnx"      "$B/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
    recupere "$V/fr_FR-siwis-medium.onnx.json" "$B/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
    if [ "$TOUT" = 1 ]; then
        recupere "$V/en_US-amy-medium.onnx"      "$B/en/en_US/amy/medium/en_US-amy-medium.onnx"
        recupere "$V/en_US-amy-medium.onnx.json" "$B/en/en_US/amy/medium/en_US-amy-medium.onnx.json"
    fi
else
    dit "piper absent — installe-le depuis github.com/rhasspy/piper/releases,"
    dit "ou reste en --tts espeak"
fi

titre "Clé et outils"
[ -f .env ] || { dit "crée .env — mets-y ta clé"; echo "OPENROUTER_API_KEY=sk-or-..." > .env; chmod 600 .env; }
grep -q "sk-or-\.\.\." .env 2>/dev/null && dit "⚠  .env contient encore la clé d'exemple"
for outil in arecord aplay ffmpeg; do
    command -v "$outil" >/dev/null || dit "⚠  $outil manquant (paquets alsa-utils, ffmpeg)"
done

titre "Vérification"
.venv/bin/python -c "import stt; print('  sherpa fr :', stt.Sherpa._suffixe('$FR'))"
printf '\nPrêt.  .venv/bin/python pipeline.py --trace sessions/\n'
printf 'Anglais et voix supplémentaires : MICROTURN_INSTALL_TOUT=1 ./install.sh\n\n'
