# microturn

Un compagnon vocal qui écoute en continu et décide **lui-même** quand répondre.

Pas de détecteur de parole, pas de mot-clé, pas de bouton. La transcription arrive
au fil de l'eau, et toutes les 1,2 seconde le modèle de langage dit ce qu'il perçoit
— *elle parle, elle a fini, elle réfléchit, elle me coupe* — et seulement dans le
deuxième cas, ce qu'il faut répondre.

```
micro ──▶ whisper ──▶ décideur ──▶ piper ──▶ haut-parleur
             │            │
       transcription   PARLE · FINI · REFLECHIT · COUPE
```

## L'idée, et d'où elle vient

Un détecteur de parole tranche sur un seuil de silence : au-delà de tant de
millisecondes, il décide que la personne a fini. Ça ne peut pas marcher, parce
qu'une pause de réflexion et une fin de phrase durent la même chose. Les gens
respirent, hésitent, cherchent leurs mots.

[DuplexCascade](https://arxiv.org/abs/2603.09180) (Yang, Fujita, Sudo — SB
Intuitions et université de Tokyo, code sous licence MIT)
propose de supprimer le détecteur et de confier ce jugement au modèle de langage,
qui lui dispose du **contenu** et pas seulement du signal. Leur implémentation
s'appuie sur les modèles Kyutai, qui demandent plus de 3 Go de mémoire : hors
d'atteinte de la cible visée ici. On reprend donc le mécanisme, pas le code — et
on l'obtient par **prompting** là où eux le font par fine-tuning.

Deux choix leur sont directement empruntés, et ils comptent :

**Le silence est une donnée.** Quand rien n'a été dit depuis le tick précédent,
on ne se tait pas : on envoie `SILENCE` au modèle. Il *voit* qu'il ne s'est rien
passé, et peut compter les silences successifs — c'est ce qui remplace le seuil.

**Les jetons décrivent l'état de la personne, pas l'action à faire.** On demande
une perception (« où en est-elle ? »), pas une décision de politique (« dois-je
parler ? »). C'est une tâche bien mieux posée pour un modèle générique.

## La contrainte qui décide de tout

La cible est un **Raspberry Pi 3B** : 905 Mio de mémoire, quatre Cortex-A53 à
1,2 GHz, pas de GPU, et un throttling thermique qui s'enclenche après 25 secondes
de charge sur les quatre cœurs. Chaque mégaoctet et chaque cycle comptent.

| Étage | Choix | Pourquoi |
|---|---|---|
| Transcription | **whisper.cpp `tiny` q5**, modèle résident | Sur le Pi : RTF **0,62** en greedy, contre 1,86 pour Vosk sur le même audio, et 103 Mo contre 241 |
| Décision | **Modèle distant** (OpenRouter) | Zéro ressource locale, ~0,4 s. En local, SmolLM2-135M met 7,6 s sur le Pi — inutilisable |
| Parole | **piper**, ou `espeak-ng` | espeak pèse 5 Mo et parle en 0,07 s ; sur le Pi c'est le mode réaliste |

Le passage de whisper en **greedy** (`best_of=1`, sans repli de température) divise
son temps par deux sur le Pi : 1,17 → 0,62 de RTF. C'est le réglage le plus rentable
du projet, et il est gratuit.

## Mesuré

Sur un i7-7500U (2 cœurs, 7,5 Go) :

- whisper `tiny` q5, `audio_ctx=1152` — RTF **0,11**, chargé une fois en 0,08 s
- décideur `llama-3.2-3b` — **0,36 s** en moyenne, connexion HTTPS réutilisée
- piper `fr_FR-siwis-medium` — premier son à **0,97 s**, RTF 0,21

Sur une vraie session de 145 secondes, le passage à l'horloge a fait tomber la part
de prises de parole de **76 % à 13 %** des décisions, à nombre de réponses constant.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install pywhispercpp numpy
mkdir -p models
curl -L -o models/ggml-tiny-q5_1.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q5_1.bin
echo "OPENROUTER_API_KEY=sk-or-..." > .env && chmod 600 .env
```

`arecord`, `aplay` et `ffmpeg` doivent être présents. `piper` est optionnel — sans
lui, `--tts espeak` suffit. Le moteur `vosk` est conservé pour comparaison et
demande `pip install vosk` plus son modèle français.

## Usage

```bash
.venv/bin/python pipeline.py                       # conversation, au micro
.venv/bin/python pipeline.py --trace sessions/     # idem, en gardant tout
.venv/bin/python pipeline.py extrait.wav --muet    # rejouer un enregistrement
```

Options : `--modele` pour changer de décideur, `--tts piper|espeak`, `--porte` pour
le seuil anti-écho, `--mic` pour choisir l'entrée.

## Analyser une session

C'est la partie qui rend le reste utilisable. Avec `--trace`, une session écrit
l'audio d'entrée (rejouable tel quel), un journal horodaté de chaque hypothèse de
transcription, de chaque prompt envoyé et de chaque réponse brute, et un fichier de
métadonnées contenant les réglages, la machine et **l'empreinte du code**.

```bash
.venv/bin/python tests/reference.py sessions/<date>   # ce qui a VRAIMENT été dit
.venv/bin/python pipeline.py --moteur rejeu sessions/<date> --modele X --muet
```

Le mode **rejeu** relit les transcriptions enregistrées au lieu de refaire tourner
whisper. C'est ce qui rend une comparaison honnête : deux modèles reçoivent alors
exactement les mêmes entrées, aux mêmes instants, et tout écart vient de ce qu'on
fait varier. Sans ça, on comparerait deux bruits.

Le protocole complet est dans [`PROTOCOLE.md`](PROTOCOLE.md), et les pistes non
tranchées dans [`IDEES.md`](IDEES.md).

## État

Prototype qui tourne, pas un produit. Ce qui marche : la boucle complète, la
décision par jetons d'état, la trace, le rejeu déterministe, une porte anti-écho
auto-calibrée. Ce qui reste ouvert : le portage sur le Pi, la comparaison de
plusieurs modèles, et le réglage du prompt — le décideur est encore trop prudent
sur les questions courtes.

Rien n'entre dans ce dépôt sans être mesuré sur une session enregistrée.
