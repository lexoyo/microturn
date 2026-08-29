#!/usr/bin/env bash
# Annulation d'écho acoustique système (le WebRTC AEC de Chrome, via PipeWire).
# Sans écouteurs, le micro réentend le TTS et le pipeline se coupe la parole.
#
#   tests/echo-cancel.sh on    puis lance le pipeline normalement
#   tests/echo-cancel.sh off   pour revenir à l'état d'avant
#
# `on` crée une paire micro/haut-parleur nettoyée et en fait les périphériques
# par défaut : le pipeline et piper les prennent sans le moindre argument.
set -euo pipefail

etat=~/.cache/microturn-echo-cancel

case "${1:-}" in
on)
  [ -f "$etat" ] && { echo "déjà actif (tests/echo-cancel.sh off pour arrêter)"; exit 0; }
  mkdir -p "$(dirname "$etat")"

  src=$(pactl get-default-source)
  snk=$(pactl get-default-sink)

  mod=$(pactl load-module module-echo-cancel \
    source_master="$src" sink_master="$snk" \
    source_name=micro_sans_echo sink_name=hp_sans_echo \
    aec_method=webrtc use_master_format=1)

  pactl set-default-source micro_sans_echo
  pactl set-default-sink hp_sans_echo
  printf '%s\n%s\n%s\n' "$mod" "$src" "$snk" > "$etat"

  echo "annulation d'écho active — micro_sans_echo / hp_sans_echo par défaut"
  echo "  micro d'origine : $src"
  echo "  sortie d'origine : $snk"
  ;;
off)
  [ -f "$etat" ] || { echo "pas actif"; exit 0; }
  { read -r mod; read -r src; read -r snk; } < "$etat"
  pactl set-default-source "$src" || true
  pactl set-default-sink "$snk" || true
  pactl unload-module "$mod" || true
  rm -f "$etat"
  echo "annulation d'écho retirée, périphériques d'origine restaurés"
  ;;
*)
  sed -n '2,9p' "$0" | sed 's/^# \?//'
  exit 1
  ;;
esac
