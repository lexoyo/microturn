# PAPIER.md — fiche de lecture de DuplexCascade

Fiche de consultation rapide sur le papier fondateur du projet. Elle sert à
retrouver en dix secondes un chiffre, un jeton ou un réglage **de chez eux**,
sans rouvrir arXiv.

**Aucun chiffre de cette fiche n'est une mesure de microturn.** Tout ce qui suit
est *leur* résultat, sur *leur* banc. Nos chiffres à nous vivent dans
`RESULTATS.md`, `RESULTATS-PI.md` et `bench/JOURNAL.md`, et ne se comparent pas
ligne à ligne à ceux-ci (cf. § 7).

Deux fiches voisines, à ne pas confondre :
- **celle-ci** — ce que dit le papier : thèse, jetons, réglages, résultats ;
- **`FORMAT-CHERCHEURS.md`** — le *format* exact, papier **et** code lu dans
  `server.py` le 29/08 (chaînes littérales, structure ChatML, absence de prompt
  système). C'est là qu'il faut aller pour écrire un prompt, pas ici.

---

## 0. Réserve de méthode — à lire avant de citer quoi que ce soit

Les chiffres de la § 5 proviennent d'une **lecture automatique de la page HTML
du papier le 03/09/2026**, pas d'une lecture ligne à ligne du PDF. Ils sont
suffisants pour orienter une discussion ; ils **ne sont pas publiables en
l'état** et ne doivent pas, seuls, trancher une décision de conception.

Trois d'entre eux sont marqués « à confirmer dans le PDF » — dont le 0,748 de la
§ 6, qui est contre-intuitif et qui engage un arbitrage en cours.

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

**Full-Duplex-Bench** :

| métrique | valeur |
|---|---|
| justesse moyenne de turn-taking | **0,858** — meilleur système open source de leur tableau |
| Pause Handling TOR (bas = mieux) | 0,058 |
| Backchannel ICC | 0,949 |
| latence de turn-taking | 1,225 s |

**VoiceBench** (intelligence conversationnelle) :

| | DuplexCascade | baseline DSM-ASR + Qwen |
|---|---|---|
| score global | **65,41** | 69,66 |
| AlpacaEval | 4,40 | — |
| CommonEval | 3,64 | — |

Le second tableau est le prix qu'ils paient : le full-duplex leur **coûte** de
l'intelligence conversationnelle par rapport à la cascade classique.

### ⚠️ Deux incohérences avec nos notes existantes, à arbitrer sur le PDF

**a) Le 0,955 des tableaux de comparaison.** `README.md`, `ARTICLE-NOTES.md`
(deux endroits) portent une colonne « fins de tour = 0,955 » pour DuplexCascade.
Ce nombre **n'est pas ressorti de la lecture du 03/09**. Il vient probablement
d'un TOR de turn-taking de Full-Duplex-Bench, mais tant qu'il n'est pas retrouvé
dans le PDF, il est **non sourcé dans trois documents publics du dépôt**.

**b) Le compromis Δt.** `IDEES.md` § 4 et `FORMAT-CHERCHEURS.md` § 5 affirment
que le papier donne « 0,858 à 0,6 s et **0,934 à 1,2 s**, la latence montant de
1,72 s à ~2,85 s ». La lecture du 03/09 donne 0,858 **avec** une latence de
1,225 s, et n'a pas retrouvé le 0,934. Les deux lectures ne peuvent pas être
vraies ensemble : ou bien 1,72 s et 1,225 s ne désignent pas la même grandeur
(auquel cas il faut nommer laquelle est laquelle — règle 4), ou bien l'une des
deux est périmée.

C'est loin d'être théorique : **notre choix de 1,2 s repose entièrement sur le
0,934**, et il est déjà signalé dans `IDEES.md` comme « retenu par
transposition, jamais mesuré chez nous ».

---

## 6. 🔴 Le backchannel n'est pas gratuit

**La variante DuplexCascade-β, celle qui active les backchannels, tombe à 0,748
de justesse de turn-taking, contre 0,858 pour la configuration phare.**

Autrement dit : **chez des gens qui ont fine-tuné pour ça, activer les
backchannels coûte environ 0,11 de justesse.** Leur configuration phare n'en a
pas — ce n'est pas un oubli, c'est un arbitrage.

⚠️ **Statut : à confirmer dans le PDF avant publication ou décision.** C'est le
chiffre le plus contre-intuitif de la fiche et celui qui engage le plus.

**Corroboration partielle, et elle est encourageante.** `IDEES.md` § 6 portait
déjà, depuis une lecture antérieure, « activer le backchannel fait tripler le
taux de prise de parole intempestive sur les pauses (0,058 → 0,343) et coûte
**11 points d'exactitude** ». 0,858 − 0,748 = 0,110 : **deux lectures
indépendantes tombent sur le même écart.** Ça ne dispense pas de la
vérification, mais ça déplace le doute du « chiffre aberrant » vers le simple
contrôle de forme.

### Ce que ça veut dire pour la décision en cours

`SPEC-PIVOT.md` § 12 (réflexions d'Alex du 03/09) envisage d'ajouter **les
backchannels dans les deux sens, par le prompt**. Cette fiche dit : ce n'est pas
gratuit, et le coût est connu chez ceux qui ont entraîné pour ça. Il n'y a aucune
raison de penser qu'un prompt ferait mieux qu'un fine-tuning sur ce point précis.

Ce n'est pas un veto — c'est un chiffre à avoir en tête avant de s'engager, et
une raison de mesurer l'ajout **isolément**, avec et sans, plutôt que de le
livrer avec le reste.

---

## 7. Sur quoi ils se mesurent — et pourquoi ça nous concerne

**Ils se mesurent sur Full-Duplex-Bench et VoiceBench. Pas sur eot-bench.**

Deux conséquences, et elles sont différentes :

1. **Notre 0,816 face à leur 0,858 est déjà une comparaison bancale** — notre
   corpus, notre banc, notre mesure contre les leurs. Les trois documents qui
   affichent ce tableau (`README.md`, `ARTICLE-NOTES.md`) le disent déjà : la
   ligne DuplexCascade « donne l'ordre de grandeur, pas un classement ». Cette
   précaution n'est pas décorative, elle est structurelle.

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

## 9. À faire — la vérification PDF

Une seule séance de lecture du PDF réglerait tout ce qui est marqué ⚠️ :

- [ ] le 0,748 de DuplexCascade-β (§ 6) — **le plus urgent, il bloque une décision**
- [ ] la définition exacte de `<user is thinking>` (§ 3) — pause intra-tour ou silence post-réponse ?
- [ ] le 0,955 affiché dans nos trois tableaux (§ 5a) — le retrouver, ou le retirer
- [ ] le compromis Δt : 0,934 à 1,2 s, et la latence 1,72 s vs 1,225 s (§ 5b)

Tant que ces cases ne sont pas cochées, les chiffres de cette fiche circulent
**en interne**, avec leur réserve.
