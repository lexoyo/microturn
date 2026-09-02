# microturn

Un compagnon vocal qui écoute en continu et décide **lui-même** quand répondre.

Pas de détecteur de parole, pas de mot-clé, pas de bouton. La transcription arrive
au fil de l'eau, et toutes les 1,2 seconde le modèle de langage dit ce qu'il perçoit
— *elle parle, elle a fini, elle réfléchit, elle me coupe* — et seulement dans le
deuxième cas, ce qu'il faut répondre.

```
micro ──▶ sherpa-onnx ──▶ décideur ──▶ piper ──▶ haut-parleur
               │              │
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

Ce que coûte leur version : un Qwen2-7B-Instruct affiné en LoRA sur **8×H100
pendant 5 heures**. La nôtre coûte un prompt. L'écart mesuré est de quatre
points — 0,816 contre 0,858, voir « Ce que ça vaut ».

Deux choix leur sont directement empruntés, et ils comptent :

**Le silence est une donnée.** Quand rien n'a été dit depuis le tick précédent,
on ne se tait pas : on envoie `<|no voice|>` au modèle. Il *voit* qu'il ne s'est rien
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
| Transcription | **sherpa-onnx**, zipformer en flux, 2 threads | Le seul à tenir le temps réel sur le Pi : **244 ms par bloc de 300 ms**, et aucun bloc au-dessus de 299 |
| Repli | whisper.cpp `tiny` q5, fenêtre 10 s, `audio_ctx=512` | Seul moteur multilingue ; RTF **0,62** en greedy sur le Pi, mais il ne rend un texte neuf que toutes les ~4,3 s |
| Décision | **Modèle distant** (OpenRouter, `gemini-2.5-flash-lite`) | Zéro ressource locale, ~0,46 s depuis le Pi. En local, SmolLM2-135M met 7,6 s — inutilisable |
| Parole | **piper** résident, un WAV par phrase, ou `espeak-ng` | Garder piper en vie économise ~8 s par réponse sur le Pi ; espeak pèse 5 Mo et parle en 0,07 s |

**Le RTF n'était pas le bon critère, et c'est ce qui a fait changer de moteur le
29/08.** whisper re-transcrit tout le tour à chaque passe : son RTF de 0,62 cache
le fait qu'il ne rend un texte neuf que toutes les 4,3 secondes sur le Pi. sherpa,
transducteur causal, en rend un toutes les 300 ms. Sur le **délai de restitution
du dernier mot** — la grandeur qui gouverne vraiment la latence vécue — whisper
perd d'un ordre de grandeur.

Deux réglages contre-intuitifs, tous les deux gratuits. Sur le Pi, **moins de
threads va plus vite** : sherpa met 244 ms par bloc à deux threads, 350 à trois,
550 à quatre — au-delà de deux cœurs la machine bride plus qu'elle ne gagne. Et
whisper, quand on le garde en repli, passe de 1,17 à **0,62** de RTF rien qu'en
lui retirant son *beam search* par défaut (`best_of=1`, sans repli de température).

### La parole : un WAV par phrase

Depuis le 03/09, piper reste **résident** et écrit **un fichier WAV par phrase**,
qu'`aplay` joue d'un bloc. C'est le protocole de `wyoming-piper`, de `rhasspy3` et
de `pipecat` : aucun projet sérieux n'utilise `piper --output-raw`.

Le tube brut ne rend que des octets concaténés, sans marqueur de fin — on en était
réduit à déduire la fin d'une phrase d'un silence de 0,35 s dans le tube, ce qui
devient faux dès que piper partage le CPU avec l'ASR. On fermait alors `aplay` en
pleine phrase, et le reste ressortait **avec la phrase suivante**. Avec un fichier,
la frontière est explicite. Résident et tube étaient deux choses distinctes ; c'est
le tube qui posait problème.

Prix accepté : le premier son attend la fin de la synthèse — de l'ordre de 0,2 s
sur `shiao`, ~2,9 s sur un Pi 3B pour une longue phrase. C'est l'arbitrage qu'ont
fait tous les autres.

## Ce que ça vaut

Deux sessions réelles rejouées en déterministe, **moyenne de cinq passes** :

| | justesse | fins de tour | pauses ratées | latence vécue |
|---|---|---|---|---|
| base du 29/08 au matin | 0,634 | 11/17 | 11/29 | 5–7 s |
| **configuration retenue** | **0,816 ± 0,015** | **13,8/17** | **5,2/29** | **3,55 / 3,75 s** |
| DuplexCascade (leur banc) | 0,858 | 0,955 | — | 1,2 s |

**Quatre points d'écart avec un Qwen2-7B affiné cinq heures sur huit H100**, et
obtenus par prompting. La ligne DuplexCascade n'est pas comparable aux deux autres
— c'est leur corpus, leur banc, leur mesure ; elle donne l'ordre de grandeur, pas
un classement.

Trois précautions qui font partie du chiffre :

- **0,816 est une moyenne de cinq passes** — 0,826 · 0,791 · 0,826 · 0,813 · 0,826,
  σ 0,015. 0,826 revenait souvent, mais c'est le haut de la distribution, pas la
  moyenne : le nombre de passes fait partie du chiffre.
- **La justesse ne va jamais seule.** Un système qui se tairait toujours obtient 0,5
  sur ce banc, et 90 % de justesse brute sur une conversation réelle, où neuf ticks
  sur dix sont « elle parle encore ». On publie 0,816 **avec** ses deux taux par
  classe.
- **L'écart entre deux passes uniques a pour écart-type ~0,021** : un gain de 0,03
  mesuré une seule fois n'est pas concluant.

Latences par poste, sur la cible :

| poste | whisper + piper relancé | **sherpa + piper résident** |
|---|---|---|
| ASR, délai du dernier mot (Pi 3B) | ~4,3 s | **0,25 s** |
| TTS, coût de relance par réponse (Pi 3B) | ~8,0 s | **~0** |
| décideur, appel distant | 0,7 s | inchangé — il ne dépend pas de la machine |

Sur une session réelle tenue sur le Pi, la latence médiane du décideur est de
**0,465 s** (p90 1,009 s), pour un budget de tick de 1,2 s ; sur `shiao`, 0,44 s.
C'est l'étage qui porte le mieux le portage, ce qui n'était pas attendu.

⚠️ Ces latences sont mesurées **poste par poste**, pas de bout en bout. Le détail,
la méthode et les réserves : [`RESULTATS.md`](RESULTATS.md) pour les micro-bancs,
[`RESULTATS-PI.md`](RESULTATS-PI.md) pour la chaîne complète sur le Pi.

Sur une même session de 145 s rejouée, le passage aux six seuils vers l'horloge fixe
a fait passer le rapport se taire / parler de 0,8 à **7,6 pour 1**. ⚠️ Une partie de
cette retenue venait d'un bug — un `DONE` sans réponse était compté comme « elle
parle encore » (`RESULTATS.md` § 8).

## Installation

```bash
./install.sh                            # venv, sherpa fr, whisper de repli, voix piper fr
MICROTURN_INSTALL_TOUT=1 ./install.sh   # + le modèle sherpa anglais et la voix en_US
```

Le script est **idempotent** : ce qui est déjà là n'est pas retéléchargé, il est sûr
à relancer.

Il ne fait pas deux choses, et il faut donc les faire à la main :

- **le binaire `piper`**, distribué en archive par plateforme — à prendre sur
  [github.com/rhasspy/piper/releases](https://github.com/rhasspy/piper/releases) et
  à mettre dans `~/.local/bin/piper`, ou pointé par `MICROTURN_PIPER`. Le script ne
  télécharge les voix que s'il trouve le binaire. Sans lui, `--tts espeak` suffit.
- **la clé OpenRouter** : le script crée un `.env` avec une clé d'exemple, il faut y
  mettre la vraie.

`arecord`, `aplay` et `ffmpeg` doivent être présents — le script prévient s'ils
manquent. Le moteur `vosk` est conservé pour comparaison ; il demande
`pip install vosk` plus son modèle français, tous deux hors du script.

**Cette section ne liste volontairement aucune URL de modèle.** C'est cette
duplication qui a laissé le README documenter `whisper-tiny` deux jours après que le
défaut soit passé à sherpa. La liste est dans `install.sh`, et nulle part ailleurs.

## Usage

```bash
.venv/bin/python pipeline.py                               # conversation, au micro
.venv/bin/python pipeline.py --trace sessions/             # idem, en gardant tout
.venv/bin/python pipeline.py extrait.wav --muet            # rejouer un enregistrement
.venv/bin/python pipeline.py --langue en --trace sessions/ # en anglais
```

Options : `--moteur sherpa|whisper|vosk|rejeu` (défaut `sherpa`), `--langue fr|en`
(défaut `fr`), `--modele` pour changer de décideur (défaut
`google/gemini-2.5-flash-lite`), `--tts piper|espeak`, `--mic` pour choisir
l'entrée, `--porte` pour le seuil anti-écho (défaut `0.0`, donc désactivée),
`--rendu sortie.wav` pour produire le format attendu par Full-Duplex-Bench.

### Le mode anglais

`--langue en` change les jetons, le prompt, la voix et le modèle ASR — il sert au
banc des chercheurs. Le modèle sherpa anglais s'installe avec
`MICROTURN_INSTALL_TOUT=1 ./install.sh`.

**Il n'est pas au niveau du français, parce qu'il n'a jamais été mesuré** : tous les
chiffres de ce README portent sur le français, faute de sessions de référence en
anglais.

Le point sensible est identifié — le prompt doit être **apparié au moteur ASR**. La
phrase qui prévient que le texte arrive en majuscules et sans ponctuation vaut
**+0,063 de justesse quand elle est vraie et −0,103 quand elle est fausse** : le
mensonge coûte presque le double de ce que la vérité rapporte, et c'est le plus gros
effet mesuré du projet pour une seule phrase de prompt. `locales/en.toml` a reçu son
`systeme_sherpa` le 03/09, après vérification que le modèle anglais rend bien des
majuscules sans ponctuation — la phrase y est donc vraie. Mais **+0,063 et −0,103
sont des chiffres français** : l'effet côté anglais reste non mesuré, et tant qu'une
session de référence anglaise n'existe pas, ce mode est un mode de dépannage.

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
décision par jetons d'état, la trace, le rejeu déterministe, et un ASR en flux qui
tient le temps réel sur un Raspberry Pi 3B.

Ce qui est **désactivé** : la porte anti-écho (`--porte 0.0` par défaut). Elle se
calibrait sur un seuil plus haut qu'une voix normale et jetait 81 % de l'audio dans
une session réelle sur le Pi ; l'écho qu'elle traitait venait en fait d'un micro
posé contre le haut-parleur. Un problème de placement traité par du logiciel, et le
logiciel coûtait plus cher que le problème. `--porte 2.0` la réactive.

Ce qui reste ouvert : le décideur est le dernier étage qui n'est pas local, la
latence vécue est encore de 3,5 s, et le mode anglais n'a aucune session de
référence sur laquelle être mesuré.

## Où va le projet

Le 02/09, un constat a réorganisé le reste : **on avait mélangé deux tâches** —
détecter qu'un tour de parole est fini, et décider quoi répondre. Le projet devient
donc une **bibliothèque d'observation du tour de parole** : elle transforme un flux
d'entrée en transitions d'état décrivant l'utilisateur, ne touche jamais au signal,
et laisse le développeur brancher derrière elle le modèle de réponse qu'il veut.
Ce n'est pas un système full-duplex — seulement la moitié amont.

Ce qui est tranché et ce qui reste ouvert : [`SPEC-PIVOT.md`](SPEC-PIVOT.md).
Comment on y va, et dans quel ordre : [`PLAN.md`](PLAN.md).

Rien n'entre dans ce dépôt sans être mesuré sur une session enregistrée.
