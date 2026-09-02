# Le pivot : d'un compagnon vocal à un observateur de tour de parole

Décisions prises en discussion le 02/09/2026. Ce fichier enregistre **ce qui est
tranché** et **ce qui reste ouvert**. Il ne décrit pas le code actuel (voir
`README.md`), mais ce vers quoi il va.

Le nom définitif du composant n'est pas arrêté — une recherche de terminologie
est en cours. « Observateur » est employé ici comme nom de travail.

---

## 1. Ce que devient le projet

**Une bibliothèque qui fait une seule chose : transformer un flux d'entrée en
transitions d'état décrivant l'utilisateur.**

Le comportement visé est celui d'un clavier : on reçoit la ligne quand
l'utilisateur a appuyé sur Entrée. Pas de phrase à moitié faite.

Ce n'est **pas** un système full-duplex. Un full-duplex parle et écoute en même
temps ; nous ne faisons que la moitié amont — l'observation du tour de
l'utilisateur. Le développeur branche derrière le modèle de réponse qu'il veut.

---

## 2. La règle qui commande tout : l'observateur ignore l'aval

**La bibliothèque ne sait rien de ce qui vient après elle.** Elle ignore si un
agent répond, s'il y a un TTS, quel modèle génère la réponse. Elle observe
l'utilisateur, point. L'API est **unidirectionnelle** : entrée d'un côté,
transitions d'état de l'autre.

**Conséquence n° 1 — l'interruption n'est pas un état.** Une interruption, c'est
un `speaking` reçu pendant que l'agent parle. La première moitié est une
observation, la seconde n'est connue que de l'appelant : c'est donc à l'appelant
de faire l'interprétation. Rien à ajouter dans la bibliothèque.

**Conséquence n° 2 — le backchannel n'est pas une action.** L'observateur signale
qu'un signal d'écoute a été émis. Ce que l'hôte en fait — un son préenregistré,
un « mhm » synthétisé, rien du tout — ne le regarde pas.

**Conséquence n° 3 — pas d'entrée `assistant_speaking()` dans l'API.** Une
version antérieure de cette spec en prévoyait une ; elle est écartée. Elle
faisait remonter dans la bibliothèque une information qui ne lui appartient pas,
et rendait le rejeu déterministe dépendant d'un état externe.

Ce que ça achète : un cœur testable en rejeu pur, sans audio, sans réseau et
sans horloge réelle, et composable avec n'importe quel aval.

### La réserve à ne pas oublier

L'**écho** est le seul cas où l'aval remonte réellement : si le micro capte le
haut-parleur, l'ASR transcrit l'agent et l'observateur voit un utilisateur qui
parle. Ce problème se traite **en amont** (annulation d'écho, ou éloignement
physique du micro — la solution qui a marché ici le 29/08), pas dans la machine
à états.

À noter que le code actuel s'en défend autrement : `_est_echo` compare le texte
entendu au **texte prononcé** par l'agent. Cette défense-là exige de connaître
l'aval et disparaît donc avec la règle ci-dessus. C'est un coût accepté, pas un
oubli.

---

## 3. Les états

Deux natures, à ne pas confondre — c'est l'erreur qu'on vient précisément
d'identifier côté détection/génération.

**Observations** (l'état courant) :

| état | sens |
|---|---|
| `silence` | rien |
| `speaking` | il parle, phrase en cours |
| `thinking` | il se tait **mais n'a pas fini** — ce qu'un VAD ne sait pas voir |
| `backchannel` | signal d'écoute, pas une prise de parole |

**Événement** (ponctuel, avec charge utile) :

| événement | charge |
|---|---|
| `turn_end` | le texte complet de la phrase — le « Entrée » du clavier |

Écartés explicitement : `interruption` (cf. § 2), et `assistant_backchannel` du
papier DuplexCascade, qui n'est pas un état de l'utilisateur mais un conseil
d'action à l'agent.

**Encore ouverts** : un `partial` optionnel (texte en cours, pour l'affichage en
direct et la génération spéculative — un hôte qui veut le comportement clavier
l'ignore) ; un `departed` (long silence, l'utilisateur est parti, ce n'est pas
`thinking`) ; et une valeur de confiance sur `turn_end`, pour que l'hôte règle
son propre compromis latence/faux découpage.

---

## 4. Ce qui sort de la bibliothèque

| Composant | Statut | Motif |
|---|---|---|
| **TTS** | dehors, point d'extension | Ne relève pas de l'observation. Concentre par ailleurs toute la non-portabilité du dépôt (`aplay`, `select` sur tube, `killpg`) |
| **Modèle de réponse** | dehors, point d'extension | Le développeur choisit |
| **ASR** | **dehors, point d'extension** | Décision du 02/09 : doit pouvoir être choisi selon le matériel disponible |
| **Capture audio** | fournie à côté, jamais imposée | Micro, fichier et « push » (l'hôte injecte ses propres blocs — cas WebRTC et téléphonie) |

L'ASR sorti, une question reste à trancher (§ 7) : la bibliothèque consomme-t-elle
encore de l'audio, ou seulement du texte horodaté ?

---

## 5. Docker

**Non pour le cœur, oui pour les modules déportés.**

Un conteneur mettrait une couche entre lui et `/dev/snd`, c'est-à-dire
exactement sur la zone la plus fragile du système — une journée entière a été
passée sur ALSA (`aplay` sans `-D` qui échoue en silence, le HDMI, le tampon) —
pour résoudre un problème d'installation qu'un script et un `requirements` figé
règlent à 90 %.

En revanche, les modules distants (vision, génération d'image, recherche) n'ont
pas d'audio du tout : bons candidats. La ligne de partage est « ça touche au
matériel ou pas ».

---

## 6. Ce que la concurrence impose de savoir

Recherche du 02/09, sources dans `ARTICLE-NOTES.md`.

- **Smart Turn v3.2** (Pipecat/Daily) est très proche du produit visé : BSD-2,
  audio → événement, **8 Mo**, 23 langues dont le français, **12,6 ms sur CPU et
  59,8 ms sur un ARM à 1 vCPU**. Poids, données et script d'entraînement ouverts.
  Il faut partir du principe qu'il existe et qu'il est gratuit.
- **LiveKit Turn Detector** a les meilleurs chiffres publiés, mais sa licence
  interdit noir sur blanc tout usage hors du framework LiveKit. **C'est le vrai
  trou du marché.**
- Ces outils rendent tous une **décision ou une probabilité binaire de fin de
  tour**. Aucun ne produit la machine à états du § 3. C'est la seule
  différenciation propre — reste à savoir si un développeur la paierait.
- **Notre 0,826 n'est comparable qu'à DuplexCascade**, dont la métrique est
  propre à ce papier. Le terrain commun du domaine est
  [eot-bench](https://github.com/livekit/eot-bench) : reproductible, données
  publiques, 14 langues dont le français.

**À faire avant d'écrire une ligne de la bibliothèque** : passer le prototype sur
eot-bench en français. C'est le seul endroit où notre chiffre devient comparable
à celui des autres.

---

## 7. Questions ouvertes, par ordre d'importance

1. **La spéculation.** Aujourd'hui `Decideur.decide()` rend l'état **et** la
   réponse dans le même appel : quand la personne s'arrête, la réponse est déjà
   prête. Séparer détecteur et répondeur en deux points d'extension supprime
   cette spéculation, et la latence redevient détection **puis** aller-retour
   complet. C'est peut-être le vrai prix du mélange qu'on critique par
   ailleurs — il achèterait de la latence, pas de la justesse. **La mesure en
   cours ne le verra pas, elle ne mesure que la justesse.**
2. **Audio ou texte en entrée ?** L'ASR sorti, la bibliothèque peut soit
   continuer à consommer de l'audio avec un ASR injecté, soit ne plus consommer
   que du texte horodaté plus un indicateur de voix. La seconde option règle
   d'un coup toute la portabilité (plus aucune dépendance plateforme), mais perd
   l'information acoustique dont `SEUIL_VOIX` et la distinction silence / bruit
   se servent aujourd'hui.
3. **Le prompt dépend de l'ASR.** Mesuré : la phrase décrivant la casse de
   l'entrée vaut **+0,063 quand elle est vraie et −0,103 quand elle est fausse**.
   Si l'ASR est branchable, le prompt du détecteur doit l'être aussi et lui être
   apparié. Le catalogue le fait déjà sans que ce soit assumé comme une décision
   d'architecture (`systeme` contre `systeme_sherpa`).
4. **Le tick appartient-il à la bibliothèque ou à l'hôte ?** `TICK_S = 1.2` porte
   toute la logique de tour de parole. Le laisser régler par l'hôte, c'est
   accepter qu'il puisse le mettre faux et ne plus rien détecter, sans message.
