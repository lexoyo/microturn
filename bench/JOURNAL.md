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

**⚠ Ce 0,820 n'est plus comparable à rien.** Il porte sur deux sessions, avec
`gemini-2.5-flash-lite` et le prompt d'avant le catalogue par moteur. Il ne peut
donc pas être mis en face du 0,824 de `llama-3.3-70b`, mesuré sur une session
avec son propre prompt — un ASR réel ne bat pas un ASR parfait, l'écart vient de
la base. À refaire avec `systeme` (et NON `systeme_sherpa` : avec une entrée
ponctuée, la phrase sur la casse ment au modèle, ce qui coûte 0,103 — on
mesurerait ce mensonge plutôt que la borne).

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

## Rendre le système prudent : les trois variantes échouent

Base sherpa 0,761. Défaut visé : 5 pauses ratées sur 22.

**⚠ Base périmée, relevé après coup.** Ces trois variantes ont été mesurées
contre 0,761, alors que la base sherpa a été portée à **0,807** juste après, en
restaurant la variante 22 qu'une série précédente avait écrasée. Les écarts
chiffrés ci-dessous sont donc trop favorables aux variantes : lus contre 0,807,
P1 perd 0,121, P2 0,092 et P3 0,063. La conclusion — aucune n'améliore — tient
dans les deux lectures, et se durcit ; les amplitudes, elles, sont fausses.

Deux leçons de méthode : une base doit être remesurée quand le code bouge entre
deux séries, et un gain perdu en silence (la variante 22) contamine tout ce qui
est mesuré ensuite.

| variante | justesse | verdict |
|---|---|---|
| P1 · une règle : « dans le doute, il n'a pas fini » | 0,686 | **−0,075**, régression nette |
| P2 · une donnée : un fragment puis un silence | 0,715 | **−0,046**, régression |
| P3 · resserrer la définition de « finie » | 0,744 | −0,017, dans le bruit |

**Les trois font perdre. Aucune n'améliore.** Et je m'étais avancé : j'avais
parié sur P2, au motif que tous les gains étaient venus d'exemples. Le pari
était mauvais, et l'exemple ajouté fait plus de mal que la règle resserrée.

L'interprétation la plus simple : le prompt est à son plateau. On lui demande
d'être prudent sur les pauses, il devient prudent partout, et perd des fins de
tour sans gagner assez sur les silences.

**Conséquence : les pauses ne se corrigeront pas dans le prompt.** Le levier
restant est dans le code — exiger N ticks de silence consécutifs avant
d'autoriser une prise de parole, ce qui ne demande rien au modèle.

## Comparaison des décideurs — session `073852`, sherpa 2 threads

| | llama-3.3-70b | **gemini-2.5-flash-lite** | gemini-2.5-flash |
|---|---|---|---|
| justesse | **0,824** | 0,807 | 0,716 |
| fins de tour | 7/8 | 6/8 | 6/8 |
| pauses ratées | 5/22 | **3/22** | 7/22 |
| coupures | 6 | 5 | 2 |
| latence vécue | 4,35 s | **3,75 s** | 2,95 s |
| tokens par appel | 1127 | 1025 | ~900 |
| cache | **55 %** | 4 % | 0 % |
| prix / M tokens | 0,71 $ | **0,10 $** | 0,30 $ |
| coût par session | ~0,085 $ | **~0,016 $** | ~0,05 $ |

**Le verdict tient à une décision.** llama fait 0,824 contre 0,807 : l'écart est
de 0,017, exactement le bruit de mesure. Pour cinq fois le prix, deux fois la
latence et un ordre de grandeur d'énergie (un 70B consomme ~100× un 7B par
token). `flash-lite` reste le défaut, sans hésitation.

Deux choses que la justesse seule cachait :

- **`flash-lite` est meilleur sur les pauses** (3/22 contre 5/22). Il coupe moins
  souvent la parole, ce qui est le défaut n° 1 côté utilisateur. La justesse
  agrégée le désavantageait.
- **`gemini-2.5-flash`, plus gros, fait moins bien** (0,716) — mais avec 2
  coupures seulement. Ce n'est pas une dégradation uniforme, c'est un autre
  profil : plus prudent, donc plus muet.

**Le cache a bougé tout seul** : 4 % pour flash-lite à 1025 tokens, contre 0 %
à 900 et 55 % pour llama à 1127. Le seuil de 1024 tokens se voit à l'œil nu dans
ces trois chiffres. Une centaine de tokens de plus dans le prompt diviserait le
coût par quatre — le seul cas mesuré où rallonger le prompt est rentable.

### Énergie — estimation, pas mesure

Le Pi n'a pas de capteur (`power_now` absent) : il faudrait un wattmètre. Ordres
de grandeur publiés : un Pi 3B en charge tire 2 à 4 W, soit ~0,2 Wh pour une
session de 3 min 44 ; un 70B coûte ~0,39 J par token de sortie sur H100 FP8,
soit ~0,6 Wh pour la même session. **Le décideur distant pèse donc trois fois le
Pi entier** — et le choix d'un petit modèle divise cette part par dix.

## Configuration retenue — les meilleures options passent par défaut

| poste | défaut | pourquoi |
|---|---|---|
| STT | **sherpa-onnx, 2 threads** | seul à tenir le temps réel sur Pi 3B (244 ms/bloc de 300) ; 0,807 contre 0,715 |
| repli STT | whisper `tiny`, fenêtre 10 s, ctx 512 | coût par passe 0,81 s au lieu de 1,35 |
| décideur | **gemini-2.5-flash-lite** | 0,807, meilleur sur les pauses (3/22), 5× moins cher que llama pour 0,017 d'écart |
| TTS | piper **résident et préchauffé** | 8 s par réponse, et plus rien sur la première |
| horloge | tick 1,2 s, horizon 20 micro-tours | 0,6 s ne gagne rien ; 20 divise le contexte par deux à score égal |
| prompt | `systeme` / `systeme_sherpa` | la phrase sur la casse vaut +0,063 avec sherpa, −0,103 avec whisper |

### Non-régression des quatre changements passés en force

Mesurée sur les deux sessions après piper résident, préchauffage, cascade de
contrainte et filtre sans accents : **0,715**, identique à la valeur d'avant.
Rien n'a été cassé — mais trois défauts restent invisibles au rejeu muet et
n'apparaîtront qu'en session réelle : le PCM d'une phrase coupée qui fuirait sur
la suivante, la syllabe de préchauffage, et la dégradation irréversible de la
contrainte sur une erreur réseau.

### R1/R2 — raccourcir les réponses coûte cher

| variante | justesse | verdict |
|---|---|---|
| base sherpa | 0,807 | — |
| R1 · « dix mots au plus » | 0,744 | **−0,063**, rejeté |
| R2 · « une phrase, sans préambule » | — | patch sans effet |

Les réponses font 68 caractères en moyenne, soit 4,8 s de parole. Les raccourcir
par le prompt coûte 0,063 de justesse : le modèle tronque la réponse plutôt que
de la resserrer. Le temps d'antenne se réduira autrement, ou pas.

## Sessions réelles du 29/08 — ce que le rejeu ne pouvait pas voir

### Sur le Pi (`20260829-122725`) : la porte jetait 81 % de l'audio

```
  blocs transmis : 134      blocs jetés : 586
  audio enregistré : 90,3 s pour une session de 104,2 s
```

La porte anti-écho se calibre sur le bruit ambiant et ferme au-dessus d'un seuil
qui, sur ce micro USB, est plus haut qu'une voix normale :

```
  26,3s  fermée   voix 286   seuil 587
  59,2s  OUVERTE  voix 5222              ← quand Alex insiste
  80,2s  fermée   voix 418   seuil 8033
```

D'où les trous de sept à onze secondes dans la transcription, et les quatre
« coupures » : la porte s'ouvre brutalement, le système voit du texte neuf et
croit qu'on reprend la parole.

**Piège de mesure évité de justesse** : le délai « dernier mot → parole » valait
0,2 s, ce qui semblait excellent. Il chronométrait entre le moment où le système
a ENFIN entendu un mot et sa réponse — pas depuis la parole réelle. Le même
travers que pour le TTS le matin même : mesurer une étape et parler de la chaîne.

### Sur shiao sans porte (`20260829-133258`) : ça marche

```
  dernier mot → parole : médiane 0,33 s   (min 0,04 · max 1,55)
  latence d'appel      : médiane 0,44 s
  coût STT par bloc    : médiane 49 ms    (budget 300)
  16 réponses, 43 caractères en moyenne   (68 le matin)
```

Première conversation réellement tenue : il suit le fil (« Enchanté Tonton ! »,
« La tour Eiffel mesure 320 mètres de haut »). Et `<|user is thinking|>` sort
**66 fois sur 129 décisions**, alors qu'il n'était jamais sorti en rejeu.

### Le défaut qui reste : cinq relances vides sur seize réponses

Délai avant qu'Alex reprenne la parole, après chaque réponse :

```
   19,5s  0,5 s ⚠  « Je t'écoute. »
   25,2s  0,5 s ⚠  « Vas-y, je suis prêt. »
   51,7s  0,3 s ⚠  « Je suis désolé d'apprendre cela. »
   54,1s  0,1 s ⚠  « Je peux essayer de vous aider avec autre chose. »
   62,5s  0,0 s ⚠  « Je vais essayer de trouver quelque chose de sympa… »
```

Les onze autres réponses sont suivies de 3 à 11 s de silence : elles tombaient
juste. **Les cinq fautives sont toutes des relances vides** — aucune n'apporte
d'information.

Ça déplace le diagnostic. Le problème n'est peut-être pas *quand parler* mais
**quoi dire quand on n'a rien à dire**. Les trois variantes P1/P2/P3 essayaient
de rendre le modèle prudent ; aucune ne lui offrait de porte de sortie. Or le
prompt a `<|assistant_backchannel|>` — « tu as compris mais tu attends plus
d'informations » — qui est fait exactement pour ça, et qui n'est jamais sorti.

Une première analyse était fausse et corrigée : comparer les longueurs de
transcript ne dit rien, puisqu'il est remis à zéro après chaque réponse. Le bon
signal est le délai avant la reprise.

## Les 2 s avant le son : ce n'est pas le tampon ALSA

Alex, en session : « deux secondes entre le moment où il écrit qu'il va dire
quelque chose et le moment où je l'entends ». Testé sur le HDMI du Pi, quatre
tailles de tampon :

```
  défaut     1,64 s de bout en bout
  500 000 µs 1,64 s
  200 000 µs 1,56 s
  100 000 µs 1,54 s
```

**Cent microsecondes de tampon ne gagnent qu'un dixième de seconde.** Le tampon
n'est pas coupable, et `MICROTURN_APLAY_BUFFER` reste à 0 par défaut.

La mesure ci-dessus est un temps de bout en bout, durée de l'audio comprise
(~1,3 s) : la latence de démarrage d'ALSA est donc d'environ 0,3 s. Le reste
vient d'ailleurs, et on l'a déjà mesuré — **piper met 806 ms à rendre son
premier échantillon** sur une phrase de 41 caractères, même résident.

Donc la décomposition des ~2 s ressenties :

| poste | durée |
|---|---|
| premier échantillon de piper | ~0,8 s |
| démarrage d'ALSA | ~0,3 s |
| le reste (phrase plus longue qu'au test) | ~0,9 s |

Le levier n'est ni le tampon ni le moteur : c'est que **piper synthétise la
phrase entière avant de rendre la main**. Découper la réponse et ne synthétiser
que les premiers mots d'abord ramènerait ce premier échantillon à ~200 ms. C'est
le pendant TTS du streaming LLM qu'on a écarté ce matin — sauf qu'ici le gain
est vingt fois plus grand.

## Candidat 60 — découper la réponse avant de la synthétiser

La QC désignait un point non mesuré : *« le coût fixe d'un appel à piper
résident. S'il est de 300 ms, découper en trois ne gagne rien et fait trois
trous. »* Mesuré d'abord, codé ensuite.

### Ce que la mesure préalable a montré

```
   4 car ·  563 ms          coût ≈ 330 ms fixes + 60 ms par caractère
  18 car · 1337 ms
  28 car · 1804 ms
  41 car · 2805 ms
```

Le coût est **linéaire**, donc le découpage a un sens. Et surtout, en régime
résident, `total ≈ premier échantillon` : **piper ne diffuse rien au fil de la
synthèse**, il fabrique la phrase entière puis la sort d'un bloc. La latence
avant le premier son EST la durée de synthèse complète.

Le ratio synthèse/audio décide si les morceaux suivants arrivent à temps :

```
  medium   2,97 s pour 3,20 s d'audio   ratio 0,93   marge faible
  low      1,72 s pour 2,97 s d'audio   ratio 0,58   confortable
```

Les deux sont sous 1, donc pas de trous — mais `medium` est à la limite.

### Le résultat

```
  medium   entier  2890 ms  →  découpé  1135 ms    −61 %
  low      entier  1721 ms  →  découpé   844 ms    −51 %
```

**Gardé, en `medium` : 1,75 s de moins par réponse**, sans toucher à la voix.
`low` descendrait à 844 ms mais échantillonne à 16 kHz au lieu de 22 — arbitrage
de qualité, à trancher à l'oreille.

### Trois mesures fausses avant la bonne

Ce chiffre a demandé quatre tentatives, et les trois premières se
contredisaient : l'une relançait piper et chronométrait son chargement, une
autre abandonnait avant que la synthèse ait commencé (timeout de silence plus
court que le délai du premier échantillon), une troisième lisait le PCM de la
phrase précédente resté dans le tube.

**Leçon : sur une mesure qui décide d'une architecture, deux résultats
concordants valent mieux qu'un seul rapide.** Les trois faux chiffres auraient
tous mené à une conclusion différente — et l'un d'eux (ratio 0,35) m'avait fait
écrire que le TTS n'était pas le goulot, ce qui était faux.

## Variantes 55, 57, 58 — mesurées sur les DEUX dimensions

Base sherpa 0,807, 32 % des réponses portant le tic « grand modèle linguistique ».

| variante | justesse | tic | verdict |
|---|---|---|---|
| 55 · `assistant_backchannel` en porte de sortie | 0,744 | — | rejeté (−0,063) |
| 57 · une identité, sans parler de ce qu'il est | 0,807 | 32 % | **sans effet, ni sur l'un ni sur l'autre** |
| **58 · tutoiement imposé** | 0,784 | **0 %** | **gardé** |

**Le tutoiement fait disparaître le tic**, de 32 % à zéro. « Je suis un grand
modèle linguistique, entraîné par Google » est une formule apprise, au registre
formel : imposer le tutoiement oblige à reformuler, et le modèle sort de sa
phrase toute faite. Coût : 0,023 de justesse, à peine au-dessus du bruit.

**Et l'identité ne marche pas.** Je l'ai proposée trois fois dans la journée, en
m'appuyant chaque fois sur ce symptôme précis. Testée en rejeu (0,668), testée
autrement (0,807 sans effet sur le tic) : elle ne corrige rien. Ce qui corrige,
c'est une contrainte de registre — pas une déclaration d'identité.

La variante 55 n'a pas pu être départagée : les relances vides sont à **zéro**
sur cette session de rejeu, alors qu'elles étaient à 5 sur 16 en session réelle.
Elle reste ouverte, et ne se jugera qu'en direct.

### Il aura fallu quatre tentatives

Les trois premières ont rendu 0,715 trois fois de suite, au millième :

1. les patchs ne touchaient que `systeme`, alors que la session utilise
   `systeme_sherpa` ;
2. `serie.py` avait perdu `MICROTURN_SESSIONS` et mesurait les sessions whisper ;
3. mes correctifs de `serie.py` échouaient sur leur assertion **sans rien
   écrire**, et je ne lisais que la sortie qui suivait.

**Trois scores identiques au millième ne sont jamais un résultat : c'est un
signal que la mesure ne mesure rien.** `serie.py` le dit maintenant tout seul.

## Configuration finale — 0,826 sur deux sessions

sherpa-onnx 2 threads · `systeme_sherpa` + tutoiement · découpage TTS ·
horizon 20 · gemini-2.5-flash-lite.

| session | justesse | fins | pauses ratées | coupures | latence vécue |
|---|---|---|---|---|---|
| `073852-sherpa` | 0,784 | 6/8 | 4/22 | 2 | 3,55 s |
| `032332-sherpa` | **0,873** | 8/9 | 1/7 | 2 | 3,75 s |
| **moyenne** | **0,826** | | | | |
| DuplexCascade | 0,858 | | | | 1,2 s |

**Trois points d'écart** avec un Qwen2-7B fine-tuné cinq heures sur huit H100 —
et 0,873 sur une session, au-dessus de leur moyenne. Le point de départ du matin
était 0,634.

### Le chemin, en sept changements gardés

| | gain |
|---|---|
| rejeu déterministe (horloge virtuelle) | bruit ±0,071 → ±0,017 |
| horizon 20 micro-tours | contexte ÷ 2, score inchangé |
| `<|no voice|>` après réponse → `is thinking` | +0,025 |
| historique de l'assistant en JSON | +0,07 |
| sherpa-onnx à la place de whisper | +0,05 et latence ÷ 12 |
| `systeme_sherpa` (la phrase sur la casse) | +0,063 |
| tutoiement imposé | tic 32 % → 0 % |

Et côté latence sur le Pi, quatre défauts trouvés en session réelle et invisibles
au rejeu : la porte qui jetait 81 % de l'audio, le mono-thread de sherpa qui en
perdait 38 %, le tampon qui accumulait du retard, et `aplay` sans périphérique
qui parlait dans le vide.

## Le TTS en session réelle : trois bugs que le rejeu ne pouvait pas voir

Tous dans `Speaker`, la classe que **ni le rejeu ni les tests de fumée
n'exécutaient** — ils tournent en `--muet`, donc sur `Silencieux`. C'est la
classe la plus modifiée du 29/08, et la seule sans couverture.

### 1. `aplay` ne se terminait jamais

Avec piper résident, le tube d'`aplay` ne se ferme plus : `aplay` attend
indéfiniment, et `speaking()` — qui teste « est-ce qu'`aplay` tourne » — répond
vrai pour le reste de la session.

Mesuré sur `134719` : **neuf « coupures » sur treize prises de parole, dont huit
APRÈS la fin de la phrase.** Une phrase de 3,4 s « coupée » 18,5 s après son
début. Le système se croyait en train de parler en permanence, donc chaque mot
d'Alex déclenchait une coupure, et l'état « je parle » envoyé au décideur était
faux tout du long.

`bench/coupures.py` mesure l'avancement dans la phrase au moment de la coupure :
c'est un avancement médian de **100 %** qui a révélé l'absurdité.

### 2. La phrase coupée mangeait la suivante

Après un `stop()`, piper garde le PCM de la phrase interrompue et le sert au
prochain `aplay` : on entend la fin de l'ancienne, puis le silence qui suit
ferme `aplay` et la nouvelle ne sort jamais. Le compteur de génération censé
l'empêcher était inopérant — je comparais `gen` à `self._gen` après les avoir
lus ensemble, donc toujours égaux.

### 3. Le découpage coupait la phrase en tranches

« Bonjour ceci … est un test un peu plus long ». Le détecteur de fin de phrase
(0,35 s sans PCM) se déclenchait ENTRE deux morceaux. C'était le risque n° 1
écrit dans la QC du candidat 60, et il s'est produit exactement comme prévu.

Corrigé en comptant les morceaux restants ; et les morceaux sont désormais
servis **un par un**, car les écrire d'un coup laissait piper synthétiser toute
la phrase même après un `stop()` — sur le Pi, couper le robot le rendait muet
plusieurs secondes.

### Ce que ça change à la méthode

`tests/son_reel.py` exerce `Speaker` pour de vrai, et tourne dans la fumée. Il a
attrapé le bug n° 2 dès sa première exécution.

Et une constante de plus calibrée sur la mauvaise machine : les délais du test
lui-même. `MICROTURN_TEST_LENT=3` sur le Pi. Après `ATTAQUE_S` (facteur 3),
`DEBIT_CAR_S` (le robot parle 2,4 s pour 4,0 s estimées) et le nombre de threads
de sherpa, **c'est la quatrième fois dans la journée.** Le rapport de puissance
entre shiao et le Pi est d'environ trois, et il faut le supposer partout où une
durée est écrite en dur.

## Candidat 59 abandonné — implémentation fausse par construction

Exiger N ticks de silence avant de parler rend le système **totalement muet**
(0,500 = zéro prise de parole, avec 1 comme avec 2 ticks).

La raison est logique : je teste `self.silences` au moment où le modèle décide de
parler — or s'il décide de parler, c'est qu'il vient d'entendre du texte, donc
le compteur est à zéro par construction. La condition n'est jamais satisfaite.

Le faire correctement demanderait de mettre la réponse en attente et de la
redéclencher N ticks plus tard. Vu que le coût en latence était déjà rédhibitoire
(1,2 s par tick sur une latence de 0,33 s), abandonné plutôt qu'approfondi.

## Le mélange détection + réponse aide-t-il la détection ? — 02/09/2026

Le système transpose DuplexCascade par prompting : une seule requête par tick
fait DEUX tâches, décider si le tour est fini et écrire la réponse. Chez eux le
fine-tuning apprend les deux conjointement, et l'argument implicite est que
préparer la réponse aide à décider. Chez nous, jamais mesuré. La question est
directement architecturale : si la détection tient seule, elle peut descendre
sur un petit modèle local et la génération partir ailleurs.

### Le piège, avant la mesure

Un prompt qui ne rend que `{"m": ...}` tombe dans `parler_sans_texte` : le
pipeline **ne prend jamais la parole**, et le banc rend 0,500. C'est le piège du
candidat 59, en pire — là le chiffre était visiblement absurde, ici il est
plausible. Un système muet et un système bavard rendent tous les deux 0,500.

Le harnais a donc été adapté, **pas le prompt** : `MICROTURN_MARQUEUR_SEUL`
(pipeline.py) fait valoir le marqueur seul comme décision de parler, avec un
texte de remplissage de **55 caractères** — la médiane exacte des réponses de la
base, pour que la durée simulée de parole ne change pas. L'historique, lui, est
écrit sans réponse : y injecter le texte de remplissage donnerait au modèle des
phrases qu'il n'a jamais écrites.

Et un second garde-fou, trouvé en cours de route : la consigne ne suffit pas.
Avec le schéma JSON inchangé, `"r"` reste autorisé, et le modèle a produit une
réponse dans **23 décisions sur 39** malgré une consigne qui l'interdit
explicitement. La variante « A » ne mesurait donc pas ce qu'elle annonçait.
D'où `MICROTURN_SANS_R` (llm.py), qui retire `"r"` du schéma : là, 0 réponse
sur 33.

### Quatre variantes, parce que « retirer la réponse » est deux changements

Retirer la consigne `"r"` ne retire pas les réponses des EXEMPLES. Ce sont deux
causes, et la boucle interdit de les bouger ensemble.

| | consigne | exemples | schéma | réponses produites |
|---|---|---|---|---|
| base | `"r"` demandé | avec réponses | `"r"` permis | 35/35 |
| A | marqueur seul | avec réponses | `"r"` permis | **23/39 — raté** |
| C | marqueur seul | avec réponses | sans `"r"` | 0/33 |
| B | marqueur seul | sans réponses | `"r"` permis | 0/28 |
| B′ | marqueur seul | sans réponses | sans `"r"` | 0/27 |

### Les deux dimensions, séparément — et c'est tout l'intérêt

Sessions `20260829-032332-sherpa` et `20260829-073852-sherpa`, rejeu `--muet`,
`google/gemini-2.5-flash-lite`. 17 fins de tour et 29 pauses en tout.

| | TOR fins ↑ | TOR pauses ↓ | justesse | passes |
|---|---|---|---|---|
| **base** | **0,812** (13,8/17) | 0,179 (5,2/29) | **0,816 ± 0,015** | 5 |
| A (raté) | 0,824 (14/17) | 0,126 | 0,849 | 3 |
| **C** — détection seule, réponses encore dans les exemples | 0,745 (12,7/17) | 0,103 | **0,821** | 3 |
| **B′** — détection pure | **0,647** (11/17) | 0,103 | **0,772** | 3 |
| B — détection pure, schéma libre | 0,627 (10,7/17) | 0,126 | 0,751 | 3 |

**L'agrégat ment, et c'est exactement le défaut annoncé.** C rend 0,821 contre
0,816 : lu seul, « aucun effet ». Sa détection de fin de tour est pourtant
**six points plus basse**. Ce qui compense est mécanique : un système qui rate
des fins de tour parle moins, donc il intervient moins dans les pauses, et la
seconde moitié du score le récompense d'avoir échoué sur la première.

### La réponse

**Oui, le mélange aide la détection — et l'essentiel du bénéfice ne vient pas de
l'acte de générer, il vient des réponses présentes dans les exemples.**

| ce qu'on retire | effet sur TOR fins |
|---|---|
| la génération seule (base → C) | **−0,067**, soit ~1 fin de tour sur 17 |
| les réponses des exemples en plus (C → B′) | **−0,098**, soit ~1,7 de plus |
| les deux (base → B′) | **−0,165**, soit ~2,8 fins de tour sur 17 |

Le premier écart est à ~2 σ : réel dans son sens, faible dans son ampleur. Le
second et le total sont hors de tout doute. Face à la référence 0,826, B′ est à
−0,054 et C à −0,005.

**Conséquence pratique.** Un détecteur séparé est jouable, mais pas en retirant
simplement la consigne : il faut lui laisser des exemples qui MONTRENT à quoi
ressemble une fin de tour répondable. Autrement dit, ce qui aide n'est pas de
calculer la réponse, c'est de savoir à quoi elle ressemblerait.

### Trois choses vues au passage

**Le bruit de ±0,017 est confirmé, et on sait maintenant d'où il vient.** Cinq
passes de la base, dont deux servant de contrôle après chaque modification du
harnais : 0,826 · 0,791 · 0,826 · 0,813 · 0,826 (σ = 0,015, l'ordre de grandeur
annoncé — mais l'étendue fait 0,035, ce qui n'est pas la même chose et se lit
trop vite comme une régression). B′ rend **0,772 trois fois de suite, au millième** : dès
que `"r"` disparaît du schéma, la sortie fait dix tokens à température 0 et le
rejeu redevient totalement déterministe. **Trois scores identiques restent le
signal d'une mesure morte** — ici ce n'en était pas un, mais il a fallu le
prouver : B′ diffère de C, qui partage son schéma, et de B, qui partage ses
exemples. Le bruit résiduel de la base, c'est le texte libre des réponses.

**La consigne ne contraint pas, le schéma contraint.** 23 réponses sur 39
produites contre une instruction explicite. Toute variante de prompt qui
prétend supprimer une sortie doit être vérifiée dans la trace, pas dans le
prompt.

**Une variante ratée peut monter le score.** A, avec sa consigne contredite par
ses propres exemples, rend 0,849 — au-dessus de la base et au-dessus de
DuplexCascade. Elle ne mesure rien de ce qu'elle annonce. Non gardée.

### Ce dont je ne suis pas sûr

- **17 fins de tour et 29 pauses**, c'est peu : une fin de tour vaut 0,059 de
  TOR. Les écarts sont donnés à ±1 tour près.
- **Le texte de remplissage casse `_est_echo`**, qui compare le delta à ce que
  le robot vient de dire. Les variantes coupent donc plus (5 à 8 coupures contre
  2 à 4). Les coupures n'entrent pas dans la justesse, mais elles arrêtent la
  parole simulée et modifient l'état des ticks suivants.
- **« Détection seule » emporte trois choses à la fois** : plus de génération,
  plus de réponses dans les exemples, et plus de réponses dans l'historique. Les
  deux premières sont séparées ci-dessus ; la troisième ne l'est pas et ne peut
  pas l'être — un détecteur pur n'a rien à se rappeler.
- **La latence des variantes est fictive.** Un vrai détecteur séparé demanderait
  un second appel pour répondre. Les colonnes « latence vécue » des variantes ne
  veulent rien dire et ne sont pas reprises ici.
- **Les passes ont été faites en série**, une par une, alors qu'elles sont
  indépendantes : ~40 minutes de réseau pour ce qui en demandait cinq en
  parallèle. Et trois passes par configuration, là où une seule suffisait vu
  l'ampleur de l'écart. Méthode à corriger, pas les chiffres.

## Qwen2.5-7B avec notre prompt : ce que le fine-tuning apporte vraiment — 03/09/2026

L'écart avec DuplexCascade (0,858) mélangeait deux choses : leur fine-tuning, et
le fait qu'ils tournent sur Qwen2-7B quand nous tournons sur
`gemini-2.5-flash-lite`. Une seule mesure sépare les deux : **notre prompt, tel
quel, sur un Qwen de la même famille et de la même taille.** Qwen2-7B n'est plus
sur OpenRouter ; `qwen/qwen-2.5-7b-instruct` est la génération suivante.

Sessions `20260829-032332-sherpa` et `20260829-073852-sherpa`, rejeu `--muet`
déterministe, 17 fins de tour et 29 pauses. **Trois passes par modèle, lancées en
parallèle**, chacune avec son propre répertoire de trace — cinq minutes de
réseau au lieu des quarante que coûtait la série (le défaut relevé hier).

Catalogue figé pour toutes les passes : `locales/fr.toml` au commit `b511c42`
(sha256 `78ecb656…`), c'est-à-dire **sans « courte »** et **avec le tutoiement**.
Le prompt réellement envoyé est `systeme_sherpa`, vérifié dans la trace et non
supposé. Un autre travail modifiait `locales/fr.toml` dans l'arbre pendant la
mesure : les passes tournent sur une copie prise à HEAD, jamais sur l'arbre.

### Les deux dimensions, séparément

| | TOR fins ↑ | TOR pauses ↓ | justesse | passes |
|---|---|---|---|---|
| **gemini-2.5-flash-lite** (base) | **0,824** (14/17) | 0,207 (6/29) | **0,808** | 3 |
| **qwen-2.5-7b-instruct** | **0,471** (8/17) | 0,172 (5/29) | **0,649** | 3 |
| DuplexCascade (Qwen2-7B fine-tuné) | | | 0,858 | |

Par session, et par passe :

| | 032332 fins | 032332 pauses | 073852 fins | 073852 pauses |
|---|---|---|---|---|
| gemini ×3 | 8/9 | 1/7 | 6/8 | 5/22 |
| qwen p1 | 3/9 | 1/7 | 6/8 | 6/22 |
| qwen p2 | 3/9 | 1/7 | 5/8 | 5/22 |
| qwen p3 | 3/9 | 1/7 | 4/8 | 1/22 |

**Ce qui s'effondre, c'est la détection de fin de tour, et elle seule.** −0,353,
soit six fins de tour sur dix-sept. L'écart sur les pauses (−0,035) est sous
l'écart-type des passes Qwen (σ = 0,091) : il ne dit rien.

**Écarts, face au bruit.** σ de la justesse sur les trois passes Qwen = 0,020 ;
l'écart entre deux moyennes de trois passes a pour écart-type ~0,016.

| écart | valeur | verdict |
|---|---|---|
| Qwen − notre base | **−0,159** | ~10 σ, hors de tout doute |
| Qwen − DuplexCascade | **−0,209** | idem |
| notre base − l'historique 0,816 | −0,008 | **sous le bruit — le contrôle retombe bien** |

### Le mécanisme : Qwen ne dit jamais « il réfléchit »

Distribution des marqueurs sur 897 décisions (trois passes) :

| marqueur | qwen | gemini |
|---|---|---|
| `<\|user is talking\|>` | **657 (73 %)** | 145 (16 %) |
| `<\|user is thinking\|>` | 101 (11 %) | **609 (68 %)** |
| `<\|user finish talking\|>` | 109 (12 %) | 132 (15 %) |
| `<\|user interruption\|>` | 27 | 0 |
| `<\|user backchannel\|>` | 3 | 0 |
| tronqué | 0 | 11 |

Une inversion complète sur le silence : là où gemini répond « il se tait, mais il
réfléchit », Qwen répond « sa phrase n'est pas finie ». Or « sa phrase n'est pas
finie » est justement l'état qui interdit de conclure le tour. C'est le défaut
mesuré sur les Llama 3.2 en août, en moins total : Qwen prend la parole presque
autant que gemini (109 fois contre 132) — mais **au mauvais moment**.

### La sortie contrainte : Qwen tient le schéma strict, sans réserve

| | appels | sous schéma strict | replis de contrainte | erreurs réseau | décisions perdues |
|---|---|---|---|---|---|
| qwen | 299 ×3 | **897/897** | **0** | **0** | 3 (0,3 %) |
| gemini | 299 ×3 | **897/897** | **0** | **0** | 11 (1,2 %) |

Aucune dégradation d'un côté ni de l'autre : les deux modèles ont tourné dans le
même régime de contrainte, la comparaison est légitime. Le petit modèle n'est pas
celui qui perd le plus de décisions — **c'est gemini**, avec onze réponses
tronquées (`finish_reason: length` sur `max_tokens = 60`, ou `error`), coupées à
`{"m": "<|user`. Les trois pertes de Qwen sont d'une autre nature :
`<|user backchannel|>`, un jeton **valide dans l'enum** mais que `lire_controle`
ne mappe sur aucune action — il tombe en `format` et la décision est jetée.

**Et la cascade de repli ne peut de toute façon pas se déclencher.**
`Decideur.decide()` construit son `response_format` en dur au niveau strict et
n'appelle jamais `self.contrainte()`. `_degrade()` incrémente `self.niveau` et
l'écrit dans la trace, mais aucune requête suivante n'en tient compte. Un modèle
qui refuserait le schéma perdrait donc 100 % de ses décisions — exactement ce que
le commentaire au-dessus de `NIVEAUX` dit vouloir éviter. Sans effet ici, les
deux modèles acceptant le schéma ; à corriger avant de tester un modèle qui ne
l'accepte pas.

### Latence et coût

| | latence d'appel méd. | p90 | max | coût / passe | tokens d'entrée / appel |
|---|---|---|---|---|---|
| gemini | **0,36 s** | 0,46 s | 0,81 s | **0,028 $** | 861 |
| qwen | 0,53 s | 0,88 s | **3,30 s** | 0,039 $ | **1 332** |

Même prompt, **55 % de tokens d'entrée en plus** : c'est le tokenizer de Qwen sur
du français. À prix affiché quasi égal, il revient 42 % plus cher. Et sur un tick
de 1,2 s, son p90 mange 73 % du budget quand son maximum le dépasse trois fois —
invisible ici (l'horloge du rejeu est virtuelle), bloquant en session réelle.

La « latence vécue » de Qwen sur `032332` (1,15 s contre 3,75 s) **ne veut rien
dire** : elle est la médiane de trois réponses sur neuf questions.

### Le piège de l'agrégat, dans nos propres chiffres

La passe 3 de Qwen a la **pire** détection (7/17 contre 9/17 en passe 1) et le
**meilleur** agrégat (0,671 contre 0,644). Elle a raté deux fins de tour de plus,
donc parlé moins, donc dérangé 2 pauses sur 29 au lieu de 7. L'agrégat la
récompense d'avoir échoué. C'est le défaut annoncé, reproduit à l'identique.

Et gemini rend **0,808 trois fois au millième** — pas une mesure morte : les
trois traces diffèrent (178/181/179 appels sur la seconde session, 4/2/5 réponses
tronquées). Le score est stable parce que 17 fins et 29 pauses sont une métrique
grossière, pas parce que la sortie est identique. Qwen, lui, varie.

### Au passage : retirer « courte » a ramené le tic, sans bouger la justesse

Le commit `b511c42` de cette nuit retire « courte » de la consigne de réponse. Le
banc ne le voit pas, `bench/compter_travers.py` si — deux passes de contrôle avec
l'ancienne rédaction, tout le reste identique :

| gemini | justesse | TOR fins | longueur méd. | tic « grand modèle » (073852) |
|---|---|---|---|---|
| avec « courte » | 0,826 · 0,808 | 0,824 | 57 car | **4 %** |
| sans « courte » | 0,808 ×3 | 0,824 | 77 car | **30 %** |

Les réponses s'allongent d'un tiers et **le tic revient**. La justesse ne bouge
pas d'un iota — c'est exactement la leçon déjà écrite : une variante qui touche à
ce que le modèle DIT ne déplace aucun marqueur. À arbitrer par Alex : « courte »
n'a pas de sens comme consigne, mais c'est elle qui tenait le registre.

Qwen, lui, fait **0 % de tic** sur les deux sessions. Le tic est un trait de
gemini, pas du prompt.

### La réponse

**À modèle constant, le fine-tuning vaut environ +0,21 de justesse, soit six fins
de tour sur dix-sept — et le prompting sur un bon petit modèle en récupère les
trois quarts sans une seule heure de GPU.**

| | justesse |
|---|---|
| Qwen2.5-7B, prompting seul | 0,649 |
| DuplexCascade, Qwen2-7B fine-tuné 5 h sur 8×H100 | 0,858 |
| nous, `gemini-2.5-flash-lite`, prompting seul | 0,808 |

Le chiffre qui manquait à l'article n'est donc pas 0,042. C'est **0,209 pour le
fine-tuning** et **0,159 rattrapés par le changement de modèle**.

### Ce dont je ne suis pas sûr

- **0,858 n'est pas mesuré sur le même banc.** C'est Full-Duplex-Bench, anglais,
  avec des pauses annotées par des humains ; nous mesurons deux sessions
  françaises d'Alex avec des pauses dérivées de ffmpeg. Le journal le dit déjà :
  « comparables ENTRE NOS VERSIONS, et seulement indicatifs face aux leurs ».
  **Toute soustraction avec 0,858 est indicative, pas une mesure.** Le seul
  chiffre solide ici est l'écart Qwen ↔ gemini, mesuré sur le même banc.
- **Le prompt a été réglé SUR gemini**, sur cinquante-huit variantes. Le faire
  tourner sur Qwen n'est pas « tout le reste identique » du point de vue de Qwen :
  c'est un prompt étranger. Une partie des 0,209 est du réglage manquant, pas du
  fine-tuning. Je ne peux pas dire quelle part.
- **Qwen2.5 n'est pas Qwen2.** Si 2.5 est meilleur en base, l'écart vrai sur
  Qwen2 est plus grand que 0,209. Ce biais joue en sens inverse du précédent, et
  je ne sais pas lequel domine.
- **17 fins de tour, 29 pauses.** Une fin de tour vaut 0,059 de TOR. Les écarts
  sont à ±1 tour près.
- **Les passes ont tourné à six en parallèle**, ce que les mesures de référence
  n'ont pas fait. Zéro erreur réseau des deux côtés et un contrôle qui retombe à
  0,808 disent que ça n'a pas dérangé — ce n'est pas une preuve que ça ne pouvait
  pas.
- **Le coût est reconstruit** depuis les tokens tracés et les prix relevés le
  03/09, pas lu dans le champ `usage.cost` : la trace ne l'enregistre pas.
- **Le dépôt a bougé sous la mesure.** Les huit passes tournent sur le code et le
  catalogue de `b511c42`, gelés dans une copie. Depuis, `5fe623a` a corrigé
  `_delta` et `tts` et **retiré « en tutoyant »** : le catalogue courant n'est
  donc plus celui mesuré ici. Les corrections de code touchent les deux modèles
  de la même façon et ne changent pas la comparaison Qwen ↔ gemini ; le retrait
  du tutoiement, lui, est un troisième changement de prompt non mesuré, qui
  s'ajoute au retrait de « courte » dont l'effet sur le tic est chiffré ci-dessus.
