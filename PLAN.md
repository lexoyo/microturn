# Plan d'implémentation de la nouvelle architecture

`SPEC-PIVOT.md` dit **ce qu'on construit**. Ce fichier dit **comment**, et dans
quel ordre. Point de départ figé : tag `v0.1-prototype`.

Les noms de classes sont provisoires (le nom du projet lui-même n'est pas
tranché, cf. `SPEC-PIVOT.md` § 11).

---

## 1. L'entrée : des observations horodatées

### Le mécanisme

Un appel **synchrone**, poussé par l'hôte. Pas de thread dans le cœur, pas d'I/O,
pas d'horloge réelle.

```python
det.feed(Observation(t=12.4, text="EST CE QUE TU PEUX ME DIRE LA"))
```

```python
@dataclass(frozen=True)
class Observation:
    t: float                     # secondes depuis le début, source unique du temps
    text: str = ""               # transcription CUMULATIVE du SEGMENT en cours
    segment: int = 0             # identifiant du segment ASR
    final: bool = False          # ce segment est figé et ne sera plus revu
    context: dict | None = None  # {"voice": True, "speakers": 2, "sound": "music"}
```

### Le prérequis, énoncé sans le contourner

**Décision du 02/09 : l'entrée exige un ASR en mode flux, et on dit
explicitement avec lesquels on a mesuré.** Pas de promesse de compatibilité
universelle tant qu'elle n'est pas vérifiée — un « marche avec tous les ASR »
non testé se paie en rapports de bug.

| moteur | statut |
|---|---|
| `sherpa-onnx` zipformer streaming fr (`2023-04-14`, int8) | **la référence** — tous les chiffres du projet en viennent |
| `whisper.cpp` (`tiny`, `base`) | mesuré, fonctionne, mais non causal : il re-transcrit tout le tour à chaque passe |
| `vosk` | mesuré et écarté — perdant sur les trois axes |
| tout le reste | **non testé, donc non promis** |

Le contrat exact — texte cumulatif du tour, ou du segment plus un drapeau
`final` — dépend de la forme réelle des sorties des moteurs courants. Une
recherche est en cours ; en attendant, la référence est le comportement de
sherpa : un texte cumulatif révisable, avec une détection de fin de segment
qu'on peut régler.

### Trois décisions non évidentes

**Le texte est cumulatif par SEGMENT, et c'est nous qui recollons.** Recherche du
02/09, sur les moteurs réels : la segmentation de l'ASR ne coïncide pas avec le
tour de parole. Un moteur qui ferme un segment sur quelques centaines de
millisecondes de silence coupe **au milieu d'une pause de réflexion** — le cas
même que cette bibliothèque existe pour détecter. Demander à l'hôte de recoller
(contrat « texte du tour ») lui ferait refaire notre travail, mal.

D'où trois champs et non un : `text` (cumulatif du segment, révisable),
`segment` (change quand l'ASR ferme), `final` (ce segment ne bougera plus).

**Précédent à citer plutôt qu'à imposer** : Deepgram est le seul moteur qui
sépare proprement `is_final` (« ce segment est figé ») de `speech_final` (« le
tour est fini »). Ni Google, ni Soniox, ni Speechmatics ne le font. Notre
contrat reprend cette distinction, et c'est **nous** qui produisons le second.

**Le contrat append-only est disqualifié**, et pas par principe : trois projets
ont dû réinventer la stabilité par-dessus (`wyoming_streaming_asr` jette le
dernier mot et calcule un suffixe à la main, sans pouvoir retirer un mot révisé ;
`RealtimeSTT` y consacre ~400 lignes ; Pipecat/Soniox republie même les tokens
finaux en interim). La forme append-only n'est pas plus simple : c'est la même
complexité déplacée chez le producteur, **avec l'information détruite au
passage**.

**À prévoir dès la v1 : un tier de stabilité intermédiaire.** Trois moteurs l'ont
inventé indépendamment — la `stability` de Google, le `stop_history_eou` de
NVIDIA Riva, le `PREFLIGHT_TRANSCRIPT` de LiveKit. C'est un besoin universel, pas
une coquetterie.

Le calcul du delta reste **chez nous**, parce que c'est le morceau le plus subtil du projet :
`_delta()` ancre par la **queue** et non par le préfixe, précisément pour survivre
au moment où l'ASR se ravise (mesuré deux fois comme critique). Un ancrage naïf
retombe à zéro dès la première correction et renvoie la phrase entière comme
neuve. C'est aussi l'opération `revoke` du modèle IU (`SPEC-PIVOT.md` § 8) : on
implémente un concept publié, pas un bricolage.

**Le temps vient de `t`, jamais de `time.time()`.** C'est ce qui rend le rejeu
déterministe gratuit — plus de patch du module `time` (le défaut G2 de la QC), et
le cœur devient testable sans attendre. Une seule règle : aucun appel à l'horloge
système dans le cœur.

**`t` est du temps AUDIO, et il ne vient pas de l'ASR.** C'est la position dans
le flux — le compteur d'échantillons de la source, ce que le code fait déjà
(`pipeline.py:245` rend `cap.lus`). Exact, monotone, insensible à la charge CPU.
Deux raisons de ne pas le prendre de l'ASR :

- **les formats divergent** : Whisper rend `start`/`end` par segment, les autres
  moteurs n'ont ni la même granularité ni la même origine. Ce serait un
  adaptateur par moteur pour une information que la source possède déjà,
  exactement ;
- **et surtout, quand l'ASR ne rend rien, il n'y a pas d'observation.** Si `t` ne
  venait que de lui, le temps s'arrêterait pendant les silences — précisément là
  où il faut décider si la personne réfléchit ou a fini.

**Conséquence sur le contrat : l'hôte pousse des observations même vides**, à
cadence régulière. Le battement vient de la source, le texte vient de l'ASR ;
ce sont deux choses distinctes qui voyagent dans le même objet. Un hôte qui ne
pousse que lorsqu'il a du texte obtient un système qui ne détecte jamais un
silence — et rien ne le lui dira. **À valider explicitement** : refuser (ou au
moins signaler) un flux dont les observations non vides sont espacées de plus de
quelques ticks.

**Le contexte est un dict, pas des champs figés.** C'est le point d'entrée des
« producteurs » du § 10 d'`IDEES.md` : caméra, ambiance sonore, domotique. Il
faut donc dire **comment un dict devient du texte pour le modèle** — un
`ContextRenderer` par défaut qui sérialise en une ligne, remplaçable. Sans ça, on
aura un champ que personne ne sait utiliser.

### Le tick appartient à la bibliothèque

`feed()` accumule et déclenche un tick quand `t` a assez avancé (défaut 1,2 s).
L'hôte peut le régler, mais pas l'oublier : le laisser piloter le tick, c'est
accepter qu'il le mette faux et que plus rien ne soit détecté, sans message.

---

## 2. Les hooks : deux vitesses, et c'est le point délicat

L'objectif est de **déclencher un TTS ou de l'interrompre**. Ces deux actions
n'ont pas du tout les mêmes contraintes de latence, et c'est ce qui commande le
mécanisme.

| | déclencher | interrompre |
|---|---|---|
| événement | `TURN_END` | `SPEAKING` |
| tolérance | ~1 tick | **le plus vite possible** |
| source | décision du modèle | l'ASR rend du texte |

**Conséquence : deux chemins d'émission.**

- **Chemin lent** — les états qui demandent un jugement (`THINKING`, `TURN_END`)
  sortent au tick, après la décision du modèle.
- **Chemin rapide** — `SPEAKING` est émis **dès que du texte non vide arrive**,
  sans attendre le tick ni le réseau. C'est ce qui rend le barge-in utilisable :
  le prototype actuel coupe déjà le TTS localement sans attendre la réponse
  distante (`pipeline.py:709-712`), et cette propriété ne doit pas être perdue
  dans l'extraction.

### La forme

Un callback unique, appelé **dans le thread de l'appelant** :

```python
det = Detector(decider=..., on_event=mon_hook)
```

Pourquoi pas un itérateur pour le cœur : un itérateur fait *tirer* les
événements par la boucle de l'hôte, donc l'interruption attend le prochain tour
de boucle. Le callback la livre dans la microseconde.

⚠️ **Le danger, à documenter en gras dans le README** : le hook tourne chez
l'appelant. Un hook lent bloque `feed()`, et on retombe exactement sur les
débordements de tampon que tout le projet a passé son temps à éliminer.
Fournir un `QueuedSink` pour les distraits, et écrire l'invariant en tête :
*personne ne bloque sur de l'I/O.*

### Par-dessus, l'API du débutant

Une classe mince (~60 lignes) qui possède un thread, lit une source et expose un
itérateur — c'est celle du README et des exemples :

```python
for ev in Stream(source=MicSource(), asr=Sherpa(), decider=Remote()):
    if ev.kind is TURN_END:
        parler(ev.draft or mon_llm(ev.text))
```

Les deux sont le même paquet. Le cœur est push et testable ; l'enveloppe est
confortable.

---

## 3. La sortie

```python
@dataclass(frozen=True)
class Event:
    kind: Kind                    # SILENCE | SPEAKING | THINKING | BACKCHANNEL | TURN_END
    t: float
    text: str = ""                # rempli sur TURN_END : la phrase complète
    draft: str | None = None      # la réponse, en mode fusionné ou spéculatif (§ 9 de la spec)
    confidence: float | None = None
```

**Émission au changement d'état seulement**, jamais à chaque tick — sinon l'hôte
est noyé sous des `SPEAKING` identiques. L'état courant reste lisible à tout
moment par `det.state`.

**`confidence` n'est pas décoratif.** eot-bench démontre que tout l'intérêt d'un
détecteur est dans le balayage seuil/latence ; rendre une décision binaire ferme
la porte au réglage du compromis par l'hôte. À rendre dès qu'on sait le produire.

---

## 4. Les états

Repris de `SPEC-PIVOT.md` § 3, sans changement.

| | sens |
|---|---|
| `SILENCE` | rien |
| `SPEAKING` | il parle, phrase en cours (absorbe aujourd'hui la pause intra-tour) |
| `THINKING` | il se tait mais n'a pas fini — le *gap* de Sacks-Schegloff-Jefferson |
| `BACKCHANNEL` | signal d'écoute, pas une prise de parole |
| `TURN_END` | événement, porte la phrase complète |

Pas d'`INTERRUPTION` : c'est un `SPEAKING` reçu pendant que l'hôte parle, et
l'hôte est seul à le savoir.

Ouverts : `PARTIAL` (texte en cours, opt-in), `DEPARTED` (le *lapse*), et la
question de savoir si la pause intra-tour mérite son propre état.

---

## 5. Les exemples livrés avec le framework

Trois, choisis pour couvrir trois usages différents — et chacun est aussi un test
exécutable.

### `examples/companion/` — ce qu'on a déjà, et le seul mesuré

sherpa-onnx → détecteur → piper. C'est le prototype `v0.1` réduit à un exemple.
Sa fonction n'est pas de démontrer, c'est de **prouver la non-régression** : il
doit retomber sur **0,816 ± 0,015, en moyenne de trois passes** après
extraction, sinon on a cassé quelque chose. **Pas 0,826 sur une passe** : voir
l'étape 5.

### `examples/no_audio/` — le cœur sans un octet de son

Des observations tapées à la main, avec leurs horodatages, poussées dans
`feed()`. Aucune dépendance : ni micro, ni ASR, ni réseau si le décideur est
simulé. C'est le meilleur exemple pédagogique, parce qu'il **démontre la thèse du
projet** — la détection se fait sur le sens, pas sur le son — et c'est le test le
plus rapide de la suite.

### `examples/chat/` — la voix comme clavier

Tu parles ; à chaque `TURN_END`, la phrase est envoyée **comme si tu avais appuyé
sur Entrée**. Rien d'autre : pas de TTS, pas de modèle de réponse, pas de
`draft`.

C'est le meilleur des trois, pour trois raisons :

- **c'est la métaphore fondatrice du projet, rendue littérale** — tout le
  `SPEC-PIVOT.md` la répète, ici on la voit tourner ;
- **c'est utile tout de suite**, sans rien brancher derrière : de la dictée dans
  n'importe quel champ de saisie, où le passage à la ligne est décidé par le sens
  et non par un raccourci clavier ou un silence de 700 ms ;
- **il démontre l'autonomie de la bibliothèque** mieux qu'un discours : ni voix
  de sortie, ni LLM de réponse, et pourtant le système fait quelque chose que
  personne d'autre ne fait.

*Idée écartée* : un exemple « écouter et illustrer » (image ou recherche à chaque
fin de tour). Même démonstration — un système qui ne parle pas — mais il demande
un modèle et une clé pour tourner, là où le chat ne demande rien.

---

## 6. Le plan des choses à faire

Ordre contraint : chaque étape est le filet de la suivante.

### Étape 0 — nettoyer avant d'extraire

Sinon on extrait du mensonge.

- Trancher `[etats]` (QC C1/G4) : la section est **vide** dans les deux
  catalogues, donc le modèle ne sait pas que l'assistant parle, `<|user
  interruption|>` n'est jamais sorti (0 fois sur 153), et **toutes les lignes de
  log affichent `[muet]`** quel que soit l'état réel.
- Supprimer le code mort du candidat 59 (`TICKS_SILENCE`) et `Vosk`.
- Corriger G3 : `robot_parle` n'est jamais rafraîchi en rejeu déterministe. Mine
  amorcée pour le jour où les marqueurs d'état reviennent.

### Étape 1 — le filet

Tests unitaires de `_delta`, `_cle`, `_est_echo`, `lire_controle`, **écrits sur
le code actuel**. Ces fonctions sont pures ou quasi ; trente lignes chacune, sans
audio ni réseau. Aujourd'hui **rien ne les protège** — le banc lance
`pipeline.py` en sous-processus, il teste une CLI, pas du code.

### Étape 2 — extraire le `Detector`

Les ~220 lignes qui comptent (`_cle`, `_rien`, `_delta`, `_tick`, `_appliquer`),
avec `t` injecté et la durée de parole en paramètre. Le reste de `pipeline.py`
est de l'orchestration et de la CLI.

### Étape 3 — rendre `llm.py` importable

`import llm` **échoue aujourd'hui sans clé OpenRouter** : `KEY = _key()` s'exécute
au chargement et lève `SystemExit`. Plus huit autres `sys.exit` déguisés dans le
chargement des catalogues. Une bibliothèque ne peut pas faire ça, et surtout pas
pour une clé dont le point d'extension « répondeur » est censé se passer.
Clé paresseuse, exceptions typées.

### Étape 4 — sortir le TTS et l'ASR

Derrière leurs protocoles. Garder `Silencieux` **dans** la bibliothèque, renommé
en modèle de durée de parole, avec ses deux constantes remontées dans la
signature — elles sont fausses d'un facteur trois sur Pi. Garder `Enregistreur`
dans l'extra `bench`, c'est le seul chemin vers un fichier audio mesurable.

### Étape 5 — remesurer

Retomber sur **0,816 ± 0,015, moyenne de trois passes**. C'est la seule preuve
que l'extraction n'a rien cassé.

⚠️ **Le critère ne peut pas être « 0,826 sur une passe »**, et cette erreur était
écrite ici avant le 02/09. L'écart-type est de 0,015 sur une passe, donc l'écart
entre **deux** passes uniques a pour écart-type σ√2 ≈ 0,021 : **une passe à 0,791
est parfaitement compatible avec un code intact.** Prendre 0,826 comme référence
produirait des fausses alertes en série pendant l'extraction — et, pire, ferait
« corriger » du code qui n'a rien.
`tests/fumee.sh` est écrit contre la CLI et sera périmé : à réécrire contre l'API.

### Étape 6 — se comparer aux autres

Passer sur **eot-bench en français**. Notre chiffre n'est aujourd'hui comparable
qu'à DuplexCascade, dont la métrique est propre à ce papier. C'est le seul
terrain où l'on saura ce qu'on vaut face à Smart Turn et LiveKit — et si l'on est
derrière, autant l'apprendre en deux jours qu'en six mois.

---

## Ce qui reste à trancher avant l'étape 2

1. **Le prompt doit être apparié à l'ASR** (+0,063 si la description de l'entrée
   est vraie, −0,103 si elle est fausse). Si l'ASR est branchable, le catalogue
   de prompts doit l'être aussi.
2. **La pause intra-tour** mérite-t-elle son propre état ? C'est la distinction
   qu'un VAD ne sait pas faire, donc l'argument de vente, et elle n'a aucun
   marqueur aujourd'hui.

---

# Reprendre demain — état au 03/09, 03 h

Une page à relire en deux minutes. Le détail des mesures est dans
`bench/JOURNAL.md`, le récit dans `ARTICLE-NOTES.md`.

## Acquis, mesuré, ne pas y revenir

| | |
|---|---|
| **Le fine-tuning vaut 0,209** à modèle constant | Qwen2.5-7B prompté : 0,649 · gemini : 0,808 · leur Qwen2-7B fine-tuné : 0,858 |
| dont **0,159 rattrapés** en changeant de modèle | c'est le seul écart qui ne mélange rien |
| **Le rappel du tour retiré rapporte** | 13/17 → 14/17 fins de tour, 3/3, −14 % de tokens |
| **Le repliage élargi coûte** | 0,804 contre 0,824 : il libère des places que la parole vient occuper |
| **Dire la durée du silence** ne change rien de mesurable | +0,3 fin de tour, distributions recouvrantes |
| **Le TTS passe par un WAV par phrase** | comme wyoming-piper, rhasspy3, pipecat. Aucun n'utilise `--output-raw` |

## Ouvert, par ordre d'importance

1. **La référence est périmée.** Le contrôle est tombé à 0,796 au lieu de
   0,808–0,816, et personne n'a isolé lequel des commits récents coûte une fin
   de tour. **Tout écart mesuré demain se compare à un chiffre faux tant que ce
   n'est pas fait.** C'est la première chose.
2. **Le tutoiement retiré a ramené le tic** — 4 % → 30 %, réponses de 57 à
   77 caractères, justesse inchangée. Arbitrage d'Alex, jamais tranché.
3. **Plus rien ne tient la longueur des réponses** : ni le prompt (« courte »
   retiré), ni le schéma (`maxLength` retiré), ni `max_tokens` (supprimé).
   Assumé ce soir ; à revoir si l'écoute devient pénible.
4. **La cascade `NIVEAUX` de `llm.py` est morte** : `decide()` construit son
   `response_format` en dur et n'appelle jamais `contrainte()`. Sans effet tant
   que le modèle accepte le schéma — 100 % des décisions perdues sinon.
5. **Le recollage après une prise de parole** (question d'Alex, non tranchée) :
   le `reset()` emporte le début du tour, qui sort ensuite de la fenêtre des
   20 micro-tours. À noter que les chercheurs n'ont pas ce problème : ils n'ont
   pas de « transcript du tour », seulement l'historique.

## Petites choses qui traînent

- Trois commentaires de `tts.py` décrivent des mécanismes retirés.
- Le verrou de synthèse est un attribut **de classe**, partagé entre instances.
- `pret()` existe mais n'est pas branché : le pipeline paie toujours le
  chargement de piper sur la première réponse.
- `session.jsonl` n'enregistre pas `silence_replie` — le comptage des repliages
  passe par le log, donc une mesure doit patcher `bench/sessions.py`.

## Et le pivot, qui n'a pas avancé aujourd'hui

`SPEC-PIVOT.md` est complet et tranché. `PLAN.md` (ci-dessus) donne l'ordre
des étapes. **Rien n'a commencé** : la journée est partie en correctifs de
session. L'étape 0 (nettoyer avant d'extraire) et l'étape 1 (les tests du
noyau) restent à faire — sauf `tests/delta.py`, écrit aujourd'hui, qui est
la moitié de l'étape 1.
