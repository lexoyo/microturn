# PAPIER.md — fiche de lecture de DuplexCascade

Fiche de consultation rapide sur le papier fondateur du projet. Elle sert à
retrouver en dix secondes un chiffre, un jeton ou un réglage **de chez eux**,
sans rouvrir arXiv.

**Aucun chiffre de cette fiche n'est une mesure de microturn.** Tout ce qui suit
est *leur* résultat, sur *leur* banc. Nos chiffres à nous vivent dans
`RESULTATS.md`, `RESULTATS-PI.md` et `bench/JOURNAL.md`, et ne se comparent pas
ligne à ligne à ceux-ci (cf. § 7).

**Statut au 03/09 au soir : le PDF a été lu à la source.** Le Tableau 1 (p. 3)
et le § 4.4 (p. 4) sont relevés ligne à ligne ; ce qui en vient est marqué et
n'a plus de réserve. Le reste garde la sienne (§ 0).

Deux fiches voisines, à ne pas confondre :
- **celle-ci** — ce que dit le papier : thèse, jetons, réglages, résultats ;
- **`FORMAT-CHERCHEURS.md`** — le *format* exact, papier **et** code lu dans
  `server.py` le 29/08 (chaînes littérales, structure ChatML, absence de prompt
  système). C'est là qu'il faut aller pour écrire un prompt, pas ici.

---

## 0. Réserve de méthode — à lire avant de citer quoi que ce soit

**Ce qui est vérifié à la source, et ne porte plus de réserve** : tout ce qui
est marqué **« Tableau 1 p. 3 »** ou **« § 4.4 p. 4 »**, c'est-à-dire les § 5.1,
5.3 et 6. Lecture directe du PDF, 03/09/2026 au soir. Elle a corrigé **trois
chiffres qui circulaient faux dans le dépôt, dont deux dans le `README.md`
public** — le détail des corrections est en § 5.4.

**Ce qui garde sa réserve** : tout le reste vient d'une lecture automatique de la
page HTML du papier, le 03/09 au matin. Concrètement les réglages du § 4, les
données synthétiques, le VoiceBench de la § 5.2 — et surtout la **définition de
`<user is thinking>`** du § 3, qui n'est ni dans le Tableau 1 ni au § 4.4, et
qui reste la case ouverte qui engage le plus (elle porte l'argument de vente du
projet). État à jour en § 9.

Rappel qui vaut pour toute la fiche : **aucun de ces chiffres n'est une mesure de
microturn**, et un chiffre lu sur un graphique n'est pas un chiffre de tableau
— quand c'est le cas, c'est écrit.

---

## 1. Références

**Titre** : *DuplexCascade: Full-Duplex Speech-to-Speech Dialogue with VAD-Free
Cascaded ASR-LLM-TTS Pipeline and Micro-Turn Optimization*

**Auteurs** : Jianing Yang, Yusuke Fujita, Yui Sudo (SB Intuitions, université de
Tokyo). **Soumis le 10 mars 2026.**

- Papier : https://arxiv.org/abs/2603.09180
- Code : github.com/sbintuitions/DuplexCascade (licence MIT)

---

## 2. La thèse, en un paragraphe

Les pipelines en cascade ASR → LLM → TTS gardent l'intelligence du LLM, mais la
segmentation par VAD leur impose des **tours half-duplex** et un contrôle
fragile. Les modèles bout-en-bout sans VAD font du full-duplex, mais peinent à
garder l'intelligence conversationnelle. La proposition : **convertir les longs
tours classiques en micro-tours par blocs**, avec des **jetons de contrôle
spéciaux** qui pilotent le comportement du LLM sous contrainte de streaming.

C'est exactement ce que microturn reprend — le mécanisme, pas le code — et qu'il
tente d'obtenir **par prompting** là où eux l'obtiennent par fine-tuning.

---

## 3. Les sept jetons

Six jetons de contrôle, plus le marqueur de silence. Le papier les écrit en
chevrons simples ; **le code utilise des pipes** (`<|user is talking|>` etc.) —
la table exacte est dans `FORMAT-CHERCHEURS.md`, section « CONSTATÉ DANS LEUR
CODE ». Ci-dessous, la graphie du papier et le sens donné par les auteurs.

| jeton | sens chez eux |
|---|---|
| `<no voice>` | le tampon s'est vidé sans texte reconnu — **le silence est une donnée envoyée au modèle**, pas une absence d'appel |
| `<user is speaking>` | l'utilisateur parle, le système se tait |
| `<user finish speaking>` | il a fini, le système doit répondre |
| `<user is interrupting>` | interruption détectée, on arrête la génération |
| `<user backchannel>` | signal d'écoute de l'utilisateur, le système **continue** |
| `<user is thinking>` | silence **après réponse** — le système attend ⚠️ |
| `<system backchannel>` | le système émet un backchannel court |

### ⚠️ Le point à vérifier sur `<user is thinking>`

Relevé du 03/09 : leur `<user is thinking>` semble défini comme un **silence
après réponse**, et non comme la **pause intra-tour** que nous détectons.

Si c'est exact, **notre `REFLECHIT` ne recouvre pas le leur**, et toute
comparaison de scores qui les apparie en souffre. Ça contredit
`FORMAT-CHERCHEURS.md` § 2, qui pose sans réserve « `<user is thinking>` est
l'équivalent de notre REFLECHIT ». **Ne pas résoudre à la lecture de cette
fiche : trancher sur le PDF, puis corriger celle des deux qui a tort.**

Enjeu concret : `SPEC-PIVOT.md` § 3 fait de `thinking` (la pause intra-tour) la
distinction qu'un VAD ne sait pas faire, donc l'argument de vente du projet. Si
le papier ne parle pas de la même chose, cet argument est **plus original qu'on
ne le croyait**, pas moins.

---

## 4. Les réglages

| | eux | nous |
|---|---|---|
| **Micro-tour (Δt)** | **0,6 s** | **1,2 s** — facteur deux |
| micro-tour utilisateur | 1 à 7 tokens, **tirés au hasard** | le delta de l'ASR, longueur subie |
| micro-tour système | **fixé à 10 tokens** | une phrase entière |

Le texte utilisateur est agrégé périodiquement en micro-tour et envoyé au LLM.

⚠️ **Leur 0,6 s n'est pas leur optimum de justesse — c'est un compromis assumé
avec la latence.** Leur propre ablation (§ 4.4 p. 4) place l'optimum de justesse
à **1,2 s**, la valeur que nous avons prise. Ce n'est donc pas « eux 0,6, nous
1,2, facteur deux » : c'est **deux arbitrages opposés sur la même courbe**, la
leur pour la réactivité, la nôtre pour la justesse. Développé en § 5.3, et c'est
le point le plus important de cette fiche.

Les 10 tokens système ne sont pas un détail de tokenisation : c'est **la
condition du barge-in**, parce qu'ils ménagent un point de décision au milieu de
la réponse (cf. `IDEES.md` § 8).

### Le fine-tuning

Qwen2-7B-Instruct en **LoRA (r=16, α=32)**, 50 k dialogues UltraChat, 5 000
étapes, batch 32, lr 1e-5, longueur max 4096. **8×H100 pendant 5 heures.**

Détail qui compte : le LoRA n'est appliqué **que sur les micro-tours système**,
pour préserver les capacités conversationnelles du modèle de base.

**Notre équivalent sans entraînement, c'est la structure du prompt.** C'est ce
qui éclaire la quatrième section proposée au § 12 de `SPEC-PIVOT.md`
(instructions / exemples / historique / phrase en cours) : chez eux la
séparation entre ce qu'on apprend et ce qu'on observe est portée par le masque
d'entraînement ; chez nous elle ne peut être portée que par la mise en page du
prompt.

### Les données sont synthétiques

Six phénomènes simulés :

| phénomène | paramètre |
|---|---|
| pauses naturelles | p = 0,10 |
| interruptions utilisateur | p = 0,30 |
| backchannels utilisateur | 0,01 par micro-tour |
| backchannels système | post-traités par Qwen2-72B |
| réflexion utilisateur | 1 à 20 micro-tours silencieux |

---

## 5. Leurs résultats

### 5.1 Full-Duplex-Bench — Tableau 1 page 3, relevé à la source

Onze colonnes, dans l'ordre du tableau. **Les deux lignes DuplexCascade sont à
Δt = 0,6 s** — ça n'était écrit nulle part chez nous, et ça change tout (§ 5.3).
dGSLM est donné pour l'échelle, pas pour l'argument.

| colonne du Tableau 1 | DuplexCascade | DuplexCascade-β | dGSLM |
|---|---|---|---|
| Pause Handling — Synthetic TOR ↓ | **0,058** | 0,343 | 0,934 |
| Pause Handling — Candor TOR ↓ | 0,222 | 0,458 | 0,935 |
| Backchannel — TOR ↓ | 0,218 | 0,309 | 0,691 |
| Backchannel — ICC Freq ↑ | 0,009 | 0,034 | 0,015 |
| Backchannel — JSD ↓ | 0,949 | 0,811 | 0,934 |
| Smooth Turn Taking — Candor TOR ↑ | 0,832 | 0,899 | 0,975 |
| Smooth Turn Taking — **Latency** ↓ | **1,724 s** | 0,567 s | 0,352 s |
| User Interruption — **TOR** ↑ | **0,955** | 0,950 | 0,917 |
| User Interruption — Synthetic GPT-4o ↑ | 4,016 | 4,011 | 0,201 |
| User Interruption — **Latency** ↓ | **1,225 s** | 0,850 s | 2,531 s |
| **Averaged Turn-Taking Accuracy** | **0,858** | **0,748** | 0,466 |

### 5.2 Les deux pièges de nommage de ce tableau

Ils ont produit, à eux deux, les chiffres faux du dépôt. Ils sont écrits ici
pour que personne ne refasse l'aller-retour.

**Piège n° 1 — trois « environ 1,2 seconde » qui ne sont pas la même grandeur :**

| ce qu'on lit | ce que c'est |
|---|---|
| **1,724 s** | leur **latence de prise de tour** (Smooth Turn Taking Latency) |
| **1,225 s** | leur latence d'**interruption** (User Interruption Latency) |
| **1,2 s** | **notre pas d'horloge Δt** — pas une latence, ni la leur ni la nôtre |

Nos tableaux publics donnaient « 1,2 s » comme *leur* latence. C'était faux deux
fois : ce n'est pas leur chiffre, et ce n'est pas une latence.

**Piège n° 2 — 0,955 n'est pas un taux de fin de tour.** C'est le **User
Interruption TOR**, le taux de prise de tour **sur interruption**. Il était
affiché dans trois tableaux du dépôt en colonne « fins de tour », face à nos
13,8/17. Retiré, pas corrigé (§ 5.4).

### 5.3 🔴 Leur 0,858 est mesuré à Δt = 0,6 s — et 1,2 s est leur optimum

**§ 4.4 page 4, lu à la source.** Ils balaient Δt ∈ {0,3 · 0,6 · 0,9 · **1,2** ·
1,5 · 1,8 s} et écrivent, mot pour mot :

> *« Averaged Turn-Taking Accuracy improves as Δt increases up to 1.2 s, after
> which it degrades. »*

> *« under our simulation setting, Δt=1.2 s provides the strongest turn-taking
> performance, but at the cost of higher latency. We therefore choose Δt=0.6 s
> as a practical trade-off between turn-taking accuracy and latency. »*

Deux conséquences, et elles vont en sens inverse.

**La mauvaise — à réglage comparable, l'écart n'est pas de quatre points, il est
d'une douzaine.** Sur leur **Figure 3**, le pic à Δt = 1,2 s est **aux alentours
de 0,93**. Cette valeur est **lue sur un graphique, à ±0,005 près : ce n'est pas
une valeur de tableau et elle ne se cite pas comme telle.** Notre 0,816 tourne à
Δt = 1,2 s. « 0,816 contre 0,858 » oppose donc **deux réglages différents** ; la
soustraction reste publiable, mais **plus jamais sans cette phrase**.

**La bonne — notre Δt = 1,2 s est leur optimum de justesse.** Le choix de 1,2 s
avait été pris par transposition et n'a jamais été mesuré chez nous
(`IDEES.md` § 4) : il est validé par **leur propre ablation**. Et ce que nous
payons en latence — 3,55 s vécue — est exactement le prix qu'ils ont refusé de
payer. Ce n'est pas une excuse, c'est **l'arbitrage inverse du leur, pris pour
la raison inverse** : leur problème était la réactivité, le nôtre est la
justesse. À écrire dans l'article en face de la mauvaise nouvelle, pas ailleurs.

**Ça clôt l'alerte du 03/09 au matin sur `IDEES.md` § 4 et
`FORMAT-CHERCHEURS.md` § 5** : la lecture antérieure — « 0,858 à 0,6 s et 0,934
à 1,2 s, latence 1,72 s → ~2,85 s » — était **bonne**. Le 1,72 s est bien la
latence de prise de tour du Tableau 1 à Δt = 0,6 s ; le pic est bien celui de la
Figure 3. Seule retouche : écrire « ~0,93, lu sur la Figure 3 » plutôt que
« 0,934 », qui affiche une précision que le graphique ne donne pas.

⚠️ **Coïncidence piégeuse, à ne pas retomber dedans** : **0,934 est aussi une
valeur du Tableau 1**, deux fois, sur la ligne **dGSLM** (Pause Handling
Synthetic TOR, et Backchannel JSD). Qui cherche « 0,934 » dans le tableau le
trouve — au mauvais endroit, sur le mauvais système. Le 0,934 du compromis Δt
est dans la **Figure 3**, pas dans le Tableau 1.

### 5.4 Ce qui a été corrigé dans le dépôt le 03/09 au soir

| document | avant | après |
|---|---|---|
| `README.md` — tableau « Ce que ça vaut » | `0,955` en colonne « fins de tour » | **case retirée**, note sous le tableau |
| `README.md` — même tableau | latence `1,2 s` | **1,724 s**, nommée « latence de prise de tour » |
| `README.md` — intro | « L'écart mesuré est de quatre points » | l'écart brut **plus le Δt de chacun** |
| `ARTICLE-NOTES.md` — deux tableaux | idem `0,955` et `1,2 s` | idem |

**La case a été retirée plutôt que corrigée.** Nos 13,8/17 ne correspondent à
aucune colonne de Full-Duplex-Bench : y mettre *quelque chose*, même une
grandeur juste, rejouerait exactement le geste qui a produit le 0,955 — aligner
deux choses différentes parce qu'une colonne était vide. **Une note sous le
tableau vaut mieux qu'une case fausse.**

🔴 **Une quatrième occurrence reste à corriger, et elle n'est pas de mon
ressort** : `bench/JOURNAL.md`, test 5 (« la borne haute »), porte la même
colonne DuplexCascade avec **`fins de tour 0,955`** et **`latence 1,2 s`**. Le
fichier appartient à la session de tests. Les deux cases sont fausses pour les
raisons ci-dessus ; à signaler à qui tient ce journal.

### 5.5 VoiceBench (intelligence conversationnelle)

⚠️ **Non vérifié dans le PDF** — lecture HTML du 03/09 au matin.

| | DuplexCascade | baseline DSM-ASR + Qwen |
|---|---|---|
| score global | **65,41** | 69,66 |
| AlpacaEval | 4,40 | — |
| CommonEval | 3,64 | — |

C'est le prix qu'ils paient : le full-duplex leur **coûte** de l'intelligence
conversationnelle par rapport à la cascade classique.

## 6. 🔴 Le backchannel n'est pas gratuit — et il casse d'abord les pauses

**Confirmé au Tableau 1 p. 3 ; la réserve « à confirmer dans le PDF » est
levée.** DuplexCascade-β, la variante qui active les backchannels, rend
**0,748** de justesse moyenne contre **0,858** pour la configuration phare :
**−0,110**. Le chiffre était déjà juste dans `IDEES.md` § 6 depuis une lecture
antérieure.

Ce qui manquait, et c'est le point qui nous concerne : **où** β perd.

| | phare | β | |
|---|---|---|---|
| **Pause Handling — Synthetic TOR ↓** | **0,058** | **0,343** | **× 5,9 — c'est là que ça casse** |
| Pause Handling — Candor TOR ↓ | 0,222 | 0,458 | × 2,1 |
| Backchannel — TOR ↓ | 0,218 | 0,309 | dégradé |
| Smooth Turn Taking — Candor TOR ↑ | 0,832 | 0,899 | gagné |
| Smooth Turn Taking — Latency ↓ | 1,724 s | 0,567 s | gagné, ÷ 3 |
| User Interruption — Latency ↓ | 1,225 s | 0,850 s | gagné |
| **Averaged Turn-Taking Accuracy** | **0,858** | **0,748** | **−0,110** |

**Activer les backchannels dégrade d'abord la détection des pauses.** Pas la
latence, pas les interruptions — β y *gagne*, et nettement. Ce qu'il perd, c'est
précisément la dimension pour laquelle ce projet existe, et précisément celle où
**trois variantes de prompt ont déjà échoué chez nous**.

Leur configuration phare n'a pas de backchannel. Ce n'est pas un oubli : c'est
le même arbitrage, fait dans le même sens.

### Pour le § 12 de `SPEC-PIVOT.md` — avertissement daté, pas veto

`SPEC-PIVOT.md` § 12 (réflexions d'Alex du 03/09) envisage d'ajouter les
backchannels dans les deux sens, par le prompt. **Avertissement du 03/09 :
l'ajout se paie d'abord sur la détection des pauses, chez des gens qui ont
entraîné pour ça.**

À lire pour ce que c'est : **leur** mesure, sur **leur** banc, **avec**
fine-tuning, sur des données synthétiques. Rien ne prouve qu'un prompt suive la
même courbe — dans un sens comme dans l'autre. Ce que ça dit, c'est qu'il n'y a
aucune raison d'espérer que ce soit gratuit, et que **l'ajout doit être mesuré
isolément, avec et sans, sur les deux TOR séparés**, jamais livré avec autre
chose. Un agrégat suffirait à cacher un TOR de pauses multiplié par six : c'est
le résultat n° 9 d'`ARTICLE-NOTES.md`, appliqué d'avance.

## 7. Sur quoi ils se mesurent — et pourquoi ça nous concerne

**Ils se mesurent sur Full-Duplex-Bench et VoiceBench. Pas sur eot-bench.**

Deux conséquences, et elles sont différentes :

1. **Notre 0,816 face à leur 0,858 est déjà une comparaison bancale** — notre
   corpus, notre banc, notre mesure contre les leurs. Les trois documents qui
   affichent ce tableau (`README.md`, `ARTICLE-NOTES.md`) le disent déjà : la
   ligne DuplexCascade « donne l'ordre de grandeur, pas un classement ». Cette
   précaution n'est pas décorative, elle est structurelle. **Et depuis le § 5.3
   elle est double** : les deux chiffres ne sont même pas au même pas d'horloge
   — 0,858 est à Δt = 0,6 s, 0,816 à Δt = 1,2 s.

2. **L'étape 6 du `PLAN.md` — passer sur eot-bench en français — ne nous rendra
   pas comparables à *eux*.** Elle nous rendra comparables à **Smart Turn et
   LiveKit**. Ce sont deux comparaisons distinctes, et aucune ne remplace
   l'autre : eot-bench donne un classement face à l'état de l'art industriel,
   Full-Duplex-Bench resterait le seul terrain où l'écart avec le fine-tuning
   serait chiffré proprement. `PLAN.md` étape 6 mérite d'être lu avec ça en tête.

---

## 8. L'angle d'article que ce papier nous ouvre

**Leurs données sont générées.** Leur « ASR » ne se ravise jamais, ne coupe
jamais un mot en deux, ne se tait jamais de façon ambiguë. Ils ont prouvé que le
mécanisme marche **sur du texte parfait** — et c'est un résultat parfaitement
légitime, ce n'est pas un reproche.

Notre agrégateur, et plus généralement tout le travail sur le texte réel de
sherpa, mesure autre chose : **ce que coûte le texte imparfait**. C'est l'écart
entre une simulation et un système qui tourne pour de vrai.

**C'est une contribution propre, pas un rattrapage.** La nuance change le récit
de l'article : nous ne sommes pas la version dégradée d'un papier, nous
mesurons une dimension que le papier a mise hors de portée en générant ses
données. À rapprocher de deux points déjà écrits dans `ARTICLE-NOTES.md` : « la
révision n'existe pas dans leur monde » (l'agrégateur comme point de COMMIT au
sens des Incremental Units), et le motif de la partie I — la différence entre
« reproduire un papier » et « brancher la même idée sur un ASR réel ».

---

## 9. À faire — ce qui reste à vérifier

**Fait le 03/09 au soir, lecture directe du PDF :**

- [x] **le 0,748 de DuplexCascade-β** (§ 6) — confirmé, Tableau 1 p. 3. Et le
      détail qui manquait : il perd sur le Pause Handling (0,058 → 0,343)
- [x] **le 0,955 de nos trois tableaux** (§ 5.2) — retrouvé, et **mal
      attribué** : c'est le User Interruption TOR. Retiré du `README.md` et
      d'`ARTICLE-NOTES.md`. ⚠️ **Une quatrième occurrence subsiste dans
      `bench/JOURNAL.md` (test 5)**, avec la latence « 1,2 s » — fichier de la
      session de tests, non corrigé ici (§ 5.4)
- [x] **le compromis Δt** (§ 5.3) — confirmé, § 4.4 p. 4 : leur 0,858 est à
      Δt = 0,6 s, leur optimum de justesse est à 1,2 s, et 1,724 s ≠ 1,225 s ≠
      1,2 s

**Toujours ouvert :**

- [ ] **la définition exacte de `<user is thinking>`** (§ 3) — pause intra-tour
      ou silence après réponse ? Elle n'est ni dans le Tableau 1 ni au § 4.4,
      donc **non tranchée**. C'est la case qui engage le plus : `SPEC-PIVOT.md`
      § 3 en fait l'argument de vente du projet, et `FORMAT-CHERCHEURS.md` § 2
      affirme sans réserve l'équivalence avec notre `REFLECHIT`
- [ ] les réglages du § 4 (micro-tours, LoRA, données synthétiques) et le
      VoiceBench du § 5.5 — encore issus de la lecture HTML du matin

Les chiffres non cochés circulent **en interne**, avec leur réserve. Les cochés
sont publiables, avec leur source de page.
