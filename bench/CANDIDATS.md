# Tests candidats, ordonnés par proximité au papier

Écrit le 29/08/2026. Réordonné à la demande d'Alex : **à gain égal, on prend le
test qui nous rapproche de DuplexCascade.**

État de départ : `f2f3427`, justesse 0,762 sur `20260829-032332`.
DuplexCascade est à 0,858.  Fins de tour 6/9 · pauses 1/7.

## Ce que « près du papier » veut dire ici

`FORMAT-CHERCHEURS.md` §1, constaté dans leur code : **ils n'ont aucun prompt
système.** Tout leur comportement vient du fine-tuning LoRA sur Qwen2-7B.

**Notre prompt EST notre fine-tuning** (arbitrage d'Alex, 29/08). C'est la
transposition par prompting de ce qu'ils obtiennent par entraînement, et c'est
tout l'objet du projet. Donc rien de ce qu'on écrit dans le prompt ne peut
« s'éloigner du papier » : le contenu du prompt est notre variable libre, au
même titre que leurs données d'entraînement sont la leur.

La proximité au papier ne se juge donc que sur ce qui est **observable chez
eux**, et sur quoi ils ont fait un choix explicite :

- les **jetons** — sept, exactement ceux-là, avec ces chaînes-là ;
- la **structure** — micro-tours entrelacés, horizon fixe, aucun marqueur
  décrivant l'état du système ;
- l'**horloge** — Δt = 0,6 s en pratique, optimum d'exactitude annoncé à 1,2 s ;
- la **qualité des briques** — ASR streaming réel, modèle 7B entraîné sur la
  tâche.

Un test qui touche à ces quatre-là se juge en conformité. Un test qui n'écrit
que dans le prompt ne se juge qu'au résultat.

Un fait mesuré à ne pas perdre de vue : **leur format exact, sur un modèle non
entraîné, donne 3/9 contre 7/9.** La sobriété de leur design est un produit du
fine-tuning. Notre prompt doit donc être plus riche que le leur — c'est
précisément ce qu'un fine-tuning nous éviterait d'écrire.

Marquage : `[=]` reproduit ce qu'ils font · `[~]` notre fine-tuning à nous, jugé
au résultat · `[≠]` contredit un de leurs quatre choix explicites.

---

## Déjà testé — 17 itérations, à ne pas refaire à l'aveugle

Détail complet dans `bench/JOURNAL.md`. Ce qui compte ici : ce qui reste vrai.

| # | ce qui a été changé | résultat | reste-t-il à refaire ? |
|---|---|---|---|
| 1 | horizon `MICRO_TOURS` 24 → 48 + rappel du tour en cours | 3/9, nul | oui — jamais testé À LA BAISSE (cf. n° 11) |
| 2 | rappel hors parenthèses | 2/9, régression | non |
| 3 | `REFLECHIT` resserré | 5/9, gain | remplacé par le n° 16 |
| 4 | `REFLECHIT` supprimé | 6/9, gain | **annulé** — le jeton est revenu avec les sept du papier |
| 5 | notation à deux champs | 6/9, neutre | non |
| 6 | exemple « je parle + rien » | 2/9, régression | non |
| 7 | `moi:` → `robot:` | 2/9, régression | non — un seul mot, deux fois moins de justesse |
| 8 | prompt 167 → 71 mots | **7/9**, meilleur de l'époque | dépassé (le prompt fait 227 mots et score mieux) |
| 9 | exemples rééquilibrés 4-3 | 6/9, nul | oui — refaire sur le prompt actuel (n° 22) |
| 10 | marqueurs d'état supprimés | 3/9, **régression majeure** | à refaire : mesuré sur l'ancien prompt (n° 46) |
| 11 | jetons du papier | 0,690 | acquis, c'est la base actuelle |
| 12 | intro supprimée | 0,595, régression | non |
| 13 | intro + deux rôles distincts | 0,524, pire résultat | non |
| 14 | « une seule tâche » | 0,651, nul | non |
| 15 | `<|no voice|>` sur la mesure du son | — | acquis |
| 16 | historique de l'assistant en JSON | **0,762**, meilleur | acquis |
| 17 | exemples dans le message système | 0,762, neutre | acquis, et conforme au prompt d'Alex |

Trois choses que ces 17 itérations ont établies, et qui orientent la suite :

- **on peut retirer les règles, pas les données** (n° 8 contre n° 10) ;
- **la formulation pèse autant que la structure** : n° 7, un mot changé, la
  justesse divisée par trois ;
- **presque tout ce qui a été mesuré l'a été sur une seule session de 9 fins de
  tour**, avec un bruit de ±0,116. Les verdicts « nul » et « neutre » ci-dessus
  sont donc surtout des « indécidable ».

---

## 0. Préalable — que la mesure puisse trancher  `[~]`

Sur 9 fins de tour, une décision qui bascule vaut 0,055 de justesse, pour un
bruit de ±0,116 : la granularité est plus grosse que les écarts cherchés. Rien
de ce qui suit n'a de sens tant que ce bloc n'est pas fait.

  1. Mesurer sur les DEUX sessions (22 fins de tour au lieu de 9). — **en cours**
  2. Trois passes par mesure ; moyenne et écart-type.
  3. Vérifier le déterminisme du rejeu à température 0.
  4. Compter par CLASSE d'erreur : deux erreurs opposées se compensent
     aujourd'hui dans le score agrégé.
  5. Séparer latence et justesse — une bonne décision arrivée 8 s trop tard
     compte aujourd'hui comme une réussite.
  6. Annoter les interruptions de `073852` : la dimension est à zéro faute de
     référence, pas faute de résultat.
  7. Transcrire les six autres sessions d'hier soir (51 à 188 décisions chacune,
     aucune référence) — dix minutes de whisper `small` chacune, sans reparler.

## 1. Conformité au papier, hors prompt  `[=]`

Les quatre choses sur lesquelles ils ont fait un choix explicite. C'est le seul
bloc où « près du papier » veut dire quelque chose.

### Structure

  8. **Le mode complétion au lieu du mode chat.** La différence de nature
     (`FORMAT-CHERCHEURS.md` §6) : eux complètent un flux, nous remplissons une
     conversation à deux rôles. De là viennent nos difficultés propres — l'état
     du système sans endroit où vivre, et des exemples qui occupent les mêmes
     rôles que le réel. Vérifier d'abord qu'OpenRouter l'expose.
  9. **Horizon de dix micro-tours système** (`MICRO_TOURS` 48 → 20), la longueur
     fixe de leurs données d'entraînement. Le n° 1 de l'ancienne série l'avait
     augmenté sans jamais le réduire.
 10. Replier les séries de `<|no voice|>` consécutifs en un tour annoté.
 11. N'envoyer l'historique que depuis la dernière réponse.

### Horloge

 12. **Δt = 0,6 s** (`TICK_S`), leur valeur en pratique. Ils annoncent un optimum
     d'exactitude à 1,2 s, où l'on est déjà : ce test échange sciemment de
     l'exactitude contre de la latence.
 13. **Descendre la latence sous la seconde.** On est à 7,1 s entre décision et
     parole, eux sous 1 s. C'est l'écart le plus large du projet, et il
     n'apparaît nulle part dans la justesse.
 14. Deux appels en vol au lieu d'un.
 15. Décider sans appel quand le delta est vide depuis moins de N ticks.

### Qualité des briques

 16. **Borne haute à ASR parfait** : rejouer avec la transcription de référence
     en entrée. Si la justesse monte à 0,85, le prompt n'est plus le problème et
     la moitié de cette liste devient inutile. Le test le plus informatif ici.
 17. **`tiny` → `base`**, puis mesure du temps réel sur le PC et sur le Pi. Cinq
     réponses sur treize de `073852` sont « je ne comprends pas » à cause de
     `tu te cheins`, `moi je remapéle`.
 18. **Un modèle plus capable** (gemini-2.5-flash) : eux ont 7B fine-tunés sur la
     tâche. Borne haute de ce que le prompt peut donner.
 19. Fenêtre whisper plus longue (`PLAFOND_S`) : leur ASR streaming a du
     contexte, le nôtre en a peu.
 20. Prompt initial à whisper (vocabulaire attendu, prénoms).
 21. Filtrer les transcriptions à faible confiance.

## 2. Notre fine-tuning : le prompt  `[~]`

Hors conformité par construction — jugé au résultat, rien d'autre. Les exemples
d'abord : ce sont l'analogue le plus direct de leurs données d'entraînement.

 22. Les deux `<|no voice|>` qui SUIVENT une réponse passent à
     `<|user is thinking|>`. Aujourd'hui l'exemple enseigne le contraire de la
     bonne réponse, dans le cas précis où l'on se trompe.
 23. Ratio des exemples : 5 `is talking` pour 2 `finish talking`, contre 171/13
     dans le réel. Le n° 9 de l'ancienne série, à refaire sur ce prompt-ci.
 24. Inverser le ratio.
 25. Un exemple de pause au milieu d'une phrase → `is talking`.
 26. Un exemple d'interruption sur une réponse longue.
 27. Un exemple de backchannel (« mmh »).
 28. Un exemple de transcription cassée où il répond quand même au sens.
 29. Exemples tirés d'une VRAIE session, fautes de whisper comprises.
 30. Doubler le nombre d'exemples (14 tours).
 31. Réduire à 3 tours.
 32. Deux conversations courtes au lieu d'une longue.
 33. Un exemple qui se termine sur une question sans réponse.
 34. Envoyer le tour en cours reconstitué en plus du delta.
 35. Enlever l'espace parasite en tête de chaque message utilisateur.
 36. Donner une identité (nom, rôle) — cinq réponses sur onze de `032332`
     étaient « je suis un grand modèle linguistique ».
 37. Dire que la transcription est machine et contient des erreurs.
 38. Interdire de commenter la transcription (5 réponses sur 13 dans `073852`).
 39. Dire que les fragments sont normaux et n'appellent pas de réponse.
 40. Dire qu'un silence après une réponse n'est pas une nouvelle question.
 41. Donner la durée du micro-tour dans le prompt.
 42. Nommer l'utilisateur.
 43. Préciser ce qu'est une fin de phrase (intonation, sens complet).
 44. Retirer les parenthèses explicatives.
 45. Prompt en anglais, jetons inchangés.

## 3. Ce qui contredit un de leurs quatre choix  `[≠]`

À ne tenter qu'après les blocs précédents, et en le disant.

 46. Remettre les marqueurs d'état. Mesurés nécessaires (7/9 contre 3/9) sur
     l'ancien prompt, et absents chez eux par construction : leur structure
     entrelacée rend l'état du système implicite.
 47. Supprimer les 4 marqueurs jamais sortis, garder les 2 utiles. Ils en ont
     sept, et c'est un choix de design.
 48. Mettre les 2 marqueurs utiles en tête de liste.
 49. `<|user finish talking|>` avant `<|user is talking|>`.
 50. Jetons traduits en français — mesurés meilleurs sur gemini (11/12 contre
     9/12), mais ce ne sont plus leurs chaînes.

---

## Changements passés en force — à mesurer

Écrit le 29/08/2026. Ces quatre changements ont été poussés sans passer par la
liste ni par une QC : ils venaient d'un diagnostic sur le Pi, pas de la file.
Ils sont donc **non mesurés en justesse** — ils peuvent avoir dégradé quelque
chose sans que rien ne le dise. Remis dans le protocole ici.

### 51. piper résident (`b55d716`)  `[~]`

Mesuré sur le Pi : 8 s par phrase économisées. **Non mesuré en justesse.**

- *Ce que le test peut montrer* : que garder piper en vie ne change rien à la
  décision. Ce n'est pas acquis — `Silencieux.speaking()` gouverne l'état « je
  parle », donc le barge-in et l'exemple `<|user interruption|>`.
- *Seuil* : ±0,017. On cherche une NON-régression, pas un gain.
- *Ce que ça rend faux ailleurs* : `stop()` ne tue plus le moteur. Si le PCM
  d'une phrase coupée fuit sur la suivante, le robot dit deux choses à la fois —
  invisible en rejeu muet, audible en vrai.
- *Non mesuré* : le comportement en session réelle, jamais joué depuis.

### 52. préchauffage de piper au démarrage  `[~]`

Les 8 s de chargement ne tombent plus sur la première réponse.

- *Ce que le test peut montrer* : que le thread de préchauffage ne perturbe pas
  le premier tour. Il écrit dans piper pendant que le pipeline démarre.
- *Seuil* : non-régression.
- *Ce que ça rend faux ailleurs* : une syllabe est synthétisée puis jetée au
  lancement. Si `aplay` n'est pas encore là, elle part dans le vide — voulu ;
  si l'ordre change, elle pourrait s'entendre.
- *Non mesuré* : rien, mais jamais joué en vrai.

### 53. cascade de contrainte + garde-fou (`9f9d9c9`)  `[~]`

Quatre niveaux de `response_format`, et vérification de chaque sortie.

- *Ce que le test peut montrer* : que le niveau strict reste choisi avec notre
  modèle, et que le garde-fou ne refuse rien à tort. Un faux refus coûterait
  une décision entière.
- *Seuil* : le compteur `non_conformes` doit rester à zéro.
- *Ce que ça rend faux ailleurs* : la dégradation est irréversible dans une
  session. Une erreur réseau prise pour un refus de schéma ferait tomber tout
  le reste de la conversation en `json_object`.
- *Non mesuré* : le comportement sous erreur réseau franche.

### 54. filtre d'artefacts sans accents  `[~]`

`r[ée]alis` au lieu de `réalis`, pour un moteur qui écrit `REALISES`.

- *Ce que le test peut montrer* : qu'on ne rejette pas de la vraie parole. Le
  motif est plus large qu'avant.
- *Seuil* : non-régression.
- *Ce que ça rend faux ailleurs* : rien, le motif reste ancré sur
  « sous-titres ».
- *Non mesuré* : rien.
