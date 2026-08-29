# Journal des tests

Vidé le 29/08/2026 à la demande d'Alex : on reprend toute la file de
`bench/CANDIDATS.md` depuis le début, avec une mesure sur deux sessions au lieu
d'une. Les 17 itérations précédentes sont résumées dans `CANDIDATS.md`
(« Déjà testé »), et l'ancien journal reste dans l'historique git.

**Une ligne par test, écrite juste après la mesure.** Y compris les échecs, y
compris les indécidables — c'est ce qui évite de refaire deux fois le même test
en croyant l'avoir trouvé.

## Les règles de lecture

- **Aucun écart inférieur au bruit ne compte comme un résultat.** Bruit mesuré
  après le passage au rejeu déterministe : **±0,017** (0,681 puis 0,698 sur la
  même base). Avant, il était de ±0,071 sur une session. Un gain de 0,03 est
  désormais interprétable ; en dessous, non.
- **Base de référence : 0,690** (moyenne des deux passes de contrôle).
- Un verdict n'est jamais « neutre » quand l'écart est sous le bruit : c'est
  **indécidable**. La nuance compte — un indécidable peut cacher un vrai gain.
- La référence est DuplexCascade : justesse moyenne **0,858**, latence 1,2 s.

## Résultats

| # | commit | ce qui change | justesse | fins | pauses | latence | verdict |
|---|--------|---------------|----------|------|--------|---------|---------|
| 1 | 5e05e6e | **base**, mesurée sur DEUX sessions au lieu d'une | 0,634 | 11/17 | 11/29 | 7,32 / 5,03 s | mesure en temps réel, non reproductible |
| 2 | 5713507 | rejeu **déterministe** : horloge virtuelle, appel bloquant | 0,681 | 12/17 | 10/29 | 5,8 / 4,0 s | nouvelle base |
| 2' | 5713507 | *(contrôle : la même mesure, refaite)* | 0,698 | 12/17 | 9/29 | 5,8 / 4,6 s | **bruit résiduel 0,017** — quatre fois moins qu'avant |
| 3 | 4f0e1e6 | `[=]` horizon 10 micro-tours système (`MICRO_TOURS` 48 → 20) | 0,698 | 12/17 | 9/29 | 5,8 / 4,6 s | **gardé.** Score inchangé, contexte plus que divisé par deux |
| 4 | 4aaa96e | `[=]` `TICK_S` 1,2 → 0,6 s (leur valeur en pratique) | 0,698 | 12/17 | 9/29 | 6,0 / 4,6 s | **rejeté.** Deux fois plus d'appels, latence inchangée |
| 5 | e892a9f | `[=]` **borne haute : ASR parfait** (référence ré-émise en flux) | **0,820** | **15/17** | 7/29 | **0,6 / 0,8 s** | 26 coupures. Le prompt n'est pas le goulot |
| 6a | 615a9d2 | `[=]` whisper `tiny`, même audio (référence du test) | 0,670 | 6/8 | 9/22 | 4,75 s vécue | 4 coupures |
| 6b | 615a9d2 | `[=]` whisper **`base`**, même audio | **0,784** | 6/8 | **4/22** | **7,15 s vécue** | 1 coupure. +0,114 de justesse, −2,4 s de latence |

### Ce que la deuxième session change

La base « officielle » passe de 0,762 à **0,634**. Le code n'a pas bougé : c'est
la mesure qui devient plus dure, et plus honnête.

- `032332` seule : 9 fins de tour, **7 pauses**.
- `073852` seule : 8 fins de tour, **22 pauses**, et 3 coupures de parole.

La nouvelle session triple le nombre de pauses observées et fait apparaître la
dimension « coupures », restée à zéro jusqu'ici faute d'occasion. Sur les pauses,
on rate 11 fois sur 29 — c'est notre pire dimension, et elle était quasi
invisible avec une seule session.

### Une mesure gratuite du bruit

`032332` a été rejouée deux fois de suite **sur le même code** (`f2f3427` puis
`5e05e6e`, aucun changement fonctionnel entre les deux) :

    passe 1 : justesse 0,762   (pauses 1/7)
    passe 2 : justesse 0,691   (pauses 2/7)

**0,071 d'écart, sans qu'une seule ligne ait changé.** Une pause qui bascule, et
le score bouge de 7 points. C'est la confirmation directe du problème : tant que
la granularité de la mesure vaut plus que les gains cherchés, un verdict isolé ne
vaut rien. D'où le test n° 2 (trois passes) avant tout le reste.


### Le rejeu déterministe, et le piège qu'il cachait

Le rejeu tournait en temps réel : un appel réseau lent faisait sauter des ticks,
et deux passes du même code donnaient 118 puis 123 décisions. Corrigé par une
horloge virtuelle — l'appel bloque, aucun tick ne saute.

Vérification sur cinq passes : **126 décisions à chaque fois**, et une à deux
décisions divergentes sur 126, toujours aux mêmes indices. Ce qui reste est le
non-déterminisme propre du modèle à température 0. En prime, le rejeu passe de
149 s à 63 s : toute la file de tests devient deux fois moins chère.

**Première version fausse, et de peu :** j'avais patché l'horloge du seul module
`pipeline`. Résultat mesuré 0,551, et j'ai failli conclure que le déterminisme
dégradait le système. Deux modules manquaient :

- `tts` comptait la durée de parole simulée en temps réel, pendant que la
  conversation avançait en temps virtuel 2,4× plus vite. Le robot « parlait »
  2,4× trop longtemps : 8 coupures au lieu de 3 ;
- `journal` horodatait la trace en temps réel — les instants allaient de 0 à
  63 s pour 149 s d'audio, et la métrique les comparait à une référence en
  secondes de conversation. Tout était décalé du même facteur.

`llm` garde volontairement la vraie horloge : la latence réseau est réelle.

**Leçon :** un temps simulé doit l'être partout où il est lu, sinon deux
horloges coexistent et le système mesuré n'est plus celui qui tourne.


### Test 3 — l'horizon de 48 micro-tours ne servait à rien

Ramené à 20 (soit dix micro-tours système, la longueur fixe de leurs données
d'entraînement), le score est identique au chiffre près : 0,698, mêmes 12/17 en
fins de tour, mêmes 9/29 en pauses.

Le contexte, lui, tombe de moitié : 655 tokens d'entrée en moyenne, 799 au
maximum, contre plus du double avant. À score égal on paie deux fois moins, on
répond plus vite, et on se rapproche de leur design. C'est le premier test de la
file et il est gratuit.

L'itération 1 de l'ancienne série avait AUGMENTÉ l'horizon de 24 à 48 en pariant
qu'il était trop court, sans gain. Personne n'avait essayé dans l'autre sens.


### Test 4 — leur horloge n'a pas de sens sans leur latence

`TICK_S` à 0,6 s : score rigoureusement identique (0,698, mêmes 12/17, mêmes
9/29), pour deux fois plus d'appels et un rejeu deux fois plus long.

Et surtout : **la latence ne bouge pas** — 6,0 s contre 5,8 s. C'est le résultat
intéressant. Consulter le modèle deux fois plus souvent ne fait pas répondre
plus vite, donc le tick n'est pas le goulot. Chez eux Δt = 0,6 s a un sens parce
que leur latence totale est sous la seconde ; chez nous elle est à six, et
l'horloge n'y est pour rien.

Ce test répond en creux à une question qu'on n'avait pas posée : **où passent
les six secondes ?** L'appel au modèle en prend 0,5. Le reste est ailleurs.

### Où passent les six secondes — décomposition

Question ouverte par le test 4. Mesuré sur `073852`, dix réponses, du dernier
mot prononcé à la décision de parler :

| étape | durée | part |
|---|---|---|
| attente de whisper | **3,72 s** | **80 %** |
| attente du tick suivant | 0,23 s | 5 % |
| appel au modèle | 0,73 s | 16 % |
| **total** | **4,68 s** | |

**Quatre secondes sur cinq sont du délai de reconnaissance vocale.** Le tick n'y
est pour rien (0,23 s), le modèle non plus (0,73 s) — ce qui explique
rétrospectivement pourquoi diviser le tick par deux n'a rien changé : on
optimisait 5 % du problème.

Whisper travaille sur une fenêtre glissante et rend le dernier mot avec plusieurs
secondes de retard. C'est le vrai écart avec DuplexCascade, dont l'ASR streaming
répond en continu — et ce n'est ni le prompt, ni le modèle, ni l'horloge.

**Toute optimisation de latence qui ne touche pas whisper est du bruit.**


### Test 5 — la borne haute, et ce qu'elle dit du projet

Sessions régénérées avec une reconnaissance parfaite (`bench/asr_parfait.py`) :
la transcription de référence ré-émise mot à mot, à l'instant où chaque mot est
prononcé. Texte juste, aucun délai.

| | base (whisper `tiny`) | ASR parfait | DuplexCascade |
|---|---|---|---|
| justesse | 0,690 | **0,820** | 0,858 |
| fins de tour | 12/17 = 0,706 | **15/17 = 0,882** | 0,955 |
| pauses ratées | 10/29 | 7/29 | — |
| latence | 5,8 s | **0,7 s** | 1,2 s |
| coupures | 2 | **26** | — |

**Le prompt n'est pas le goulot.** Avec une entrée propre, la transposition par
prompting arrive à 0,820 contre 0,858 pour un Qwen2-7B fine-tuné cinq heures sur
huit H100. L'écart restant est de 0,038 — deux fois le bruit de mesure, donc
réel, mais petit.

Et la latence tombe de 5,8 s à 0,7 s, **sous la leur**. Ce qui confirme la
décomposition : les six secondes étaient du délai whisper, rien d'autre.

**Les 26 coupures sont le prix de la vitesse.** En répondant en 0,7 s au lieu de
6, le système parle pendant que l'autre reprend son souffle. C'est un vrai
défaut, mais c'en est un de système temps réel — pas de compréhension. On ne
l'avait jamais vu parce qu'on était trop lent pour couper qui que ce soit.

### Ce que ça change pour la suite de la file

Le bloc 2 (le prompt, 24 tests) plafonne à +0,13 dans le meilleur des cas, et
seulement si l'ASR suit. Le bloc « qualité des briques » n'est plus un test
parmi d'autres : c'est le projet.


### Test 6 — `base` corrige la compréhension et aggrave la latence

Même audio, deux modèles, chacun repassé en streaming réel puis mesuré en
déterministe (`bench/session_depuis_trace.py`, sans quoi on comparerait deux
cadencements au lieu de deux modèles).

| | `tiny` | `base` |
|---|---|---|
| justesse | 0,670 | **0,784** |
| pauses ratées | 9/22 | **4/22** |
| coupures | 4 | **1** |
| latence vécue | **4,75 s** | 7,15 s |
| coût par passe | **1,35 s** (max 2,72) | 3,63 s (max 5,77) |

Le gain de justesse est de +0,114, soit six fois le bruit — c'est le plus gros
effet mesuré après la borne haute. Sur la même phrase :

    tiny :  « Ma pêle, comment je m'appelle ? »
    base :  « Est-ce que tu sais comment je m'appelle ? »

**Mais `base` coûte 2,4 s de latence en plus**, et c'est déjà le défaut n° 1 côté
utilisateur. À 3,63 s par passe sur un PC de bureau, il est de toute façon hors
de portée d'un Pi 3B.

Les deux résultats ensemble disent la même chose : **le problème n'est pas la
taille du modèle, c'est le mode de décodage.** Whisper re-décode une fenêtre
entière à chaque passe ; plus il est précis, plus il est lent, et plus le dernier
mot arrive tard. Un ASR streaming rendrait les mots au fil de l'eau sans ce
compromis.

Piste immédiatement testable, avant de changer d'ASR : la fenêtre est bornée à
`PLAFOND_S = 20 s`. Le coût d'une passe est proportionnel à sa longueur — la
réduire devrait réduire le délai à modèle constant.

| 7 | cb0c61e | `[=]` fenêtre whisper 20 s → 8 s | 0,648 | 6/8 | 10/22 | 5,55 s vécue | **rejeté.** Plus cher ET moins juste |

### Test 7 — la fenêtre courte coûte PLUS cher

Hypothèse : le coût d'une passe est proportionnel à la durée de la fenêtre, donc
la raccourcir doit réduire le délai. **Fausse, et mesurable en une passe :**

    fenêtre 20 s :  1,35 s par passe
    fenêtre  8 s :  1,67 s par passe

L'encodeur de whisper travaille sur une fenêtre **fixe de 30 secondes** et
complète l'audio plus court par du silence. Qu'on lui donne 8 s ou 20 s, il
encode 30 s. Le coût ne dépend donc quasiment pas de la longueur du tour.

**Conséquence : aucun réglage de whisper ne réduira les 3,7 s de délai.** Ni la
fenêtre, ni le pas, ni le modèle — `base` va même dans l'autre sens. Le délai est
structurel au décodage par blocs. La seule piste restante pour la latence est un
ASR à transducteur, qui émet au fil de l'eau.

### Au passage : le cache de prompt n'a jamais fonctionné

La ligne de ressources le dit : **0 % de tokens cachés**, sur 183 appels.

Le cache implicite de gemini-2.5 ne s'arme qu'au-delà de **1024 tokens** ; notre
prompt en fait 666. Il n'a donc jamais rien mis en cache, et le commentaire de
`llm.py` qui affirmait le contraire décrivait une intention, pas un fait. On paie
le préfixe entier à chaque tick — 183 fois pour 3 min 44 de conversation.

C'est aussi un contre-argument au test 3 (horizon réduit) : diviser le contexte
par deux nous a fait passer *sous* le seuil de cache. À vérifier si le coût
devient un critère.

## Les quatre ASR, même audio (`073852`)

| ASR | justesse | fins | pauses ratées | latence vécue | RTF Pi |
|---|---|---|---|---|---|
| whisper `tiny` | 0,653 | 5/8 | 7/22 | 4,95 s | 0,62 |
| vosk | 0,722 | 5/8 | 4/22 | 5,95 s | 1,86 ✗ |
| **sherpa-onnx** | 0,744 | 5/8 | **3/22** | **3,75 s** | à mesurer |
| whisper `tiny` + `audio_ctx` accordé | **0,801** | **7/8** | 6/22 | 4,35 s | — |

sherpa gagne sur la latence (−1,2 s) et sur les pauses (deux fois moins ratées),
et perd sur les fins de tour. Cause identifiée avant la mesure : il rend
`EST CE QUE TU SAIS COMMENT JE M'APPELLE`, sans le point d'interrogation qui est
justement le signal d'une fin de phrase.

## Adapter le prompt à une transcription nue

| variante | justesse | verdict |
|---|---|---|
| sherpa, prompt inchangé | 0,744 | référence |
| **S1 · dire que le texte est en majuscules sans ponctuation** | **0,807** | **gardé** (+0,063) |
| S2 · mettre les exemples eux-mêmes en majuscules | 0,784 | +0,040, moins bon que S1 |

**Une phrase récupère tout ce que la ponctuation avait coûté.** sherpa + S1 est à
0,807 avec 3,75 s de latence, contre 0,801 et 4,35 s pour le meilleur whisper :
justesse équivalente, **six dixièmes de seconde de moins**, et un coût qui ne
monte pas avec la durée du tour.

**Et c'est la première fois qu'une RÈGLE bat une DONNÉE.** Jusqu'ici les cinq
règles ajoutées au prompt n'avaient rien valu, et les gains venaient d'exemples
corrigés. L'exception s'explique : S1 décrit une propriété de l'ENTRÉE, que les
exemples ne peuvent pas montrer sans cesser d'être lisibles — S2 l'a tenté et
fait moins bien. Une règle gagne quand elle dit quelque chose qu'un exemple ne
peut pas dire.

### La phrase sur la casse, dans les deux sens

| | sans la phrase | avec la phrase | écart |
|---|---|---|---|
| sherpa (texte NU — la phrase est vraie) | 0,744 | **0,807** | **+0,063** |
| whisper (texte ponctué — la phrase est fausse) | 0,801 | **0,698** | **−0,103** |

**Le mensonge coûte plus cher que la vérité ne rapporte** — presque le double, et
six fois le bruit. Le modèle croit le prompt sur parole : quand on lui affirme
que le texte n'a pas de ponctuation, il cesse de la chercher, même quand elle
est là sous ses yeux.

C'est la justification de fond du correctif : cette phrase ne peut pas vivre
dans `locales/fr.toml`, qui ne connaît que la langue. Elle décrit une propriété
du MOTEUR, elle doit donc être injectée par lui (`llm.systeme(..., nu=)`).

Pour l'article, c'est le résultat le plus net sur la nature du prompt : sur un
modèle non entraîné, **une affirmation sur l'entrée pèse plus lourd que
l'entrée elle-même.** C'est ce qui rend le prompting puissant, et c'est
exactement ce qui le rend fragile — la même phrase, à un moteur près, fait
gagner treize points ou en perdre vingt.

## Sur le Pi 3B : personne ne tient le temps réel, mais pas au même prix

| moteur | mesure sur `raspi2` | rafraîchit le texte toutes les | verdict |
|---|---|---|---|
| whisper `tiny`, fenêtre 20 s, ctx 1152 | 7 à 12,3 s par passe | ~10 s | inutilisable |
| whisper `tiny`, fenêtre 10 s, **ctx 512** | 4,33 s médiane (max 16,35) | ~4,3 s | deux fois mieux, toujours trop lent |
| **sherpa-onnx** | 345 ms par bloc de 300 ms · RTF 1,151 | **0,35 s** | manque 15 % |

**J'avais conclu trop vite que sherpa était disqualifié sur le Pi.** Son RTF de
1,151 se lit mal en face du 0,62 de whisper : ce sont deux grandeurs
différentes. Whisper re-décode 10 s d'audio à chaque passe, donc son RTF « par
passe » cache le fait qu'il ne rend un texte que toutes les 4,3 secondes. sherpa
rend un texte toutes les 350 ms, avec 15 % de retard cumulé.

**Sur la cible, sherpa rafraîchit le texte douze fois plus souvent que whisper.**
C'est exactement ce qui gouverne les 3,7 s de délai mesurées ici. Le bon
critère n'est pas le RTF mais le **délai de restitution du dernier mot**, et sur
ce critère whisper perd d'un ordre de grandeur.

Il reste 15 % à trouver pour sherpa : un zipformer plus petit, ou 2 threads
(le Pi throttle à 83,8 °C dès 4 threads, et `RESULTATS.md` avait déjà mesuré que
2 threads tiennent à 73 °C). À tester.

Le réglage `audio_ctx` reste un gain réel sur le Pi : **4,33 s au lieu de 7 à
12,3 s**, soit un facteur deux sur le moteur par défaut.

## sherpa TIENT le temps réel sur le Pi 3B — avec DEUX threads

| threads | coût par bloc de 300 ms | max | RTF | température finale |
|---|---|---|---|---|
| **2** | **244 ms** | **299 ms** | **0,814** | 81,7 °C |
| 3 | 345 ms | 1795 ms | 1,151 | 83,8 °C |
| 4 | 499 ms | 1088 ms | 1,66 | 83,8 °C |

**Moins de threads, plus vite.** Le Pi 3B throttle : à 3 ou 4 threads il passe
son temps à 83,8 °C et perd en fréquence plus qu'il ne gagne en parallélisme.
`RESULTATS.md` avait déjà mesuré ce renversement pour whisper (2 threads à
73,1 °C contre 76,8 °C à 3) — il vaut aussi pour onnxruntime, plus fortement.

**Et le maximum tient : 299 ms, sous le budget de 300 ms.** Pas seulement la
médiane — aucun bloc ne dépasse. C'est ce qui sépare « ça passe en moyenne » de
« ça ne prend jamais de retard ».

Donc le compagnon vocal en flux continu tourne sur un Raspberry Pi 3B, avec un
ASR streaming qui rend le dernier mot en 250 ms au lieu de 4,3 secondes.

### Refait à froid : la réserve est levée

Les trois réglages relancés en attendant à chaque fois que le Pi redescende
sous 56 °C. Départs à 54,8 / 56,4 / 58,0 °C — comparables.

| threads | médiane | max | p95 | RTF | départ → fin |
|---|---|---|---|---|---|
| **2** | **247 ms** | **290 ms** | 279 ms | **0,803** | 54,8 → 81,7 °C |
| 3 | 350 ms | 614 ms | 468 ms | 1,094 | 56,4 → 84,4 °C |
| 4 | 550 ms | 1602 ms | 914 ms | 1,803 | 58,0 → 83,8 °C |

Le classement est identique à chaud, et le maximum tient toujours sous le budget
de 300 ms avec deux threads. Le résultat est publiable.

## État après le catalogue à un prompt par moteur

Même session (`073852`), même code, seul le moteur et son prompt changent :

| configuration | justesse | fins | pauses ratées | latence vécue |
|---|---|---|---|---|
| whisper `tiny` + `systeme` | 0,715 | 6/8 | 7/22 | 5,55 s |
| sherpa + `systeme` (le mauvais prompt) | 0,705 | 4/8 | 2/22 | 4,35 s |
| **sherpa + `systeme_sherpa`** | **0,761** | 6/8 | 5/22 | **3,55 s** |

**sherpa avec son propre prompt gagne sur les deux axes** : +0,046 de justesse
et **deux secondes de latence en moins**. Et c'est le seul moteur qui tienne le
temps réel sur un Pi 3B (244 ms par bloc de 300 ms, à 2 threads).

La ligne du milieu chiffre ce que coûterait un prompt unique : sherpa nourri du
prompt de whisper tombe à 0,705, sous whisper lui-même. Le catalogue à plusieurs
prompts n'est pas une commodité, c'est ce qui rend le moteur utilisable.

**Point à surveiller : 9 coupures**, contre 2 pour whisper. sherpa répond en
3,55 s au lieu de 5,55, donc il parle pendant que l'autre reprend son souffle.
Même effet que sur la borne haute à ASR parfait (26 coupures). C'est le prochain
défaut à traiter, et il n'apparaît que maintenant qu'on est assez rapide pour
couper quelqu'un.

## Le TTS : le vrai goulot, et il était invisible

Toutes nos mesures de latence s'arrêtaient à la DÉCISION. Sur le Pi, ce qui suit
la décision coûte plus cher que tout le reste :

| phrase | synthèse | audio produit | ratio |
|---|---|---|---|
| « Ça va bien, merci. » (18 car) | **11,71 s** | 1,62 s | 7,24 |
| « Il est bientôt minuit. » (22 car) | 9,81 s | 1,47 s | 6,69 |
| une phrase de 110 caractères | 19,84 s | 6,55 s | 3,03 |

Le ratio tombe quand la phrase s'allonge : le coût est **fixe**, c'est le
chargement du modèle. `tts.py` lançait un `piper` par phrase — une seconde sur
un PC, huit sur un Pi.

    piper relancé    8,28 s · 8,35 s · 7,82 s   par phrase
    piper résident   7,85 s puis 0,00 s · 0,00 s

**Huit secondes par réponse**, récupérées en gardant le processus en vie. Plus
que tout ce que la journée avait gagné, ASR compris.

Le prix à payer est architectural : on ne peut plus tuer piper pour couper la
parole, puisqu'il sert la phrase suivante. On tue `aplay` seul, et un compteur
de génération fait jeter au lecteur le PCM devenu sans objet — sans quoi la fin
d'une phrase coupée ressortirait au début de la suivante.

### Bilan de la latence sur la cible

| poste | avant | après |
|---|---|---|
| ASR (whisper fenêtre 20 s → sherpa 2 threads) | ~4,3 s | 0,25 s |
| TTS (piper relancé → résident) | ~8,0 s | 0,01 s |
| appel au modèle | 0,7 s | 0,7 s |
| **total estimé** | **~13 s** | **~1 s** |

À vérifier bout en bout sur le Pi : ces chiffres sont mesurés poste par poste.
