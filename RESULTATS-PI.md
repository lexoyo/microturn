# Le budget temps réel sur Raspberry Pi 3B

Mesuré le 29/08/2026 sur `raspi2` (Pi 3B, 4× Cortex-A53 @1,2 GHz, 905 Mio, sans
dissipateur), en rejouant les sessions déjà enregistrées — pas des micro-bancs
par étage, mais la chaîne complète telle qu'elle tourne. Référence : `shiao`
(i7-7500U, 2 cœurs / 4 threads).

Méthode : `pipeline.py sessions/<h>/entree.wav --trace <dir>`, en `--muet` puis
en `--rendu` (qui exerce piper pour de vrai). Chaque passe démarre sous 60 °C
comme l'impose le `PROTOCOLE.md`, avec température et throttling échantillonnés
toutes les deux secondes. Les coûts par étage sont lus dans la trace du projet
lui-même (`partial.cout`, `llm_reponse.latence`), rien n'a été instrumenté.

**Aucun code du dépôt n'a été modifié.** Ce qu'il a fallu installer sur le Pi
est listé en fin de document.

---

## 1. Le budget de chaque étage

L'horloge du système est `TICK_S = 1,2 s` : c'est la cadence à laquelle le
décideur est consulté, et donc le budget que chaque étage doit tenir pour que le
système voie la conversation en temps réel.

| Étage | budget | `shiao` | **`raspi2`** | facteur |
|---|---|---|---|---|
| Capture + porte | 125 ms/bloc | tient | **tient** | — |
| **STT, une passe** | **1,2 s** | 1,3 – 1,8 s | **7,0 – 12,3 s** | **×5 à ×7** |
| STT, RTF effectif | < 1,0 | 0,10 | **0,35** | ×3,4 |
| Décideur (distant) | 1,5 s (timeout) | 0,41 – 0,55 s | **0,46 – 0,54 s** | **×1,0** |
| TTS piper, une réponse | — | 3,3 – 4,3 s | **9,9 s** | ×2,5 à ×3 |

Deux sessions rejouées, 37,1 s et 90,9 s d'audio, en muet et en rendu.

---

## 2. Ce qui explose en premier : le STT

**Dès la première passe, et d'un facteur 6.** Une transcription coûte 7 s sur un
tour court, et jusqu'à 12,3 s sur un tour long, quand le budget est de 1,2 s.

Coûts successifs des passes sur la session de 90,9 s, dans l'ordre :

```
raspi2   7,5   8,2   9,9   11,2   12,3   12,2   9,4   10,0     (8 passes)
shiao    1,3   1,4   1,6    1,6    1,6    1,6   1,5   1,5 …    (15 passes, plat)
```

La forme de la courbe dit la cause. Sur `shiao` le coût est **plat** ; sur le Pi
il **monte avec la durée du tour**, puis retombe quand le tampon est remis à zéro.
Ce n'est donc pas whisper qui est trop lent — son RTF de 0,62 mesuré dans
`RESULTATS.md` est confirmé ici (RTF effectif 0,35 sur la chaîne complète, soit
sous le temps réel). C'est que `stt.py` **re-transcrit tout le tour à chaque
passe**, jusqu'à `PLAFOND_S = 20 s`. À RTF 0,6, une fenêtre de 16 s coûte
mécaniquement 10 s de calcul. Sur `shiao`, le facteur 4 de CPU masque le
problème ; sur le Pi il devient la contrainte dominante.

Conséquence : le décideur travaille sur une transcription vieille de sept à
douze secondes, soit six à dix ticks de retard. Et le nombre de passes tombe de
15 à 8 pour le même audio — le système voit passer deux fois moins de ce qui est
dit.

**Le mode de défaillance n'est pas un plantage.** L'architecture non bloquante
encaisse : `evenements_perdus = 0`, aucun débordement du tube, le rejeu se
termine proprement (102,7 s de mur pour 90,9 s d'audio, dont ~4 s de coût fixe
de démarrage mesuré à part). Le système ne casse pas, il devient **sourd**.

---

## 3. Ce qui tient sans effort : le décideur

**0,46 à 0,54 s de latence médiane depuis le Pi, contre 0,41 à 0,55 s depuis
`shiao`. Aucun dépassement du timeout de 1,5 s sur 160 appels.**

C'est le résultat le moins attendu : l'étage distant, celui qu'on soupçonnerait
en premier sur une petite machine en wifi, est le seul dont le budget ne bouge
pas d'une machine à l'autre. Il ne dépend ni du CPU ni de la thermique. La
décision distante, choisie par contrainte au §3 de `RESULTATS.md`, se trouve être
la partie de l'architecture qui porte le mieux le portage.

---

## 4. Le TTS : l'horloge interne devient fausse

Même session, même machine, même réponse — seul le moteur change :

| | `shiao` | **`raspi2`** |
|---|---|---|
| durée estimée par le code (`--muet`) | 3,45 s | 3,25 s |
| durée réelle mesurée (`--rendu`) | 3,29 s | **9,87 s** |
| écart | −5 % | **×3,0** |

`tts.Silencieux` estime la durée de parole avec `ATTAQUE_S = 0,95` et
`DEBIT_CAR_S = 14`, calibrés sur `shiao` où ils sont justes à 5 % près. Sur le Pi
ils sous-estiment la synthèse **d'un facteur trois**. Le système croit donc avoir
fini de parler quand piper synthétise encore : l'état « je parle » qui protège du
barge-in et de l'écho se termine sept secondes trop tôt.

C'est un défaut de constante, pas d'architecture — mais il ne se voit qu'en
mesurant sur la machine cible.

⚠️ **Une seule prise de parole par session** : deux mesures en tout. L'ordre de
grandeur est net et concorde avec le §6 de `RESULTATS.md` (piper-medium, 7,61 s
d'attaque sur le Pi), le chiffre exact ne l'est pas.

---

## 5. Le mur thermique, en conditions réelles

Chaque passe a démarré sous 60 °C, comme l'exige le protocole. Aucune n'a fini
sans bridage :

| session | mode | T départ | T max | fréquence min | bridé |
|---|---|---|---|---|---|
| 37 s | muet | 58,5 °C | 81,7 °C | 1087 MHz | oui |
| 37 s | rendu | 59,1 °C | 82,2 °C | **600 MHz** | oui |
| 91 s | muet | 59,1 °C | 83,8 °C | **600 MHz** | oui |
| 91 s | rendu | 59,6 °C | 84,4 °C | **600 MHz** | oui |

**La chaîne vocale complète fait tomber le Pi à la moitié de sa fréquence, en
moins de quarante secondes, en partant froid.** Le §2 de `RESULTATS.md` annonçait
un bridage à −14 % après 25 s de charge sur quatre cœurs ; en usage réel c'est
−50 %, et c'est l'état permanent, pas un pic.

Le refroidissement fonctionne (retour à 65 °C en quelques minutes après arrêt) et
le repos observé cette nuit-là descend à 50,5 °C — plus bas que les 58 °C notés
dans `RESULTATS.md`, sans doute l'ambiante nocturne.

Ce bridage aggrave d'un facteur 2 au pire. Il n'explique donc pas les facteurs 5
à 7 du STT : la cause reste la fenêtre re-transcrite.

---

## 6. Ce que le Pi a fait sans broncher

À noter, parce que c'était la crainte initiale et qu'elle est levée : **la
mémoire n'est jamais un problème**. 905 Mio suffisent largement, whisper résident
compris (le modèle charge en 0,33 s). Aucun événement perdu, aucun débordement du
tube audio, aucune sous-tension. La contrainte est le CPU et la température,
jamais la RAM — ce que le §4 de `RESULTATS.md` disait déjà, et qui se vérifie sur
la chaîne complète.

---

## Installation faite sur `raspi2`

Le dépôt n'y était pas. Ce qui a été ajouté, sans toucher au code :

| Élément | Comment |
|---|---|
| dépôt `~/microturn` | rsync, hors `.venv`, vosk et `ggml-small` |
| venv | `--system-site-packages` — réutilise le numpy 2.2.4 système |
| pywhispercpp 1.5.1 | **wheel aarch64 piwheels, aucune compilation** |
| `ggml-tiny-q5_1.bin` | copié, charge en 0,33 s |
| piper + `fr_FR-siwis-medium` | la voix était déjà là (`~/bench/piper/fr.onnx`) ; enveloppe `~/.local/bin/piper` pour ses `.so` et ses données espeak |
| ffmpeg | 7.0.2 statique aarch64 via le paquet PyPI `imageio-ffmpeg`, **sans sudo** |
| `.env` | copié — le décideur distant répond depuis le Pi |

`bash tests/fumee.sh` sur le Pi : **10 réussis, 1 échoué**. Le seul échec est le
moteur `vosk`, absent du venv et dont le modèle n'a pas été copié — moteur
secondaire, déjà écarté au §1 de `RESULTATS.md`.

---

## Limites, honnêtement

- **Deux sessions, deux longueurs** (37 s et 91 s). La série sur la session de
  149 s a été interrompue. La pente du coût STT est nette sur ce qu'on a, elle
  n'est pas confirmée au-delà de 91 s.
- **Le TTS repose sur deux mesures.** Une prise de parole par session.
- **Le code n'était pas strictement identique** sur les deux machines au moment
  du rejeu : `stt.py`, `audio.py` et `tts.py` l'étaient (mêmes sha256, mêmes
  `reglages_stt`), donc les chiffres STT, TTS et thermiques sont comparables ;
  `llm.py`, `pipeline.py` et les catalogues ont divergé entre-temps (une autre
  session travaillait sur le dépôt). **Les chiffres de comportement — décisions,
  prises de parole — ne sont donc pas comparables entre les deux machines et ne
  figurent pas ici.**
- **Le décideur est non déterministe** : deux rejeux du même audio ne prennent
  pas les mêmes décisions. Seules les latences sont comparées, pas les choix.
- **Une seule nuit, une seule ambiante.** La thermique d'un Pi sans dissipateur
  dépend de la pièce ; ces chiffres valent pour ~50 °C au repos.
