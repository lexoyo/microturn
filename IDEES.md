# Idées à tester

**Ce fichier est un parking, pas une feuille de route.** Posé par Alex le
29/08/2026 : on parle dans tous les sens, et le plus simple est presque toujours
le mieux. Donc on **note** les idées compliquées ici et on y revient **si le
besoin se présente** — pas parce qu'elles sont écrites.

Rien ne descend d'ici vers le code sans une raison mesurée : un symptôme observé
sur une vraie session, ou un chiffre qui manque pour trancher. Une idée qui reste
en `à tester` pendant des semaines est une bonne nouvelle, pas une dette.

Une idée par section, avec une **hypothèse falsifiable** et le **protocole** qui
la tranche. Rien n'entre dans le code parce que ça semble raisonnable : on rejoue
la même session enregistrée avec et sans, et on compare les chiffres.

Statuts : `à tester` · `en cours` · `retenu` · `écarté` (avec le chiffre qui a tranché).

---

## 1. Donner au modèle des repères temporels, en français

**Statut : à tester.** Proposée par Alex le 29/08/2026.

Aujourd'hui le décideur ne voit **que du texte**. Il ignore depuis combien de temps
la personne parle, si c'est son premier silence ou son troisième, s'il vient de
répondre il y a deux secondes ou trente. Or c'est exactement ce que le fine-tuning
de DuplexCascade encode implicitement : leur simulation insère 1 à 5 micro-tours
silencieux au milieu d'un tour, supervisés en « elle parle encore ». Faute de
pouvoir entraîner, on peut le **dire** au modèle.

**Hypothèse** : ajouter des repères temporels verbalisés augmente la part de
« elle parle encore » sur les pauses intra-tour, sans réduire le nombre de
réponses aux vraies questions.

**Verbaliser, ne pas chiffrer.** Un 3B ne fera rien de `débit: 2,3 mots/s`, mais
il comprend « troisième silence d'affilée ». Les modèles raisonnent sur du langage.

Trois variantes, à tester séparément et dans cet ordre :

- **a) Compteur de silences consécutifs** — « elle n'a rien dit depuis trois tours ».
  Le plus prometteur : c'est le signal qui sépare une respiration d'une fin de phrase.
- **b) Durée du tour en cours** — « elle parle depuis huit secondes ». Aide à ne pas
  couper un long développement.
- **c) Variation du débit** — ⚠️ **une accélération, pas une vitesse** (remarque
  d'Alex, et elle est décisive) : le signal linguistique est l'*allongement final*,
  donc c'est le **ralentissement par rapport au débit habituel de la personne** qui
  annonce une fin de tour. Un débit absolu ne dit rien, chacun a le sien. À exprimer
  en « elle ralentit » / « elle accélère », après calibrage sur les 30 dernières
  secondes du même locuteur. Le plus incertain des trois : signal subtil, petit
  modèle.

**Protocole** : rejouer trois sessions enregistrées, quatre configurations
(rien, a, a+b, a+b+c). **Mesurer** : ratio se taire / parler ; nombre de prises de
parole survenues alors que la personne n'avait pas fini (comparé à la
transcription de référence) ; latence entre le dernier mot et la réponse.

**Coût à surveiller** : chaque ligne est payée à chaque appel, 50 fois par minute.

---

## 1 bis. Traduire les transcriptions en anglais avant de les donner au modèle

**Statut : à tester.** Proposée par Alex le 29/08/2026.

Le prompt système et les jetons sont en anglais, l'entrée en français. Faudrait-il
aligner en traduisant la transcription ?

**Mon avis, à réfuter** : non, et pour deux raisons mesurées. Le QC a montré que ce
qui fait s'effondrer les petits modèles, c'est la langue des **jetons**, pas celle
de l'entrée — labels français : 2 bonnes décisions sur 21 sur le 1B, labels anglais :
16. Et l'entrée française est précisément ce qui **ancre la réponse en français**
(0 réponse en anglais sur 21 mesurées) ; la retirer, c'est risquer la dérive
linguistique que le few-shot compense aujourd'hui.

**Coût** : un appel de traduction avant chaque décision, donc latence et facture
doublées, 50 fois par minute. Sauf à traduire dans le même appel — mais alors on
demande deux tâches au modèle, ce qui est exactement ce qui pose déjà problème.

**Ce qu'on perdrait** : les erreurs de transcription caractéristiques. Un traducteur
« réparerait » ou déformerait « un an et plus en t'es non assez fan ce fil », alors
que le modèle doit apprendre à reconnaître ce bruit et à répondre SPEAKING.

**Mesure du 29/08 qui affaiblit encore l'hypothèse** : instructions en anglais
contre instructions en français, à jetons identiques, sur 11 cas — **9/11 contre
8/11, et zéro réponse en anglais dans les deux cas**. L'écart est dans le bruit.
Si la langue des *instructions* ne change rien, il est peu probable que celle de
l'*entrée* change grand-chose : c'est la langue des **jetons** qui porte l'effet,
et elle est déjà en anglais.

**Ce qui pourrait quand même la justifier** : faire tourner le banc des
chercheurs, dont le corpus est anglais. Mais dans ce cas on ne traduit rien —
on bascule simplement `--langue en`, ce qui existe désormais.

**Protocole si on y revient** : rejouer une session avec et sans traduction,
comparer le taux de détection des vraies questions et le taux de fausses prises de
parole sur le bruit.

## 2. Le few-shot déséquilibré aide-t-il vraiment ?

**Statut : à tester — et je me suis contredit dessus, donc il faut trancher.**

Le prompt contient 12 exemples avec 9 « elle parle encore » pour 2 prises de parole,
pour reproduire le ratio structurel d'une vraie conversation (~10 pour 1) qu'un
modèle instruction-tuné n'a pas : il est dressé à répondre.

**Mais** : sur l'ancien format de jetons, j'ai mesuré que le few-shot **dégradait**
(4 bonnes décisions sur 5 sans exemples, 3 sur 5 avec). Format différent, exemples
équilibrés — pas comparable, mais pas rassurant non plus.

**Hypothèse** : avec le format « état perçu », un few-shot déséquilibré améliore le
ratio sans faire manquer de vraies questions.

**Protocole** : même session, avec et sans `FEWSHOT`. Si l'écart est nul, on
supprime — 12 exemples payés 50 fois par minute, ça se justifie ou ça saute.

---

## 2 bis. Passer à une vraie bibliothèque d'internationalisation

**Statut : écarté pour l'instant, à revoir si le nombre de langues augmente.**
Question d'Alex, 29/08/2026.

Les catalogues `locales/<langue>.txt` sont maison. Pourquoi pas `gettext` ou
`babel` ?

**Une objection d'Alex, et elle est juste** : les jetons *sont* des traductions
(`A_FINI` / `FINISHED`), et les deux prompts disent aujourd'hui la même chose.
L'argument « ce ne sont pas des traductions » était une justification a posteriori.
Le seul endroit où ça ne se traduit pas est marginal : l'exemple de bruit de
transcription doit être un vrai extrait de la langue concernée — l'anglais actuel
a été inventé en traduisant le français mot à mot, ce qui n'a pas de sens.

**Les raisons qui tiennent sont des raisons de commodité** : `gettext` vise des
chaînes courtes d'interface, et un prompt de vingt lignes dans un `msgid` est
ingérable ; il impose une compilation `.po` → `.mo` avant chaque exécution ; et
ce serait une dépendance pour deux fichiers édités par une seule personne.

**Quand y revenir** : dès qu'il y a plus de trois ou quatre langues, ou qu'une
personne extérieure contribue un catalogue. L'outillage — éditeurs dédiés,
détection des entrées manquantes ou périmées — vaudrait alors la cérémonie.

## 3. La taille du modèle change-t-elle quelque chose ?

**Statut : à tester.** Trois modèles très différents sur la même session.

**Hypothèse (la mienne, à réfuter)** : décider si quelqu'un a fini sa phrase est
une tâche de **perception**, pas de raisonnement. La taille n'aiderait donc pas —
et pourrait même nuire, un gros modèle étant plus dressé à se rendre utile, donc
plus bavard.

Si elle se vérifie, ça change tout pour le Pi : le petit modèle suffit.

**Contrainte dure** : la latence doit rester sous `TICK_S`, sinon chaque appel
déborde. `llama-3.3-70b` est à **10,46 s** — éliminé d'office.

**Protocole** : mesurer d'abord la latence des candidats, puis rejouer la même
session avec les trois qui tiennent. Comparer ratio, moments de prise de parole,
et coupures de phrase.

---

## 4. Quelle valeur pour l'horloge ?

**Statut : 1,2 s retenu par transposition, jamais mesuré chez nous.**

Le papier donne 0,858 d'exactitude à 0,6 s et **0,934 à 1,2 s**, avec la latence
qui monte de 1,72 s à ~2,85 s. Ils ont choisi 0,6 s pour la réactivité ; nous avons
pris 1,2 s parce que notre problème est la justesse. **Leur mesure, pas la nôtre.**

**Protocole** : rejouer la même session à 0,6 / 1,2 / 1,8 s. Attention, ce n'est pas
gratuit : 0,6 s double le coût en appels réseau.

---

## 5. Sources de contexte externes

**Statut : à concevoir.** Idée d'Alex : injecter dans le prompt du texte venant
d'ailleurs — ce que la caméra voit, ce que YAMNet entend, l'heure, la pièce.

**Hypothèse** : le modèle peut réagir à ce qui se passe, pas seulement à ce qui se
dit. C'est ce qui sépare un assistant vocal d'un compagnon qui habite la pièce.

**À trancher avant de coder** : la fréquence de rafraîchissement (YuNet coûte 46 ms
en résident, YAMNet 157 ms — on ne les appelle pas à chaque tick), et comment ne pas
noyer le prompt.

---

## 6. Réintroduire le backchannel, mais autrement

**Statut : écarté pour l'instant, sur une mesure.**

Chez eux, activer le backchannel fait **tripler** le taux de prise de parole
intempestive sur les pauses (0,058 → 0,343) et coûte 11 points d'exactitude. Leur
configuration phare n'en a pas.

**Si on y revient** : un clip audio **pré-enregistré**, tiré au hasard, jamais passé
par le TTS — c'est leur solution, et elle supprime la latence de synthèse.

---

## 7. Streamer le texte au TTS au fil des mots

**Statut : à tester.**

Ils poussent le texte au TTS **token par token**, sans attendre la ponctuation.
Nous synthétisons la phrase entière avant d'émettre un son.

**Hypothèse** : plusieurs centaines de millisecondes de latence perçue à gagner.

**Réserve mesurée** : piper recharge son modèle de 63 Mo à chaque invocation
(~0,7 s ici, plusieurs secondes sur un Pi). Découper n'a de sens qu'avec un piper
**résident** lisant sur son entrée standard. Sinon c'est une pessimisation.

---

## 8. Un point de décision pendant que le robot parle

**Statut : à concevoir.**

Chez eux, le système parle par tranches de **10 tokens**, avec un point de décision
entre chaque — c'est **la condition du barge-in**. Si notre TTS prononce une phrase
entière d'un bloc, aucun réglage ne nous rendra interruptibles.

**À vérifier d'abord** : est-ce que `Speaker.stop()` coupe vraiment net, y compris
le tampon d'ALSA ? Sinon le reste est sans objet.
