# microturn — notes pour un article

Journal des décisions et des découvertes, tenu au fil de l'eau. Ce fichier garde
le **pourquoi** ; `bench/JOURNAL.md` garde les chiffres, `bench/CANDIDATS.md` la
file de tests, `FORMAT-CHERCHEURS.md` ce qu'on a constaté chez eux.

**Fiche de lecture du papier fondateur : `PAPIER.md`** — thèse, sept jetons,
réglages, résultats, et les quatre points encore à vérifier dans le PDF.

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

### 8. Notre métrique ne couvre qu'une des deux tâches du système

Le système décide **quand parler** et **quoi dire** dans le même appel.
Full-Duplex-Bench ne note que la première : le 0,816 et les sept changements
gardés sont des résultats de **détection de fin de tour**, pas de qualité de
réponse — laquelle n'a jamais été mesurée. Ce n'est pas une réserve de portée,
c'est un angle mort, et il a une conséquence de coût : sur une session réelle
comptée le 02/09, **92 % des appels ne produisent aucune parole** et paient
pourtant le prompt complet.

### 9. La justesse agrégée peut récompenser un système d'avoir échoué

Mesuré le 02/09 sur la variante « détection seule » : justesse **0,821** contre
0,816 pour la base — lu seul, « aucun effet » — alors que sa détection de fin de
tour est **six points plus basse** (0,745 contre 0,812). Le mécanisme est
mécanique et non anecdotique : **un système qui rate des fins de tour parle
moins, donc il intervient moins dans les pauses, et la seconde moitié du score
le récompense d'avoir échoué sur la première.**

C'est la démonstration la plus nette qu'on ait du piège annoncé au § 7 de
`RESULTATS.md` (« le mutisme ressemble à de la sagesse »), et elle est arrivée
sur la mesure censée trancher le sujet même de l'article. **Ne jamais publier un
agrégat sans ses deux TOR** cesse d'être une précaution de méthode : c'est un
résultat. Développé en partie IV.

### 10. Le fine-tuning vaut environ 0,21 — et changer de modèle en rend les trois quarts

Mesuré le 03/09 (`b2127ec`) : **notre prompt, tel quel, sur
`qwen/qwen-2.5-7b-instruct`** — la même famille et la même taille que le Qwen2-7B
que DuplexCascade fine-tune. Trois passes par modèle, deux sessions, rejeu
déterministe.

| | TOR fins ↑ | TOR pauses ↓ | justesse |
|---|---|---|---|
| `gemini-2.5-flash-lite` (nous) | **0,824** | 0,207 | **0,808** |
| `qwen-2.5-7b-instruct`, prompté | **0,471** | 0,172 | **0,649** |
| Qwen2-7B **fine-tuné** (le papier) | | | 0,858 |

**Le chiffre qui manquait à l'article n'est pas 0,042. C'est 0,209 pour le
fine-tuning, dont 0,159 rattrapés en changeant simplement de modèle.** Le
prompting sur un bon petit modèle récupère les trois quarts de ce que coûtent
8×H100 pendant cinq heures — mais **seulement sur un bon modèle**. Sur le leur,
sans fine-tuning, notre prompt s'effondre. Développé en partie II, réserves
comprises.

### 11. Les deux mécanismes qu'on avait ajoutés au design du papier étaient les deux qui coûtaient

Le 03/09, deux inventions maison ont été mesurées puis retirées : le **rappel du
tour en cours** concaténé après le delta (retiré : +1 fin de tour sur 17 et 14 %
de tokens en moins) et le **découpage TTS** (retiré : trois bugs, dont un qui
rendait une phrase sur trois entièrement muette). Une troisième, le **repliage
élargi**, a été mesurée puis rejetée avant d'entrer.

Ce n'est pas une coïncidence dont on tire une morale : c'est un constat à trois
occurrences, et il faut l'écrire comme tel — **chacun de ces trois mécanismes
nous éloignait du design des chercheurs, et chacun coûtait.** Le corollaire n'est
pas « ne rien inventer », il est plus utile : *un écart au design de référence
est une hypothèse, donc il se mesure comme telle, et il ne se mesure jamais en
même temps qu'un autre.*

## Chiffres de référence

| | justesse | fins de tour | pauses ratées | latence |
|---|---|---|---|---|
| DuplexCascade | 0,858 | 0,955 | — | 1,2 s |
| microturn, base du 29/08 au matin | 0,634 | 11/17 | 11/29 | 5–7 s |
| **microturn, configuration retenue** | **0,816 ± 0,015** | **13,8/17** | **5,2/29** | **3,55 / 3,75 s** |

Les deux lignes microturn portent sur les **mêmes deux sessions** (`032332` et
`073852`), rejouées en déterministe : elles sont comparables entre elles. La
ligne DuplexCascade ne l'est pas — c'est leur banc, leur corpus, leur mesure.

⚠️ **La ligne du bas est une moyenne de cinq passes, et les fractions ne sont
donc plus entières.** C'est volontaire : voir « Le chiffre du projet est 0,816 »
en partie IV. Toute valeur citée sans son nombre de passes est suspecte, la
nôtre comprise.

Un système qui se tairait toujours obtiendrait 0,5. Un système qui parlerait
toujours aussi. L'agrégat seul ne veut rien dire — il faut lire les deux TOR.

### ⚠️ 0,816 ne décrit plus le code — la référence a bougé quatre fois le 03/09

**C'est la chose la plus importante à savoir avant d'écrire une ligne de
l'article ce soir.** La ligne « configuration retenue » ci-dessus a été mesurée
le 02/09 sur une configuration qui comportait le **découpage TTS** (supprimé), la
consigne **« courte »** (retirée) et le **tutoiement imposé** (retiré). Trois des
éléments de sa définition n'existent plus. Le chiffre n'est pas faux : il a cessé
de décrire quoi que ce soit.

Ce que le 03/09 a effectivement mesuré, toujours sur les deux mêmes sessions
sherpa, `gemini-2.5-flash-lite`, rejeu déterministe :

| état du dépôt | passes | TOR fins ↑ | TOR pauses ↓ | justesse |
|---|---|---|---|---|
| config du 02/09 (avec découpage, « courte », tutoiement) | 5 | 0,812 | 0,179 | **0,816 ± 0,015** |
| `b511c42` — sans « courte » | 3 | 0,824 (14/17) | 0,207 (6/29) | 0,808 |
| `b5a6652` — sans tutoiement, + 3 commits | 3 | 0,765 (13/17) | 0,172 (5/29) | **0,796** |
| `752f20d` — contrôle, reproduit | 3 | 0,765 ± 0,000 | 0,161 ± 0,020 | 0,802 ± 0,010 |
| `752f20d` **+ rappel du tour retiré** | 3 | **0,824 ± 0,000** | **0,149 ± 0,020** | **0,837 ± 0,010** |

Trois choses à en tirer, et aucune n'est confortable :

1. **La fourchette 0,808–0,816 est périmée.** Une fin de tour a été perdue entre
   `b511c42` et `b5a6652` — quatre commits et le retrait du tutoiement — et
   **personne n'a isolé lequel**. Le contrôle est tombé à 0,796 sans qu'on
   l'attende, et il a fallu s'en apercevoir en lisant un chiffre de contrôle.
   C'est le résultat n° 5 bis en action : *une base doit être remesurée quand le
   code bouge entre deux séries*, et cette fois nous ne l'avions pas fait.
2. **La dernière ligne est le meilleur état mesuré du projet — et elle n'est pas
   encore la configuration retenue.** Le retrait du rappel du tour vit dans
   l'arbre de travail d'Alex, non commité au soir du 03/09. Tant qu'il n'est pas
   commité et remesuré comme base, **le chiffre du projet reste à trancher**, et
   l'article ne cite ni 0,816 ni 0,837 sans dire sur quel état du code.
3. **La justesse agrégée a caché le mouvement, encore une fois.** Entre
   `b511c42` et `b5a6652` elle ne perd que 0,012 — sous le bruit — quand la
   dimension qui compte perd 0,059, soit ~4 σ de ce qu'une fin de tour vaut. Lire
   l'agrégat seul aurait conclu « rien n'a bougé ».

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

---

# Plan de l'article

Posé le 29/08/2026. La vision tient en **trois axes**, et l'article suit leur
enchaînement plutôt que de les énumérer : la contrainte matérielle **impose** le
prompting ; le prompting **permet** d'ajouter des capteurs ; les capteurs
**retombent** sous la contrainte de départ. Chaque partie justifie la suivante.

**Titre de travail** : *Reproduire DuplexCascade sans entraîner — un compagnon
vocal full-duplex sur un Raspberry Pi 3B.*

**Thèse en une phrase** : le mécanisme du papier s'obtient par prompting, pour
une fraction des ressources, et ce détour se révèle être une propriété — un
prompt se transporte d'un modèle à l'autre et accepte n'importe quelle source de
texte, là où des poids entraînés enferment.

## I. La contrainte décide de tout

Ce que coûte l'original : Qwen2-7B fine-tuné en LoRA, 8×H100 pendant 5 heures ;
les modèles Kyutai au-delà de 3 Go. Ce qu'on vise : 905 Mio, quatre Cortex-A53,
pas de GPU.

- **Le mur thermique est un fait de conception, pas une anecdote** : 25 s de
  charge sur quatre cœurs suffisent à déclencher le throttling. D'où le
  renversement mesuré deux fois, sur whisper puis sur onnxruntime : **2 threads
  vont plus vite que 4** (sherpa 244 ms/bloc à 2 threads, 499 ms à 4). Le
  meilleur réglage n'est pas celui qu'on choisirait en optimisant le seul RTF.
- **Le RTF n'est pas le bon critère** : whisper re-décode tout le tour à chaque
  passe et ne rend le dernier mot qu'au bout de 4,3 s ; sherpa le rend en
  250 ms. Le critère utile est le **délai de restitution du dernier mot**.
- **Le réglage le plus rentable est gratuit** : whisper en greedy, RTF 1,17 →
  0,62, sans changer la transcription.
- **Le TTS était le vrai goulot, et il était invisible** parce que toutes nos
  mesures de latence s'arrêtaient à la décision. « Ça va bien, merci » — 18
  caractères — coûtait **11,71 s** de synthèse pour 1,62 s d'audio. Le coût est
  fixe, c'est le chargement du modèle : `tts.py` lançait un piper par phrase.
  Gardé en vie, ce coût de chargement tombe à ~0. **Huit secondes par réponse,
  soit plus que tout ce que l'ASR avait gagné.**
  Le prix est architectural : on ne peut plus tuer piper pour couper la parole,
  donc on tue `aplay` seul et un compteur de génération fait jeter le PCM devenu
  sans objet.
  ⚠️ **Ce qui tombe à ~0, c'est le chargement, pas le délai avant le son.** Une
  fois résident, piper synthétise encore la phrase entière avant de rendre la
  main : il ne diffuse rien au fil de l'eau, donc **le délai avant le premier
  son EST la durée de synthèse complète**. Ne pas confondre les deux dans le
  texte (voir la décomposition ci-dessous, et la réserve en partie IV).
- **Le découpage de la réponse a été supprimé le 03/09, et il ne fait plus
  partie de la configuration retenue.** ⚠️ *Cette ligne remplace une description
  périmée : les notes ont décrit pendant deux jours un système qui n'existait
  plus.* Le mécanisme (candidat 60) divisait bien le délai avant le premier son
  par 2,5 — **2 890 → 1 135 ms en `medium` sur le Pi**, 1 721 → 844 ms en `low`,
  le coût de synthèse étant linéaire, ≈ 330 ms fixes + 60 ms par caractère. Mais
  il a produit **les trois bugs les plus coûteux du projet** : la phrase sortie
  en tranches, le détecteur de fin de phrase qui se déclenchait entre deux
  morceaux, et la comptabilité des morceaux restants sous interruption. Retiré
  au commit `763b91c`. **Ce qui reste de la mesure est le modèle de coût, pas le
  mécanisme** — et le chiffre de 1 135 ms ne décrit plus rien d'existant.
  L'arbitrage assumé à sa place : la phrase part d'un bloc, et le premier son
  attend la fin de la synthèse (~0,2 s sur `shiao`, ~2,9 s sur un Pi 3B pour une
  longue phrase).
- **Le tube brut était une invention maison, et personne d'autre ne fait ça.**
  Vérification d'état de l'art le 03/09 : aucun projet sérieux n'utilise
  `piper --output-raw` — ni wyoming-piper (Home Assistant), ni rhasspy3, ni
  pipecat, ni le serveur HTTP de piper. Tous gardent piper **résident**, et
  exactement pour notre raison (le rechargement coûte 8 s sur le Pi), mais tous
  écrivent **un WAV par phrase**. *Résident* et *tube* sont deux décisions
  distinctes, et nous les avions prises comme une seule : c'est le tube qui
  posait problème. Sans marqueur de fin dans le flux, on déduisait la fin de
  phrase d'un silence de 0,35 s dans le tube — faux dès que piper partage le CPU
  avec l'ASR, et le reste de la phrase sortait alors **avec la suivante**.
  Mesure avant / après sur trois phrases enchaînées, en **durée d'audio
  réellement servie au haut-parleur** (et non en délai) : 1,58 → 1,12 s,
  **0,00 → 1,29 s — une phrase entièrement muette avant**, 2,41 → 1,43 s ; et une
  phrase coupée puis reprise passe de muette à 2,97 s complète.
  **Leçon d'article : là où l'on a inventé un protocole que tout l'écosystème
  évite, ce n'est pas de l'audace, c'est une dette non identifiée.**
- **Le ratio synthèse / audio reste le chiffre qui décide, mais il ne décide plus
  la même chose.** `medium` synthétise **2,97 s pour 3,20 s d'audio, soit 0,93 —
  7 % de marge** ; `low` est à 0,58. Tant qu'il y avait des morceaux, ce ratio
  décidait si la parole se trouait en son milieu. Depuis que la phrase part d'un
  bloc, **il ne décide plus d'un trou mais d'un délai** : au-dessus de 1, le
  temps d'attente avant le premier son dépasse la durée de ce qu'on va entendre.
  **Décision d'architecture du 02/09, toujours valable : le TTS est le goulot du
  Pi pour une raison structurelle, pas par lenteur.** Le Pi passe la chaîne
  complète à demi-fréquence (600 MHz, `RESULTATS-PI.md` §5), et le ratio de
  `medium` passe alors au-dessus de 1. ⚠️ **C'est une inférence, pas une
  mesure** : le lien throttling → ratio > 1 n'a jamais été mesuré directement. Le
  repli existe (`low`, ratio 0,58) mais échantillonne à 16 kHz au lieu de 22 —
  arbitrage de qualité à trancher à l'oreille. Protocole en `IDEES.md` § 12.
- **Les deux secondes avant le son n'étaient pas le tampon ALSA.** Symptôme
  rapporté par Alex en session : « deux secondes entre le moment où il écrit
  qu'il va dire quelque chose et le moment où je l'entends ». Quatre tailles de
  tampon testées sur le HDMI du Pi : 1,64 s au défaut, 1,54 s à 100 ms de
  tampon. **Cent millisecondes de tampon ne gagnent qu'un dixième de seconde.**
  Le démarrage d'ALSA vaut ~0,3 s ; le reste est la synthèse elle-même. Un
  soupçon d'infrastructure levé par une mesure de dix minutes — et le réglage
  reste désactivé par défaut.
- **Le défaut de constante qui ne se voit que sur la cible** : `ATTAQUE_S` et
  `DEBIT_CAR_S`, justes à 5 % sur un laptop, sous-estiment d'un facteur 3 sur le
  Pi. Le système se croit muet pendant qu'il parle encore.
- **Et ce n'est pas un incident isolé : quatre constantes calibrées sur la
  mauvaise machine dans la même journée.** `ATTAQUE_S`, `DEBIT_CAR_S`, le nombre
  de threads de sherpa (4 sur le laptop, 2 sur le Pi), puis les délais du test de
  son lui-même (`MICROTURN_TEST_LENT=3`). **Le rapport de puissance entre
  `shiao` et le Pi est d'environ trois, et il faut le supposer partout où une
  durée est écrite en dur.** C'est la formulation générale de la leçon, et elle
  vaut mieux que l'anecdote : sur une cible embarquée, toute constante de temps
  est un réglage de machine déguisé en constante physique.

→ *Sur cette machine, entraîner est hors de question. D'où la partie II.*

## II. Le prompt est notre fine-tuning

- **Leur sobriété est un produit de l'entraînement, pas une propriété du
  design** : leur format exact, sur un modèle non entraîné, donne 3/9 contre
  7/9. Corollaire contre-intuitif : notre prompt doit être **plus riche** que le
  leur — c'est précisément ce qu'un fine-tuning nous éviterait d'écrire.
- **On peut retirer les règles, pas les données** : 167 → 71 mots fait gagner
  (5/9 → 7/9) ; supprimer les marqueurs d'état fait perdre quatre questions sur
  neuf. Une règle est du bavardage, un exemple est de la donnée transposée.
- **La formulation pèse autant que la structure** : `moi:` → `robot:`, un seul
  mot, 6/9 → 2/9. Le prompt n'est pas une spécification, c'est une amorce
  statistique.
- **Une affirmation sur l'entrée pèse plus lourd que l'entrée elle-même** : la
  phrase sur l'absence de ponctuation rapporte +0,063 quand elle est vraie et
  coûte **−0,103** quand elle est fausse. Le mensonge coûte le double de ce que
  la vérité rapporte. C'est ce qui rend le prompting puissant et fragile.
- **Le silence est une donnée** : on envoie `SILENCE` plutôt que rien, et le
  modèle compte les silences au lieu de franchir un seuil.
- **Ce que le refus du fine-tuning achète** : changer de décideur est changer un
  flag. Pas de ré-entraînement par modèle testé, donc la possibilité de
  comparer — et l'obsolescence des modèles cesse d'être notre problème.
  Corollaire d'écriture : on obtient un catalogue de scores, et il faut décider
  lequel on revendique (voir plus bas).
- **Mais la portabilité se construit, elle n'est pas donnée** : le schéma JSON
  strict, qui est notre équivalent de ce que leur fine-tuning garantit, n'est pas
  portable — gpt-4o-mini répond 400 et on perdait 100 % des décisions. D'où une
  cascade de repli (strict → souple → `json_object` → rien) et un garde-fou qui
  vérifie chaque réponse contre l'énumération des sept marqueurs. Le prompt se
  transporte ; l'API sous laquelle il s'exécute, non.

### Combien vaut le fine-tuning, exactement ? La mesure du 03/09

C'est le chiffre qui manquait à l'article depuis le premier jour, et il change la
thèse. Jusqu'ici nous écrivions « quatre points d'écart avec un modèle
fine-tuné » — 0,858 contre 0,816 — en mélangeant sans le dire **deux** choses :
leur entraînement, et le fait qu'ils tournent sur un Qwen2-7B quand nous tournons
sur `gemini-2.5-flash-lite`. Une seule mesure les sépare : **notre prompt, tel
quel, sur un Qwen de la même famille et de la même taille.**

Qwen2-7B n'est plus servi sur OpenRouter ; `qwen/qwen-2.5-7b-instruct` est la
génération suivante. Trois passes par modèle, lancées en parallèle, catalogue et
code gelés dans une copie parce que le dépôt bougeait pendant la mesure.

| | TOR fins ↑ | TOR pauses ↓ | justesse |
|---|---|---|---|
| `gemini-2.5-flash-lite` (nous) | **0,824** | 0,207 | **0,808** |
| `qwen-2.5-7b-instruct`, **prompté** | **0,471** | 0,172 | **0,649** |
| Qwen2-7B, **fine-tuné** (le papier) | | | 0,858 |

**Le chiffre du fine-tuning est 0,209. Le changement de modèle en rattrape
0,159.** Autrement dit : le prompting sur un bon petit modèle récupère les trois
quarts de ce que coûtent 8×H100 pendant cinq heures — **mais seulement sur un bon
modèle**. Sur le leur, sans entraînement, notre prompt s'effondre.

C'est la formulation la plus honnête de la thèse, et elle est plus intéressante
que l'ancienne : le prompting ne remplace pas le fine-tuning, **il déplace le
budget de l'entraînement vers le choix du modèle**.

**Le mécanisme, et il est net.** Distribution des marqueurs sur 897 décisions par
modèle :

| ce que le modèle répond | qwen | gemini |
|---|---|---|
| « sa phrase n'est pas finie » (`user is talking`) | **73 %** | 16 % |
| « il se tait, mais il réfléchit » (`user is thinking`) | 11 % | **68 %** |
| « il a fini » (`user finish talking`) | 109 fois | 132 fois |

Une **inversion complète sur le silence**. Qwen prend la parole presque autant que
gemini — 109 fois contre 132 — mais **au mauvais moment**. Et ce n'est pas un
défaut de format : les deux modèles ont tenu le schéma strict sur 897 décisions
sur 897, zéro repli, zéro erreur réseau. Le petit modèle n'est même pas celui qui
perd le plus de décisions : c'est gemini, avec onze réponses tronquées.

**Deux réserves, et elles ne sont pas décoratives** — elles jouent en sens
inverse l'une de l'autre, et on ne sait pas laquelle domine :

- **Notre prompt a été réglé sur gemini**, à travers cinquante-huit variantes. Le
  faire tourner sur Qwen n'est pas « tout le reste identique » du point de vue de
  Qwen : c'est un prompt étranger. **Une part inconnue des 0,209 est du réglage
  que Qwen n'a jamais reçu, pas du fine-tuning.**
- **Ils ont fine-tuné Qwen2 quand nous mesurons Qwen2.5.** Si 2.5 est meilleur en
  base, l'écart vrai sur Qwen2 est *plus grand* que 0,209.

**Le seul écart qui ne mélange rien est gemini ↔ Qwen à prompt identique :
0,159**, mesuré sur le même banc, les mêmes sessions, le même jour. C'est celui
sur lequel l'article doit s'appuyer. Toute soustraction avec 0,858 reste
indicative : leur banc est Full-Duplex-Bench, en anglais, avec des pauses
annotées par des humains ; le nôtre est deux sessions françaises d'Alex avec des
pauses dérivées de ffmpeg.

Détail qui vaut d'être gardé : le tic « je suis un grand modèle linguistique »
est à **0 % chez Qwen** sur les deux sessions. C'est un trait de gemini, pas un
effet de notre prompt.

### Deux mécanismes de notre invention, retirés après mesure

C'est le fil de la journée du 03/09, et il porte mieux la thèse que n'importe
quel gain : **les deux ajouts qui nous éloignaient du design du papier étaient
les deux qui coûtaient.**

**Le rappel du tour en cours — retiré, et ça rapporte.** Le mécanisme
concaténait tout le tour *après* le delta, pour que le modèle n'oublie pas la
question quand le delta n'est qu'un marqueur de silence. Il coûtait deux choses :
il **dupliquait** le texte (`… BUILD A DEEP LEARNING MODEL SO COULD YOU EX` après
`MODEL SO COULD YOU EX`), et il **cassait le repliage des silences**, qui teste si
le delta *se termine* par le marqueur — avec le rappel collé derrière, ce test est
toujours faux. Mesuré (`8c02dcd`), trois passes : **13/17 → 14/17 fins de tour,
écart-type nul des deux côtés**, sans rien payer en pauses (4,7 → 4,3 intrusions,
donc dans l'autre sens), et **14 % de tokens d'entrée en moins** (871 → 745). *Le
seul des quatre bras qui améliore les deux dimensions à la fois.*

**Le repliage élargi — essayé, mesuré, rejeté.** Alex avait proposé un meilleur
critère : replier dès que le modèle **répond deux fois la même chose**, au lieu
d'exiger « il parle encore » — car le modèle répond « il réfléchit » sur 84 % des
silences, et *c'est nous qui le lui avons appris*, par l'exemple ajouté pour
+0,025. Le critère élargi fait passer les replis de **2 % à 55 % des ticks**. **Et
c'est pire** : 0,804 contre 0,824 en fins de tour, 0,241 contre 0,149 en pauses.

Le mécanisme est le plus intéressant du lot et il mérite d'être expliqué dans
l'article : **le repliage ne raccourcit pas le prompt** — 745 tokens sans lui, 858
avec — il **libère des places dans l'historique**, que des micro-tours de *parole*
viennent aussitôt occuper. Le modèle voit donc plus de parole, détecte une fin de
tour de plus, et paie trois intrusions. *Un mécanisme d'économie qui, en
économisant, change ce que le modèle voit.* C'est l'arbitrage bavard/prudent
connu, obtenu par un chemin qu'on n'avait pas prévu.

**Et la question de départ reste sans réponse.** Dire au modèle depuis combien de
temps il attend — le suffixe `<\|no voice\|> ×{n}` sur les silences repliés —
donne +0,3 fin de tour et +1,3 intrusion par passe, distributions recouvrantes :
**non concluant à n = 3**. La question « est-ce que dire que ça dure aide à
conclure ? » n'est pas tranchée ; elle est seulement devenue testable, et le
mécanisme qui la rend testable coûte plus qu'il ne rapporte. Idée n° 1,
variante a) d'`IDEES.md`.

### Le meilleur score n'est pas le nôtre

Trois décideurs, même session (`073852`), même ASR (sherpa, deux threads) :
llama-3.3-70b 0,824, gemini-2.5-flash-lite 0,807, gemini-2.5-flash 0,716.

`flash-lite` reste le défaut. L'écart de 0,017 avec llama est **sous** le bruit
de mesure — chacun de ces scores est une passe unique, et l'écart entre deux
passes a pour écart-type ~0,021 (voir partie IV). En face : un coût par session de 0,016 $ contre 0,085 $, une
latence vécue de 3,75 s contre 4,35 s, et un ordre de grandeur d'énergie de
moins.

**Ce que la justesse agrégée cachait** : `flash-lite` rate 3 pauses sur 22,
llama en rate 5. La pause ratée est le défaut n° 1 côté utilisateur. Le meilleur
agrégat est donc le moins bon sur la dimension qui compte — un agrégat qui
départage deux modèles départage mal.

Troisième profil, contre-intuitif : `gemini-2.5-flash`, plus gros, fait moins
bien (0,716) mais ne coupe la parole que 2 fois. Ce n'est pas une dégradation
uniforme, c'est un modèle plus prudent, donc plus muet.

**Le chiffre du projet est celui de la configuration retenue, et lui seul.**
0,824 est le score d'un modèle qu'on écarte ; il n'entre jamais dans l'article
comme « notre » résultat. Au moment de cette comparaison, la configuration
retenue était à 0,807 sur `073852`, une passe ; elle est depuis à **0,816 ±
0,015 de moyenne sur les deux sessions et cinq passes** (voir partie IV). Deux
chiffres, deux bases : ne jamais les mettre dans la même phrase sans dire
laquelle, ni sans dire sur combien de passes.

### Le seuil de cache : un prompt plus long qui coûte moins cher

Le cache implicite de gemini-2.5 ne s'arme qu'au-delà de 1024 jetons. Le seuil
se lit à l'œil nu dans les trois mesures de la comparaison des décideurs :

    gemini-2.5-flash        ~900 jetons →   0 % de jetons cachés
    gemini-2.5-flash-lite   1025 jetons →   4 %
    llama-3.3-70b           1127 jetons →  55 %

Précision qui compte : ce sont trois décideurs, pas un même prompt allongé trois
fois. Le seuil est net, la courbe entre les points ne l'est pas.

Notre prompt franchit ce seuil de peu, et ne cache donc presque rien. Il lui
manque une centaine de jetons pour le passer pour de bon. Le journal chiffre
le gain à un coût divisé par quatre — c'est une projection à partir du tarif du
cache, pas une facture mesurée, et l'article doit le dire ainsi.

**Rallonger le prompt le rendrait moins cher.** C'est le seul cas mesuré où
allonger est rentable, et c'est aussi un contre-argument au test 3 : réduire
l'horizon à 20 micro-tours a divisé le contexte par deux, donc nous a fait
passer sous le seuil.

Même famille que « deux threads vont plus vite que quatre » (partie I). Dans les
deux cas, optimiser la grandeur évidente — un prompt court, tous les cœurs —
mène au mauvais réglage, parce que la vraie limite est un seuil situé ailleurs.

### Où le prompting plafonne — et c'est mesuré

La partie qui empêche l'article d'être un plaidoyer. Défaut visé : 5 pauses
ratées sur 22. Trois variantes, trois échecs : une règle (« dans le doute, il
n'a pas fini »), un exemple (fragment puis silence), une définition resserrée.

**Les amplitudes ont été corrigées, et la question de base est tranchée.** Ces
trois variantes ont été mesurées contre 0,761, alors que la base sherpa a été
portée à **0,807** juste après, en restaurant une variante qu'une série
précédente avait écrasée. Lues contre la bonne base, les trois pertes sont donc
plus lourdes : **−0,121**, **−0,092**, **−0,063**. La conclusion ne bouge pas —
aucune n'améliore — mais elle se durcit, et c'est bien 0,807 qu'il faut citer
comme base des trois échecs dans l'article, jamais 0,761.

Deux leçons de méthode, à écrire comme telles : une base doit être remesurée
quand le code bouge entre deux séries, et **un gain perdu en silence contamine
tout ce qui est mesuré ensuite**.

**Aucune n'améliore, et le pari sur l'exemple était le mauvais** alors que tous
les gains précédents en étaient venus. L'interprétation la plus simple est aussi
la plus instructive : **on demande au modèle d'être prudent sur les pauses, il
devient prudent partout.** Un prompt agit sur le comportement global ; il ne sait
pas viser une dimension. C'est précisément ce qu'un fine-tuning ferait avec des
données ciblées — la limite structurelle de la transposition, pas un manque
d'astuce dans la formulation.

Conséquence assumée : les pauses ne se corrigeront pas dans le prompt. Le levier
restant est dans le code — exiger N ticks de silence consécutifs avant
d'autoriser une prise de parole, ce qui ne demande rien au modèle.

**Et ce levier-là a échoué à son tour, pour une raison logique et non
empirique** (candidat 59, abandonné). Tester le compteur de silences au moment
où le modèle décide de parler ne peut rien donner : s'il décide de parler, c'est
qu'il vient d'entendre du texte, donc le compteur est à zéro **par
construction**. Le système devient totalement muet — 0,500, zéro prise de
parole, avec un tick de garde comme avec deux. Le faire correctement
demanderait de mettre la réponse en attente et de la redéclencher N ticks plus
tard, pour un coût en latence (1,2 s par tick, sur une latence descendue à
0,33 s) déjà jugé rédhibitoire. À écrire tel quel dans l'article : **un score de
0,500 pile est un symptôme, pas un résultat** — c'est la signature d'un système
qui ne prend jamais une des deux décisions.

### Le prompt sait viser une autre dimension que la justesse

C'est le résultat qui a servi de déclencheur à la partie IV, et il mérite d'être
lu deux fois. Trois variantes visant non plus les pauses mais **la forme des
réponses**, mesurées sur les deux dimensions à la fois — justesse de détection,
et part des réponses portant le tic « je suis un grand modèle linguistique,
entraîné par Google » (32 % de la base) :

| variante | justesse | tic | verdict |
|---|---|---|---|
| 55 · `assistant_backchannel` offert comme porte de sortie | 0,744 | — | rejeté (−0,063) |
| 57 · lui donner une identité, sans dire ce qu'il est | 0,807 | 32 % | sans effet, ni sur l'un ni sur l'autre |
| **58 · tutoiement imposé** | 0,784 | **0 %** | **gardé** |

**Le tutoiement fait tomber le tic de 32 % à zéro, pour 0,023 de justesse** —
soit, sous le modèle de bruit corrigé le 02/09 (σ = 0,015 la passe, donc σ√2 ≈
0,021 pour l'écart entre deux passes), **un écart qui ne sort pas du bruit**. La
lecture prudente est donc : le tic tombe, et la détection ne bouge pas de façon
mesurable. « Je suis un grand modèle linguistique »
est une formule apprise, au registre formel : imposer le tutoiement oblige à
reformuler, et le modèle sort de sa phrase toute faite.

**L'identité, elle, ne marche pas.** Proposée trois fois dans la journée sur ce
symptôme précis, testée deux fois (0,668 en rejeu, puis 0,807 sans le moindre
effet sur le tic) : elle ne corrige rien. Ce qui corrige est une **contrainte de
registre**, pas une déclaration d'identité. À garder pour l'article : c'est la
différence entre dire au modèle *qui il est* et lui interdire *comment il
parle*.

Enfin, la variante 55 n'a **pas pu être départagée** : les relances vides
qu'elle vise sont à zéro sur les sessions de rejeu, alors qu'elles étaient à 5
sur 16 en session réelle. Elle reste ouverte, et ne se jugera qu'en direct — ce
qui est déjà un indice du trou de mesure décrit en partie IV.

### Interlude : mesurer, et d'abord mesurer sa mesure

C'est la partie qui donne sa crédibilité au reste, et elle vaut d'être écrite
comme telle plutôt que reléguée en annexe.

- **Le prompt qu'on lit n'est pas celui qu'on envoie** : deux conventions pour la
  même chose, invisibles dans les fichiers de configuration, +0,07 une fois
  trouvées en extrayant ce qui partait réellement sur le réseau.
- **On mesurait le réseau, pas le prompt** : même code, même session, 0,762 puis
  0,691 — le rejeu en temps réel faisait sauter des ticks. La moitié des verdicts
  rendus jusque-là étaient des indécidables. Corrigé par une horloge virtuelle.
  *Avant de mesurer une amélioration, mesurer le bruit de la mesure.*
- **Une seule session ne mesure rien** : passer à deux sessions fait tomber la
  base de 0,762 à 0,634 sans qu'une ligne change. La dimension « se taire »
  était quasi invisible, et c'est la pire.
- **Le goulot n'est pas toujours le modèle** : cinq réponses sur treize étaient
  « je ne comprends pas » parce que l'ASR rendait `tu te cheins`. La borne haute
  à ASR parfait le confirmait — mais le chiffre publié, 0,820, ne décrit plus la
  configuration actuelle et doit être refait (partie IV).
- **Refroidir avant chaque passe** : 12,07 s à froid contre 16,4 s à chaud pour
  le même fichier. Toute mesure sans refroidissement est fausse.
- **Trois scores identiques au millième sont un signal d'alarme** — mais pas
  toujours une mesure morte, et la nuance a été payée deux fois. À l'aller : il
  a fallu quatre tentatives pour évaluer les variantes 55/57/58, les trois
  premières rendant 0,715 au millième — les patchs ne touchaient que `systeme`
  quand la session utilise `systeme_sherpa` ; le lanceur avait perdu la variable
  qui choisit les sessions ; et une assertion échouait **sans rien écrire** dans
  une sortie qu'on ne lisait qu'à partir de la ligne suivante. Le lanceur le dit
  maintenant tout seul. Au retour, le 02/09 : la variante « détection pure » rend
  0,772 **trois fois au millième**, et c'est légitime — sans texte libre à
  générer, la sortie fait dix tokens à température 0, donc le rejeu redevient
  parfaitement déterministe. Il a fallu le **prouver** (elle diffère de la
  variante qui partage son schéma, et de celle qui partage ses exemples) plutôt
  que de l'affirmer. Corollaire précieux : **le bruit résiduel du banc vient du
  texte des réponses, pas de la détection.**
- **Une consigne en français ne contraint pas un modèle ; le schéma, si.** La
  première variante « détection seule » demandait explicitement de ne rendre que
  le marqueur : le modèle a quand même produit une réponse dans **23 décisions
  sur 39**. Il a fallu retirer le champ du schéma JSON pour que la variante
  mesure ce qu'elle annonçait — après quoi, 0 sur 33. **Toute variante qui
  prétend supprimer une sortie se vérifie dans la trace, jamais dans le prompt.**
- **Une variante ratée peut monter le score, et c'est le pire des cas.** Cette
  même variante, consigne contredite par ses propres exemples, rendait **0,849**
  — au-dessus de la base *et* au-dessus de DuplexCascade. Elle ne mesurait rien
  de ce qu'elle annonçait. Un bon chiffre n'est pas une validation de la mesure ;
  c'est même le moment où l'on vérifie le plus.
- **Le score d'un système muet est plausible, pas absurde.** Un prompt qui ne
  rend que le marqueur tombe dans le cas « parler sans texte » : le pipeline ne
  prend jamais la parole et le banc rend **0,500**. C'est le piège du candidat 59
  en pire — là, 0,500 pile sautait aux yeux ; ici il aurait pu passer pour un
  résultat. Corrigé dans le **harnais** et non dans le prompt, avec un texte de
  remplissage calé sur la médiane exacte des réponses de la base (55 caractères)
  pour ne pas changer la durée de parole simulée.
- **Sur une mesure qui décide d'une architecture, deux résultats concordants
  valent mieux qu'un seul rapide.** Le délai avant le premier son de piper a
  demandé quatre tentatives, dont trois fausses et mutuellement contradictoires :
  l'une relançait piper et chronométrait son chargement, une autre abandonnait
  avant que la synthèse ait commencé (son délai d'attente de silence était plus
  court que le délai du premier échantillon), une troisième lisait le PCM de la
  phrase précédente resté dans le tube. **Les trois menaient à une décision
  d'architecture différente**, et l'une d'elles avait fait écrire que le TTS
  n'était pas le goulot — ce qui était faux.

#### Quatre pièges de plus, tous du 03/09

- **Une mesure peut être vide sans qu'on le voie.** La première tentative sur le
  suffixe `×{n}` a rendu un écart **nul** — six passes, le même chiffre au
  millième sur les deux dimensions et sur chaque session prise à part. Pas
  « petit » : nul. La cause a été trouvée dans la trace : **le repliage ne se
  déclenchait que 13 fois sur 1 362 ticks de silence.** Deux verrous se cachaient
  l'un l'autre — le critère exigeait « il parle encore » quand 84 % des silences
  sont étiquetés « il réfléchit », et le rappel du tour tuait 92 % du reste.
  **Les deux avaient été ajoutés séparément, chacun mesuré, leur interaction
  jamais.** C'est un défaut de méthode en soi, pas une subtilité de la variante :
  *deux mécanismes qui touchent au même champ doivent être mesurés ensemble au
  moins une fois.*
- **La fourchette de référence était périmée, et personne ne l'avait vu.** Le
  contrôle est retombé à 0,796 au lieu des 0,808–0,816 attendus, sans qu'on sache
  lequel des quatre commits récents coûte la fin de tour manquante. Voir
  l'avertissement en tête de fichier. *Le contrôle n'est pas une formalité : ce
  jour-là, c'est lui seul qui a signalé la régression.*
- **`finish_reason` valait la peine d'être tracé.** Ajouté le matin (`cd5aac8`)
  parce qu'un schéma contraint garantit la grammaire de chaque jeton mais pas que
  la génération aille au bout. Le soir même, il expliquait une décision perdue en
  session : `finish_reason = length`, `max_tokens = 60`, JSON coupé en plein mot
  à `{"m": "<|user`. **La troncature ne coûte pas la fin de la phrase : elle
  coûte la décision entière**, puisque le JSON devient illisible. Onze fois sur
  897 chez gemini. `max_tokens` a été retiré ; le garde-fou est désormais le
  `TIMEOUT`, qui limite le **temps** — la bonne grandeur dans une boucle à 1,2 s,
  et qui rend une erreur franche au lieu d'un JSON tronqué.
- **`maxLength` dans un schéma JSON n'est pas respecté à la lettre, mais il
  influence fortement.** Mesuré le 03/09 : à limite de 200, la réponse fait
  4 231 caractères — et pourtant aucune limite → 7 995 caractères, 200 → 4 231,
  80 → 1 515, **sans jamais casser le JSON**. C'est donc un levier réel bien que
  non contraignant, ce qui est un objet curieux et vaut d'être dit : *le schéma
  contraint la forme, mais une borne numérique y agit comme une suggestion
  statistique.* Essayé puis retiré sur décision d'Alex — on ne limite plus rien
  du tout, comme les chercheurs, chez qui la longueur est apprise des données.
  Le levier qui reste est le **prompt** : la consigne « courte » tenait les
  réponses à 57 caractères contre 77 sans elle.

### Les trois bugs que ni la mesure ni la relecture n'ont vus

À écrire sans l'adoucir, parce que c'est le contrepoint de tout ce qui précède.
Le 29/08 au soir, **trois bugs graves** ont été trouvés dans la synthèse vocale :

1. **`aplay` ne se terminait jamais.** Avec piper résident, le tube ne se ferme
   plus ; `aplay` attend indéfiniment, et `speaking()` — qui teste « est-ce
   qu'`aplay` tourne » — répond vrai pour le reste de la session. Sur la session
   `134719` : **neuf « coupures » sur treize prises de parole, dont huit APRÈS la
   fin de la phrase**, dont une phrase de 3,4 s « coupée » 18,5 s après son
   début. Le système se croyait en train de parler en permanence, donc chaque mot
   d'Alex déclenchait une coupure, et l'état « je parle » envoyé au décideur était
   faux tout du long. Ce qui a rendu l'absurdité visible est un chiffre :
   l'avancement médian dans la phrase au moment de la coupure valait **100 %**.
2. **La phrase coupée mangeait la suivante.** Après un `stop()`, piper garde le
   PCM interrompu et le sert au prochain `aplay` : on entend la fin de
   l'ancienne, puis le silence qui suit ferme `aplay` et la nouvelle ne sort
   jamais. Le compteur de génération censé l'empêcher était inopérant.
3. **Le découpage tranchait au milieu des mots.** Le détecteur de fin de phrase
   (0,35 s sans PCM) se déclenchait entre deux morceaux — le risque n° 1 écrit
   noir sur blanc dans la revue du candidat 60, et qui s'est produit exactement
   comme annoncé.

**Aucun des trois n'a été trouvé par la mesure ni par la relecture. Les trois
l'ont été par l'oreille d'Alex, en session réelle.** Et la raison est
structurelle, pas anecdotique : la classe `Speaker` était la **seule sans
couverture**, parce que le banc et les tests de fumée tournent en `--muet` et
n'exercent donc que sa doublure silencieuse. C'était aussi la classe la plus
modifiée de la journée.

La leçon n'est pas « il faut plus de tests », elle est plus précise : **le rejeu
déterministe, qui est notre meilleur outil, achète sa reproductibilité en
débranchant la seule partie du système qui produit un effet physique.** Le banc
mesure une décision ; il ne peut pas entendre. Un test qui exerce `Speaker` pour
de vrai a été ajouté à la fumée, et il a attrapé le bug n° 2 dès sa première
exécution.

### Et trois de plus le 03/09 — le motif se confirme, et il a un nom

Trois bugs, tous invisibles en rejeu, **tous trouvés parce qu'Alex écoutait**.
Le motif n'est plus une anecdote de journée : c'est une propriété de notre
dispositif de mesure, et l'article doit la nommer.

1. **`_delta` devenait sourd, et c'est le pire des trois.** Un ASR en flux
   *complète* son dernier mot au fil de la reconnaissance — `M'ENTEND` devient
   `M'ENTENDS` — et en français les élisions rendent le phénomène permanent. Le
   dernier mot vu ne peut donc pas servir d'ancre : les trois ancrages rataient,
   et le repli comptait le même nombre de mots des deux côtés, donc rendait
   **zéro**. Résultat en session : **quarante secondes de conversation morte**,
   pendant lesquelles le modèle n'a jamais rien reçu d'autre que `SALUT TU M'`.
   Et il répondait « il parle encore » à chaque tick — **ce qui était la bonne
   réponse à ce qu'il voyait**. Correctif en deux temps : ancrage complet puis
   sur les mots stables (`2c3de52`), puis alignement gauche-droite par
   `difflib.get_matching_blocks` au lieu d'une recherche depuis la fin, qui
   s'accrochait à la mauvaise occurrence dès qu'un mot se répétait (`160affb`).
   Le filet compte désormais des **caractères** et non des mots — `m'` →
   `m'entends` ne gagne aucun mot mais sept caractères. **Rejeu de la session
   cassée : 1 prise de parole → 18.** `tests/delta.py` est passé de 7 à 20 cas.
2. **Le TTS passait par un tube brut**, protocole que personne d'autre n'utilise.
   Détaillé en partie I.
3. **Les deux backchannel étaient dans l'`enum` du schéma mais pas dans le code
   qui lit la réponse.** `lire_controle` ne testait que quatre marqueurs sur six :
   le modèle avait donc parfaitement le droit de les choisir — et il les
   choisissait — mais la décision tombait en « hors format » et **était jetée**,
   alors que le catalogue promet qu'ils sont « ramenés à *ne prends pas la
   parole* ». Un signal d'écoute n'est pas une prise de parole : c'est
   `reflechit`. *Un `enum` qui offre plus de valeurs que le code n'en traite est
   un piège silencieux, et il ne se voit que sur la trace d'une session réelle.*

**Ce que ça dit, et c'est bon pour l'article** : notre meilleur outil — le rejeu
déterministe — achète sa reproductibilité en figeant l'entrée. Or les trois bugs
du 29/08 venaient de la **sortie physique** (`Speaker`, débranché en `--muet`) et
celui du 03/09 vient de l'**entrée en flux** (`_delta`, dont le rejeu ne rejoue
que des transcriptions déjà stabilisées). **Le banc mesure ce qui se passe entre
les deux, et il est structurellement aveugle aux deux bouts.** C'est la
formulation générale, et elle vaut mieux que « il faut plus de tests ».

Corollaire opérationnel, déjà appliqué deux fois avec succès : **quand un bug de
bout est trouvé en session, on en fait un cas de test unitaire et on rejoue la
session cassée en comptant les prises de parole.** 1 → 18 sur `_delta`, 13/13 à la
fumée sur le TTS. C'est la seule boucle qui rattrape ce que le banc ne voit pas.

## III. Tout capteur devient du texte

- **La preuve d'existence est déjà là** : `SILENCE` est un VAD textualisé, occupant
  le même emplacement qu'un mot. Les autres capteurs n'en sont que des instances.
- **La généralisation** : prosodie (« sa voix retombe » — le signal humain de fin
  de tour, et notre pire dimension), nombre de voix, ambiance sonore, caméra
  (présence, regard), contexte gratuit (heure, agenda, domotique).
- **Pourquoi ça n'est possible que sans fine-tuning** : ajouter un sens est
  ajouter une ligne, pas une campagne d'entraînement et de collecte.
- **Les deux règles qui décident si ça tient** : un capteur n'écrit que quand il
  change ; un capteur écrit dans la trace, sinon il n'est pas rejouable donc pas
  mesurable.
- **L'architecture d'extension** (idée n° 10) : producteurs contre
  transformateurs, MQTT comme transport, Home Assistant comme premier écosystème
  déjà installé, et les capteurs coûteux déportés sur une autre machine.
- **Anecdote à garder, parce qu'elle dit quelque chose du travail au long
  cours** : le 02/09, Alex a redemandé une architecture modulaire pour les
  capteurs — sans se souvenir qu'elle était déjà spécifiée, transport compris,
  au § 10 d'`IDEES.md`. Un parking d'idées n'a de valeur que s'il est relu ; le
  même oubli se répète en partie IV, en plus coûteux.
- **Docker : non pour le cœur, oui pour les modules déportés** (décision du
  02/09, arbitrage d'Alex). La couche entre un conteneur et `/dev/snd` tomberait
  exactement sur la zone la plus fragile du système — une journée entière a été
  passée sur ALSA : `aplay` sans `-D` qui échoue en silence, le HDMI, le tampon —
  pour résoudre un problème d'installation qu'un script et un `requirements` figé
  règlent à 90 %. **Les modules distants, eux, n'ont pas d'audio du tout** : la
  vision, la génération d'image, la recherche web n'ouvrent aucun périphérique
  son, tournent déjà sur une autre machine, et sont donc de bons candidats. La
  ligne de partage n'est pas « conteneur ou pas », c'est **« touche au matériel
  ou pas »**. Détail et réserves en `IDEES.md` § 13.

→ *La boucle se referme sur la partie I : le prompt est relu 50 fois par minute,
donc chaque capteur retombe sous le budget de départ.*

## IV. Où on en est, et ce qui reste ouvert

Chiffres honnêtes en regard : 0,858 pour DuplexCascade, **0,816 pour nous** au
02/09 — et ce dernier chiffre est **en cours de remplacement**, voir
l'avertissement en tête de fichier.

0,816 est la moyenne de **cinq passes**, sur les deux sessions, de la
configuration telle qu'elle était le 02/09 : sherpa-onnx à deux threads,
`systeme_sherpa` avec la consigne « courte » et le tutoiement imposé, découpage
TTS, horizon 20 micro-tours, `gemini-2.5-flash-lite`.

⚠️ **Trois de ces cinq éléments ont été retirés le 03/09** — le découpage TTS, la
consigne « courte », le tutoiement. Le dernier état mesuré, trois passes, donne
**0,824 en TOR fins, 0,149 en TOR pauses, 0,837 en justesse**, et il n'est pas
encore commité. Tout ce qui suit dans cette partie a été écrit contre 0,816 : les
raisonnements de méthode tiennent, **les chiffres sont à repasser**.

### Le chiffre du projet est 0,816, et 0,826 était le haut de la distribution

Corrigé le 02/09, et c'est la correction la plus importante de ce fichier.
Cinq passes de la même configuration, à harnais identique, sur les mêmes deux
sessions :

    0,826 · 0,791 · 0,826 · 0,813 · 0,826
    moyenne 0,816 · σ 0,015 · étendue 0,035

**0,826 est la valeur la plus fréquente, et c'est le haut de la distribution.**
Elle avait été retenue parce qu'elle revenait ; ça n'en fait pas une moyenne. Le
chiffre à publier est **0,816 ± 0,015 sur cinq passes**, et le nombre de passes
fait partie du chiffre.

Ce n'est pas de la coquetterie statistique : c'est exactement le détail qui
décrédibilise un article quand un lecteur refait la mesure et tombe sur 0,791.

**Et le modèle de bruit change avec lui.** Le ±0,017 annoncé depuis le rejeu
déterministe est confirmé — mais comme **écart-type d'une passe**, pas comme
étendue. Conséquences arithmétiques, à tenir dans tout le texte :

- une passe unique peut légitimement s'écarter de la moyenne de 0,035 ;
- l'écart entre **deux** passes uniques a pour écart-type σ√2 ≈ **0,021** ;
- donc un écart de 0,03 entre deux mesures d'une passe vaut ~1,4 σ : **il n'est
  pas concluant**, contrairement à ce que la règle de lecture du journal
  (« un gain de 0,03 est désormais interprétable ») laissait croire.

**À revérifier avant publication, et c'est inconfortable** : les verdicts rendus
sur une seule passe avec un écart inférieur à ~0,04 ne sont pas établis sous ce
modèle. Dans le tableau des sept changements gardés, **deux sont dans ce cas** —
`<\|no voice\|>` → `is thinking` (+0,025) et sherpa (+0,05, à ~2,4 σ, limite).
Ça ne dit pas qu'ils sont faux ; ça dit qu'ils sont non conclusifs tant qu'ils
n'ont pas été repassés. Les gros écarts — la phrase sur la casse (+0,063 /
−0,103), l'historique en JSON (+0,07) — ne sont pas concernés.

⚠️ **`PLAN.md` demande de « retomber sur 0,826 » comme preuve de non-régression
après l'extraction de la bibliothèque.** Sous ce modèle de bruit, une passe
unique à 0,791 est parfaitement compatible avec un code intact : le critère doit
être une moyenne de passes contre 0,816 ± 0,015, sinon il déclenchera de fausses
alertes. À signaler à qui tient ce fichier.

### En face de DuplexCascade

| session | justesse | fins | pauses ratées | coupures | latence vécue |
|---|---|---|---|---|---|
| `073852-sherpa` | 0,784 | 6/8 | 4/22 | 2 | 3,55 s |
| `032332-sherpa` | **0,873** | 8/9 | 1/7 | 2 | 3,75 s |
| moyenne de cette passe | 0,826 | 14/17 | 5/29 | 4 | |
| **moyenne des cinq passes** | **0,816 ± 0,015** | **13,8/17** | **5,2/29** | | |
| DuplexCascade | 0,858 | 0,955 | — | — | 1,2 s |

**Quatre points d'écart avec un Qwen2-7B fine-tuné cinq heures sur huit H100.**
Le point de départ du même matin était 0,634.

Quatre précautions à tenir, et elles ne sont pas négociables dans le texte :

- **On revendique la moyenne des passes, pas la meilleure passe** — et surtout
  pas 0,873, qui est la meilleure session de la meilleure passe. Une session ne
  mesure rien (résultat n° 6) ; une passe non plus.
- **0,824 n'est pas notre chiffre** : c'est celui de llama-3.3-70b, un modèle
  qu'on écarte. **0,807 non plus**, désormais : c'était la configuration retenue
  d'avant le tutoiement, sur une seule session et une seule passe.
- **La justesse ne va jamais seule** : c'est le résultat établi n° 9, et il est
  né sur cette même série de mesures. On publie 0,816 **avec** ses deux TOR —
  fins 0,812, pauses 0,179.
- **Aucune borne haute n'est citée**, pour la raison exposée plus bas.

### Le chemin, en sept changements gardés

C'est le tableau qui porte la thèse de l'article : ce que le prompting et
l'ingénierie de mesure ramassent quand on ne peut pas entraîner.

| | gain |
|---|---|
| rejeu déterministe (horloge virtuelle) | bruit ±0,071 → ±0,017 |
| horizon 20 micro-tours | contexte ÷ 2, score inchangé |
| `<\|no voice\|>` après réponse → `is thinking` | +0,025 |
| historique de l'assistant en JSON | +0,07 |
| sherpa-onnx à la place de whisper | +0,05 et latence ÷ 12 |
| `systeme_sherpa` (la phrase sur la casse) | +0,063 |
| tutoiement imposé | tic 32 % → 0 % |

⚠️ **Le tableau a vieilli en un jour, et il faut le dire dans l'article.** Le
03/09, le tutoiement a été **retiré du prompt à la demande d'Alex**, sans mesure
préalable — comme la consigne « courte » la veille. Deux des sept changements
gardés ne sont donc plus dans le code, dont un dont l'effet était chiffré (tic de
formulation 32 % → 0 %, réponses de 68 à 43 caractères). *Un changement retiré
n'est pas un changement neutre : son retrait est lui-même à passer au banc.*
Et une huitième ligne attend d'y entrer : **le rappel du tour en cours retiré**,
+1 fin de tour sur 17, reproduit trois fois sur trois, 14 % de tokens en moins.

⚠️ **Deux lignes de ce tableau ne survivent pas au modèle de bruit corrigé** :
+0,025 et +0,05 ont été mesurés sur une passe unique, quand l'écart entre deux
passes a pour écart-type ~0,021. Elles sont **non conclusives**, pas fausses. À
repasser en trois passes avant publication — le tableau n'a de valeur que si
chacune de ses lignes tient.

**Le premier n'est pas une amélioration du système, c'est une amélioration de la
mesure** — et sans lui, aucun des six autres n'aurait été décidable, puisque le
bruit valait quatre fois ce qu'on cherchait. À dire dans cet ordre dans
l'article : la première chose qu'on a réparée est l'instrument.

Et le dernier ne se lit pas sur l'axe de la justesse : il la fait même **baisser
de 0,023**. Il a été gardé sur une seconde dimension, comptée séparément. C'est
le fil qu'on tire ci-dessous.

**Le défaut apparu avec la vitesse s'est refermé sans qu'on sache pourquoi.**
Les coupures de parole étaient nées du passage à sherpa — le système répond en
3,55 s au lieu de 5,55 et devient enfin assez rapide pour couper quelqu'un :
9 coupures avec `systeme_sherpa`, puis 5 dans la comparaison des décideurs,
contre 2 pour whisper. La configuration retenue en compte **2 par session**,
soit le niveau de whisper, à latence inchangée. Aucun des changements gardés
depuis ne visait les coupures. **À ne pas revendiquer comme un correctif** :
c'est un effet de bord non expliqué, entre le tutoiement, le découpage TTS et le
passage aux deux sessions. À isoler avant d'en écrire quoi que ce soit — **et
deux des trois suspects ont depuis été retirés du code**, donc la mesure qui
l'isolerait est à refaire de zéro.

Et la question ouverte, posée à la communauté : le décideur est le dernier étage
qui n'est pas local.

Sur la cible, poste par poste : ASR 4,3 s → 0,25 s, TTS 8,0 s → ~0 s, décideur
0,7 s inchangé. **Environ 13 s → environ 1 s.** Trois précautions à tenir dans le
texte :

1. ce total est une **somme de postes, pas une mesure de bout en bout** ;
2. le poste TTS ainsi ramené à ~0 est le **coût de chargement du modèle**, pas le
   délai avant le premier son : piper résident synthétise toujours la phrase
   entière avant de rendre la main, et le délai avant le son se compte en
   centaines de millisecondes (partie I). Trois chiffres différents circulent
   pour ce délai, voir la réserve ci-dessous ;
3. la constante d'estimation de la durée de parole reste fausse d'un facteur
   trois sur le Pi (partie I).

**Règle de publication** : aucun chiffre de bout en bout n'entre dans l'article
avant d'avoir été mesuré de bout en bout sur une session rejouée. Les sommes
poste par poste restent dans le journal.

### Le pivot : on a mélangé deux tâches

**Alex, le 02/09 : « on a mélangé deux concepts — détecter qu'une phrase est
finie, et décider quoi répondre ».** C'est la remarque qui réorganise tout ce qui
précède, et probablement le cœur de la partie IV de l'article.

Le système fait aujourd'hui les deux dans **un seul appel** : le même modèle, le
même prompt, le même tick, rendent à la fois un marqueur de tour de parole et,
le cas échéant, le texte à dire. Ça n'a jamais été décidé — c'est hérité de
DuplexCascade, où le fine-tuning rend les deux indissociables. Nous, nous ne
fine-tunons pas : rien ne nous obligeait à les garder ensemble.

**Attention à l'ordre du récit.** Trois faits établissent d'abord qu'on
confondait deux tâches et qu'on n'en mesurait qu'une ; la mesure qui a suivi
montre ensuite que le mélange **aide** la détection. L'article doit tenir les
deux : le mélange n'était pas une erreur, mais il était **non examiné**, et son
coût était payé au mauvais endroit.

Trois faits pour poser le problème, **tous tirés de nos propres données** :

**1. Notre métrique ne mesure qu'une des deux tâches.** Full-Duplex-Bench se lit
en **TOR** — le taux de prise de parole (*take-over rate*), compté séparément
sur les pauses, les fins de tour et les interruptions. Ce que ça note est
**quand le système parle**, jamais ce qu'il dit. Le 0,816 et les sept
changements gardés portent donc **sur la détection seule**.
La qualité des réponses, elle, n'a jamais été mesurée — pas une fois. La limite
était écrite depuis le début (`RESULTATS.md`, « Limites » : *« nous avons mesuré
le comportement de tour de parole, pas la qualité des réponses »*), mais elle y
était lue comme une modestie de portée, pas comme un angle mort.

Le corollaire est inconfortable et il faut l'assumer dans l'article :
**n'importe lequel des sept changements gardés a pu dégrader les réponses sans
qu'on le voie.** L'historique en JSON, l'horizon ramené à 20 micro-tours, le
prompt `systeme_sherpa` — tous modifient ce que le modèle a sous les yeux au
moment de rédiger, et aucun n'a été jugé là-dessus.

**2. Les deux axes sont empiriquement indépendants, et nous l'avions mesuré sans
le voir.** Le tutoiement imposé fait tomber le tic de formulation de **32 % à
0 %** pour 0,023 de justesse de détection — un écart qui, sous le modèle de bruit
corrigé le 02/09, **ne sort pas du bruit**. Une intervention qui déplace
complètement une dimension sans qu'on puisse mesurer d'effet sur l'autre. Nous
l'avons gardée pour cette raison précise, et nous n'en avons pas tiré la
conclusion d'architecture sur le moment.

**3. Le coût est payé à 92 % par la mauvaise tâche.** Compté le 02/09 sur la
trace de la session réelle `20260829-134719` (Pi 3B, sherpa, `flash-lite`,
212 s) :

| | |
|---|---|
| décisions | **159** |
| dont prises de parole | **13, soit 8,2 %** |
| tokens d'entrée | **109 029** (dont 100 085, 91,8 %, sur des ticks muets) |
| tokens de sortie | **1 756** (dont 1 460, 83 %, sur des ticks muets) |
| latence médiane | **0,465 s** (p90 1,009 s, max 2,492 s) |
| budget de tick | 1,2 s |

Chiffres relus directement dans `sessions/20260829-134719/session.jsonl`. Une
réserve, sans effet ici : cette session **précède les trois correctifs de
`Speaker`**, donc ses « coupures » sont fausses (bug n° 1). Les décisions, les
jetons et les latences, eux, ne dépendent pas de ce bug.

**Neuf ticks sur dix consomment un prompt de génération de réponse pour ne rien
dire.** Le prompt entier — les douze exemples, l'historique, les consignes de
registre, tout ce qui n'existe que pour bien répondre — est payé à chaque tick,
50 fois par minute, alors que la sortie utile de 92 % d'entre eux tient dans un
choix parmi **six** valeurs d'énumération.

C'est le même chiffre que le déséquilibre structurel de la conversation déjà
noté au § 7 de `RESULTATS.md` (« neuf ticks sur dix sont "elle parle encore" »),
mais lu du côté de la facture au lieu du côté du score. Il y avait servi
d'avertissement de mesure ; il devient ici un argument d'architecture.

#### L'anecdote qui fait le sel de l'histoire

**L'intuition dormait dans nos propres notes depuis plusieurs jours.**
`IDEES.md` § 1 bis, à propos d'un tout autre sujet — faut-il traduire la
transcription en anglais avant de la donner au modèle ? — on lit :

> « Sauf à traduire dans le même appel — mais alors on demande deux tâches au
> modèle, ce qui est exactement ce qui pose déjà problème. »

Écrite, jamais relue, jamais poussée jusqu'à la question d'architecture qu'elle
contenait. Elle y est restée plusieurs jours. C'est le deuxième oubli du même
genre dans la même journée (voir partie III : le § 10 d'`IDEES.md` spécifiait
déjà l'architecture modulaire qu'Alex a redemandée le 02/09).

Pour l'article, c'est mieux qu'une anecdote : **le parking d'idées a produit la
bonne phrase et l'a enterrée**, parce qu'elle était rangée sous la mauvaise
rubrique. Un fichier d'idées bien tenu n'est pas une garantie de relecture.

#### La réponse est tombée le 02/09 : oui, le mélange aide la détection

La question ouverte a été mesurée le soir même, et **elle est tranchée dans le
sens qui dérange**. Deux sessions, `gemini-2.5-flash-lite`, rejeu `--muet`,
trois passes par variante :

| | TOR fins ↑ | TOR pauses ↓ | justesse |
|---|---|---|---|
| **base** — détection et réponse dans le même appel | **0,812** (13,8/17) | 0,179 | 0,816 |
| **C** — détection seule, réponses encore dans les exemples | 0,745 (12,7/17) | 0,103 | 0,821 |
| **B′** — détection pure, consigne + exemples + schéma retirés | **0,647** (11/17) | 0,103 | 0,772 |

**−0,165 de TOR sur les fins de tour, soit près de trois fins ratées sur
dix-sept.** Préparer la réponse aide bel et bien à décider si le tour est fini.
L'argument implicite de DuplexCascade était juste, et il vaut aussi sans
fine-tuning.

#### Mais le résultat qui fait l'histoire est le décomposé

C'est ici que la mesure devient intéressante, parce que « retirer la réponse »
est en réalité **deux changements distincts** : ne plus la calculer, et ne plus
en montrer dans les exemples. La boucle interdit de bouger les deux ensemble,
donc ils ont été séparés :

| ce qu'on retire | effet sur TOR fins |
|---|---|
| la génération seule (base → C) | **−0,067**, ~1 fin de tour sur 17 |
| les réponses des exemples **en plus** (C → B′) | **−0,098**, ~1,7 de plus |
| les deux (base → B′) | **−0,165**, ~2,8 fins sur 17 |

**Ce qui aide n'est pas de calculer la réponse : c'est de savoir à quoi elle
ressemblerait.** Les trois cinquièmes de l'effet viennent des exemples, pas de
l'acte de générer. Et c'est la bonne nouvelle pour l'architecture : **un
détecteur séparé reste jouable**, à condition de lui laisser des exemples qui
montrent à quoi ressemble une fin de tour *répondable*. Des exemples ne coûtent
rien à l'exécution — ils sont dans le préfixe, donc dans le cache.

Le premier écart (−0,067) est à ~2 σ : réel dans son sens, faible dans son
ampleur. Le second et le total sont hors de tout doute.

Pour l'article, c'est la formulation à garder, parce qu'elle survit au cas
particulier : **le prompt n'a pas besoin que le modèle fasse la seconde tâche,
il a besoin qu'il l'ait en tête.** Même famille que la phrase sur la casse — une
affirmation sur ce que le modèle va rencontrer pèse plus lourd que le travail
qu'on lui demande.

#### Et l'agrégat n'a rien vu — sur la mesure censée trancher l'article

La variante C rend **0,821 contre 0,816** pour la base. Lu sur la justesse
seule : « aucun effet, la séparation est gratuite ». Sa détection de fin de tour
est pourtant **six points plus basse**.

Le mécanisme, et il est mécanique : un système qui rate des fins de tour parle
moins ; parlant moins, il intervient moins dans les pauses ; et la seconde
moitié du score **le récompense d'avoir échoué sur la première**.

C'est l'établi n° 9, et il vaut d'être raconté à cet endroit précis de
l'article : le piège annoncé au § 7 de `RESULTATS.md` — « le mutisme ressemble à
de la sagesse » — nous a repris **sur la mesure qui devait trancher le sujet de
l'article**. Rien ne protège d'un piège de mesure, sinon de compter les deux
classes séparément à chaque fois, y compris le jour où on croit ne mesurer qu'un
détail d'architecture.

#### Ce que ça débloque quand même

Le verdict le plus lourd du projet reste à refaire. `RESULTATS.md` § 3 classe
les LLM locaux du Pi « inutilisables » : SmolLM2-135M à **7,64 s**,
SmolLM2-360M à 15,16 s. **Mais ce verdict a été rendu sur 48 tokens de sortie.**
La détection demande un choix parmi six valeurs — une sortie de dix tokens,
mesurée.

**Le verdict est donc à refaire sur la tâche séparée**, et il n'est acquis
d'avance dans aucun sens : le débit mesuré (6,3 tok/s) ne dit rien du coût du
*prompt processing*, qui domine sur une entrée de plusieurs centaines de tokens
— et le résultat ci-dessus impose de **garder les exemples**, donc un prompt qui
ne rétrécit pas beaucoup. C'est l'entrée, pas la sortie, qu'il faut mesurer sur
le Pi, et ça n'a jamais été fait.

**Le coût de la séparation, à ne pas cacher.** En cascade, le tick où l'on
répond paie les deux appels au lieu d'un. Ordre de grandeur : ~0,7 s contre
0,465 s aujourd'hui. ⚠️ **Estimation, pas mesure** — les latences des variantes
mesurées sont fictives, puisqu'aucune ne fait le second appel. Et 8,2 % des ticks
seulement sont concernés : un surcoût rare contre un allègement permanent.

#### Statut : ce qui est établi et ce qui reste ouvert

**Établi** : la métrique ne couvre qu'une des deux tâches ; les deux axes
bougent indépendamment ; 92 % du coût est payé par des ticks muets ; le mélange
aide la détection de 0,165 de TOR fins, dont les trois cinquièmes viennent des
exemples et non de la génération ; l'agrégat seul ne voit rien de tout ça.

**Ouvert** : qu'un modèle local tienne la tâche réduite sur le Pi (à mesurer sur
le traitement du prompt, pas sur le débit de sortie) ; et la seconde dimension,
qui n'a toujours aucune mesure — le seul indicateur de qualité de réponse jamais
compté reste la part de réponses portant le tic de formulation (32 % → 0 %).
C'est aussi ce qui laisse la variante 55 (les relances vides) indécidable.

**Mise à jour du 03/09** : la mesure Qwen apporte un élément à la seconde
dimension sans l'avoir cherché — le tic de formulation est à **0 % chez Qwen**
contre 32 % chez gemini avec la même consigne, donc *c'est un trait du modèle et
non du prompt*. Et le retrait de « courte » le ramène de 4 % à 30 % chez gemini
**sans déplacer d'un iota la justesse de détection** (0,824 en TOR fins des deux
côtés). Deuxième démonstration, indépendante de celle du tutoiement, que **les
deux axes sont mesurablement disjoints**.

Réserves à reprendre telles quelles dans l'article : **17 fins de tour et 29
pauses, c'est peu** — une fin de tour vaut 0,059 de TOR, donc les écarts sont
donnés à ±1 tour près. Et « détection seule » emporte **trois** changements à la
fois : plus de génération, plus de réponses dans les exemples, plus de réponses
dans l'historique. Les deux premiers ont été séparés ; le troisième ne peut pas
l'être, un détecteur pur n'ayant rien à se rappeler.

Hypothèses, protocole et suite : `IDEES.md` § 11.

### Troisième chiffre à trancher : le délai avant le premier son

Repéré le 02/09 en relisant le journal, non résolu. Trois valeurs coexistent
pour la **même grandeur** — le délai jusqu'au premier échantillon d'un piper
déjà résident :

- **806 ms** pour une phrase de 41 caractères (mesure de 13 h 58, qui sert de
  base à la décomposition des « 2 s avant le son ») ;
- **2 805 ms** pour une phrase de 41 caractères (mesure de 14 h 08, celle qui a
  décidé du découpage) ;
- **2 890 ms** pour la phrase entière en `medium`, ramenée à 1 135 ms découpée
  (même mesure de 14 h 08). ⚠️ *La branche « découpée » n'existe plus depuis le
  03/09 ; seule la valeur pleine phrase reste dans le périmètre.*

Un facteur 3,5 sépare les deux premières, à dix minutes d'intervalle et à
longueur de phrase identique. Deux explications possibles, et **le journal ne
tranche pas** : soit les deux machines (`shiao` et le Pi, dont le rapport de
puissance est justement d'environ trois — partie I), soit le fait que le chiffre
de 13 h 58 est l'une des **trois mesures fausses** que le journal de 14 h 08
décrit et remplace, dont précisément celle qui « abandonnait avant que la
synthèse ait commencé » — un mode d'erreur qui sous-estime.

Conséquence à assumer : **la décomposition des « 2 s avant le son » repose sur
un chiffre possiblement périmé.** La conclusion de cette mesure — ce n'est pas
le tampon ALSA — tient quand même, parce qu'elle vient de la comparaison des
quatre tailles de tampon et pas du poste piper. Mais la répartition des postes
ne peut pas être publiée telle quelle. À refaire en une passe, sur une machine
nommée.

**Et la question s'est simplifiée le 03/09 sans être résolue.** Depuis le retrait
du découpage, il n'y a plus qu'une grandeur à mesurer et elle a un nom exact :
**le délai entre la fin de l'appel au modèle et le premier échantillon envoyé au
haut-parleur, pour la phrase entière, piper résident.** Une seule mesure, sur une
machine nommée, la remplacerait toutes. Le commit `5d9e0e4` avance ~0,2 s sur
`shiao` et ~2,9 s sur un Pi 3B pour une longue phrase — **ce sont des ordres de
grandeur annoncés dans un message de commit, pas la mesure attendue ici.**

### À trancher avant publication : la borne haute à ASR parfait est périmée

`bench/JOURNAL.md` donne **0,820** comme borne haute à ASR parfait. La
comparaison des décideurs donne **0,824** à llama-3.3-70b avec un ASR réel. Un
ASR réel ne peut pas dépasser un ASR parfait. Les deux mesures ne portent donc
pas sur la même base.

**Et la configuration retenue a depuis atteint cette borne : 0,816 ± 0,015 sur
les mêmes deux sessions que le 0,820, avec un ASR réel** — trois passes sur cinq
la dépassent. L'objection n'est plus seulement qu'un modèle écarté fait mieux que
la borne : c'est nous, et à ASR imparfait. La contradiction est donc tranchée
dans un sens : **le 0,820 est mort comme borne haute**, et il ne reste plus qu'à
en mesurer une vraie.

Ce qui diffère est établi, et tient en trois points :

- **Le nombre de sessions.** 0,820 est mesuré sur deux sessions : 15 fins de
  tour sur 17, 7 pauses ratées sur 29. 0,824 l'est sur la seule `073852` : 7
  fins sur 8, 5 pauses sur 22.
- **Le prompt.** 0,820 date du commit `e892a9f`, donc d'avant le catalogue à un
  prompt par moteur et d'avant la phrase sur la casse, qui vaut +0,063 avec
  sherpa.
- **Le décideur.** La borne haute a été mesurée avec `flash-lite`, pas avec
  llama.

**0,820 est périmé comme borne haute de la configuration actuelle.** Le chiffre
n'est pas faux : il a cessé d'être comparable. Il ne décrit ni le prompt, ni la
base de sessions d'aujourd'hui.

Ce qui manque pour lever la contradiction : rejouer
`sessions/20260829-073852-parfait/` avec la configuration retenue, et publier ce
score. Le matériau est là, la mesure ne l'est pas.

Un piège à prévoir avant de la refaire. Avec un ASR parfait, le texte est
ponctué. `systeme_sherpa` affirme le contraire, et cette affirmation fausse
coûte −0,103. La borne haute doit donc être mesurée avec `systeme`, sans quoi
elle mesurera surtout le mensonge de la phrase sur la casse.

**Tant que ce score n'est pas refait, l'article ne cite aucune borne haute.**

### Tranché : la base sherpa était 0,807, pas 0,761

Cette contradiction-là est levée, et sa résolution vaut d'être racontée. Le
journal donnait « base sherpa 0,761 » pour les trois variantes sur les pauses et
« base sherpa 0,807 » pour les suivantes. Explication trouvée : **une série
précédente avait écrasé en silence une variante gagnante**, que la restauration a
rendue juste après. La base réelle de la configuration retenue était donc 0,807.

Conséquence corrigée en partie II : les trois échecs valent **−0,121, −0,092 et
−0,063**, et non −0,075, −0,046 et −0,017. La conclusion tient dans les deux
lectures — aucune n'améliore — mais l'amplitude était sous-estimée du simple au
double.

**Ce qu'il faut en écrire n'est pas le chiffre, c'est le mode de défaillance** :
un gain perdu sans bruit contamine tout ce qui est mesuré ensuite, et une base
doit être remesurée dès que le code bouge entre deux séries. C'est le pendant du
résultat n° 5 — après « mesurer le bruit de sa mesure », **vérifier que sa
référence est encore la bonne**.

### Le positionnement s'est déplacé deux fois dans la même semaine — 03/09

Trois définitions du projet en six jours, et elles ne diffèrent pas seulement
par le vocabulaire :

- **29/08** — un **compagnon vocal** : on lui parle, il répond.
- **02/09** — une **bibliothèque qui observe le tour de parole** : elle ne parle
  jamais, elle rend des transitions d'état décrivant l'utilisateur, et le
  développeur branche derrière le modèle de réponse qu'il veut
  (`SPEC-PIVOT.md` § 1).
- **03/09** — **« transformer un LLM en full-duplex »** : en entrée du texte
  horodaté, en sortie du texte ou une interruption (`SPEC-PIVOT.md` § 12, commit
  `9f928d8`, noté tel quel et pas encore tranché).

Le troisième déplacement n'étend pas le deuxième, il le contredit là où ça
compte : ce n'est plus **un composant qu'on branche**, c'est **une
transformation qu'on applique à un modèle**. La sortie reporte le texte de la
réponse — exactement ce que le § 1 avait écarté en posant que la bibliothèque ne
fait que la moitié amont.

**L'angle d'article, et c'est l'enchaînement des trois axes qui se referme sur
lui-même** : la contrainte matérielle — Pi 3B, 905 Mio, donc pas de fine-tuning
— a imposé le prompting ; et le prompting, à force d'être la seule variable
libre du projet, a fini par **redéfinir le produit**. Le déplacement de
positionnement ne vient pas d'une étude de marché, il vient d'une contrainte
d'exécution. C'est la version forte du « le prompt est notre fine-tuning » de la
partie II : ce que le prompt fabrique, ce n'est pas seulement un comportement,
c'est le périmètre de ce qu'on vend.

#### Les deux renversements du 03/09 vont dans le même sens : la fusion

Deux points de la spec du 02/09 sont renversés, et par la même logique.

1. **Détection et réponse restent dans le MÊME appel** (contre le § 9, qui
   faisait des trois modes une option et présentait le mode séparé comme la voie
   de la modularité). Ce renversement-là **est adossé à une mesure** : séparer
   coûte **−0,165 de TOR sur les fins de tour** (mesure du 02/09, détaillée plus
   haut). Le fusionné n'était donc pas un compromis qu'on tolérait faute de
   mieux : c'était le bon choix, et on ne le savait pas.
2. **Les backchannels, dans les deux sens, passent par le prompt** (contre le
   § 2, où l'`assistant_backchannel` avait été confié au second modèle au motif
   qu'émettre un « mhm » suppose de connaître l'aval). L'objection tombe
   mécaniquement dès que le modèle qui répond est celui qui observe. Ce
   renversement-ci **n'est pas mesuré** : c'est une conséquence logique du
   premier, pas un résultat.

**Ce que l'article doit en tirer** : la modularité qu'on croyait vertueuse
coûtait des points de justesse. Découper un système en organes propres est un
réflexe d'ingénieur, et il est ici **payé au comptant** — sur une tâche de
langage, une frontière d'architecture est aussi une frontière d'information, et
le modèle perd ce qu'on lui retire de l'autre côté. La formulation à garder est
celle déjà écrite plus haut : *le prompt n'a pas besoin que le modèle fasse la
seconde tâche, il a besoin qu'il l'ait en tête.* Le 03/09 en tire la conséquence
d'architecture qui manquait.

#### Ce qui est neuf, et n'existait dans aucune version : l'agrégateur

Une couche **derrière le STT**, avant que quoi que ce soit n'atteigne le modèle :
c'est là que vivraient le calcul du delta, le recollage des segments et la
révision. Aucune des trois définitions ne la mentionnait — elle apparaît le
03/09, et elle apparaît parce que la journée a été passée dedans (le bug `_delta`
de la partie II, quarante secondes de conversation morte).

Pour le récit, c'est une bonne illustration d'un motif récurrent du projet :
**un étage d'architecture qui se découvre en réparant un bug**, pas en dessinant
un schéma. Il n'a encore ni spec ni mesure.

#### La décision du 03/09 : sortir du dépôt pour tester la brique la plus élémentaire

Avant toute extraction de bibliothèque, un prototype isolé teste **une seule
question** : à partir du texte seul, décider si une phrase est complète ou non.
Pas de micro, pas d'ASR, pas de Pi.

Il vit **hors du dépôt microturn**, délibérément, pour que ses mesures ne se
mêlent pas à celles du projet — le fichier `RESULTATS.md` a déjà connu quatre
bougés de référence en une journée (voir l'avertissement en tête de fichier), et
une seconde source de chiffres portant sur une autre tâche est exactement ce
qu'il ne faut pas y ajouter.

**L'intérêt éditorial est qu'il réduit la thèse du projet à son os** : *la
détection de fin de tour se fait sur le sens, pas sur le son.* Tout le reste —
l'ASR en flux, les micro-tours à horloge fixe, le TTS, le budget de 905 Mio —
est de la plomberie autour de cette affirmation. Si elle tient sur du texte nu,
elle est démontrable par n'importe qui, sans matériel, en quelques lignes ; si
elle ne tient pas, aucun des sept changements gardés ne compte.

C'est aussi la première fois que le projet accepte de **mesurer quelque chose
qui n'est pas Full-Duplex-Bench**. À suivre : rien n'est mesuré à ce stade, la
décision seule est prise.

### Le prototype a changé le contrat de sortie : une probabilité, pas un booléen — 03/09 au soir

Le prototype isolé décidé dans l'après-midi (« phrase complète ou non, à partir
du texte seul », hors du dépôt) a produit sa première matière d'article le soir
même. Aucun score n'est disponible à ce stade : ce qui suit est de la méthode et
une décision de conception, pas un résultat.

#### Le jeu de test est fait de nos propres transcriptions, et il est gelé

**156 exemples en français, construits à partir des transcriptions réelles des
sessions déjà enregistrées du projet** — pas des phrases écrites pour
l'occasion. Les exemples « incomplets » sont de vraies troncatures d'ASR en
temps réel : *« salut est ce que tu m'ent »*, *« je voudrais que tu que tu te
choisisses un autre »*. Ils arrivent donc avec leurs fautes de transcription,
leurs répétitions et leurs mots coupés — c'est-à-dire dans le **régime réel du
système**, pas dans du français propre qu'il ne verra jamais.

**Le jeu est gelé dès qu'il est écrit, et le scorer aussi.** La boucle
d'amélioration n'a pas le droit de toucher à son propre juge. C'est un point de
méthode qui mérite sa place dans l'article, et il se dit en une phrase : **un
agent qui répare son jeu de test ne mesure plus rien.** Le motif est le même que
celui de l'interlude « mesurer, et d'abord mesurer sa mesure » de la partie II —
sauf qu'ici la règle est posée *avant* la première mesure au lieu d'être
découverte après.

#### La question d'Alex sur « Hi » a déplacé le contrat

Il a demandé s'il était normal qu'un « Hi » tout seul compte comme une phrase
finie. La réponse est oui, et elle oblige à écrire le critère en toutes lettres :
une salutation est un **acte de parole entier**, et **la longueur n'est pas le
critère**. Ce qui sépare complet d'incomplet, c'est qu'un complément soit
**syntaxiquement obligatoire** ou non.

Le jeu de test le montre à longueur égale — trois mots des deux côtés :

| complets | incomplets |
|---|---|
| « ça va » | « je m'appelle » |
| « et toi » | « tu sais » |
| « tu m'entends » | « c'est quoi ton » |

Une bonne illustration pour l'article, parce qu'elle démonte l'intuition
disponible (« court = pas fini ») en six exemples et sans une seule mesure.

#### Et derrière la question, le vrai problème : la vérité terrain est ambiguë

C'est le meilleur morceau. **Le même texte peut être les deux.** « ça va » est un
tour complet ici, et le début de « ça va faire trois ans que… » là. Sans
historique de la conversation et sans prosodie, la vérité terrain sur les
**fragments courts** est **intrinsèquement ambiguë** — ce n'est pas un étiquetage
mal fait, c'est une information qui n'est pas dans le texte.

D'où le problème de mesure, qui vaut bien au-delà de ce prototype : **un
étiquetage binaire force un choix arbitraire sur toute une zone.** Et une boucle
qui optimise la justesse binaire passe alors son temps à courir après du **bruit
d'étiquetage** plutôt qu'après la tâche — elle progresse sur le score en
apprenant nos arbitrages, pas la langue.

#### La décision : le détecteur rend une probabilité

**Le détecteur rend une probabilité que le tour soit fini, plus un booléen.** Ce
n'est pas un raffinement de confort : c'est ce qui **laisse la zone grise être
grise**. Le seuil devient un **réglage de l'hôte**, pas une propriété du
détecteur — celui qui construit l'application sait, lui, ce que coûte une coupure
de parole comparée à un silence de trop.

La décision converge avec deux choses déjà écrites, ce qui est plutôt bon signe :
`PLAN.md` § 3 posait déjà que « `confidence` n'est pas décoratif », et eot-bench,
la référence que le projet vise, a tout son intérêt dans le **balayage
seuil/latence**. Ce qui était une case à remplir « dès qu'on sait la produire »
devient la sortie principale.

**Conséquence directe sur la mesure**, à répercuter quand les chiffres arriveront :

- l'**AUC** remplace la justesse comme critère de comparaison entre variantes ;
- accompagnée de la **courbe seuil → (rappel sur les complètes, rappel sur les
  incomplètes)**, qui est la forme lisible du compromis pour l'hôte ;
- et d'un **diagramme de calibration**, sans lequel une probabilité n'est qu'un
  score déguisé.

#### La réserve de méthode : une probabilité demandée n'est pas une probabilité

À garder telle quelle dans l'article, parce que c'est un piège très répandu :
**demander en toutes lettres une probabilité à un LLM donne des valeurs mal
calibrées et grumeleuses** — il répond 0,9 ou 0,95, jamais 0,63. La voie propre
est de lire les **logprobs du jeton de décision** ; le repli est
l'**échantillonnage à température non nulle**, qui reconstruit une fréquence au
prix de plusieurs appels.

**Laquelle des deux voies marche effectivement sur `gemini-2.5-flash-lite` via
OpenRouter n'est pas encore connue — la mesure tourne.** Point ouvert, à
compléter ; ne rien en déduire d'ici là.

### L'agrégateur derrière le STT : l'étage neuf prend forme — 03/09 au soir

Séance de conception sur la couche identifiée le matin même (`SPEC-PIVOT.md`
§ 12) : ce qui vit **entre l'ASR et le modèle**. Rien de ce qui suit n'est
mesuré — c'est de la conception adossée à une relecture de code et à une
recherche bibliographique. Aucun chiffre nouveau n'entre ici.

#### La frontière stable/instable n'est pas à deviner : sherpa la donne déjà

Le réflexe était de reconstruire la stabilité avec un timer — « un mot qui n'a
pas bougé depuis N millisecondes est acquis ». En relisant `stt.py`, il s'avère
que l'information existe déjà et qu'elle est de meilleure qualité que ce qu'un
chrono pourrait produire : sherpa maintient d'un côté `fige` — les segments
fermés, que le décodeur ne reverra **jamais** — et de l'autre `get_result()`, le
segment courant, révisable à chaque bloc de 300 ms.

Le hic est ailleurs, et il est structurel : **`fige` ne se remplit qu'à
l'endpoint**, donc après 1,2 s (règle 2) à 2,4 s (règle 1) de silence. Un
décideur qui tourne à 1,2 s n'a, à l'instant où il décide, encore **rien** de
garanti. La certitude arrive après la décision qu'elle devait servir.

D'où une sortie à **trois tiers** et non deux :

| tier | source | garantie |
|---|---|---|
| `figé` | `fige` de sherpa | ne bougera plus, garanti par l'ASR |
| `probable` | segment courant, mots que le décodeur a dépassés et qui n'ont pas bougé depuis K blocs | heuristique de l'agrégateur |
| `provisoire` | la queue en cours d'écriture | change au bloc suivant |

**L'angle d'article** : le tier intermédiaire n'est pas une invention de
microturn. Trois moteurs l'ont fabriqué séparément, chacun sous un nom
différent — la `stability` de Google, le `stop_history_eou` de NVIDIA Riva, le
`PREFLIGHT_TRANSCRIPT` de LiveKit (déjà noté dans `PLAN.md`, section contrat
d'entrée). Quand quatre équipes qui ne se parlent pas ajoutent le même étage,
ce n'est plus une coquetterie d'implémentation, c'est que le contrat à deux
états est faux.

#### « Figé » ne veut pas dire « correct » — et c'est un piège de vocabulaire

Le tier `figé` a la meilleure garantie du lot, et cette garantie ne porte **pas**
sur la justesse : elle porte sur l'immuabilité. La règle 3 de sherpa coupe sur
une **durée d'énoncé continu, sans égard au contenu**, donc tôt ou tard en plein
milieu d'un mot — et ce qui est figé échappe définitivement à la révision. C'est
le cas déjà consigné le 03/09 : `SUMMARISE`, coupé pendant qu'il s'écrivait, a
laissé `SUM` dans le figé puis `ARISE` au segment suivant, et le transcript
portait « PLEASE SUM ARISE OUR DIALOGUE ». Reproduit hors de notre code : sherpa
seul, en flux, révise correctement `SUM` → `SUMMARI` → `SUMMARISE`.

Conséquence de conception : un agrégateur propre **met la règle 3 hors circuit**
et ferme lui-même. Le raisonnement est le même que celui qui a fait tomber
plusieurs mécanismes du projet — notre tour se ferme sur **la prise de parole**,
pas sur un chronomètre. Laisser à l'ASR un pouvoir de fermeture qu'il exerce sur
un critère qui n'est pas le nôtre, c'est accepter des dégâts irréversibles pour
un service qu'on ne lui demande pas.

Pour l'article, c'est une bonne phrase courte : **immuable et exact sont deux
propriétés différentes, et l'ASR ne garantit que la première.**

#### Le signal le plus important du projet est celui que l'ASR ne produit jamais

Troisième trouvaille de la relecture, et la plus contre-intuitive. Sherpa
n'émet un `partial` que **si le texte a changé** (`if txt and txt != vu`). Entre
le dernier mot prononcé et l'endpoint, il ne se passe donc **rien** : pas
d'événement, pas de battement, deux secondes de flux vide.

Or c'est exactement l'intervalle où se joue toute la thèse du projet. Le
décideur doit distinguer « il réfléchit » de « il a fini » — et le flux d'entrée
ne lui donne, dans les deux cas, rien du tout. **C'est donc l'agrégateur qui doit
fabriquer le battement**, depuis l'horloge audio : à intervalle fixe, émettre
l'état courant même quand le texte n'a pas bougé, et compter le silence.

Le paradoxe est joli et il est vrai : **la grandeur qui décide de la fin du tour
est la seule que le moteur de reconnaissance ne rapporte pas.** Il rapporte des
mots ; le silence n'est pas un mot. On retrouve, un étage plus bas, ce que le
projet a déjà écrit ailleurs : le vide informationnel doit être matérialisé pour
atteindre le modèle (c'est le rôle qu'occupe déjà `SILENCE` côté micro-tours).

#### Le cadre publié : notre débat n'était pas un débat, c'était un placement

Recherche du soir. Le modèle des **Incremental Units** (Schlangen & Skantze,
*A General, Abstract Model of Incremental Dialogue Processing*, EACL 2009 —
https://aclanthology.org/E09-1081/) définit trois opérations sur un flux
incrémental : **ADD**, **REVOKE** et **COMMIT**. Implémentations de référence :
Inprotk (Java, Baumann & Schlangen 2012) et ReTiCo (Python, Michael & Möller
2019).

Le cadre était déjà cité dans `SPEC-PIVOT.md` § 8 pour `revoke`. Ce que la
séance ajoute, et qui vaut pour l'article : **les deux options de design qu'on
opposait ne sont pas deux philosophies, ce sont deux placements du COMMIT du
même papier.**

- Retenir le texte jusqu'à ce qu'il soit sûr = **commit en amont**, chez nous.
- Tout émettre avec des révocations = **commit en aval**, chez le consommateur.

Ce n'est donc pas « le papier contre notre bricolage ». **L'agrégateur *est* le
point de commit** — le nommer ainsi transforme une question d'implémentation en
une décision d'architecture qui a un nom depuis 2009.

#### Ce qui tranche : notre consommateur ne sait pas défaire

Un REVOKE n'a de sens que si quelqu'un, en face, sait annuler ce qu'il a déjà
consommé. Notre aval est un LLM dont l'historique **est un prompt**. Il ne défait
pas : il se réécrit. Et un préfixe réécrit n'est plus le même préfixe — donc
plus cachable.

C'est l'argument concret pour le commit en amont, et il tient sans chiffre. **Ne
pas chiffrer le gain de cache** : ce serait une projection, pas une facture, et
le projet a déjà payé cher les sommes poste par poste présentées comme des
mesures de bout en bout.

À relier au point déjà noté dans `PLAN.md` (questions ouvertes, § recollage) :
**DuplexCascade n'a pas ce problème du tout**, parce que les chercheurs n'ont
pas de transcript du tour, seulement l'historique. La révision n'existe pas dans
leur monde. C'est une différence de plus entre « reproduire un papier » et
« brancher la même idée sur un ASR réel » — le motif de la partie I.

#### Ce que les moteurs exposent, et où ils s'arrêtent

- **Deepgram** est le seul à séparer proprement `is_final` (ce segment est figé)
  de `speech_final` (le tour est fini) — interim autour de 150 ms
  (https://developers.deepgram.com/docs/understand-endpointing-interim-results).
  C'est le précédent que notre contrat d'entrée reprend, à ceci près que le
  second signal, chez nous, c'est **nous** qui le produisons.
- **Google** ne sépare pas les deux, mais expose un signal `stability`.
- **Speechmatics** et **Soniox** ne font ni l'un ni l'autre.
- Deepgram a depuis sorti **Flux**, un STT vendu comme « conversationnel »,
  centré sur les interruptions
  (https://deepgram.com/learn/introducing-flux-conversational-speech-recognition).
  À surveiller pour le positionnement : le marché bouge vers l'endroit exact où
  le projet se place.

#### Deux écoles sur « que fait l'ASR pendant que l'agent parle » — et la seconde nous contredit

Point de recherche à présenter comme un débat ouvert, pas comme une évidence.

**École 1 — l'orchestrateur décide, le modèle ASR ignore tout.** Pipecat et
LiveKit traitent l'interruption et la suppression du backchannel **au niveau de
l'orchestrateur, pas du modèle**
(https://livekit.com/blog/turn-detection-and-interruption-handling). Chez
Pipecat, le processeur STT bufferise mais ignore l'audio jusqu'au frame
« started speaking », et finalise au « stopped speaking ». C'est notre règle du
§ 2 de `SPEC-PIVOT.md` : l'observateur ignore l'aval.

**École 2 — l'ASR sait ce que l'agent vient de dire.** Contre-exemple net :
Pipecat diffuse un `LLMContextAssistantTurnFrame` à la fin de chaque tour du
bot, qu'AssemblyAI consomme comme `agent_context`
(https://www.assemblyai.com/docs/voice-agents/pipecat-universal-3-5-pro). Là,
le moteur de reconnaissance **connaît l'aval**, et cela contredit frontalement
la règle qui commande tout notre § 2.

**Ce que l'article doit en faire** : ne pas défendre notre règle comme une
évidence de conception, mais comme un **choix** — pris sous la contrainte du
troisième axe (tout capteur devient du texte : un observateur qui ne connaît pas
l'aval se branche sur n'importe quoi), et payé par ce qu'on perd à ne pas savoir
ce que l'agent vient de dire. Le fait que le même framework, Pipecat, héberge
les deux écoles est l'argument qu'il n'y a pas de réponse tranchée dans l'état
de l'art.

#### Dette de sourçage : le § 7 renvoie ici, et ici il n'y avait rien

`SPEC-PIVOT.md` § 7 annonce « Recherche du 02/09, **sources dans
`ARTICLE-NOTES.md`** ». Vérifié ce soir : ni Deepgram, ni Soniox, ni
Speechmatics, ni Smart Turn, ni MaAI, ni eot-bench n'apparaissaient dans ce
fichier. Les conclusions de cette recherche circulent depuis dans `PLAN.md` et
`SPEC-PIVOT.md` **sans leurs liens** — c'est-à-dire sous une forme non
vérifiable. Un renvoi qui pointe vers rien est pire qu'une absence de renvoi : il
donne l'illusion que le travail de sourçage a été fait.

Liens reconstitués ce soir, à traiter comme **reconstitution et non comme la
source consultée le 02/09** (rien ne garantit que c'est la page qui avait été
lue) :

- Smart Turn (Pipecat/Daily) — https://github.com/pipecat-ai/smart-turn ;
  poids v3 : https://huggingface.co/pipecat-ai/smart-turn-v3
- MaAI (Kyoto) — https://github.com/MaAI-Kyoto/MaAI
- LiveKit Turn Detector — https://huggingface.co/livekit/turn-detector
  (modèle sous **LiveKit Model License**, plugin sous Apache-2.0 : c'est bien le
  modèle, pas le code, qui est enfermé)
- eot-bench — https://github.com/livekit/eot-bench (le seul lien qui existait
  déjà, dans `SPEC-PIVOT.md` § 7)
- Deepgram, `is_final` / `speech_final` —
  https://developers.deepgram.com/docs/understand-endpointing-interim-results

**Manquent toujours, et je n'invente pas d'URL** : les pages de documentation
Speechmatics et Soniox sur lesquelles reposait l'affirmation « ni l'un ni
l'autre ne séparent les deux signaux », ainsi que les trois projets cités dans
`PLAN.md` pour disqualifier l'append-only (`wyoming_streaming_asr`,
`RealtimeSTT`, le connecteur Pipecat/Soniox). Ces affirmations restent dans les
notes **sans source vérifiable** : à re-sourcer avant publication, ou à retirer.

**Et la leçon de méthode, qui a sa place dans l'interlude « mesurer, et d'abord
mesurer sa mesure »** : le projet a une règle stricte sur les chiffres — rien
n'entre sans mesure — et n'en avait aucune sur les **affirmations sur le monde
extérieur**. Résultat : « Deepgram est le seul moteur qui… » a circulé six jours
dans trois fichiers avec exactement le même statut épistémique qu'un chiffre
mesuré, sans jamais avoir été rattaché à quoi que ce soit. Une affirmation sur la
concurrence est une donnée comme une autre ; elle mérite le même régime que les
scores.
