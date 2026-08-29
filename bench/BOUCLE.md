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

## La QC, avant le plan et avant la méthode

Posé par Alex le 29/08/2026, après que deux QC successives aient chacune trouvé
un défaut bloquant que le travail lui-même n'aurait pas révélé :

- la première a trouvé que `mesurer.py` ne refaisait pas les rendus à la
  première passe d'une nouvelle itération : j'aurais évalué l'ancien code dix
  fois de suite en croyant mesurer le nouveau ;
- la seconde a trouvé que mon plan d'optimisation vérifiait le parallélisme en
  comparant des scores dont le bruit (±0,116) rendait toute comparaison
  impossible — et surtout que j'allais optimiser la vitesse d'une mesure sans
  avoir vérifié qu'elle mesurait quelque chose.

**Règle : avant d'exécuter un plan, le passer en revue comme s'il était d'un
autre.** Deux questions, toujours les mêmes :

1. **La méthode** — si ce que je m'apprête à mesurer était entièrement faux,
   est-ce que je m'en apercevrais ? Qu'est-ce qui, dans mon dispositif, pourrait
   produire un chiffre plausible mais vide de sens ?
2. **Le plan** — chaque étape a-t-elle un critère de réussite que le bruit de
   mesure permet réellement de trancher ? Une vérification incapable d'échouer
   n'est pas une vérification.

Une QC qui ne trouve rien est suspecte : les deux premières ont trouvé quelque
chose à chaque fois.

## Un seul changement par itération

Posé par Alex le 29/08/2026 : « en mode itératif, c'est un test par test ».
Enfreint deux fois dans la même session, et les deux fois l'information a été
perdue :

- itération 1 : `MICRO_TOURS` **et** le rappel du tour changés ensemble. Score
  inchangé — j'ai failli conclure que les deux étaient inutiles. Seule la
  lecture de la trace a montré que le rappel marchait et qu'un détail de forme
  l'annulait.
- itération 7 : un exemple retiré **et** les champs renommés. 2/9, et on ne
  saura jamais lequel des deux a coûté quatre questions.

La tentation est toujours la même : « ces deux changements traitent la même
cause, autant les faire ensemble ». C'est faux. Deux changements qui traitent
la même cause peuvent avoir des effets opposés qui s'annulent — et on conclut
alors que la cause n'était pas la bonne.

Exception admise : revenir en arrière. Annuler une régression n'est pas un
changement à mesurer, c'est un retour à un état déjà mesuré.

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

Révisée le 29/08/2026. La première version enchaînait le réglage des dix-neuf
constantes ; Alex a demandé si dix itérations avaient encore du sens ainsi. Non :
elles n'auraient couvert que du réglage fin, YAMNet n'aurait jamais été atteint,
et surtout elles auraient poli des détails pendant que le système ne répond pas
aux questions qu'on lui pose. Trois blocs, donc.

### Bloc A — la ligne de base (2 à 3 itérations)

Rien à modifier. Établir les chiffres sur les quatre tâches, avec leur
écart-type. C'est ce qui manque totalement : sans point de départ, aucune
itération suivante ne veut rien dire.

Prédiction posée AVANT la mesure, pour ne pas la réécrire après : pause
handling bon (le système parle peu), turn-taking mauvais (il n'a pas répondu à
trois questions consécutives bien transcrites ce soir). Si la mesure contredit
ça, c'est la mesure qu'il faut d'abord comprendre, pas le système.

### Bloc B — pourquoi il se tait devant une question (3 à 4 itérations)

C'est le défaut principal, et `smooth_turn_taking` en est exactement la mesure.
Hypothèses, dans l'ordre :

1. **L'horizon est trop court.** `MICRO_TOURS = 24`, soit douze tours, soit
   quatorze secondes — mesuré, une question de quarante secondes en sortait.
   Tester 36 et 48. Surveiller le coût en tokens.
2. **Le modèle ne voit jamais la phrase entière**, seulement des deltas de
   quelques mots. Lui transmettre aussi le tour en cours. Coûte des tokens et
   s'écarte de DuplexCascade — eux ont un modèle entraîné à recomposer.
3. **La règle « dans le doute, PARLE_ENCORE »** produit un mutisme parfait quand
   l'ASR ramène de la bouillie. À reformuler — mais sans ajouter d'heuristique
   sur un signal faux, l'erreur déjà commise et retirée ce soir.

### Bloc C — YAMNet (3 itérations)

Remplacer le seuil RMS de la porte par une vraie classification (parole,
musique, bruit, silence). C'est le remplacement le mieux fondé : il retire d'un
coup `FACTEUR_BRUIT`, `PLANCHER_BRUIT` et la déduction bancale derrière
`bruit_sans_texte`. Mesuré à 157,8 ms en résident, soit 13 % d'un cœur sur un
tick de 1,2 s.

Réserve connue : YAMNet ne distingue pas la voix d'Alex de celle du robot. La
porte reste nécessaire pour l'écho — ce sont deux problèmes, pas un.

### Après, seulement après

Le réglage fin des constantes (la fenêtre `6.0` s, `TICK_S`, le chien de garde,
`PLAFOND_S`, le seuil de `_est_echo`, les huit valeurs de la porte). On saura
alors ce qu'on règle.

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
