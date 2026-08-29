#!/bin/bash
# Test de fumée — à lancer APRÈS CHAQUE modification, avant toute analyse.
#
# Vérifier la fonction qu'on vient de changer ne suffit pas : une constante
# supprimée par une réécriture de bloc ne casse pas la fonction, elle casse le
# programme au démarrage. C'est arrivé, et c'est Alex qui l'a découvert en
# lançant une session.
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
ok=0; ko=0
essai() {
  printf "  %-44s " "$1"; shift
  if timeout 120 "$@" >/dev/null 2>/tmp/fumee.err; then echo "OK"; ok=$((ok+1))
  else echo "ÉCHEC"; grep -E "Error|Traceback" /tmp/fumee.err | tail -2; ko=$((ko+1)); fi
}
echo "=== analyse statique ==="
# pyflakes attrape en 0,2 s la famille de bugs qui nous a coûté des heures :
# deux définitions concurrentes d'une même fonction, la seconde écrasant la
# première sans le moindre message. C'est arrivé deux fois (_lire_controle,
# puis Decideur), et les deux fois ça a faussé des mesures.
essai "pyflakes (doublons, imports morts)" $PY -m pyflakes audio.py stt.py llm.py tts.py journal.py pipeline.py
echo "=== import et démarrage ==="
essai "modules importables"        $PY -c "import audio, stt, llm, tts, journal, pipeline"
essai "pipeline --help"            $PY pipeline.py --help
essai "stt --help"                 $PY stt.py --help
echo "=== chaîne complète sur un vrai enregistrement ==="
essai "pipeline (muet)"            $PY pipeline.py samples/00-fumee.wav --muet
essai "pipeline (muet + trace)"    $PY pipeline.py samples/00-fumee.wav --muet --trace /tmp/fumee_trace
essai "pipeline (vosk)"            $PY pipeline.py samples/00-fumee.wav --muet --moteur vosk
essai "rendu au format du banc"   $PY -c "
import subprocess, sys, wave
sortie = '/tmp/fumee_rendu.wav'
subprocess.run([sys.executable, 'pipeline.py', 'samples/00-fumee.wav',
                '--rendu', sortie], stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL, check=True)
a = wave.open('samples/00-fumee.wav'); b = wave.open(sortie)
# Full-Duplex-Bench exige EXACTEMENT la même durée que l'entrée : un écart
# d'une trame décale toutes les frontières et fausse chaque métrique.
sys.exit(0 if a.getnframes() == b.getnframes()
           and a.getframerate() == b.getframerate() else 1)"
essai "tampon vidé, porte fermée" $PY tests/reset_tampon.py
echo "=== étages isolés ==="
essai "décideur (réseau)"          $PY llm.py fr "[je n'ai pas parlé] tu peux allumer la lumière du salon"
essai "filtre d'artefacts"         $PY -c "
import stt, sys
cas=[('(musique) (musique)',0),('[Rire]',0),('... ... ... ...',0),
     ('on se passe, on se passe, on se passe, on se passe',0),
     ('Sous-titres réalisés par la communauté',0),
     (\"Comment tu t'appelles ?\",1),('bonjour tu peux allumer la lumière',1)]
rates=[t for t,a in cas if stt.utile(t)!=bool(a)]
sys.exit(1 if rates else 0)"
echo
echo "  $ok réussis, $ko échoués"
[ $ko -eq 0 ] || exit 1
