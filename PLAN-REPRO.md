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
que tu parles » et que le modèle ne le sait pas : **0 sur 897 décisions**
(`bench/JOURNAL.md`, `gemini-2.5-flash-lite`, la configuration retenue). La
sortie ne passe pas par l'enrichissement de l'entrée mais par un déplacement de
la décision — voir l'étape 3.

⚠️ **Ce 0/897 porte sur `<|user interruption|>`, l'ancien nom** : il a été
mesuré avant `d721c84`, qui a renommé les jetons **et** multiplié la fenêtre par
13,5. L'écrire `<user is interrupting>` laisserait croire que la mesure a été
refaite depuis — elle ne l'a pas été. C'est l'étape 2 qui la refera. *(Et le
« 0 sur 153 » de `PLAN.md` n'a aucune session en face : ne pas le citer.)*

**Le banc de démos n'existe pas encore.** La chaîne de synthèse, elle, a été mise
en marche dans la nuit du 03 au 04/09 — c'est de là que sortent les trois
contraintes d'API du § 1.1. Mais **aucun fichier du banc n'est au dépôt** au
04/09 : tant qu'il n'y en a pas, l'étape 1 est à faire, pas à vérifier.

---

## Étape 1 — le banc des trois démos

Rien ne commence avant ça : sans banc, chaque correction qui suit se juge à
l'oreille.

### 1.1 Les sons

Un fichier audio **par scénario**, pas par question. La démo 1 est du
multi-tour et la décision dépend de tout l'historique ; découper détruirait ce
qu'on teste. Pour l'interruption, il faut de toute façon un flux continu.

Chaque scénario est un **montage** : segments synthétisés, séparés par des
silences de durée **choisie et notée**. Un TTS ne produit pas de pause de
réflexion — or le silence est la donnée qu'on mesure, il doit être piloté au
dixième de seconde.

En anglais, comme eux (`locales/en.toml` existe, le mode anglais est vérifié).

**Ce n'est plus piper.** Le TTS du banc est **`openai/gpt-audio-mini`, appelé via
OpenRouter** — donc avec la clé que le projet a déjà : aucune clé nouvelle,
aucun service à ouvrir. Voix **masculine américaine**, `ash` ou `onyx`, Alex
tranche à l'écoute. piper a été écarté sur écoute, il ne fait pas le poids.

*Portée du changement* : ce TTS **fabrique les fixtures du banc et n'entre jamais
dans la chaîne mesurée**. `piper` reste la voix de l'assistant sur le Pi : la
chaîne temps réel ne gagne aucune dépendance.

Trois contraintes trouvées en le faisant marcher, écrites ici pour qu'elles ne
coûtent pas une demi-heure à la prochaine personne :

- la sortie audio **exige `stream: true`** — sinon HTTP 400, « Audio output
  requires stream: true » ;
- en streaming, **le seul format accepté est `pcm16`** : ni `wav`, ni `mp3`, ni
  `opus`. Le PCM brut est à emballer dans un conteneur WAV **soi-même** ;
- le flux sort en **24 kHz mono**, quand la chaîne du projet consomme du 16 kHz
  (`audio.py`, `RATE = 16000`). **Le rééchantillonnage est obligatoire, et c'est
  celui qu'on oublie** : du 24 kHz consommé comme du 16 kHz dure une fois et
  demie plus longtemps — les silences fabriqués au dixième de seconde ne veulent
  alors plus rien dire, et c'est eux qu'on mesure.

*Pourquoi une voix de synthèse plutôt que celle d'Alex* : `ARTICLE-NOTES.md`,
« La voix des démos est synthétique par nécessité, pas par confort ». En deux
mots — un locuteur français en anglais ferait mesurer l'accent au lieu de la
détection de fin de tour.

**Les réponses de l'assistant sont fixées**, de durée connue, et **l'interruption
est placée à un délai fixe après la fin de la question** (décision d'Alex : on
fait comme si nos réponses avaient la durée des leurs). Si on laisse le modèle
générer une longueur libre, l'instant de l'interruption tombe ailleurs à chaque
passe et le test n'est plus reproductible.

**La piste injectée ne contient QUE la voix de l'utilisateur.** Pas la réponse de
l'assistant : ce que le micro en réentend est un problème d'écho, il se teste au
haut-parleur en 1.3, pas dans la mesure déterministe.

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

⚠️ **Le gain de l'agrégateur pour NOTRE aval n'est pas établi, et ce 0,979 ne
peut pas servir tel quel de justification.** Il se lit `fid`, révocations
appliquées — c'est le chiffre d'un aval qui **sait défaire**. Au même point de
fonctionnement, la lecture `fid+` (un aval qui ne défait rien, ce qu'est un
prompt de LLM) donne **0,9639**. Et le `fid+` de `stt.py` seul **n'est pas
mesuré** : la paire « 0,979 contre 0,964 » n'a donc **aucune comparaison propre
derrière elle** — les deux nombres ne se lisent pas dans la même colonne, et
0,964 s'écrit numériquement pareil que le `fid` de `stt.py`, ce qui achève de
brouiller la lecture. **À demander à la session de tests avant de s'appuyer sur
cette étape** : le `fid+` de `stt.py` seul, au même point de fonctionnement.
Tant qu'il manque, on sait que `_delta` abîme le texte (0,807 est mesuré des
deux côtés), pas de combien l'agrégateur fait mieux que `stt.py` seul chez nous.

⚠️ **Collision d'écriture** : ce **0,807** est une *fidélité de recollage*. Le
0,807 de « la base sherpa était 0,807 » (`ARTICLE-NOTES.md`, partie IV) est une
*justesse de décision*. Même nombre, deux grandeurs sans rapport.

**Ce qui n'est PAS démontré non plus : que ces 68 mots changent une décision.** La
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

**Les voix synthétiques ne sont pas des voix réelles.** Un TTS — piper hier,
`gpt-audio-mini` aujourd'hui — ne produit ni hésitation, ni bruit de fond, ni
débit irrégulier, c'est-à-dire précisément ce qui rend la détection difficile. Le
banc des démos sera plus facile que la vie. Les sessions réelles restent
nécessaires pour cette raison.

*Et c'est un biais assumé contre un autre* : la voix d'Alex, française en
anglais, ferait mesurer l'accent au lieu de la détection (§ 1.1). On échange donc
un biais sans correctif contre un biais qui en a un — les sessions réelles au
banc, en non-régression. Le raisonnement complet est dans `ARTICLE-NOTES.md`.
