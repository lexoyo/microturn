# microturn

Un compagnon vocal qui écoute en continu, et qui décide **lui-même** quand répondre.

Pas de détecteur de parole, pas de mot-clé, pas de bouton. La transcription arrive
mot par mot, et c'est le modèle de langage qui tranche, au fil du texte : attendre,
glisser un signe d'écoute, ou prendre la parole.

```
micro ──▶ Vosk (partiels mot à mot) ──▶ décideur LLM ──▶ piper ──▶ haut-parleur
                                            │
                                 <WAIT> · <HMM> · réponse
```

## D'où ça vient

L'idée est celle de [DuplexCascade](https://github.com/sbintuitions/DuplexCascade) (MIT) :
supprimer le VAD en confiant la décision de tour de parole au LLM, qui émet des tokens
de contrôle à partir du flux de transcription. Leur implémentation s'appuie sur les
modèles Kyutai, qui demandent plus de 3 Go de RAM — hors d'atteinte de la cible visée ici.
On reprend donc le mécanisme, pas le code, et on l'obtient par prompting plutôt que par
apprentissage : moins finement, mais avec n'importe quel modèle instruct.

## La contrainte qui décide de tout

La cible est un **Raspberry Pi 3B** : 905 Mio de RAM, quatre Cortex-A53 à 1,2 GHz, pas de
GPU, et un throttling thermique qui s'enclenche après 25 secondes de charge sur les quatre
cœurs. Chaque mégaoctet et chaque cycle comptent. C'est ce qui explique tous les choix :

| Étage | Choix | Pourquoi |
|---|---|---|
| STT | **Vosk** small FR (66 Mo) | streaming natif mot par mot ; whisper travaille par blocs et ne rend rien avant la fin d'un segment |
| Décision | **LLM distant** (OpenRouter) | zéro ressource locale, ~0,5 s ; un modèle local prendrait les cœurs dont Vosk a besoin |
| TTS | **piper** (ou `espeak-ng`) | piper pour la voix, espeak quand il ne reste que 5 Mo |

## Mesuré

Sur un i7-7500U (2 cœurs, 7,5 Go) :

- Vosk — RTF **0,39** à un mètre, **0,64** à trois mètres ; premier mot en **0,7 à 1,5 s** ;
  chargement du modèle 0,66 s
- Décideur — **0,51 s** en moyenne. `llama-3.2-3b` répond juste 4 fois sur 5 ;
  `llama-3.2-1b` temporise systématiquement et n'est pas utilisable
- piper `fr_FR-siwis-medium` — premier son à **0,97 s**, RTF 0,21

Soit environ **1,5 s** entre la fin d'une phrase et le début de la réponse.

## Installation

```bash
python3 -m venv .venv && .venv/bin/pip install vosk
mkdir -p models && cd models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip
unzip vosk-model-small-fr-0.22.zip && cd ..
echo "OPENROUTER_API_KEY=sk-or-..." > .env && chmod 600 .env
```

`arecord`, `aplay` et `ffmpeg` doivent être présents ; `piper` est optionnel
(sinon `espeak-ng`).

## Usage

```bash
.venv/bin/python pipeline.py                    # micro, conversation en direct
.venv/bin/python pipeline.py samples/01.wav     # rejoue un enregistrement
.venv/bin/python stt.py samples/01.wav          # l'étage STT seul, pour voir les partiels
.venv/bin/python llm.py "quelle heure il est"   # le décideur seul
```

Options utiles : `--tts piper|espeak`, `--mic hw:0,0`, `--muet` (mesure sans parler).
Le modèle se change par `MICROTURN_MODEL`.

### `--trace DOSSIER` — rejouer et comprendre après coup

```bash
.venv/bin/python pipeline.py --trace traces/          # enregistre la session
.venv/bin/python pipeline.py traces/20260829-0030/entree.wav   # la rejoue
```

Écrit `entree.wav` (le flux micro complet, rejouable tel quel), `session.jsonl`
(un événement par ligne : transcriptions, **prompt exact** envoyé au modèle et
**réponse brute** avec sa latence, décisions, paroles, coupures, niveaux audio)
et `meta.json` (configuration, durée, résumé chiffré). Tout est écrit par un seul
thread derrière une queue : la boucle et le thread audio ne touchent pas au disque.
Sans l'option, le module n'est même pas importé.

### `--porte FACTEUR` — anti-écho auto-calibré

Sans casque, le micro réentend le robot et il finit par se répondre à lui-même.
Pendant qu'il parle, le seul son possible est son propre écho : on y **mesure**
le niveau reçu, et on ne transmet plus au STT que ce qui le dépasse d'un facteur
(2,0 par défaut, `0` désactive). Aucun réglage manuel, et le barge-in continue de
marcher — la voix directe passe la porte, l'écho non. Les niveaux mesurés et les
blocs jetés partent dans la trace, pour rerégler le facteur après coup.

## État

Prototype. La boucle tourne de bout en bout, mais **le décideur n'est pas encore consulté
pendant la parole** : on attend que le partiel se stabilise, ce qui revient à un VAD
déguisé — précisément ce que le projet cherche à éviter. C'est le prochain chantier.

Hors périmètre pour l'instant : l'interruption complète, les backchannels, plusieurs
locuteurs, et le portage sur Pi.
