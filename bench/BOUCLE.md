# La boucle d'amélioration, en autonomie

Écrit le 29/08/2026 après une QC demandée par Alex : « l'objectif est que tu
sois autonome et que tu puisses t'améliorer pendant une heure ou deux pendant
que je fais autre chose ». Ce fichier est la procédure exacte. Il complète le
`PROTOCOLE.md`, qui dit *comment* corriger ; celui-ci dit *quoi* faire, *dans
quel ordre*, et *quand s'arrêter*.

## Avant de commencer : mesurer le bruit

```bash
.venv/bin/python bench/mesurer.py --taches pause --echantillon 10 --passes 3 \
    --note "bruit de mesure"
```

Le chiffre qui compte est l'**écart-type**. Il est le seuil de tout le reste :

> Aucun écart inférieur à l'écart-type ne compte comme un résultat.

Le refaire aussi avec `--modele simule` : la différence entre les deux
écarts-types sépare le bruit venant du modèle distant de celui venant de la
mécanique (cadencement temps réel, whisper). Si le second est déjà grand, c'est
lui qu'il faut réduire avant toute autre chose.

## Une itération

1. **Choisir UNE hypothèse** dans la file ci-dessous. Une seule.
2. **La formuler avant de coder** : « je crois que X est mauvais parce que Y,
   et le changer devrait déplacer la métrique Z dans le sens S. » Une hypothèse
   qui ne prédit pas de sens n'est pas testable — la sauter.
3. **Modifier**, une cause à la fois.
4. `bash tests/fumee.sh` — **impérativement**. Une constante supprimée en
   réécrivant un bloc ne casse pas la fonction, elle casse le démarrage.
5. **Mesurer** sur le même sous-ensemble, avec le même `--echantillon`.
6. **Comparer à l'écart-type.** En dessous : le résultat est nul, pas positif.
7. **Consigner** une ligne dans `bench/JOURNAL.md`, verdict compris — surtout
   si c'est un échec.
8. **Commiter dans tous les cas**, réussite comme échec. Sans commit par
   itération, impossible de revenir en arrière proprement au bout de dix tours.
   Un échec se commite avec son verdict dans le message, puis se `git revert`.

## La file, dans l'ordre

L'ordre va du mieux fondé au plus spéculatif. Ne pas picorer.

1. **`MICRO_TOURS = 24`** — mesuré comme trop court : douze tours, soit quatorze
   secondes d'horizon, et une question de quarante secondes en sortait. Tester
   36 et 48. Coût attendu : plus de tokens par appel, à surveiller.
2. **La fenêtre `6.0` s de « je viens de répondre »** (`pipeline.py`, en dur,
   même pas dans `meta.json`). C'est la deuxième constante de tour de parole du
   système et elle produit à elle seule la moitié des `reflechit`.
3. **`TICK_S = 1.2`** — la seule valeur héritée d'une mesure (l'optimum de
   DuplexCascade), mais mesurée sur LEUR système, pas le nôtre. Tester 0,8 et
   1,6.
4. **Le chien de garde `4 * TICK_S`** — arbitraire.
5. **`PLAFOND_S = 20`** (fenêtre whisper) — arbitraire, et il gouverne le coût
   de chaque passe.
6. **Le seuil de `_est_echo`** (`len(inconnus) <= len(mots) // 2`) — écrit à la
   va-vite, « moitié » sans raison. Ne se teste qu'avec la porte active.
7. **Les huit constantes de la porte** — à ne toucher qu'après, et seulement si
   les corpus avec chevauchement (`user_interruption`) montrent un problème.
8. **YAMNet** en source de vérité pour « est-ce que quelqu'un parle », en
   remplacement du seuil RMS. C'est le plus gros chantier, donc le dernier.

## Quand s'arrêter

- **Dix itérations**, comme convenu.
- **Ou trois itérations d'affilée sans dépasser le bruit** — continuer serait du
  bricolage, pas de la mesure.
- **Ou un blocage qui demande un arbitrage d'Alex.** Le principal est connu :
  `pause_handling` pénalise la prise de parole, `smooth_turn_taking` la
  récompense. Optimiser l'un dégrade l'autre. Ne pas trancher seul — surveiller
  les deux et lui montrer l'arbitrage.

## Le rapport final

Court. Chiffres avant/après avec leur écart-type, ce qui a marché, ce qui n'a
pas marché, ce qui reste ouvert. Les questions en **choix multiples**.
