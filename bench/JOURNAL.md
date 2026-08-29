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
