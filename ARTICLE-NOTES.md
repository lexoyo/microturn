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

### 8. Notre métrique ne couvre qu'une des deux tâches du système

Le système décide **quand parler** et **quoi dire** dans le même appel.
Full-Duplex-Bench ne note que la première : le 0,826 et les sept changements
gardés sont des résultats de **détection de fin de tour**, pas de qualité de
réponse — laquelle n'a jamais été mesurée. Ce n'est pas une réserve de portée,
c'est un angle mort, et il a une conséquence de coût : sur une session réelle
comptée le 02/09, **92 % des appels ne produisent aucune parole** et paient
pourtant le prompt complet. Développé en partie IV.

## Chiffres de référence

| | justesse | fins de tour | pauses ratées | latence |
|---|---|---|---|---|
| DuplexCascade | 0,858 | 0,955 | — | 1,2 s |
| microturn, base du 29/08 au matin | 0,634 | 11/17 | 11/29 | 5–7 s |
| **microturn, configuration retenue** | **0,826** | **14/17** | **5/29** | **3,55 / 3,75 s** |

Les deux lignes microturn portent sur les **mêmes deux sessions** (`032332` et
`073852`), rejouées en déterministe : elles sont comparables entre elles. La
ligne DuplexCascade ne l'est pas — c'est leur banc, leur corpus, leur mesure.

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
- **Découper la réponse avant de la synthétiser** (candidat 60, gardé). Puisque
  le coût est linéaire — mesuré à **≈ 330 ms fixes + 60 ms par caractère** — ne
  donner d'abord que les premiers mots divise d'autant le délai avant le son :
  **2 890 → 1 135 ms en `medium` (−61 %)**, 1 721 → 844 ms en `low`. Le gain
  vient de la longueur du premier morceau, pas du moteur.
- **Ce qui décide que la parole ne se troue pas : le ratio synthèse / audio.**
  `medium` synthétise **2,97 s pour 3,20 s d'audio, soit 0,93 — 7 % de marge** ;
  `low` est à 0,58. Sous 1, les morceaux suivants arrivent avant que le
  précédent ne finisse. **Décision d'architecture du 02/09 : le TTS est le
  goulot du Pi pour une raison structurelle, pas par lenteur.** Le Pi passe la
  chaîne complète à demi-fréquence (600 MHz, `RESULTATS-PI.md` §5) ; quand le
  CPU descend, le ratio de `medium` passe au-dessus de 1 et les morceaux
  n'arrivent plus à temps. ⚠️ **C'est une inférence, pas une mesure** : le lien
  throttling → ratio > 1 → trous audibles n'a jamais été mesuré directement. Le
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

### Le meilleur score n'est pas le nôtre

Trois décideurs, même session (`073852`), même ASR (sherpa, deux threads) :
llama-3.3-70b 0,824, gemini-2.5-flash-lite 0,807, gemini-2.5-flash 0,716.

`flash-lite` reste le défaut. L'écart de 0,017 avec llama vaut exactement le
bruit de mesure. En face : un coût par session de 0,016 $ contre 0,085 $, une
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
retenue était à 0,807 sur `073852` ; elle est depuis à **0,826 de moyenne sur
les deux sessions** (voir partie IV). Deux chiffres, deux bases : ne jamais les
mettre dans la même phrase sans dire laquelle.

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

**Le tutoiement fait tomber le tic de 32 % à zéro, pour 0,023 de justesse** — à
peine au-dessus du bruit de ±0,017. « Je suis un grand modèle linguistique »
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
- **Trois scores identiques au millième ne sont jamais un résultat** : c'est le
  signal que la mesure ne mesure rien. Il a fallu quatre tentatives pour évaluer
  les variantes 55/57/58, les trois premières rendant 0,715 au millième — les
  patchs ne touchaient que `systeme` quand la session utilise `systeme_sherpa` ;
  le lanceur avait perdu la variable qui choisit les sessions ; et une assertion
  échouait **sans rien écrire** dans une sortie qu'on ne lisait qu'à partir de la
  ligne suivante. Le lanceur le dit maintenant tout seul.
- **Sur une mesure qui décide d'une architecture, deux résultats concordants
  valent mieux qu'un seul rapide.** Le délai avant le premier son de piper a
  demandé quatre tentatives, dont trois fausses et mutuellement contradictoires :
  l'une relançait piper et chronométrait son chargement, une autre abandonnait
  avant que la synthèse ait commencé (son délai d'attente de silence était plus
  court que le délai du premier échantillon), une troisième lisait le PCM de la
  phrase précédente resté dans le tube. **Les trois menaient à une décision
  d'architecture différente**, et l'une d'elles avait fait écrire que le TTS
  n'était pas le goulot — ce qui était faux.

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

Chiffres honnêtes en regard : 0,858 pour DuplexCascade, **0,826 pour nous**.

C'est la moyenne de la configuration retenue — sherpa-onnx à deux threads,
`systeme_sherpa` avec tutoiement imposé, découpage TTS, horizon 20 micro-tours,
`gemini-2.5-flash-lite` — sur **les deux sessions** :

| session | justesse | fins | pauses ratées | coupures | latence vécue |
|---|---|---|---|---|---|
| `073852-sherpa` | 0,784 | 6/8 | 4/22 | 2 | 3,55 s |
| `032332-sherpa` | **0,873** | 8/9 | 1/7 | 2 | 3,75 s |
| **moyenne** | **0,826** | 14/17 | 5/29 | 4 | |
| DuplexCascade | 0,858 | 0,955 | — | — | 1,2 s |

**Trois points d'écart avec un Qwen2-7B fine-tuné cinq heures sur huit H100** —
et 0,873 sur une session, au-dessus de leur moyenne. Le point de départ du même
matin était 0,634.

Trois précautions à tenir, et elles ne sont pas négociables dans le texte :

- **On revendique la moyenne, pas 0,873.** Une session ne mesure rien : c'est le
  résultat n° 6, et l'oublier ici invaliderait tout le reste de l'article. La
  comparaison honnête est 0,826 contre 0,858.
- **0,824 n'est pas notre chiffre** : c'est celui de llama-3.3-70b, un modèle
  qu'on écarte. **0,807 non plus**, désormais : c'était la configuration retenue
  d'avant le tutoiement, sur une seule session.
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
passage aux deux sessions. À isoler avant d'en écrire quoi que ce soit.

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

Trois preuves que le mélange nous coûte, **toutes tirées de nos propres
données** :

**1. Notre métrique ne mesure qu'une des deux tâches.** Full-Duplex-Bench se lit
en **TOR** — le taux de prise de parole (*take-over rate*), compté séparément
sur les pauses, les fins de tour et les interruptions. Ce que ça note est
**quand le système parle**, jamais ce qu'il dit. Le 0,826 et les sept changements gardés portent donc **sur la détection seule**.
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
0 %** en ne coûtant que 0,023 de justesse de détection — l'équivalent d'un bruit
et demi. Une intervention qui déplace complètement une dimension sans presque
toucher l'autre. Nous l'avons gardée pour cette raison, et nous n'en avons pas
tiré la conclusion d'architecture sur le moment.

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

#### Ce que la séparation débloquerait

Le verdict le plus lourd du projet est peut-être à refaire. `RESULTATS.md` § 3
classe les LLM locaux du Pi « inutilisables » : SmolLM2-135M à **7,64 s**,
SmolLM2-360M à 15,16 s. **Mais ce verdict a été rendu sur 48 tokens de sortie.**
La détection seule demande un choix parmi six valeurs — une sortie d'une poignée
de tokens, avec un prompt qui peut se passer de tout ce qui sert à rédiger.

**Le verdict est donc à refaire sur la tâche séparée**, et il n'est pas acquis
d'avance dans un sens ni dans l'autre : le débit mesuré (6,3 tok/s) ne dit rien
du coût du *prompt processing*, qui domine sur une entrée de plusieurs centaines
de tokens et qui n'a jamais été mesuré séparément sur le Pi. Si ça passe, le
dernier étage distant redevient local — c'est la question ouverte de la partie I
qui se referme.

**Son coût, à ne pas cacher.** En cascade, le tick où l'on répond paie les deux
appels au lieu d'un. Ordre de grandeur : ~0,7 s contre 0,465 s aujourd'hui.
⚠️ **Estimation, pas mesure** — elle suppose un détecteur plus court que l'appel
actuel, ce qui reste à établir. Et 8,2 % des ticks seulement sont concernés :
c'est un surcoût rare payé pour un allègement permanent.

#### Statut : question ouverte, avec son protocole

**Rien n'est tranché.** Une mesure est en cours pour répondre à la seule question
qui décide : **le mélange apporte-t-il quelque chose à la détection ?** On peut
défendre que oui — un modèle qui sait ce qu'il s'apprêterait à répondre juge
peut-être mieux si le tour est fini. Tant que le chiffre n'existe pas, la
séparation reste une hypothèse, pas un résultat.

Protocole, dans l'ordre :

1. **Mesurer ce que le mélange apporte à la détection.** Rejouer les deux
   sessions avec un prompt de détection seule — mêmes six jetons, sortie réduite
   au marqueur, sans les consignes de rédaction. Si la justesse ne bouge pas
   au-delà de ±0,017, le mélange n'apportait rien à la détection et la séparation
   est gratuite du côté du score.
2. **Se donner une mesure de la seconde tâche**, qui n'existe pas. Le seul
   indicateur de qualité de réponse déjà compté est la part de réponses portant
   le tic de formulation (32 % → 0 %). Il en faut d'autres, et l'occasion de
   trancher enfin la variante 55 (les relances vides), qui reste indécidable
   parce qu'elle ne se manifeste qu'en session réelle.
3. **Alors seulement** refaire le verdict des LLM locaux sur la tâche de
   détection isolée, sur le Pi, à froid.

**Ce qui est établi** : la métrique ne couvre qu'une des deux tâches ; les deux
axes bougent indépendamment ; 92 % du coût est payé par des ticks muets.
**Ce qui est ouvert** : que la séparation soit gratuite, et qu'un modèle local
tienne la tâche réduite.

Hypothèses, contre-hypothèse et protocole complet : `IDEES.md` § 11.

### Troisième chiffre à trancher : le délai avant le premier son

Repéré le 02/09 en relisant le journal, non résolu. Trois valeurs coexistent
pour la **même grandeur** — le délai jusqu'au premier échantillon d'un piper
déjà résident :

- **806 ms** pour une phrase de 41 caractères (mesure de 13 h 58, qui sert de
  base à la décomposition des « 2 s avant le son ») ;
- **2 805 ms** pour une phrase de 41 caractères (mesure de 14 h 08, celle qui a
  décidé du découpage) ;
- **2 890 ms** pour la phrase entière en `medium`, ramenée à 1 135 ms découpée
  (même mesure de 14 h 08).

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

### À trancher avant publication : la borne haute à ASR parfait est périmée

`bench/JOURNAL.md` donne **0,820** comme borne haute à ASR parfait. La
comparaison des décideurs donne **0,824** à llama-3.3-70b avec un ASR réel. Un
ASR réel ne peut pas dépasser un ASR parfait. Les deux mesures ne portent donc
pas sur la même base.

**Et la configuration retenue a depuis dépassé cette borne : 0,826, sur les
mêmes deux sessions que le 0,820, avec un ASR réel.** L'objection n'est plus
seulement qu'un modèle écarté fait mieux que la borne — c'est nous. La
contradiction est donc tranchée dans un sens : **le 0,820 est mort comme borne
haute**, et il ne reste plus qu'à en mesurer une vraie.

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
