# Journal des tests

Vidé le 29/08/2026 à la demande d'Alex : on reprend toute la file de
`bench/CANDIDATS.md` depuis le début, avec une mesure sur deux sessions au lieu
d'une. Les 17 itérations précédentes sont résumées dans `CANDIDATS.md`
(« Déjà testé »), et l'ancien journal reste dans l'historique git.

**Une ligne par test, écrite juste après la mesure.** Y compris les échecs, y
compris les indécidables — c'est ce qui évite de refaire deux fois le même test
en croyant l'avoir trouvé.

## Les règles de lecture

- **Aucun écart inférieur au bruit ne compte comme un résultat.** Bruit mesuré
  après le passage au rejeu déterministe : **±0,017** (0,681 puis 0,698 sur la
  même base). Avant, il était de ±0,071 sur une session. Un gain de 0,03 est
  désormais interprétable ; en dessous, non.
- **Base de référence : 0,690** (moyenne des deux passes de contrôle).
- Un verdict n'est jamais « neutre » quand l'écart est sous le bruit : c'est
  **indécidable**. La nuance compte — un indécidable peut cacher un vrai gain.
- La référence est DuplexCascade : justesse moyenne **0,858**, latence 1,2 s.

## Résultats

| # | commit | ce qui change | justesse | fins | pauses | latence | verdict |
|---|--------|---------------|----------|------|--------|---------|---------|
| 1 | 5e05e6e | **base**, mesurée sur DEUX sessions au lieu d'une | 0,634 | 11/17 | 11/29 | 7,32 / 5,03 s | mesure en temps réel, non reproductible |
| 2 | 5713507 | rejeu **déterministe** : horloge virtuelle, appel bloquant | 0,681 | 12/17 | 10/29 | 5,8 / 4,0 s | nouvelle base |
| 2' | 5713507 | *(contrôle : la même mesure, refaite)* | 0,698 | 12/17 | 9/29 | 5,8 / 4,6 s | **bruit résiduel 0,017** — quatre fois moins qu'avant |
| 3 | 4f0e1e6 | `[=]` horizon 10 micro-tours système (`MICRO_TOURS` 48 → 20) | 0,698 | 12/17 | 9/29 | 5,8 / 4,6 s | **gardé.** Score inchangé, contexte plus que divisé par deux |
| 4 | — | `[=]` `TICK_S` 1,2 → 0,6 s (leur valeur en pratique) | 0,698 | 12/17 | 9/29 | 6,0 / 4,6 s | **rejeté.** Deux fois plus d'appels, latence inchangée |

### Ce que la deuxième session change

La base « officielle » passe de 0,762 à **0,634**. Le code n'a pas bougé : c'est
la mesure qui devient plus dure, et plus honnête.

- `032332` seule : 9 fins de tour, **7 pauses**.
- `073852` seule : 8 fins de tour, **22 pauses**, et 3 coupures de parole.

La nouvelle session triple le nombre de pauses observées et fait apparaître la
dimension « coupures », restée à zéro jusqu'ici faute d'occasion. Sur les pauses,
on rate 11 fois sur 29 — c'est notre pire dimension, et elle était quasi
invisible avec une seule session.

### Une mesure gratuite du bruit

`032332` a été rejouée deux fois de suite **sur le même code** (`f2f3427` puis
`5e05e6e`, aucun changement fonctionnel entre les deux) :

    passe 1 : justesse 0,762   (pauses 1/7)
    passe 2 : justesse 0,691   (pauses 2/7)

**0,071 d'écart, sans qu'une seule ligne ait changé.** Une pause qui bascule, et
le score bouge de 7 points. C'est la confirmation directe du problème : tant que
la granularité de la mesure vaut plus que les gains cherchés, un verdict isolé ne
vaut rien. D'où le test n° 2 (trois passes) avant tout le reste.


### Le rejeu déterministe, et le piège qu'il cachait

Le rejeu tournait en temps réel : un appel réseau lent faisait sauter des ticks,
et deux passes du même code donnaient 118 puis 123 décisions. Corrigé par une
horloge virtuelle — l'appel bloque, aucun tick ne saute.

Vérification sur cinq passes : **126 décisions à chaque fois**, et une à deux
décisions divergentes sur 126, toujours aux mêmes indices. Ce qui reste est le
non-déterminisme propre du modèle à température 0. En prime, le rejeu passe de
149 s à 63 s : toute la file de tests devient deux fois moins chère.

**Première version fausse, et de peu :** j'avais patché l'horloge du seul module
`pipeline`. Résultat mesuré 0,551, et j'ai failli conclure que le déterminisme
dégradait le système. Deux modules manquaient :

- `tts` comptait la durée de parole simulée en temps réel, pendant que la
  conversation avançait en temps virtuel 2,4× plus vite. Le robot « parlait »
  2,4× trop longtemps : 8 coupures au lieu de 3 ;
- `journal` horodatait la trace en temps réel — les instants allaient de 0 à
  63 s pour 149 s d'audio, et la métrique les comparait à une référence en
  secondes de conversation. Tout était décalé du même facteur.

`llm` garde volontairement la vraie horloge : la latence réseau est réelle.

**Leçon :** un temps simulé doit l'être partout où il est lu, sinon deux
horloges coexistent et le système mesuré n'est plus celui qui tourne.


### Test 3 — l'horizon de 48 micro-tours ne servait à rien

Ramené à 20 (soit dix micro-tours système, la longueur fixe de leurs données
d'entraînement), le score est identique au chiffre près : 0,698, mêmes 12/17 en
fins de tour, mêmes 9/29 en pauses.

Le contexte, lui, tombe de moitié : 655 tokens d'entrée en moyenne, 799 au
maximum, contre plus du double avant. À score égal on paie deux fois moins, on
répond plus vite, et on se rapproche de leur design. C'est le premier test de la
file et il est gratuit.

L'itération 1 de l'ancienne série avait AUGMENTÉ l'horizon de 24 à 48 en pariant
qu'il était trop court, sans gain. Personne n'avait essayé dans l'autre sens.


### Test 4 — leur horloge n'a pas de sens sans leur latence

`TICK_S` à 0,6 s : score rigoureusement identique (0,698, mêmes 12/17, mêmes
9/29), pour deux fois plus d'appels et un rejeu deux fois plus long.

Et surtout : **la latence ne bouge pas** — 6,0 s contre 5,8 s. C'est le résultat
intéressant. Consulter le modèle deux fois plus souvent ne fait pas répondre
plus vite, donc le tick n'est pas le goulot. Chez eux Δt = 0,6 s a un sens parce
que leur latence totale est sous la seconde ; chez nous elle est à six, et
l'horloge n'y est pour rien.

Ce test répond en creux à une question qu'on n'avait pas posée : **où passent
les six secondes ?** L'appel au modèle en prend 0,5. Le reste est ailleurs.
