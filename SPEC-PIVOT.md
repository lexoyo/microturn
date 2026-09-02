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
| `thinking` | il se tait **mais n'a pas fini** — ce qu'un VAD ne sait pas voir ; *intra-turn pause* dans la littérature, cf. § 7 |
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
- **MaAI** (Kyoto, MIT) est le concurrent le plus proche du périmètre :
  turn-taking et backchannel en temps réel, autonome, **sans connaissance de
  l'aval** — notre contrainte, déjà implémentée. Mais il rend des **prédictions
  continues**, sans machine à états et sans le texte de la phrase. **Notre delta
  face à lui est la couche d'états et le texte, pas le signal.**
- **Notre 0,826 n'est comparable qu'à DuplexCascade**, dont la métrique est
  propre à ce papier. Le terrain commun du domaine est
  [eot-bench](https://github.com/livekit/eot-bench) : reproductible, données
  publiques, 14 langues dont le français.

**À faire avant d'écrire une ligne de la bibliothèque** : passer le prototype sur
eot-bench en français. C'est le seul endroit où notre chiffre devient comparable
à celui des autres.

---

---

## 7. Le vocabulaire du domaine

Recherche du 02/09. **À employer partout** : ces mots rendent le projet
trouvable, et la plupart de nos états portent un nom depuis cinquante ans.

### Trois niveaux à ne pas confondre

```
endpointing  ⊂  end-of-turn detection (EOU)  ⊂  turn-taking prediction (PTTM)
```

- **endpointing** — terme historique de l'ASR, décision binaire sur le signal
  acoustique. C'est le mot de MRCPv2 (RFC 6787).
- **end-of-turn detection / EOU** — même décision, mais avec des indices
  sémantiques et pragmatiques. « Semantic end-of-turn detector » est le terme
  précis (Aldeneh et al. 2018).
- **turn-taking prediction / PTTM** — pas une décision mais une prévision
  continue de l'activité vocale à venir des deux interlocuteurs. Famille
  TurnGPT / VAP.

**Nous ne sommes dans aucun des trois** : nous produisons une machine à états
observée. Il n'existe pas de terme consacré pour ça — espace lexical libre, avec
son revers : personne ne cherchera la bibliothèque par ce mot-clé.

### Nos états ont des noms depuis 1974

Sacks, Schegloff & Jefferson (1974) distinguent trois silences, et la
distinction est exactement la nôtre :

| terme du domaine | sens | notre état |
|---|---|---|
| **pause** | silence **à l'intérieur** d'un tour | `thinking` |
| **gap** | silence court **entre** deux tours, à un TRP | ce qui suit `turn_end` |
| **lapse** | silence long, personne ne reprend | `departed` (encore ouvert) |

⚠️ « pause » seul est ambigu hors analyse conversationnelle. Employer
**intra-turn pause** ou **turn-holding pause**.

Autres termes à reprendre tels quels : **TRP** (*transition-relevance place*, le
moment où le tour peut changer), **the floor** (la ressource disputée),
**backchannel** (Yngve, 1970 — en français, la littérature dit « régulateur »).

### Le précédent le plus proche : FSTTM

Raux & Eskenazi, NAACL 2009, *A Finite-State Turn-Taking Model* : six états
(`USER`, `SYSTEM`, `FREE_S`, `FREE_U`, `BOTH_S`, `BOTH_U`). Notre `thinking` est
leur `FREE_U` ; « il commence à parler pendant que l'agent parle » est leur
`BOTH_S`.

**La différence est exactement notre parti pris** : le FSTTM modélise le floor
*joint* et sert à **choisir une action**, donc il connaît l'aval. Ce que nous
construisons est **la projection du FSTTM sur le seul axe utilisateur, en mode
observation**. C'est la formule la plus juste du périmètre, et rien de tel n'a
été trouvé dans la littérature ni dans le logiciel libre.

### Un cadre à connaître : IU (Incremental Units)

Schlangen & Skantze, EACL 2009. Formalise le transport incrémental entre modules
qui ne savent pas qui les consomme — notre principe d'indépendance de l'aval,
déjà publié. Ses opérations `add` / `commit` / **`revoke`** décrivent la révision
d'une hypothèse déjà émise : c'est précisément ce que gère notre `_delta` quand
l'ASR se ravise. Implémentations : InproTK (Java), retico (Python, peu adopté).

IU donne le **transport**, pas le modèle du tour. Les deux sont complémentaires.

### Le nom

**`microturn` est libre partout (PyPI, npm, crates.io) mais mauvais pour ce
périmètre.** « micro-turn » n'existe pas dans la littérature, et pour quelqu'un
du domaine un « tout petit tour de parole » *est* un backchannel — le nom pointe
donc vers le plus mineur de nos états.

Candidats libres et vérifiés : **turnstream** (aucune collision, nulle part),
**floorstate** (le plus juste conceptuellement), **turnfsm** (exact, laid).

Décision non prise. Si le nom reste, lui adosser une tagline descriptive et des
mots-clés `turn-taking`, `end-of-turn`, `EOU`, `backchannel`, `endpointing`.

---

## 8. Détection et réponse : trois modes

### Décision du 02/09 — les trois modes sont une option, pas un choix de conception

Le problème : aujourd'hui `Decideur.decide()` rend l'état **et** la réponse dans
le même appel. Quand la personne s'arrête, la réponse est déjà prête. Séparer
détecteur et répondeur supprime cette spéculation et rajoute un aller-retour.
Mais faire faire la détection de fin de phrase par un gros modèle coûte cher.

**Tranché : c'est une option offerte par la bibliothèque, pas une architecture
imposée.** Et la forme retenue évite d'avoir deux produits — **un champ
facultatif dans l'événement, pas deux API** :

```
turn_end(text="...", draft=None)    # mode séparé  : l'hôte appelle son modèle
turn_end(text="...", draft="...")   # mode fusionné : la réponse est déjà là
```

Le protocole `Decider` reste unique, sa sortie porte une réponse facultative.
Aucune branche dans le cœur ; changer de mode ne change pas le code de l'hôte.

**Les trois modes** :

| mode | détection | réponse | latence | coût |
|---|---|---|---|---|
| **séparé** | petit modèle, local | l'hôte appelle après `turn_end` | détection **+** aller-retour | le plus bas |
| **fusionné** | le gros modèle, à chaque tick | même appel que la détection | minimale | 159 appels pour 13 réponses (mesuré) |
| **spéculatif** | petit modèle, local | déclenchée **en avance** quand la fin approche, en parallèle | ≈ fusionné | ~20-30 appels au lieu de 159 |

Le mode **spéculatif** domine probablement les deux autres et n'était dans aucun
énoncé : il donne la latence du fusionné pour environ cinq fois moins d'appels au
gros modèle, au prix des générations jetées — arbitrage réglé par un seuil que
l'hôte choisit. Il ne demande aucune conception supplémentaire : c'est le même
champ `draft`, rempli plus tôt.

**Deux conséquences à assumer dans l'API** :

- En mode fusionné, **détecteur et répondeur ne sont plus deux points d'extension
  mais un seul**. Sans ça, un développeur croira pouvoir associer un petit
  détecteur local à un gros répondeur, et découvrira que dans ce mode c'est le
  même objet.
- Le mode fusionné perd l'argument central du projet — pas de réseau dans la
  boucle serrée. C'est pourtant **le seul qu'on ait mesuré** : les 0,826 en
  viennent. Les chiffres des deux autres modes n'existent pas encore.

---

## 9. Questions ouvertes, par ordre d'importance

1. **Audio ou texte en entrée ?** L'ASR sorti, la bibliothèque peut soit
   continuer à consommer de l'audio avec un ASR injecté, soit ne plus consommer
   que du texte horodaté plus un indicateur de voix. La seconde option règle
   d'un coup toute la portabilité (plus aucune dépendance plateforme), mais perd
   l'information acoustique dont `SEUIL_VOIX` et la distinction silence / bruit
   se servent aujourd'hui.
2. **Le prompt dépend de l'ASR.** Mesuré : la phrase décrivant la casse de
   l'entrée vaut **+0,063 quand elle est vraie et −0,103 quand elle est fausse**.
   Si l'ASR est branchable, le prompt du détecteur doit l'être aussi et lui être
   apparié. Le catalogue le fait déjà sans que ce soit assumé comme une décision
   d'architecture (`systeme` contre `systeme_sherpa`).
3. **Le tick appartient-il à la bibliothèque ou à l'hôte ?** `TICK_S = 1.2` porte
   toute la logique de tour de parole. Le laisser régler par l'hôte, c'est
   accepter qu'il puisse le mettre faux et ne plus rien détecter, sans message.
