# DuplexCascade — résumé du papier / paper summary

Fiche de lecture de [arXiv 2603.09180](https://arxiv.org/abs/2603.09180), Yang, Fujita & Sudo (SB Intuitions, université de Tokyo). Code sous MIT : [sbintuitions/DuplexCascade](https://github.com/sbintuitions/DuplexCascade). Démo : [sbintuitions.github.io/DuplexCascadeDemo](https://sbintuitions.github.io/DuplexCascadeDemo/).

**Français puis anglais dans chaque section.** Les chiffres sont relevés à la source, dans le PDF ; ce qui est lu sur un graphique est signalé comme tel.

Reading notes on the paper microturn reimplements. **French first, English second, in every section.** Figures are taken from the PDF itself; anything read off a plot is flagged.

---

## La thèse / The thesis

Les cascades ASR → LLM → TTS gardent l'intelligence du modèle de langage, mais leur découpage par détecteur de parole leur impose des tours half-duplex. Les modèles bout-en-bout font du full-duplex mais perdent en intelligence conversationnelle. La proposition : **convertir les longs tours en micro-tours par blocs**, pilotés par des **jetons de contrôle** que le modèle produit sous contrainte de streaming. C'est le mécanisme que microturn reprend, et qu'il tente d'obtenir par prompting là où eux l'obtiennent par fine-tuning.

Cascaded ASR → LLM → TTS keeps the language model's intelligence but its VAD segmentation forces half-duplex turns. End-to-end models are full-duplex but lose conversational ability. Their proposal: **turn long turns into block-wise micro-turns**, driven by **control tokens** the model emits under streaming constraints. That is the mechanism microturn borrows, and tries to obtain by prompting rather than fine-tuning.

## Les jetons / The tokens

Six jetons de contrôle plus le marqueur de silence. Le papier les écrit en chevrons simples, **leur code utilise des pipes** (`<|user is talking|>`). Le silence est envoyé au modèle, ce n'est pas une absence d'appel.

Six control tokens plus the silence marker. The paper writes plain angle brackets, **their code uses pipes**. Silence is sent to the model; it is not a skipped call.

| jeton / token | sens chez eux / their meaning |
|---|---|
| `<no voice>` | le tampon s'est vidé sans texte / buffer emptied with no recognised text |
| `<user is speaking>` | l'utilisateur parle, le système se tait / user speaking, system silent |
| `<user finish speaking>` | il a fini, le système répond / user done, system replies |
| `<user is interrupting>` | interruption, on arrête la génération / interruption, stop generating |
| `<user backchannel>` | signal d'écoute, le système continue / listening signal, system continues |
| `<user is thinking>` | silence après réponse, le système attend / post-reply silence, system waits |
| `<system backchannel>` | le système émet un backchannel court / system emits a short backchannel |

## Les réglages / The settings

| | eux / them | microturn |
|---|---|---|
| micro-tour Δt | **0,6 s** | **1,2 s** |
| micro-tour utilisateur | 1 à 7 tokens, tirés au hasard | le delta de l'ASR |
| micro-tour système | fixé à 10 tokens | une phrase entière |
| entraînement | LoRA r=16 α=32, 50 k dialogues UltraChat, 5 000 étapes, **8×H100 pendant 5 heures** | aucun |

Deux détails qui comptent. Le LoRA n'est appliqué **que sur les micro-tours système**, pour préserver les capacités conversationnelles du modèle de base. Et les 10 tokens système ne sont pas un détail de tokenisation : ils ménagent un point de décision au milieu de la réponse, ce qui **conditionne le barge-in**.

Two details that matter. The LoRA is applied **to system micro-turns only**, to preserve the base model's conversational ability. And the 10-token system micro-turn is not a tokenisation detail: it creates a decision point mid-reply, which is **what makes barge-in possible**.

## Leurs résultats / Their results

Full-Duplex-Bench, Tableau 1 page 3. **Les deux lignes DuplexCascade sont à Δt = 0,6 s.** dGSLM est donné pour l'échelle.

Full-Duplex-Bench, Table 1 page 3. **Both DuplexCascade rows are at Δt = 0.6 s.** dGSLM is there for scale.

| colonne / column | DuplexCascade | DuplexCascade-β | dGSLM |
|---|---|---|---|
| Pause Handling — Synthetic TOR ↓ | **0,058** | 0,343 | 0,934 |
| Pause Handling — Candor TOR ↓ | 0,222 | 0,458 | 0,935 |
| Backchannel — TOR ↓ | 0,218 | 0,309 | 0,691 |
| Backchannel — ICC Freq ↑ | 0,009 | 0,034 | 0,015 |
| Backchannel — JSD ↓ | 0,949 | 0,811 | 0,934 |
| Smooth Turn Taking — Candor TOR ↑ | 0,832 | 0,899 | 0,975 |
| Smooth Turn Taking — Latency ↓ | **1,724 s** | 0,567 s | 0,352 s |
| User Interruption — TOR ↑ | **0,955** | 0,950 | 0,917 |
| User Interruption — Synthetic GPT-4o ↑ | 4,016 | 4,011 | 0,201 |
| User Interruption — Latency ↓ | **1,225 s** | 0,850 s | 2,531 s |
| **Averaged Turn-Taking Accuracy** | **0,858** | 0,748 | 0,466 |

## Le piège du pas d'horloge / The clock-step trap

**Leur 0,6 s n'est pas leur optimum de justesse, c'est un compromis avec la latence.** Leur ablation du § 4.4 balaie Δt de 0,3 à 1,8 s : la justesse monte jusqu'à **1,2 s** puis se dégrade, et à 1,2 s leur courbe culmine autour de **0,93** — valeur lue sur un graphique, à ±0,005 près. Ce n'est donc pas « eux 0,6, nous 1,2, facteur deux » : ce sont **deux arbitrages opposés sur la même courbe**, la leur pour la réactivité, la nôtre pour la justesse. Conséquence directe : comparer notre 0,816 à leur 0,858 sous-estime l'écart, qui est plutôt d'une douzaine de points à réglage égal.

**Their 0.6 s is not their accuracy optimum, it is a latency trade-off.** Their § 4.4 ablation sweeps Δt from 0.3 to 1.8 s: accuracy rises to **1.2 s** then degrades, and at 1.2 s their curve peaks around **0.93** — read off a plot, ±0.005. So this is not "them 0.6, us 1.2, factor of two": these are **two opposite choices on the same curve**. Comparing our 0.816 to their 0.858 therefore understates the gap, which is about a dozen points at matched settings.

## Deux pièges de nommage / Two naming traps

Ils ont produit, à eux deux, des chiffres faux dans ce dépôt. Ils sont écrits ici pour que personne ne refasse l'aller-retour.

Between them, these two produced wrong figures in this repository. They are written down so nobody makes the round trip again.

**Trois « environ 1,2 seconde » qui ne sont pas la même grandeur.** 1,724 s est leur latence de **prise de tour** ; 1,225 s leur latence d'**interruption** ; 1,2 s est **notre pas d'horloge**, qui n'est pas une latence du tout.

**Three "about 1.2 seconds" that are different quantities.** 1.724 s is their **turn-taking** latency; 1.225 s their **interruption** latency; 1.2 s is **our clock step**, not a latency at all.

**0,955 n'est pas un taux de fin de tour**, c'est leur taux de prise de parole **sur interruption**. Il a été affiché un temps en face de nos fins de tour, ce qui ne voulait rien dire.

**0.955 is not a turn-end rate**, it is their take-over rate **on interruption**. It was shown against our turn-end counts for a while, which meant nothing.

## Ce que ça change pour microturn / What it means here

Ils n'ont **pas de prompt système** : le comportement vient entièrement du fine-tuning. Il n'y a donc rien à copier de ce côté, et tout notre prompt est une invention rendue nécessaire par le fait qu'on n'entraîne pas. Parler de « conformité au papier » à propos du prompt n'a pas de sens ; ça n'en a que pour le vocabulaire des jetons et la structure des messages.

They have **no system prompt**: the behaviour comes entirely from fine-tuning. There is nothing to copy there, and our whole prompt is an invention forced by not training. "Faithfulness to the paper" is meaningless about the prompt; it only means something about the token vocabulary and the message structure.
