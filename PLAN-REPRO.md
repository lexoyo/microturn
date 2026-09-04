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

## L'état au 04/09 au soir : les démos passent, la vérification reste

**Constat d'Alex en clôture de session, et c'est un changement de phase :**
*« On est bon là pour faire les démos. Il faudra faire les derniers tests, et si
ça marche on pourra écrire l'article et faire une vidéo. »* Le doute ne porte
plus sur la faisabilité, il porte sur la vérification. Le raisonnement complet
est dans `ARTICLE-NOTES.md`, « Changement de phase ».

Ce qui a tourné le 04/09, et qu'il faut lire avec sa réserve :

- **la démo 1 passe en entier** — six fins de tour sur six, latence médiane
  **3,16 s**, et le résumé final cite **les cinq questions**. *(Leur vidéo n'en
  restitue que quatre ; la réserve « à vérifier sur leur vidéo » de `DEMOS.md`
  § 3 n'est pas levée.)* ;
- **la séquence complète de la démo 2 est reproduite, dans l'ordre** :
  `<system backchannel>` émis, réponse déroulée, backchannels ignorés,
  interruption détectée et parole coupée, réponse résumée — **une seule coupure,
  au bon endroit** ;
- **Qwen2.5-7B non fine-tuné fait le même score que `gemini-2.5-flash-lite`** sur
  les quatre scénarios : **14/16 fins de tour, 4/4 pauses tenues**. ⚠️ **Un seul
  run, pas de passes multiples** ; sur 16 fins de tour, l'écart d'un cas est dans
  le bruit. Ce n'est pas une égalité établie, c'est un run qui n'a pas su les
  distinguer. ⚠️ **Et les deux runs ne portent pas le même code** (`ac39310` pour
  gemini, `6081aec` pour qwen, `74e655e` pour son dernier scénario) : la
  comparaison est à refaire à l'étape 2 avant d'être citée.

### ⚠️ Le banc est gelé à partir du 04/09

Le banc audio a été **modifié trois fois pendant que les mesures étaient
prises** : les durées de silence, d'abord estimées au nombre de mots puis
recalées sur leurs vidéos ; les gains du mixage des deux voix ; enfin le recalage
des instants sur les **formes d'onde** de leurs vidéos, blancs finaux allongés
dans la foulée. Les scores pris sur deux versions différentes **ne portent pas
sur les mêmes sons et ne se comparent pas** — en particulier, le
« 13/16 → 14/16 » de la journée ne doit pas être cité comme le gain d'une
correction. Relevé par Alex : *« Mais d'où tu as changé tes sons de test, ce
n'est pas normal ça. »*

**Consigne, sans exception** : pistes, silences et blancs finaux ne bougent plus
tant que la baseline de l'étape 2 n'est pas prise. Si une modification devient
nécessaire, elle **invalide tout ce qui a été mesuré avant elle** et se déclare
comme telle dans le journal.

## La suite immédiate — cinq points, dans cet ordre

Rien de ce qui suit ne se cite en public avant d'avoir été mesuré **après le
gel** du banc.

1. **La baseline propre des quatre scénarios sur le banc gelé** (étape 2). C'est
   la référence de tout ce qui suit : sans elle, aucune des corrections de la
   journée n'a de « avant » auquel se comparer, et les runs archivés du 04/09 ne
   peuvent pas en tenir lieu — ils portent trois états du dépôt différents.
2. **Mesurer le retrait du « short »** dans le prompt anglais (`74e655e`). Le
   commit qui retirait la consigne de brièveté n'avait touché que `fr.toml`,
   alors que tout le banc tourne en anglais. **L'effet n'a jamais été mesuré.**
   Ce qu'on sait est l'écart de **durée de parole** qui l'a fait découvrir, sur
   le scénario de l'interruption : **16,8 s pour leur réponse**, relevée sur la
   forme d'onde de leur vidéo, contre **11,4 s pour la nôtre** — assez pour que
   les backchannels calés sur leur vidéo tombent une fois qu'on a fini de parler.
   Nos réponses devraient s'allonger ; reste à voir ce que ça coûte aux fins de
   tour et aux pauses.
3. **Vérifier la démo 3**, la moins vérifiée des quatre. `<system backchannel>`
   sort bien et les clips existent, mais **personne n'a vérifié qu'il tombe au
   bon moment** — c'est le critère de réussite du § 1.2, et il ne se lit pas dans
   un score de fins de tour. Rappel du prix chez eux : 0,858 → 0,748 et un TOR de
   pauses multiplié par près de six.
4. **Intégrer l'enregistrement humain** quand il arrivera, avec
   `ideas/demos-audio/remonter.py` (côté idea-lab) : il découpe la prise et la
   remonte aux durées du banc, silences compris. La voix de synthèse est là parce
   que **l'accent français d'Alex passe mal à l'ASR** et ferait mesurer l'accent
   au lieu de la détection de fin de tour ; la prise humaine apporte en retour
   l'hésitation et le débit irrégulier qu'aucun TTS ne produit. Les deux pistes
   se gardent, elles ne se remplacent pas. ⚠️ **Remonter une nouvelle piste, c'est
   modifier le banc** : ça se fait après la baseline du point 1, et ça se déclare.
5. **Écrire l'article et faire la vidéo**, une fois les quatre points passés.
   C'est l'ordre posé par Alex — *« si ça marche on écrit l'article et on fait
   une vidéo »* — et le matériel de tournage existe déjà : les conversations
   complètes en mp3 avec les deux voix, les traces et les réponses horodatées,
   archivées par modèle hors dépôt. Le plan de l'article est dans
   `ARTICLE-NOTES.md`.

## L'état au 04/09 au matin, sans fard

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

**Les quatre pistes audio existent** depuis la nuit du 03 au 04/09, hors dépôt
(workspace d'idea-lab, `ideas/demos-audio/`) : le script et les scénarios sont
versionnés, les WAV non — ils se régénèrent. Recalées sur les durées mesurées
au `silencedetect` dans leurs vidéos, elles tombent à 104,1 s contre 103,8 pour
la leur, et 90,0 contre 90,2.

⚠️ *Périmé le 04/09 au soir pour la démo 2* : le `silencedetect` fusionne les deux
locuteurs quand ils se chevauchent, et plaçait le premier backchannel 14 s trop
tard. Les instants de cette démo viennent désormais de la **lecture des formes
d'onde** de leur interface, image par image.

**Ce qui manque encore à l'étape 1, c'est le scorer et l'injection** (§ 1.3) :
sans eux les pistes ne mesurent rien.

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
aucun service à ouvrir. Voix **`ash`** (masculine, américaine),
retenue à l'écoute. piper a été écarté sur écoute, il ne fait pas le poids.

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
| 1 · multi-tour | mémoire longue de l'historique | les six tours reçoivent une réponse ; le résumé final cite **les cinq questions** (le sixième tour *est* la demande de résumé — `DEMOS.md` § 3) |
| 2 · backchannel + interruption | « okay » et « yes » ignorés, puis coupure | le TTS ne s'arrête PAS sur les deux premiers, s'arrête sur le troisième |
| 3 · backchannel assistant | émettre un signal d'écoute | un clip part avant la réponse, sans retarder la réponse |
| 4 · hésitations *(le nôtre)* | ne pas confondre pause et fin de tour | aucune réponse pendant les quatre pauses ; une réponse après chaque phrase achevée |

La démo 1 est la seule atteignable sans nouveau code : c'est donc elle qui donne
la **première référence** du nouveau banc. Le scénario 4 n'a pas d'équivalent
chez eux — leurs trois dialogues ne contiennent aucune pause de réflexion en
milieu de phrase, ils montrent le full-duplex et non la difficulté de
l'endpointing. C'est lui qui doit faire échouer un détecteur à seuil.

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
