# Journal des itérations

Une ligne par tour de la boucle du `PROTOCOLE.md`. But : pouvoir dire, à la fin,
ce qui a marché et ce qui n'a pas marché — et revenir en arrière sans deviner.

Règle : **aucun écart inférieur à l'écart-type de la mesure ne compte comme un
résultat.** Le décideur est un modèle distant, la lecture est en temps réel, la
latence réseau varie du simple au quadruple entre deux appels. La première
mesure à faire est donc celle du bruit, pas celle d'une amélioration.

| # | commit | hypothèse | ce qui change | chiffres | verdict |
|---|--------|-----------|---------------|----------|---------|
| 0 | b53f9ce | ligne de base, rien changé | — | session 032332 : **TOR fins 3/9 = 0,333**, latence méd 7,18 s, 0 coupure, pauses non détectables | référence. DuplexCascade : TOR 0,955 et latence 1,225 s |

## Ce que dit la ligne de base

Il répond à **une question sur trois**, et met **sept secondes**. L'écart avec
DuplexCascade (0,955 et 1,2 s) n'est pas un écart de réglage : c'est un facteur
trois sur la justesse et six sur la latence, avec la même architecture en
cascade. La différence tient à leur fine-tuning et, on en fait l'hypothèse, à
ce que leur modèle voit de la conversation.

Limite de la mesure, à corriger si elle gêne : la transcription de référence
(`small`) découpe en segments de dix à quinze secondes contigus, donc aucun
silence de plus d'une seconde n'apparaît ENTRE segments et aucune pause n'est
détectée. La justesse agrégée est donc incalculable sur une session seule — il
faut plusieurs sessions, ou une détection de pauses indépendante du découpage.

La latence de 7,18 s est mesurée depuis la fin du segment de référence. Ces
segments étant longs, la vraie latence est plus basse — le chiffre est un
majorant, utile pour comparer nos versions entre elles, pas à publier tel quel.
| 1 | — | l'horizon est trop court (MICRO_TOURS=24, 14 s) | MICRO_TOURS 48 + rappel du tour en cours | **3/9**, inchangé | ÉCHEC. La trace montre que la question ÉTAIT dans le contexte : l'hypothèse était fausse. Mais le rappel, entre parenthèses comme (silence), était lu comme un marqueur d'absence de parole → REFLECHIT |
| 2 | — | le rappel doit être hors parenthèses | rappel après le delta, sans parenthèses, exclu sur les silences | **2/9** | RÉGRESSION. Exclure le rappel quand le delta est un silence le supprime précisément quand il sert. Et 110 REFLECHIT sur 123 décisions, dont 89 interdits par le prompt |
| 3 | 4c3f6a1 | REFLECHIT est trop attractif depuis ma modif A11 | définition resserrée à [je viens de répondre] seul, exemple `[je parle] (silence)` retiré, rappel rétabli sur les silences | **5/9 = 0,556**, parle 67 / reflechit 46 / parler 8 | **GAIN +22 pts.** Le mur de REFLECHIT s'effondre (110 → 46), les réponses passent de 3 à 8 |

## Ce que les trois premières itérations apprennent

**Ma propre correction A11 coûtait deux questions sur neuf.** Ajoutée cette nuit
pour boucher un trou réel — deux combinaisons état × contenu que le prompt ne
décrivait pas — elle élargissait REFLECHIT à `[je parle]`. Le jeton est devenu
dominant et le modèle l'a appliqué partout, y compris là où le prompt
l'interdit. Elle avait été commitée sur la foi du raisonnement, sans mesure.

**Une correction peut marcher et être annulée par sa forme.** Le rappel du tour
en cours fonctionnait dès l'itération 1 : la trace le montre dans le contexte.
Mais il était entre parenthèses, comme les trois marqueurs qui signifient
« rien entendu ». Le modèle a appris la forme, pas le sens. Deux sémantiques
opposées ne doivent jamais partager une apparence.

**Vérifier l'effet sur le contexte, pas seulement le score.** Sans lire la
trace, j'aurais conclu que l'hypothèse du rappel était morte et je l'aurais
retirée — alors qu'elle contribue au 5/9 actuel.
| 4 | — | REFLECHIT est un jeton que NOUS avons inventé ; DuplexCascade n'en a que trois | REFLECHIT retiré du prompt (clé gardée comme filet), silence après réponse → PARLE_ENCORE | **6/9 = 0,667**, parle 96 / parler 9 / coupe 16 / reflechit 0 | **GAIN +11 pts.** Mais `coupe` passe de 1 à 16 décisions : le modèle reporte sur ME_COUPE. Une seule coupure effective, les autres bloquées par les gardes anti-écho — à surveiller |
| 5 | — | la notation est ambiguë (crochets non définis, parenthèses polysémiques) | notation à deux champs `moi:` / `entendu:` | **6/9**, inchangé | neutre. Gardée : le code ne cherche plus de mots dans des phrases |
| 6 | — | le trou `je parle + rien` fait choisir ME_COUPE faute de mieux | exemple `je parle + rien → PARLE_ENCORE` | **2/9** | RÉGRESSION. Supprime bien les 15 ME_COUPE, mais PARLE_ENCORE passe à 116/120 et les réponses tombent de 8 à 4 |
| 7 | — | « moi » dans un message `user` désigne l'humain, pas le robot | `moi:` → `robot:` + identification explicite | **2/9** | RÉGRESSION. Un seul mot changé, quatre questions perdues. Hypothèse plausible, mesure implacable |
| 8 | — | le prompt est trop compliqué (Alex) | 167 → 71 mots : retrait de « dans le doute », de la règle sur la transcription fausse, des redites | **7/9 = 0,778**, parler 12 | **MEILLEUR SCORE.** Rapproche du papier : eux n'ont aucune règle en prose |

## Le motif, après huit itérations

Deux gains sur retrait, deux régressions sur ajout, et le plus gros gain en
supprimant la moitié du prompt. Sur un modèle générique en prompting, **chaque
règle ajoutée pour un jeton rend ce jeton dominant** et écrase les autres :
REFLECHIT à 110 décisions sur 123, puis PARLE_ENCORE à 116 sur 120.

Les hypothèses formulées avec le plus d'assurance — l'horizon de contexte, la
forme du rappel, la notation, l'ambiguïté du pronom — n'ont rien donné ou ont
nui. Celles qui ont marché venaient toutes d'Alex et disaient la même chose :
enlève.

Sensibilité mesurée à la formulation : 6/9 avec « moi », 2/9 avec « robot ».
Un mot. Ce système est bien plus sensible aux mots qu'à la structure.
