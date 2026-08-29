# 50 tests candidats pour faire monter le score

Écrit le 29/08/2026, après que le prompt d'Alex (marqueurs des chercheurs,
exemples dans le système) ait atteint 0,762 sur `20260829-032332`.

État de départ : `f2f3427`, justesse 0,762 — DuplexCascade est à 0,858.
Décomposition : fins de tour 6/9 (TOR 0,667), pauses 1/7 (TOR 0,143).

**Le bruit de mesure est de ±0,116.** Un test qui gagne moins que ça n'a rien
gagné. Sur une seule session de 9 fins de tour, une décision qui bascule vaut
0,055 de justesse : la granularité de la mesure est presque aussi grosse que
les écarts qu'on cherche. C'est le vrai obstacle, avant tous les tests listés
ici — d'où le bloc A.

Ordre : le coût de l'erreur décroît en descendant. Les premiers tests changent
ce qu'on peut CONCLURE ; les derniers ne changent qu'un score.

## A. Rendre la mesure capable de trancher (avant tout le reste)

  1. Mesurer sur les DEUX sessions au lieu d'une (22 fins de tour au lieu de 9).
  2. Trois passes par mesure, retenir la moyenne et l'écart-type.
  3. Vérifier que le rejeu est déterministe à température 0 (deux passes
     identiques ⇒ tout écart vient du modèle, pas de nous).
  4. Compter les décisions par CLASSE (fin de tour ratée vs pause ratée) et non
     un score agrégé — deux erreurs opposées se compensent aujourd'hui.
  5. Isoler la latence de la justesse : une bonne décision arrivée 8 s trop tard
     compte aujourd'hui comme une réussite.
  6. Annoter à la main les vraies interruptions de la session 073852 : la
     dimension est à zéro faute de référence, pas faute de résultat.
  7. Élargir le corpus : 3 sessions de 4 minutes valent mieux que 10 tests sur
     une seule (risque de sur-ajustement à la voix et au débit d'Alex).

## B. Le prompt — ce qui manque

  8. Ajouter au prompt qui il est (nom, rôle). Cinq réponses sur onze étaient
     « je suis un grand modèle linguistique » faute d'identité.
  9. Dire que la transcription est fabriquée par une machine et contient des
     erreurs (la phrase avait disparu à la réécriture).
 10. Dire de ne JAMAIS commenter la transcription elle-même : cinq réponses sur
     treize de la session 073852 sont « je ne comprends pas, reformule ».
 11. Dire que les fragments sont normaux et n'appellent pas de réponse.
 12. Donner la durée du micro-tour (1,2 s) dans le prompt.
 13. Dire explicitement qu'un silence long après une réponse n'est PAS une
     nouvelle question.
 14. Nommer l'utilisateur si on le connaît.
 15. Prompt en anglais, jetons en anglais (le modèle est majoritairement
     anglophone ; à remesurer, l'inverse avait été mesuré sur gemini).
 16. Prompt en anglais, jetons inchangés.
 17. Supprimer la liste des 4 marqueurs jamais sortis, garder les 2 utiles.
 18. Garder les 6 mais mettre les 2 utiles en tête de liste.
 19. Réordonner : mettre `<|user finish talking|>` avant `<|user is talking|>`.
 20. Retirer les parenthèses explicatives (tester la nudité maximale).
 21. Une phrase de plus sur ce qu'est une fin de phrase (intonation, sens
     complet) plutôt que « sa phrase est finie ».

## C. Les exemples

 22. Les deux `<|no voice|>` qui SUIVENT une réponse passent à
     `<|user is thinking|>` (aujourd'hui ils enseignent le contraire).
 23. Un exemple de pause au MILIEU d'une phrase (hésitation) → `is talking`.
 24. Un exemple d'interruption (l'utilisateur repart sur une réponse longue).
 25. Un exemple de backchannel (« mmh ») → `<|user backchannel|>`.
 26. Un exemple de transcription cassée → le modèle répond quand même au sens.
 27. Doubler le nombre d'exemples (14 tours au lieu de 7).
 28. Réduire à 3 tours (tester si les exemples pèsent surtout par leur ratio).
 29. Rééquilibrer le ratio : aujourd'hui 5 `is talking` pour 2 `finish talking`,
     alors que le réel est à 171/13.
 30. Inverser le ratio : plus de `finish talking` que de `is talking`.
 31. Exemples tirés d'une VRAIE session (transcription whisper, fautes comprises)
     plutôt qu'écrits à la main proprement.
 32. Deux conversations d'exemple courtes au lieu d'une longue.
 33. Un exemple qui se termine sur une question restée sans réponse.

## D. L'historique envoyé

 34. Faire varier `MICRO_TOURS` : 48 → 24, → 12, → 96.
 35. N'envoyer que les tours depuis la dernière réponse (l'historique lointain
     n'aide sans doute rien et noie le signal).
 36. Replier les séries de `<|no voice|>` consécutifs en un seul tour annoté.
 37. Remettre les marqueurs d'état (robot parle / vient de parler) — mesurés
     nécessaires à 7/9 contre 3/9, retirés depuis l'alignement.
 38. Envoyer le tour EN COURS reconstitué en plus du delta.
 39. Enlever l'espace parasite en tête de chaque message utilisateur.

## E. La reconnaissance vocale (la piste la plus lourde de la session 073852)

 40. Passer de `tiny` à `base` : mesurer le coût en temps réel sur le PC, puis
     sur le Pi. « tu te cheins », « moi je remapéle » viennent de là.
 41. Mesurer la justesse avec la transcription de RÉFÉRENCE en entrée : borne
     haute de ce que le prompt peut atteindre à ASR parfait.
 42. Augmenter la fenêtre whisper (`PLAFOND_S`) pour lui donner du contexte.
 43. Passer un prompt initial à whisper (vocabulaire attendu, prénoms).
 44. Filtrer les transcriptions dont whisper donne une confiance basse.
 45. Ne pas envoyer de delta quand il ne contient qu'un mot douteux.

## F. Le rythme

 46. Faire varier `TICK_S` : 1,2 → 0,6 (leur valeur en pratique) et → 2,0.
 47. Réduire la latence : aujourd'hui 7,1 s entre décision et parole, alors que
     leur système répond en moins d'une seconde.
 48. Autoriser deux appels en vol au lieu d'un.
 49. Décider immédiatement (sans appel) quand le delta est vide ET que le
     silence dure depuis moins de N ticks.
 50. Un modèle plus gros pour la décision (gemini-2.5-flash) : borne haute de ce
     que le prompt peut donner, indépendamment de la taille du modèle.
