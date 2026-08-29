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
  Gardé en vie, il rend le premier échantillon en moins de 10 ms. **Huit
  secondes par réponse, soit plus que tout ce que l'ASR avait gagné.**
  Le prix est architectural : on ne peut plus tuer piper pour couper la parole,
  donc on tue `aplay` seul et un compteur de génération fait jeter le PCM devenu
  sans objet.
- **Le défaut de constante qui ne se voit que sur la cible** : `ATTAQUE_S` et
  `DEBIT_CAR_S`, justes à 5 % sur un laptop, sous-estiment d'un facteur 3 sur le
  Pi. Le système se croit muet pendant qu'il parle encore.

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
- **Mais la portabilité se construit, elle n'est pas donnée** : le schéma JSON
  strict, qui est notre équivalent de ce que leur fine-tuning garantit, n'est pas
  portable — gpt-4o-mini répond 400 et on perdait 100 % des décisions. D'où une
  cascade de repli (strict → souple → `json_object` → rien) et un garde-fou qui
  vérifie chaque réponse contre l'énumération des sept marqueurs. Le prompt se
  transporte ; l'API sous laquelle il s'exécute, non.

### Où le prompting plafonne — et c'est mesuré

La partie qui empêche l'article d'être un plaidoyer. Défaut visé : 5 pauses
ratées sur 22, depuis une base à 0,761. Trois variantes, trois échecs :
une règle (« dans le doute, il n'a pas fini ») **−0,075**, un exemple
(fragment puis silence) **−0,046**, une définition resserrée −0,017.

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
  « je ne comprends pas » parce que l'ASR rendait `tu te cheins`. Borne haute à
  ASR parfait : 0,820.
- **Refroidir avant chaque passe** : 12,07 s à froid contre 16,4 s à chaud pour
  le même fichier. Toute mesure sans refroidissement est fausse.

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

→ *La boucle se referme sur la partie I : le prompt est relu 50 fois par minute,
donc chaque capteur retombe sous le budget de départ.*

## IV. Où on en est, et ce qui reste ouvert

Chiffres honnêtes en regard : 0,858 pour DuplexCascade, 0,761 pour nous, 0,820
comme borne haute à ASR parfait. Le nouveau défaut est né de la vitesse — neuf
coupures contre deux, parce qu'on répond maintenant en 3,55 s au lieu de 5,55.
Et la question ouverte, posée à la communauté : le décideur est le dernier étage
qui n'est pas local.

Sur la cible, poste par poste : ASR 4,3 s → 0,25 s, TTS 8,0 s → 0,01 s, décideur
0,7 s inchangé. **Environ 13 s → environ 1 s.** Deux précautions à tenir dans le
texte : ce total est une somme de postes, pas une mesure de bout en bout ; et le
0,01 s du TTS est le **délai avant le premier son**, pas la durée de synthèse —
la synthèse continue en tâche de fond, ce qui rend d'autant plus critique la
constante d'estimation encore fausse d'un facteur trois sur le Pi (partie I).

**Règle de publication** : aucun chiffre de bout en bout n'entre dans l'article
avant d'avoir été mesuré de bout en bout sur une session rejouée. Les sommes
poste par poste restent dans le journal.
