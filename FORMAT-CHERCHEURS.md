# Le format de DuplexCascade, en face du nôtre

Sources : arXiv 2603.09180 (papier) et github.com/sbintuitions/DuplexCascade.
Vérifié le 29/08/2026. Ce qui n'est pas documenté est signalé comme tel.

## 1. Ils n'ont pas de prompt système

Le comportement vient **entièrement** du fine-tuning LoRA sur Qwen2-7B-Instruct
(8×H100, 5 heures). Ni le papier ni le dépôt ne montrent de prompt système, et
la méthode — « next-token prediction LoRA fine-tuning on system micro-turns
only » — n'en demande pas.

**Conséquence directe pour nous : il n'y a rien à copier de ce côté.** Tout
notre prompt est une invention rendue nécessaire par le fait qu'on n'entraîne
pas. Parler de « conformité au papier » à propos du prompt n'a pas de sens ;
ça n'en a que pour le vocabulaire des jetons et la structure des messages.

## 2. Leurs jetons de contrôle — il y en a SIX

    <user is speaking>        <user backchannel>
    <user finish speaking>    <user is thinking>
    <user is interrupting>    <system backchannel>

Chevrons SIMPLES, pas `<|...|>`.

À noter : `<user is thinking>` est l'équivalent de notre REFLECHIT. Il a été
supprimé de notre prompt le 29/08 avec la justification « DuplexCascade n'a que
trois jetons » — c'était FAUX. Le gain mesuré était réel (5/9 → 6/9), la
justification ne l'était pas.

Nous n'avons pas d'équivalent de `<user backchannel>` ni de
`<system backchannel>` — le backchannel a été écarté tôt dans le projet.

## 3. Le silence

    <no voice>

Un seul marqueur, inséré quand le tampon se vide sans texte reconnu. Nous en
avons trois : `(silence)`, `(toujours rien, depuis N fois)` et `(ça parle, mais
je ne comprends pas)`. Les deux derniers sont des ajouts du 29/08, jamais
mesurés isolément.

## 4. La structure

Micro-tours utilisateur et système **entrelacés**, séparés par `<EOS>`
(= `<|im_end|>` dans le format Qwen). Longueur fixe de dix micro-tours système
dans les données d'entraînement.

**L'état du système n'apparaît nulle part dans l'entrée.** Le papier ne le
mentionne pas, et la structure entrelacée le rend implicite : le modèle voit sa
propre réponse précédente.

Nous avons trois marqueurs d'état (`[je parle]`, `[je viens de répondre]`,
`[je n'ai pas parlé]`). Les supprimer tous les trois coûte quatre questions sur
neuf (mesuré). Mais deux d'entre eux ne servent à rien :
- `[je viens de répondre]` servait à REFLECHIT, supprimé depuis ;
- `[je n'ai pas parlé]` est le cas par défaut.

Et le troisième est ambigu : dans un message de rôle `user`, « je » se lit
naturellement comme l'utilisateur, pas comme le robot.

## 5. L'horloge

Δt = 0,6 s en pratique. Le papier note un optimum d'EXACTITUDE à 1,2 s, avec un
compromis exactitude/latence entre les deux. Nous sommes à 1,2 s.

**Confirmé sur le PDF le 03/09 au soir** (§ 4.4 p. 4) : ils balaient
Δt ∈ {0,3 · 0,6 · 0,9 · 1,2 · 1,5 · 1,8 s}, la justesse monte jusqu'à 1,2 s puis
se dégrade, et ils retiennent 0,6 s comme « practical trade-off » avec la
latence. **Leur 0,858 est donc un chiffre à 0,6 s, pas leur meilleur.** À notre
Δt de 1,2 s, leur Figure 3 est vers ~0,93 (lu sur un graphique, ±0,005).
Détail : `PAPIER.md` § 5.3.

## Ce qui reste non documenté chez eux

- le format littéral d'un micro-tour (aucun exemple concret publié) ;
- s'il y a un séparateur entre le texte utilisateur et le jeton de contrôle ;
- comment le texte de la réponse suit le jeton `<user finish speaking>`.

## 6. À quoi ça ressemble concrètement

### Chez eux — RECONSTITUTION, pas une citation

Le format littéral n'est publié nulle part. Ce qui suit est déduit de trois
phrases du papier : les micro-tours utilisateur et système sont « interleaved
using a dedicated end-of-turn token `<EOS>` », le silence est représenté par
`<no voice>`, et le modèle est entraîné par prédiction du token suivant « on
system micro-turns only ».

    est-ce que tu peux<EOS><user is speaking><EOS>
    me dire<EOS><user is speaking><EOS>
    <no voice><EOS><user is speaking><EOS>
    quelle heure il est<EOS><user finish speaking>Il est bientôt minuit.<EOS>

Pas de rôles, pas de messages, pas de système : **un seul flux de tokens**. Le
modèle complète après chaque `<EOS>` utilisateur. L'entraînement ne porte que
sur les segments système — c'est-à-dire exactement ce qu'il doit produire.

### Chez nous — le vrai, tel qu'envoyé à l'API

    system     Quelqu'un te parle. […] Chaque ligne commence par ce que TU fais
               — [je parle], [je viens de répondre] ou [je n'ai pas parlé] […]

    user       [je n'ai pas parlé] est-ce que tu peux
    assistant  <|user is talking|>
    user       [je n'ai pas parlé] me dire
    assistant  <|user is talking|>
    user       [je n'ai pas parlé] (silence)
    assistant  <|user is talking|>
    user       [je n'ai pas parlé] quelle heure il est
    assistant  <|user finish talking|> Il est bientôt minuit.

### La différence de nature, qui explique presque tout le reste

Eux complètent **un flux**. Nous remplissons **une conversation à deux rôles**.

C'est de là que viennent nos difficultés propres, dont aucune n'existe chez eux :

- l'état du système doit être écrit quelque part, et le seul endroit disponible
  est le message `user` — où « je » se lit naturellement comme l'utilisateur ;
- il faut un prompt système, donc des instructions, donc des règles — et chaque
  règle ajoutée rend un jeton dominant (mesuré deux fois) ;
- les exemples few-shot occupent les mêmes rôles que la vraie conversation, donc
  rien ne les en sépare.

Une piste jamais testée en découle : utiliser l'API en mode **complétion** plutôt
qu'en mode chat, pour reproduire leur flux. Reste à vérifier que le modèle qu'on
utilise l'expose.

---

# CONSTATÉ DANS LEUR CODE (server.py), le 29/08/2026

Tout ce qui précède était déduit du papier. Ce qui suit est lu dans le code.
**Trois de mes affirmations précédentes étaient fausses.**

## Les chaînes exactes (server.py:45-50)

    <|no voice|>              <|user is thinking|>
    <|user is talking|>       <|user interruption|>
    <|user finish talking|>   <|user backchannel|>
                              <|assistant_backchannel|>

Avec des PIPES. Le papier écrit `<user is speaking>` — c'est une simplification
typographique. Les chaînes utilisées à notre itération 11 étaient donc les
bonnes ; ma correction disant le contraire était erronée.

## Le format exact (server.py:539-548)

    <|im_start|>user
    est-ce que tu peux<|im_end|>
    <|im_start|>assistant
    <|user is talking|><|im_end|>
    <|im_start|>user
    <|no voice|><|im_end|>
    <|im_start|>assistant

Le code est sans ambiguïté :

    history_ids.extend(self.header_user)
    if delta_text.strip():
        history_ids.extend(tokenizer.encode(delta_text))
    else:
        history_ids.extend(self.no_voice_ids)

Le message utilisateur contient **le delta, ou `<|no voice|>`**. Rien d'autre.

## Ce que ça corrige

1. **Ils utilisent bien un format à rôles** (ChatML de Qwen), pas un flux brut.
   Ma « différence de nature entre un flux et un dialogue » était fausse : leur
   structure est exactement la nôtre.
2. **Aucun prompt système** — confirmé par absence dans le code, plus seulement
   déduit du papier.
3. **Aucun marqueur d'état du système** — confirmé par le code.

## Ce que ça établit, et qui est le résultat le plus solide de la session

Leur format exact, appliqué à un modèle non entraîné, a été mesuré chez nous :
c'est l'itération 10, et elle donne **3/9 contre 7/9**.

Autrement dit, la sobriété de leur format n'est pas une qualité transposable :
elle est le PRODUIT du fine-tuning. Ce qu'ils obtiennent par l'entraînement,
nous devons l'écrire — marqueurs d'état, prompt système, exemples. Non par
maladresse, mais parce que c'est le seul canal qui nous reste.
