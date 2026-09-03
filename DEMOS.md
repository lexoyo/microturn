# DEMOS.md — les trois démos des chercheurs, comme cahier des charges

Ce fichier n'est pas une fiche de lecture du papier (ça, c'est `PAPIER.md`) ni
un relevé de format (`FORMAT-CHERCHEURS.md`). C'est **la liste de ce que leur
système sait faire en public**, transcrite mot à mot, pour servir de cible :
ce que microturn devra savoir refaire, et l'état d'aujourd'hui en face.

**Aucun chiffre de ce fichier n'est une mesure de microturn**, et une démo n'est
pas une mesure du tout — c'est une prise réussie, montrée par ses auteurs. Elle
dit ce que le système *peut* faire, jamais à quelle fréquence il le fait. Nos
mesures vivent dans `RESULTATS.md`, `RESULTATS-PI.md` et `bench/JOURNAL.md`.

## Sources

- **Page de démo** : https://sbintuitions.github.io/DuplexCascadeDemo/
- **Code** (licence MIT) : https://github.com/sbintuitions/DuplexCascade
- **Papier** : arXiv 2603.09180 — références complètes en `PAPIER.md` § 1

Les trois vidéos, telles que la page les titre :

| fichier | durée | titre sur la page |
|---|---|---|
| `basic_question_answering.mp4` | 1:43 | Multi-turn Question Answering |
| `user_backchannel_and_interruption.mp4` | 0:49 | User Backchannel and Interruption |
| `assistant_backchannel.mp4` | 1:30 | Assistant Backchannel |

La page ne porte qu'une seule légende, sous la troisième : *« Assistant's
Backchannel is shown in Blue color. »* Aucun modèle, aucune latence, aucun
réglage n'y est indiqué.

### ⚠️ Où sont les vidéos, et pourquoi pas ici

**Les trois `.mp4` restent dans `~/Downloads/`, hors du dépôt** — 62 Mio à eux
trois. Ce dépôt porte du code et des mesures ; il ne portera pas de vidéo. Ce
qui suit en est la seule trace versionnée.

### ⚠️ Ce que vaut ce transcript

**Il a été établi par Alex le 03/09/2026, à la lecture des captures d'écran des
vidéos.** Ce n'est donc ni un transcript officiel, ni une transcription
automatique de la bande son : c'est le texte affiché à l'écran, relevé à l'œil.
Suffisant pour travailler ; à revérifier à la source avant d'en citer une ligne
publiquement. Les mentions entre crochets sont les backchannels de l'assistant,
affichés en bleu dans leur interface.

---

# Les trois dialogues, verbatim

## 1. Multi-turn Question Answering
`basic_question_answering.mp4` — 1:43

**User** — Who wrote Harry Potter?

**System** — Harry Potter was written by J.K. Rowling.

**User** — What is the capital of Japan?

**System** — The capital of Japan is Tokyo.

**User** — What is the capital of France?

**System** — The capital of France is Paris.

**User** — What is the largest planet in our solar system?

**System** — The largest planet in our solar system is Jupiter.

**User** — What is the tallest mountain on Earth?

**System** — The tallest mountain on Earth is Mount Everest, which reaches an elevation of 8,848 meters (29,029 feet) above sea level.

**User** — Please summarize our dialogue.

**System** — Our dialogue covered several topics:

1. **Literary Inquiry**: You asked who wrote Harry Potter, and I replied that it was written by J.K. Rowling.
2. **Geographical Question**: Next, you wanted to know the capital of Japan, and I provided the answer: Tokyo.
3. **Another Geographical Query**: You then asked about the capital of France, and I confirmed that Paris is the capital.
4. **Astronomical Inquiry**: Lastly, you sought information on the largest planet in our solar system, and I informed you that Jupiter holds this title.

Each question was answered with a straightforward response, providing factual information on literature, geography, and astronomy.

---

## 2. User Backchannel and Interruption
`user_backchannel_and_interruption.mp4` — 0:49

**User** — Hi, I want to build a deep learning model. So could you explain what steps are needed?

**System** — Certainly! Building a deep learning model involves several key steps. Here's a general guide to help you get started:

1. Define the Problem- Understand the Task: Determine what you want your model to do (e.g., image classification, text generation, etc.).
- Collect Data: Gather relevant data that will be used to train and test your model.

2. Prepare the Data- Data Cleaning: Handle missing values, remove duplicates, and correct errors.
- Data Splitting: Divide your data into training, validation, and test sets.
- Data Preprocessing: Normalize or standardize data, encode categorical variables, and possibly augment the dataset to improve model performance.

3. Choose a Model Architecture- Select a Framework: Choose a deep learning framework like TensorFlow, PyTorch, or Keras.
- Design the Model: Decide on the type of neural network (e.g., CNN for images, RNN for sequences) and its architecture (number of layers, types of layers, activation functions).

**User** *(interruption)* — Okay, yes. Okay, please summarize in one sentence.

**System** — Building a deep learning model involves defining the problem, preparing the data, selecting an appropriate architecture, training the model, tuning hyperparameters, validating its performance, and deploying it for use.

---

## 3. Assistant Backchannel
`assistant_backchannel.mp4` — 1:30

**User** — Hello, how are you doing today?

**System** — *[Mhmm.]* Hello! I'm an AI and don't have feelings, but I'm here and ready to assist you with any questions or tasks you might have. How can I help you today?

**User** — Okay, what is the capital city of Japan?

**System** — *[Sure.]* The capital city of Japan is Tokyo.

**User** — Wow, actually, I'm currently planning a trip to Tokyo. So could you give me a one week travel plan?

**System** — *[Uh-huh.]* Absolutely! Here's a one-week travel plan for Tokyo:

Day 1: Arrival and Exploration
- Morning: Arrive at Narita or Haneda Airport. Take the Narita Express (N'EX) or Keikyu Line to Tokyo Station.
- Afternoon: Visit the Imperial Palace East Garden near Tokyo Station. Then head to Akihabara for electronics shopping and anime culture.
- Evening: Enjoy dinner in Shinjuku or Shibuya.

Day 2: Historical and Cultural Sites
- Morning: Visit Senso-ji Temple in Asakusa. Explore the surrounding markets.
- Afternoon: Take the train to Ueno Park, visit the Tokyo National Museum, and explore the Ueno Zoo.
- Evening: Head to the Tsukiji Outer Market for dinner.

**User** *(interruption)* — Okay, stop. Tell me the one Tokyo attraction you recommend the most and why in one sentence.

**System** — *[Gotcha.]* I would highly recommend visiting the Senso-ji Temple in Asakusa. It's not only one of the oldest and most iconic temples in Tokyo, but it also provides a unique glimpse into traditional Japanese culture and history. The vibrant atmosphere, beautiful architecture, and the experience of walking through the Nakamise Shopping Street leading up to the temple gates make it a must-visit attraction for anyone traveling to Tokyo.

---

# Ce qu'il faut avoir compris avant de relire ces transcripts

## 1. 🔴 La ligne d'interruption de la démo 2 contient **trois** actes de parole

Sans cette précision, le transcript se lit de travers. Cette ligne :

> **User** *(interruption)* — Okay, yes. Okay, please summarize in one sentence.

n'est pas une interruption. C'est une séquence de trois :

| ce qui est dit | quand | ce que le système doit faire |
|---|---|---|
| « Okay » | **pendant que le système parle** | **rien** — backchannel utilisateur, continuer |
| « yes » | **pendant que le système parle** | **rien** — backchannel utilisateur, continuer |
| « Okay, please summarize in one sentence » | ensuite | **s'arrêter** — vraie interruption |

**La démo teste les deux comportements coup sur coup, et c'est ce qui la rend
difficile : le même mot, « Okay », joue les deux rôles selon le moment.** Un
système qui déciderait sur le vocabulaire échoue forcément ici ; il faut décider
sur autre chose — longueur, position dans le flux, et surtout **contenu
propositionnel** de la ligne entière.

*Précision d'Alex, 03/09, à la lecture de la vidéo. Elle ne se déduit pas du
texte du transcript, qui aplatit les trois en une ligne.*

⚠️ *Une version antérieure de ce paragraphe listait aussi « l'état courant de
l'assistant » parmi les signaux nécessaires. Retiré le 04/09 : c'est de là
qu'est partie la grille fausse du § 4. L'état existe, mais il est chez l'hôte —
il ne sert pas à reconnaître un backchannel, seulement à déduire l'interruption.*

## 2. Les backchannels de l'assistant arrivent **en tête** de réponse

Dans la démo 3, les quatre réponses s'ouvrent toutes par un `[Mhmm.]`,
`[Sure.]`, `[Uh-huh.]`, `[Gotcha.]` — **avant** le contenu, jamais au milieu,
jamais pendant que l'utilisateur parle encore.

Et l'implémentation, qui est le détail utile si on veut reproduire : quand leur
LLM sort `<system backchannel>`, **ils jouent un clip audio pré-synthétisé tiré
au hasard**. Ce n'est pas du TTS à la volée.

⚠️ *Ce point vient du papier, mais pas d'une des sections relues à la source
(cf. `PAPIER.md` § 0 : seuls le Tableau 1 p. 3 et le § 4.4 p. 4 sont vérifiés).
Il porte donc la réserve générale, et est à confirmer dans le PDF avant
publication.*

Deux conséquences pour nous, si l'ablation le confirme :

- **côté coût, c'est presque gratuit** — un clip pré-enregistré ne passe pas par
  Piper, ne coûte ni CPU ni délai de synthèse sur le Pi 3B. Ça cadre avec l'axe
  « performance, ressources, matériel » au lieu de le contredire ;
- **côté décision, c'est le prix fort** — le jeton, lui, se paie. `PAPIER.md`
  § 6 : leur variante β, celle qui active les backchannels, rend **0,748**
  contre **0,858**, et **le TOR de pauses est multiplié par 5,9**. C'est-à-dire
  qu'elle casse exactement la dimension pour laquelle ce projet existe.

## 3. Leur propre système perd de l'historique, et ça se voit dans la démo 1

Comptage exact du transcript ci-dessus :

- **cinq questions factuelles** posées (Harry Potter, capitale du Japon,
  capitale de la France, plus grande planète, plus haute montagne), plus une
  sixième demande, « Please summarize our dialogue » ;
- **le résumé n'en restitue que quatre.** Le mont Everest — la plus récente des
  cinq — a disparu.

Pire que l'omission, la formulation : le résumé écrit *« **Lastly**, you sought
information on the largest planet »*, alors que Jupiter était l'avant-dernière.
Ce n'est pas une abréviation choisie, c'est une fin d'historique qui manque, et
le modèle l'ignore.

⚠️ **À vérifier sur la vidéo avant d'en tirer une conclusion publique** : le
transcript vient de captures d'écran (cf. plus haut), et une capture manquante
au bon endroit produirait exactement cette apparence. Vérifier que l'échange sur
l'Everest est bien à l'écran, dans la même session, avant la demande de résumé.

**Si ça se confirme, c'est un point d'article** : la limite de fenêtre n'est pas
un défaut propre à notre implémentation. Une démo choisie, montée et publiée par
les auteurs eux-mêmes perd un tour sur cinq dans son propre résumé, sur un
échange de 1:43. À écrire sans triomphalisme — c'est une limite de LLM en
cascade, partagée, pas une faiblesse de leur travail.

## 4. La grille — ce que chaque démo exige de nous

### ⚠️ Cette grille dit l'inverse de sa version du 04/09 au matin

**La version précédente (commit `30ce1e3`) donnait les démos 2 et 3 pour hors
d'atteinte**, au motif que `<user is interrupting>` ne sort jamais et que le
modèle ne sait pas qu'il est en train de parler — donc qu'il fallait d'abord
remplir la section `[etats]` du catalogue. **C'est faux, et ça l'était déjà
quand ça a été écrit.**

`SPEC-PIVOT.md` § 2, tranché le 02/09, disait déjà : *« Une interruption, c'est
un `speaking` reçu pendant que l'agent parle. La première moitié est une
observation, la seconde n'est connue que de l'appelant : c'est donc à l'appelant
de faire l'interprétation. »* La grille du matin a raisonné comme si le décideur
devait tout porter, en oubliant une règle posée deux jours plus tôt et
versionnée.

**Position arrêtée par Alex le 04/09, et c'est celle de la grille ci-dessous :
l'état de l'assistant n'a pas à entrer dans le modèle.** On a failli renoncer à
deux démos sur trois pour une contrainte qui n'existe pas. La trace est gardée
exprès : le raisonnement faux fait partie du projet.

### La grille

| démo | ce qu'elle exige | ce qui manque, précisément |
|---|---|---|
| **1. Multi-turn QA** | mémoire longue de l'historique, six tours, résumé fidèle en fin | **rien d'identifié comme bloquant — et rien de mesuré.** Le banc porte sur la décision de prendre la parole, pas sur la fidélité du contenu sur six tours. Rien à citer aujourd'hui |
| **2. User backchannel + interruption** | ignorer deux backchannels utilisateur **pendant** qu'on parle, puis s'arrêter à la vraie interruption — dans la même séquence | **une ligne de prompt et un ET logique dans l'hôte.** Pas un état à donner au modèle |
| **3. Assistant backchannel** | émettre `[Mhmm.]` en tête de réponse, plus une interruption en fin | **une ligne de prompt et un lecteur de clips dans l'hôte.** Le jeton existe, le code le ramène à « ne prends pas la parole » |

### L'état côté microturn, sans arrondir

**L'interruption se déduit dans l'hôte, et le jeton disparaît.** Un
`<user is speaking>` reçu pendant que l'hôte lit une réponse **est** une
interruption : l'hôte est le seul à savoir qu'il parle, et il le sait
exactement — par état interne, pas par inférence. On remplace un marqueur qui
ne sortait jamais par un ET logique déterministe. `<user is interrupting>` est
donc voué à être **retiré du catalogue** (`PLAN-REPRO.md`, étape 3.1). Rien à
ajouter dans l'entrée du modèle, et la règle de `SPEC-PIVOT.md` § 2 tient : ce
n'est pas l'observateur qui déduit, c'est l'appelant.

*Dépendance à ne pas perdre de vue* : cette déduction suppose que l'hôte sache
**jusqu'à quand** il parle. `ATTAQUE_S` et `DEBIT_CAR_S` sont faux d'un facteur
3 — l'état « je parle » s'y termine trop tôt. À corriger avant de mesurer quoi
que ce soit sur la démo 2 (`PLAN-REPRO.md`, étape 3.4).

**Le backchannel utilisateur se reconnaît au CONTENU, pas à l'état.** « okay »,
« yes », « mhm » sont des signaux d'écoute quel que soit le moment ; le modèle a
le texte, ça lui suffit. Ce qui manque n'est donc pas une information d'état
mais **une instruction**. Aujourd'hui les deux backchannels sont bien listés
parmi les marqueurs et glosés ligne à ligne, mais **glosés par le moment**
(`locales/en.toml:25` — *« a listening signal while you speak — ignore it, go
on »*), c'est-à-dire par une condition que le modèle ne peut pas évaluer. Aucune
ligne ne dit **quand en émettre**, et **aucun des sept exemples n'en montre un**
en sortie. Les définir par ce qu'ils sont, et non par le moment où ils tombent,
est le travail de l'étape 3.2.

*Ce que ça n'efface pas* : le § 1 ci-dessus reste vrai — un système qui
trancherait sur le **vocabulaire** échoue à la démo 2, puisque le même « Okay »
y joue les deux rôles. Décider sur le contenu veut dire sur le contenu
**propositionnel** de la ligne entière (« Okay » seul contre « Okay, please
summarize in one sentence »), pas sur la présence du mot.

**`<system backchannel>` n'est pas traité par le code, et là c'est un vrai
manque.** Il est ramené à `reflechit`, soit « ne prends pas la parole »
(`llm.py`, `lire_controle`) : même émis, il ne se passe rien. Eux jouent un
**clip audio pré-synthétisé tiré au hasard**. C'est du code d'hôte, pas du
prompt — étape 3.3.

Rappel de l'historique du code, pour ne pas republier une version périmée du
constat : les deux backchannels étaient **jetés** jusqu'au 03/09 —
`lire_controle` ne testait que quatre marqueurs sur six et toute décision qui en
choisissait un tombait en « hors format ». Corrigé au commit `b5a6652`.

### ⚠️ Un chiffre à recouper avant de le sortir du dépôt

Le relevé tracé est dans `bench/JOURNAL.md` : sur **897 décisions** (trois
passes, deux sessions sherpa, rejeu déterministe), le marqueur d'interruption
sort **0 fois avec `gemini-2.5-flash-lite`** — la configuration retenue — et
**27 fois avec Qwen**, qui est le modèle écarté. Même distribution pour le
backchannel utilisateur : **0 pour gemini**, 3 pour Qwen. Le 27 de Qwen n'est
pas un résultat du projet.

Trois précautions avant d'en citer une ligne :

1. **Ce 0/897 porte sur `<|user interruption|>`, l'ancien nom.** Il a été mesuré
   **avant** `d721c84`, qui a renommé les jetons. Le republier sous le nom
   d'aujourd'hui laisserait croire que la mesure a été refaite depuis. Elle ne
   l'a pas été.
2. **Le même commit a fait passer la fenêtre d'historique de 20 à 270 entrées**,
   sans mesure. Le constat « l'interruption ne sort jamais » est donc à
   **remesurer** avant d'être publié comme un résultat — même si tout laisse
   penser qu'il tiendra.
3. **Le « 0 fois sur 153 » qui circule dans `PLAN.md` n'a aucune session en
   face** : à rattacher à sa session ou à retirer, pas à citer.

Et de toute façon, avec la grille ci-dessus, **ce chiffre ne condamne plus
rien** : il décrit un jeton qu'on retire, pas une démo qu'on ne peut pas faire.

---

## Ce que ça donne comme file d'attente

Dans l'ordre, parce que chaque étape est la condition de la suivante. Le plan
détaillé est dans `PLAN-REPRO.md` ; ce qui suit n'en est que la lecture par
démo.

1. **Monter le banc des trois scénarios, et mesurer l'existant dessus**
   (`PLAN-REPRO.md`, étapes 1 et 2). Sans avant, aucune correction ne se juge.
   La démo 1 est la seule qui puisse tourner telle quelle aujourd'hui : c'est
   elle qui donne la première référence.
2. **Corriger la durée de parole** (`ATTAQUE_S`, `DEBIT_CAR_S`), puis **déduire
   l'interruption dans l'hôte** et retirer le jeton. C'est la démo 2, volet
   interruption, et elle ne demande rien au modèle.
3. **Réécrire les deux backchannels dans le prompt** — par le contenu, avec une
   consigne d'émission. C'est la démo 2, volet backchannel, et la moitié de la
   démo 3.
4. **Traiter `<system backchannel>` dans le code** — quelques WAV courts,
   générés une fois. C'est l'autre moitié de la démo 3.

Chaque correction se mesure **séparément**, sinon on ne saura pas laquelle a
payé. Et le backchannel assistant se mesure **avec et sans, sur les deux TOR
séparés** (`PAPIER.md` § 6) : chez eux il coûte 0,110 de justesse et multiplie
le TOR de pauses par 5,9 — *leur configuration phare n'en a pas*. Reproduire la
démo 3, c'est donc reproduire la variante β, pas celle qu'ils mettent en avant.
*(Inférence : la page de démo ne dit pas quelle configuration tourne dans quelle
vidéo — à confirmer.)*
