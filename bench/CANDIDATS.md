# Tests candidats, ordonnés par proximité au papier

Écrit le 29/08/2026. Réordonné à la demande d'Alex : **à gain égal, on prend le
test qui nous rapproche de DuplexCascade.**

État de départ : `f2f3427`, justesse 0,762 sur `20260829-032332`.
DuplexCascade est à 0,858.  Fins de tour 6/9 · pauses 1/7.

## Ce que « près du papier » peut vouloir dire — et ne peut pas

`FORMAT-CHERCHEURS.md` §1, constaté dans leur code : **ils n'ont aucun prompt
système.** Tout leur comportement vient du fine-tuning LoRA sur Qwen2-7B.

Donc la proximité au papier ne discrimine que sur quatre choses : les **jetons**,
la **structure des messages**, l'**horloge**, et la **qualité des briques**
(ASR, taille du modèle). Sur le contenu du prompt, il n'y a rien à copier — nos
227 mots sont entièrement une invention, rendue nécessaire par le fait qu'on
n'entraîne pas.

Une distinction utile en découle, et elle recoupe ce qu'on a mesuré hier
(« on peut retirer les règles, pas les données ») :

- une **règle** ajoutée au prompt n'a aucun équivalent chez eux — elle s'en
  éloigne ;
- un **exemple** ajouté est la transposition directe de leurs données
  d'entraînement — le few-shot est ce qui remplace leur fine-tuning. Il s'en
  rapproche.

Enfin, un fait mesuré à ne pas perdre de vue : **leur format exact, sur un modèle
non entraîné, donne 3/9 contre 7/9.** La sobriété de leur design est un produit
du fine-tuning, pas une propriété transposable. Se rapprocher d'eux peut coûter
du score, et c'est une décision assumée, pas un accident à corriger.

Marquage : `[=]` reproduit ce qu'ils font · `[~]` hors de leur périmètre ·
`[≠]` s'en éloigne sciemment.

---

## 0. Préalable — rendre la mesure capable de trancher  `[~]`

Le bruit est de ±0,116. Sur 9 fins de tour, une décision qui bascule vaut 0,055
de justesse : la granularité est presque aussi grosse que les écarts cherchés.
Tant que ça tient, chaque test a une chance sérieuse de faire conclure l'inverse
de la vérité (arrivé aux itérations 1, 5 et 14).

  1. Mesurer sur les DEUX sessions (22 fins de tour au lieu de 9).
  2. Trois passes par mesure ; retenir moyenne et écart-type.
  3. Vérifier que le rejeu est déterministe à température 0.
  4. Compter par CLASSE d'erreur — deux erreurs opposées se compensent
     aujourd'hui dans un score agrégé.
  5. Séparer latence et justesse : une bonne décision arrivée 8 s trop tard
     compte aujourd'hui comme une réussite.
  6. Annoter à la main les interruptions de `073852` : la dimension est à zéro
     faute de référence, pas faute de résultat.
  7. Une troisième session, pour ne pas sur-ajuster à une voix et un débit.

## 1. Ce qui nous rapproche d'eux  `[=]`

  8. **Le mode complétion au lieu du mode chat.** C'est LA différence de nature
     (`FORMAT-CHERCHEURS.md` §6) : eux complètent un flux, nous remplissons une
     conversation à deux rôles. De là viennent nos trois difficultés propres —
     l'état du système sans endroit où vivre, le besoin d'un prompt donc de
     règles, et des exemples qui occupent les mêmes rôles que le réel. Vérifier
     d'abord qu'OpenRouter expose la complétion sur un modèle utilisable.
  9. **Δt = 0,6 s** (`TICK_S`), leur valeur en pratique. Le papier note un
     optimum d'exactitude à 1,2 s — on est dessus, donc ce test échange de
     l'exactitude contre de la latence, en connaissance de cause.
 10. **Descendre la latence sous la seconde.** On est à 7,1 s entre décision et
     parole ; eux répondent en moins d'une seconde. C'est l'écart le plus large
     de tout le projet, et il ne se voit pas dans la justesse.
 11. **Horizon de dix micro-tours système** (`MICRO_TOURS` 48 → 20), la longueur
     fixe de leurs données d'entraînement.
 12. **Un ASR qui ne casse pas.** `tiny` → `base`, puis mesure du temps réel sur
     le PC et sur le Pi. Cinq réponses sur treize de `073852` sont « je ne
     comprends pas » à cause de `tu te cheins`, `moi je remapéle`.
 13. **Borne haute à ASR parfait** : rejouer avec la transcription de référence
     en entrée. Si la justesse monte à 0,85, le prompt n'est plus le problème et
     la moitié de cette liste devient inutile. Le test le plus informatif ici.
 14. **Un modèle plus capable** (gemini-2.5-flash) : eux ont 7B fine-tunés sur la
     tâche. Borne haute de ce que le prompt peut donner.
 15. Fenêtre whisper plus longue (`PLAFOND_S`) : leur ASR streaming a du
     contexte, le nôtre en a peu.

## 2. Les données — le substitut de leur fine-tuning  `[~]`

 16. Les deux `<|no voice|>` qui SUIVENT une réponse passent à
     `<|user is thinking|>`. Aujourd'hui l'exemple enseigne le contraire de la
     bonne réponse, dans le cas précis où on se trompe.
 17. Un exemple de pause au milieu d'une phrase (hésitation) → `is talking`.
 18. Un exemple d'interruption sur une réponse longue.
 19. Un exemple de backchannel (« mmh »).
 20. Un exemple de transcription cassée où il répond quand même au sens.
 21. Exemples tirés d'une VRAIE session, fautes de whisper comprises, plutôt
     qu'écrits proprement à la main.
 22. Ratio : 5 `is talking` pour 2 `finish talking` aujourd'hui, 171/13 dans le
     réel. Rapprocher l'un de l'autre.
 23. Inverser le ratio (plus de `finish talking`).
 24. Doubler le nombre d'exemples (14 tours).
 25. Réduire à 3 tours.
 26. Deux conversations courtes au lieu d'une longue.
 27. Un exemple qui se termine sur une question sans réponse.
 28. Replier les séries de `<|no voice|>` consécutifs en un tour annoté.
 29. Enlever l'espace parasite en tête de chaque message utilisateur.
 30. N'envoyer l'historique que depuis la dernière réponse.
 31. Envoyer le tour en cours reconstitué en plus du delta.

## 3. Ce qui s'en éloigne  `[≠]`

À ne tenter qu'après épuisement des deux blocs précédents, et en le disant.

 32. Donner une identité (nom, rôle). Cinq réponses sur onze étaient « je suis un
     grand modèle linguistique » — mais eux n'ont aucun prompt système.
 33. Dire que la transcription est machine et contient des erreurs.
 34. Interdire de commenter la transcription (« je ne comprends pas, reformule »
     = 5 réponses sur 13 dans `073852`).
 35. Dire que les fragments sont normaux et n'appellent pas de réponse.
 36. Dire qu'un silence après une réponse n'est pas une nouvelle question.
 37. Donner la durée du micro-tour dans le prompt.
 38. Nommer l'utilisateur.
 39. Remettre les marqueurs d'état — mesurés nécessaires (7/9 contre 3/9), et
     explicitement absents chez eux.
 40. Supprimer les 4 marqueurs jamais sortis, garder les 2 utiles (ils en ont 7).
 41. Mettre les 2 marqueurs utiles en tête de liste.
 42. `<|user finish talking|>` avant `<|user is talking|>`.
 43. Retirer les parenthèses explicatives.
 44. Préciser ce qu'est une fin de phrase (intonation, sens complet).
 45. Prompt en anglais, jetons en anglais.
 46. Prompt en anglais, jetons inchangés.
 47. Deux appels en vol au lieu d'un.
 48. Décider sans appel quand le delta est vide depuis moins de N ticks.
 49. Filtrer les transcriptions à faible confiance whisper.
 50. Prompt initial à whisper (vocabulaire, prénoms).
