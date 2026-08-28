# Protocole d'amélioration continue

Posé par Alex le 29/08/2026, après une session où le système ne répondait plus et
où l'analyse partait dans tous les sens. L'idée : ne jamais juger à l'oreille, et
ne solliciter Alex que quand il y a vraiment quelque chose à décider.

## La boucle

**1. Établir ce qui a vraiment été dit.**
Le système tourne avec `tiny` pour être temps réel sur un Pi ; il se trompe. On ne
peut donc pas juger ses décisions sur sa propre transcription. On repasse l'audio
dans un modèle bien plus gros, hors ligne, avec des timecodes :

```bash
.venv/bin/python tests/reference.py sessions/<horodatage>
```

**2. Comparer** cette référence à ce que le système a fait (`session.jsonl` :
transcriptions, prompts envoyés, réponses brutes, décisions, niveaux de la porte).
Repérer où ça diverge, et *à quel étage* — micro, STT, décideur, TTS.

**3. Comprendre avant de toucher.** Tant que la cause n'est pas identifiée, ne rien
corriger : sinon on empile des rustines sur un symptôme. Distinguer en particulier
ce qui vient du **matériel** (un micro Bluetooth en HFP détruit le signal, et aucun
code ne le rattrapera) de ce qui vient du **code**.

**4. Corriger** une cause à la fois.

**5. Tester de bout en bout — AVANT de solliciter Alex.**

```bash
bash tests/fumee.sh
```

Vérifier la fonction qu'on vient de changer ne suffit pas : une constante
supprimée en réécrivant un bloc ne casse pas la fonction, elle casse le
**programme au démarrage**. C'est arrivé le 29/08, et c'est Alex qui l'a découvert
en lançant une session — après que j'aie annoncé que c'était prêt.

Règle : **dès qu'une modification peut avoir cassé quelque chose ailleurs, la
chaîne complète doit tourner avant qu'Alex soit sollicité.**

**6. Rejouer la scène** sur le même audio, et comparer les chiffres :

```bash
.venv/bin/python pipeline.py sessions/<horodatage>/entree.wav --muet --trace /tmp/rejeu
```

C'est le seul moyen de savoir si une correction améliore vraiment : même audio,
mêmes conditions, seul le code change. L'empreinte du code est dans `meta.json`,
donc deux traces sont toujours comparables.

**7. Recommencer** en 4-5-6 tant que ce n'est pas bon.

**8. S'arrêter** quand c'est vraiment bien, ou après **dix tours**. Alors seulement :
un rapport court à Alex, avec les chiffres avant/après, ce qui reste ouvert, et
les questions posées **en choix multiples**.

## Ce qu'on juge, et ce qu'on ne juge pas

**On évalue le comportement de tour de parole, pas la pertinence des réponses.**
Posé par Alex le 29/08/2026 : la bêtise des réponses tient à la taille du modèle
(un 3B distant, ou un 1B), c'est attendu et ce n'est pas le sujet.

Ce qui compte, et qui est mesurable :
- coupe-t-il la parole au milieu d'une phrase ?
- répond-il à un fragment, avant que la phrase soit finie ?
- se tait-il quand il faut se taire, et parle-t-il quand on lui demande quelque chose ?
- combien de temps entre le dernier mot et le premier son de la réponse ?
- s'interrompt-il tout seul sur son propre écho ?

Ce qui ne compte pas : la justesse ou la finesse de ce qu'il dit. Une réponse plate
au bon moment vaut mieux qu'une réponse brillante qui coupe la parole.

Corollaire pour l'analyse : quand il répond à côté, distinguer **« il a mal
compris »** (modèle, hors sujet) de **« il a répondu trop tôt, sur un bout de
phrase »** (timing, notre problème). Exemple réel : « Une fière, ça veut dire
quoi ? » alors que la phrase était « je vais faire une phrase très longue » — ce
n'est pas une erreur de modèle, c'est une prise de parole prématurée.

## Ce qui ne se corrige pas par le code

- **Le micro.** Un casque Bluetooth en HSP/HFP CVSD est en 8 kHz : la moitié du
  spectre de la parole manque, et même un modèle six fois plus gros échoue sur le
  même fichier. Basculer en mSBC (16 kHz), ou utiliser un vrai micro.
- **L'écho**, sans casque : la porte de volume le limite, elle ne l'annule pas.

## Sur le Pi

Même boucle, en ajoutant à chaque mesure la température et l'état de throttling —
le Pi atteint 80 °C en 25 s de charge sur quatre cœurs et se bride, ce qui fausse
toute mesure prise à chaud. Refroidir sous 60 °C avant chaque passe.
