# microturn — notes pour un article

Journal des décisions et des découvertes, tenu au fil de l'eau. Ce fichier garde
le **pourquoi** ; `bench/JOURNAL.md` garde les chiffres, `bench/CANDIDATS.md` la
file de tests, `FORMAT-CHERCHEURS.md` ce qu'on a constaté chez eux.

## Le sujet

DuplexCascade (arXiv 2603.09180) fait tenir une conversation vocale sans
détecteur de parole : ASR → LLM → TTS, micro-tours à horloge fixe, et c'est le
modèle qui décide s'il doit parler, au moyen de jetons de contrôle décrivant
l'état de l'**utilisateur**. Ils obtiennent 0,858 de justesse moyenne sur
Full-Duplex-Bench, avec un Qwen2-7B fine-tuné en LoRA (8×H100, 5 heures).

**La question de microturn : est-ce que ça se transpose par prompting ?** Sans
entraînement, sur un modèle hébergé, avec un Raspberry Pi 3B au bout.

## Ce qui est établi, par la mesure

### 1. Leur sobriété est un produit du fine-tuning, pas une propriété du design

Leur format exact — sept jetons, aucun prompt système, micro-tours entrelacés —
appliqué tel quel à un modèle non entraîné donne **3/9 contre 7/9**. Ce qu'ils
n'ont pas besoin d'écrire, nous devons l'écrire. Le prompt EST notre
fine-tuning : c'est la variable libre, au même titre que leurs données
d'entraînement sont la leur (arbitrage d'Alex, 29/08).

Corollaire contre-intuitif : notre prompt doit être **plus riche** que le leur.

### 2. On peut retirer les règles, pas les données

Le prompt réduit de 167 à 71 mots a fait gagner (5/9 → 7/9). Supprimer les
marqueurs d'état a fait perdre quatre questions sur neuf. Une règle est du
bavardage ; un exemple est de la donnée d'entraînement transposée.

### 3. La formulation pèse autant que la structure

Un seul mot changé — `moi:` en `robot:` dans le préfixe des micro-tours — a fait
passer la justesse de 6/9 à 2/9. Sur un modèle non entraîné, le prompt n'est pas
une spécification : c'est une amorce statistique.

### 4. Le prompt qu'on lit n'est pas celui qu'on envoie

Le défaut le plus coûteux de la session n'était visible dans aucun fichier de
configuration : les exemples partaient en JSON contraint, l'historique
reconstruit partait en texte brut. Deux conventions pour la même chose, et la
mauvaise était la plus proche de la réponse à produire. Trouvé en extrayant les
prompts réellement envoyés (`bench/extraire_prompts.py`), corrigé, +0,07.

**Leçon de méthode : instrumenter ce qui part sur le réseau, pas ce qu'on croit
envoyer.**

### 5. On mesurait le réseau, pas le prompt

La même session rejouée deux fois, sur le même code, a donné 118 puis 123
décisions, et 0,762 puis 0,691 de justesse. Cause : le rejeu tournait en temps
réel et un appel lent faisait sauter des ticks. La moitié des verdicts rendus
jusque-là — « neutre », « pas de gain » — étaient des indécidables.

Corrigé par un rejeu à horloge virtuelle (`--deterministe`) : l'appel bloque,
aucun tick ne saute, deux exécutions du même code donnent le même résultat. En
prime, le rejeu devient plus rapide que le temps réel.

**Leçon de méthode : avant de mesurer une amélioration, mesurer le bruit de la
mesure. Ici il était plus grand que tout ce qu'on cherchait.**

### 6. Une seule session ne mesure rien

Passer de une à deux sessions a fait tomber la base de 0,762 à 0,634 — sans
qu'une ligne change. La première session ne contenait que 7 pauses et zéro
interruption ; la seconde en apporte 22 et trois coupures. La dimension « se
taire » était quasi invisible, et c'est notre pire.

### 7. Le goulot n'est peut-être pas le modèle

Cinq réponses sur treize d'une session réelle sont « je ne comprends pas,
reformule » — parce que whisper `tiny` rend `tu te cheins`, `moi je remapéle`.
Le modèle décide correctement sur une entrée fausse. Reste à mesurer la borne
haute à ASR parfait.

## Chiffres de référence

| | justesse | fins de tour | pauses | latence |
|---|---|---|---|---|
| DuplexCascade | 0,858 | 0,955 | — | 1,2 s |
| microturn, 29/08 | 0,634 | 11/17 | 11/29 | 5–7 s |

Un système qui se tairait toujours obtiendrait 0,5. Un système qui parlerait
toujours aussi. L'agrégat seul ne veut rien dire — il faut lire les deux TOR.

## Décisions de conception, et pourquoi

- **Sortie contrainte par schéma JSON** plutôt qu'espérée. 122 décisions sur 122
  avaient été perdues parce que le parseur découpait sur le premier mot alors
  que le modèle répondait parfaitement. Un `enum` sur les sept jetons rend
  l'erreur de format structurellement impossible. C'est notre équivalent de ce
  que leur fine-tuning garantit.
- **Les jetons sont ceux du papier, exactement les sept, pas un de plus** —
  contrainte posée par Alex. Ça coûte du score par rapport à des jetons inventés
  plus lisibles, et c'est assumé : l'intérêt de l'exercice est la transposition,
  pas le score.
- **`<|no voice|>` sur deux sources** : ASR muet ET mesure du son sous −40 dBFS.
  Le filtre lexical ne rattrape que les artefacts connus ; sur un tick
  silencieux, whisper invente des phrases plausibles qu'aucune liste ne prévoit.
- **Pas d'annulation d'écho logicielle** : le Pi n'aura pas Chrome. On coupe sur
  la mesure de la porte, pas sur un traitement du signal.
