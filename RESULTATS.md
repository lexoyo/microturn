# Mesures

Tout ce qui a été mesuré pendant la construction de `microturn`, avec la méthode
et ses limites. Rien n'est extrapolé sans le dire.

**Deux machines** : `shiao`, un laptop i7-7500U (2 cœurs / 4 threads, 7,5 Go), et
`raspi2`, un Raspberry Pi 3B (4× Cortex-A53 @1,2 GHz, 905 Mio, sans GPU).
**Audio de test** : deux enregistrements réels d'une voix française, 20 s chacun,
16 kHz mono — l'un à un mètre du micro, l'autre à trois.

---

## 1. Reconnaissance vocale sur Raspberry Pi 3B

Le RTF (*real-time factor*) est le temps de traitement divisé par la durée de
l'audio. **Sous 1,0, le système suit le temps réel.**

| Moteur | à 1 m | à 3 m | RSS |
|---|---|---|---|
| Vosk small FR 0.22 | 1,86 | 3,03 | 241-293 Mo |
| whisper.cpp `tiny` q5, beam 5 (défaut) | 1,17 | 1,39 | 130 Mo |
| **whisper.cpp `tiny` q5, greedy** | **0,62** | **0,66** | **103 Mo** |
| whisper.cpp `base` q5 | 2,75 | — | 197 Mo |

**Le résultat le plus rentable du projet est gratuit.** `whisper-cli` tourne par
défaut en *beam search* 5 avec repli de température ; `-bs 1 -bo 1 -nf` divise son
temps par deux et lui fait gagner 27 Mo, **sans changer la transcription**. Nous
avons donc failli conclure que whisper ne tenait pas le temps réel sur un Pi 3B
alors qu'il était simplement mal configuré.

**Vosk perd sur les deux tableaux**, à rebours de ce que la littérature laisse
attendre pour l'embarqué. L'explication tient en un mot : il est **mono-thread**,
donc il n'utilise qu'un cœur sur les quatre. Et son empreinte gonfle en cours de
tour, le treillis de décodage n'étant pas remis à zéro.

`base` transcrit **exactement comme `tiny`** sur nos échantillons, pour 2,6 fois
le temps. Aucune raison de l'utiliser.

### Nombre de threads (whisper `tiny` q5, greedy)

| Threads | RTF | Température finale |
|---|---|---|
| 4 | 0,59 | 78,4 °C |
| **3** | **0,64** | 76,8 °C |
| **2** | **0,86** | **73,1 °C** |
| 1 | 1,66 | 67,7 °C |

`-t 2` reste sous le temps réel **tout en laissant deux cœurs libres** et en
évitant le throttling. C'est le meilleur point de fonctionnement pour une chaîne
complète, et pas celui qu'on choisirait en optimisant le seul RTF.

---

## 2. Le mur thermique

Mesuré sur `raspi2`, alimentation saine (1,3125 V constants, jamais de
sous-tension) :

```
t+25 s   80,1 °C   1200 MHz   throttling déclenché
t+30 s   80,6 °C   1087 MHz
t+35 s   81,7 °C   1034 MHz   -14 % de fréquence
```

**Vingt-cinq secondes de charge sur quatre cœurs suffisent.** Le Pi ne redescend
jamais sous **58 °C** au repos, sans dissipateur : la marge est de 22 °C.

Conséquence directe et quantifiée : whisper `tiny` met **12,07 s** sur machine
froide et **16,4 s** à chaud pour le même fichier de 11 s — **36 % de perte**.
Toute mesure prise sans refroidissement préalable est fausse.

---

## 3. Modèles de langage locaux sur le Pi

| Modèle | Temps | Débit | RSS |
|---|---|---|---|
| SmolLM2-135M q4 | 7,64 s | 6,3 tok/s | 229 Mo |
| SmolLM2-360M q4 | 15,16 s | 3,2 tok/s | 458 Mo |

Pour une réponse de 48 tokens. **Inutilisable** dans une boucle conversationnelle :
un appel distant coûte 0,4 s. La décision reste donc distante, et c'est une
contrainte d'architecture, pas une préférence.

---

## 4. Ce qui tient en parallèle sur le Pi

Ralentissement de chaque tâche par rapport à son temps seul :

| Combinaison | RAM libre au pire | T max | Ralentissement |
|---|---|---|---|
| STT + espeak | 566 Mo | 75,8 °C | stt ×1,00 · esp ×2,48 |
| **STT + API + espeak** | **606 Mo** | 76,3 °C | **stt ×0,99 · api ×0,79 · esp ×2,53** |
| STT + son + vision | 588 Mo | 78,4 °C | stt ×0,98 · son ×0,76 · vis ×0,39 |
| STT + son + vision + API + espeak | 506 Mo | 81,7 °C | stt ×1,20 · son ×0,61 |

**La chaîne vocale complète ne se ralentit pas elle-même.** Même cinq couches
simultanées laissent 506 Mo libres. La contrainte est le CPU et la température,
jamais la mémoire — contrairement à ce qu'on supposait au départ.

---

## 5. Le coût d'un appel à froid

| Traitement | À froid | En service résident |
|---|---|---|
| YuNet (visages) | 7,74 s | **46,6 ms** |
| MobileNet-SSD (personnes) | 10,40 s | **270,5 ms** |
| YAMNet (sons) | 1,56 s | **157,8 ms** |
| Mouvement MOG2 | 13,84 s | 124,0 ms |

**Un facteur 40 à 165.** Toute mesure qui relance le processus à chaque appel
mesure le chargement du modèle, pas le traitement. C'est un piège dans lequel nous
sommes tombés avant de le corriger.

---

## 6. Synthèse vocale

Sur `shiao` : piper `fr_FR-siwis-medium` rend son premier son en **0,97 s**
(RTF 0,21), `upmc` en 1,10 s, `tom` en 2,32 s. Sur le Pi : espeak-ng **0,07 s et
5 Mo**, piper-low 5,92 s et 152 Mo, piper-medium 7,61 s et 236 Mo.

Détail utile : piper **ne streame pas** — sa synthèse totale égale le temps du
premier son. Et il **recharge son modèle de 63 Mo à chaque phrase**, ce qui fait
du découpage en phrases une pessimisation tant qu'il n'est pas résident.

---

## 7. Le décideur — le résultat le plus surprenant

Douze cas étiquetés à la main, **les deux classes comptées séparément** : sept où
la personne n'a pas fini (le système doit se taire), cinq où elle attend une
réponse. `temperature=0`.

| Modèle | Total | Silences tenus | **Questions vues** | Latence |
|---|---|---|---|---|
| llama-3.2-**3b** | 7/12 | **7/7** | **0/5** | 0,41 s |
| llama-3.2-**1b** | 7/12 | **7/7** | **0/5** | 0,39 s |
| **gemini-2.5-flash-lite** | 9/12 | 5/7 | **4/5** | **0,52 s** |
| nova-micro-v1 | 7/12 | 6/7 | 1/5 | 0,48 s |
| gpt-4o-mini | **10/12** | 6/7 | 4/5 | 0,87 s |
| llama-3.3-70b | — | — | — | **10,46 s** |

**Les deux Llama 3.2 ne prennent jamais la parole.** Zéro question détectée sur
cinq, l'un comme l'autre, et cela résiste à tous les prompts essayés — anglais,
français, court, long, avec ou sans exemples, critères grammaticaux explicites.
Ils tiennent parfaitement les silences et c'est tout.

**Et c'est un piège de mesure**, qui est peut-être le résultat le plus utile de
tout ce travail : dans une conversation réelle, neuf ticks sur dix sont
effectivement « elle parle encore ». **Un modèle qui répond toujours cela obtient
donc mécaniquement 90 % de justesse globale.** Nous l'avons vécu : un score de
16/21 sur un banc dominé par cette classe, pour un modèle en réalité incapable de
répondre. Il faut compter les deux classes séparément, faute de quoi le mutisme
ressemble à de la sagesse.

La taille n'explique rien ici : le `1b` et le `3b` échouent pareil, tandis que
`gemini-flash-lite` réussit pour une latence comparable. C'est une question
d'entraînement, pas de capacité.

---

## 8. Effet des corrections d'architecture

Même audio, même session de 145 s rejouée, seul le code change :

| | Six seuils | Horloge fixe |
|---|---|---|
| Décisions prises | 23 | 120 |
| Prises de parole | 13 | 14 |
| Se taire / parler | 0,8 pour 1 | 7,6 pour 1 |

⚠️ **Ce dernier chiffre est à prendre avec précaution** : une partie de cette
retenue apparente venait d'un bug — un `DONE` sans réponse était silencieusement
compté comme « elle parle encore ». Le système ne s'était pas assagi, il était
devenu **aphasique au bon moment**. Mesurer les deux classes séparément, encore
une fois, aurait montré le problème immédiatement.

---

## Limites, honnêtement

- **Petits échantillons** : douze cas pour les modèles, deux enregistrements de
  20 s pour le STT. Les écarts francs (0/5 contre 4/5) sont solides ; les écarts
  d'un point ne le sont pas.
- **Un seul locuteur, une seule pièce, un seul micro.** Les chiffres de distance
  et d'écho ne se généralisent pas.
- **`temperature=0.3` invalidait tout** : dix décisions sur vingt-et-une changeaient
  d'une passe à l'autre. Les mesures antérieures à ce correctif ne valent rien.
- **Les mesures du Pi et du laptop ne sont pas comparables** entre elles : matériel,
  configuration de whisper et thermique diffèrent. Chaque tableau vaut pour sa
  machine.
- **Nous avons mesuré le comportement de tour de parole, pas la qualité des
  réponses.** La bêtise d'un petit modèle est attendue et n'est pas le sujet.
