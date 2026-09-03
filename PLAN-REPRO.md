# Plan : reproduire les trois démos des chercheurs

**But, décidé par Alex le 03/09/2026 :** faire tourner sur `shiao` — pas sur le
Pi — les trois scénarios que DuplexCascade met en démo, et comparer. L'article
vient après, et il vient tout seul une fois que ça marche.

Le cahier des charges des trois scénarios est dans `DEMOS.md` (dialogues
verbatim). La lecture du papier est dans `PAPIER.md`. Ce fichier-ci ne dit que
**quoi faire, dans quel ordre, et comment on saura que c'est fait**.

`PLAN.md` reste valable, mais **après** : c'est le plan d'extraction de la
bibliothèque, et il suppose un système qui marche.

---

## L'état au 04/09, sans fard

**Il n'y a plus de référence chiffrée.** Le commit `d721c84` a changé les jetons
et fait passer la fenêtre d'historique de 20 entrées à 270 — sans mesure, à
dessein. Tout ce qui a été mesuré avant est périmé, **0,837 compris**. C'est le
prix assumé d'un changement de cible.

**Trois jetons sur six ne sortaient jamais** parce qu'ils sont définis « pendant
que tu parles » et que le modèle ne le sait pas : 0 `<user is interrupting>` sur
897 décisions. La sortie ne passe pas par l'enrichissement de l'entrée mais par
un déplacement de la décision — voir l'étape 3.

**Aucun son n'est généré.** Rien du banc de démos n'existe aujourd'hui.

---

## Étape 1 — le banc des trois démos

Rien ne commence avant ça : sans banc, chaque correction qui suit se juge à
l'oreille.

### 1.1 Les sons

Un fichier audio **par scénario**, pas par question. La démo 1 est du
multi-tour et la décision dépend de tout l'historique ; découper détruirait ce
qu'on teste. Pour l'interruption, il faut de toute façon un flux continu.

Chaque scénario est un **montage** : segments synthétisés par piper, séparés par
des silences de durée **choisie et notée**. Un TTS ne produit pas de pause de
réflexion — or le silence est la donnée qu'on mesure, il doit être piloté au
dixième de seconde.

En anglais, comme eux (`locales/en.toml` existe, le mode anglais est vérifié).

**Les réponses de l'assistant sont fixées**, de durée connue. Si on laisse le
modèle générer une longueur libre, l'instant de l'interruption tombe ailleurs à
chaque passe et le test n'est plus reproductible.

### 1.2 Ce que chaque scénario doit produire

| démo | ce qu'elle exige | critère de réussite |
|---|---|---|
| 1 · multi-tour | mémoire longue de l'historique | les six questions reçoivent une réponse ; le résumé final en cite six |
| 2 · backchannel + interruption | « okay » et « yes » ignorés, puis coupure | le TTS ne s'arrête PAS sur les deux premiers, s'arrête sur le troisième |
| 3 · backchannel assistant | émettre un signal d'écoute | un clip part avant la réponse, sans retarder la réponse |

La démo 1 est la seule atteignable aujourd'hui : c'est donc elle qui donne la
**première référence** du nouveau banc.

### 1.3 Comment on injecte

**D'abord l'injection directe** du fichier dans le pipeline (le mode rejeu
existe déjà) : déterministe, rejouable, c'est lui qui sert de mesure.

**Ensuite seulement** haut-parleur + micro : c'est le vrai bout en bout, il
teste l'écho, et il n'est pas reproductible. Les deux, dans cet ordre.

---

## Étape 2 — mesurer l'EXISTANT sur ce banc

Avant toute correction. On ne saura ce que valent les corrections que si on a un
avant. Trois passes, et le chiffre entre au journal comme la nouvelle référence.

C'est aussi le moment de vérifier que la fenêtre à 270 et les jetons renommés
n'ont rien cassé — deux changements imposés sans mesure, il faut bien qu'ils
soient regardés une fois.

---

## Étape 3 — le prompt et l'hôte, une correction à la fois

Chacune se mesure séparément, sinon on ne saura pas laquelle a payé.

### 3.1 L'interruption sort du modèle et passe dans l'hôte

`<user is interrupting>` est **retiré** du catalogue. À la place : un
`<user is speaking>` reçu pendant que l'hôte lit une réponse **est** une
interruption. L'hôte est le seul à savoir qu'il parle, et il le sait exactement.

On remplace un marqueur qui ne sortait jamais par un ET logique déterministe.
Ça reste conforme à `SPEC-PIVOT` § 2 : c'est l'hôte qui déduit, pas
l'observateur.

### 3.2 Les backchannels sont expliqués dans le prompt

Ils sont listés dans les marqueurs, mais **aucune ligne ne dit quand les
émettre**. Il faut écrire les deux sens :

- **ignorer** ceux de l'utilisateur — « okay », « yes », « mhm » se
  reconnaissent au **contenu**, sans savoir si l'on parle. L'hôte s'en sert pour
  ne pas couper le TTS ;
- **en émettre** : quand, et à quelle fréquence.

⚠️ Le papier chiffre le prix : leur variante avec backchannels tombe à **0,748**
contre 0,858, et son TOR de pauses est multiplié par près de six. Ce n'est pas
un veto — c'est leur mesure, sur leur banc, avec fine-tuning — mais la démo 3 va
contre la démo 1 et il faut le mesurer chez nous.

### 3.3 `<system backchannel>` est traité par le code

Aujourd'hui il est ramené à « ne prends pas la parole » : même émis, rien ne se
passe. Eux jouent un **clip audio pré-synthétisé tiré au hasard** — pas du TTS à
la volée. On fait pareil : quelques WAV courts, générés une fois.

### 3.4 La durée de parole

`ATTAQUE_S` et `DEBIT_CAR_S` sont faux d'un facteur 3. Tant qu'ils le sont,
l'état « je parle » se termine trop tôt — et c'est précisément la donnée dont
dépend la déduction de l'interruption du 3.1. À corriger avant de mesurer 3.1,
pas après.

---

## Étape 4 — la correction de `_delta` (le test décisif de l'agrégateur)

Le prototype d'agrégateur a mesuré, sur un jeu de validation fermé, que le
chemin actuel (`stt.py` + `pipeline._delta`) laisse passer **68 mots parasites
sur 471** — fidélité 0,807 contre 0,979 possible. La cause tient en une phrase :
`_delta` s'ancre sur la **queue du tour** là où il faut s'ancrer sur le
**préfixe du segment**. Le recollage de `stt.py`, lui, faisait déjà bien son
travail (0,964).

**Ce qui n'est PAS démontré : que ces 68 mots changent une décision.** La
fidélité du texte n'est pas la justesse de la détection. Le test est simple —
corriger, relancer le banc de l'étape 2, regarder si la justesse bouge.

Si elle ne bouge pas, l'agrégateur aura été un travail propre sans effet sur
microturn, et il faudra l'écrire. Le reste du prototype (les trois tiers de
stabilité, le curseur de tolérance) est de la spec pour la bibliothèque, pas un
gain pour aujourd'hui — et le coude coûte 0,50 s de latence médiane, 1,25 s au
p90, soit un tick entier de retard dans le pire cas.

---

## Étape 5 — les trois démos, en entier

Quand 3 et 4 sont mesurées, rejouer les trois scénarios de bout en bout et
enregistrer le résultat. C'est le but ; le reste était la route.

---

## Après, et seulement après

- **eot-bench en français** — la seule mesure qui nous compare à Smart Turn et à
  LiveKit. Elle ne nous compare **pas** à DuplexCascade, qui se mesure sur
  Full-Duplex-Bench et VoiceBench : ce sont deux comparaisons différentes.
- **L'extraction de la bibliothèque** : `PLAN.md`, étapes 0 à 6.
- **L'article** : `ARTICLE-NOTES.md`.

---

## Ce qui peut faire échouer ce plan

**Les poids ne sont pas publiés.** Leur code est en MIT
(github.com/sbintuitions/DuplexCascade) mais le LoRA n'y est pas, et leur pile
utilise Kyutai STT/TTS. Sur `shiao` — 2 cœurs, 7,5 Gio, pas de GPU — leur
système ne tournera pas. **On ne compare donc pas deux systèmes, on compare le
nôtre à trois vidéos qu'ils ont choisies.** C'est une impression, pas une
mesure, et ça doit être dit tel quel partout où le résultat sera présenté.

**Viser trois démos pousse au sur-ajustement.** On peut réussir leurs trois
scénarios et être plus mauvais en conversation réelle. Garde-fou : les sessions
enregistrées restent au banc comme test de non-régression, même si elles ne sont
plus l'arbitre.

**La démo 3 est peut-être leur configuration dégradée.** Leur page ne dit pas
quelle variante tourne dans quelle vidéo ; si c'est bien DuplexCascade-β,
reproduire la démo 3 c'est reproduire leur système à 0,748. Inférence à
confirmer, pas un fait.

**Les voix synthétiques ne sont pas des voix réelles.** piper ne produit ni
hésitation, ni bruit de fond, ni débit irrégulier — c'est-à-dire précisément ce
qui rend la détection difficile. Le banc des démos sera plus facile que la vie.
Les sessions réelles restent nécessaires pour cette raison.
