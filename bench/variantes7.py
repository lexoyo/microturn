# -*- coding: utf-8 -*-
"""Détection SEULE : le mélange détection + réponse aide-t-il la détection ?

Chez DuplexCascade, le fine-tuning apprend conjointement à détecter la fin de
tour et à produire la réponse. Ici, la transposition par prompting fait la même
chose en une requête : {"m": ...} à chaque tick, plus "r" sur
<|user finish talking|>. L'argument implicite est que préparer la réponse aide à
décider si le tour est fini. Non mesuré jusqu'ici.

⚠ Deux changements, pas un — d'où deux variantes. Retirer la CONSIGNE "r" ne
retire pas les réponses des EXEMPLES ; retirer les deux à la fois mélangerait
les causes, ce que la boucle interdit.

  A · consigne seule, exemples inchangés (les réponses restent sous les yeux)
  B · consigne + exemples sans réponse : détection vraiment pure

⚠ Le catalogue porte DEUX prompts (`systeme`, `systeme_sherpa`). Le paragraphe
patché est identique dans les deux, et `str.replace` les prend tous les deux —
c'est voulu, et `serie.py` le vérifie pour le seul qui compte ici (sherpa).

QC avant mesure (règle du 29/08/2026) :

1. **Ce que ça peut montrer que je ne sais pas déjà.** Si la détection tient
   toute seule, la moitié du prompt et des tokens de sortie disparaissent, et
   l'architecture peut se scinder (un petit modèle qui détecte, un gros qui
   répond). Si elle s'effondre, l'argument du papier est confirmé chez nous par
   la mesure et non par l'analogie. Les deux issues changent quelque chose.
2. **De combien doit bouger le score.** Bruit ±0,017. On conclut à partir de
   0,05 ; entre les deux, on ne conclut rien.
3. **Ce que ça rend faux ailleurs.** Le système ne produit plus de réponse : le
   pipeline tombe alors dans `parler_sans_texte`, ne prend jamais la parole et
   rend 0,500 — le score d'un système muet, qui ne mesure RIEN. C'est le piège
   du candidat 59, en pire, parce que 0,500 y est plausible. Le harnais est
   donc adapté (`MICROTURN_MARQUEUR_SEUL`, cf. pipeline.py) pour que le
   marqueur seul vaille prise de parole, avec un texte de remplissage de 55
   caractères — la médiane des réponses de la base, pour que la durée simulée
   de parole reste la même. L'historique, lui, est écrit SANS réponse.
4. **Ce sur quoi je me repose sans l'avoir mesuré.** Le schéma JSON continue
   d'autoriser "r" : rien n'empêche mécaniquement le modèle d'en produire
   malgré la consigne. À compter dans les traces avant d'interpréter — si "r"
   reste là, la variante n'est pas ce qu'elle prétend être.
"""

CONSIGNE = (
    'Cas particulier : avec <|user finish talking|>, et seulement là, ajoute une \\\n'
    "phrase qui sera transmise à l'utilisateur : \\\n"
    '{"m": "<|user finish talking|>", "r": "ta phrase, courte et parlée, en tutoyant"}'
)

DETECTION = (
    'Tu ne produis JAMAIS de phrase pour l\'utilisateur : ta sortie ne contient \\\n'
    'que le marqueur, y compris avec <|user finish talking|>. Une autre partie \\\n'
    'du système se charge de répondre.'
)

EX_TOUR = ('sortie = \'\'\'{"m": "<|user finish talking|>", '
           '"r": "La tour Eiffel mesure 320 mètres"}\'\'\'')
EX_HEURE = ('sortie = \'\'\'{"m": "<|user finish talking|>", '
            '"r": "Il est bientôt minuit."}\'\'\'')
EX_NU = 'sortie = \'\'\'{"m": "<|user finish talking|>"}\'\'\''


def a_consigne_seule(t):
    """La consigne "r" retirée, les exemples INCHANGÉS.

    Le modèle voit encore deux réponses complètes dans les exemples : si le
    bénéfice du mélange vient de ce que la réponse est *présente sous les
    yeux*, il est conservé ici et perdu en B."""
    assert t.count(CONSIGNE) == 2, t.count(CONSIGNE)   # systeme ET systeme_sherpa
    return t.replace(CONSIGNE, DETECTION)


def b_detection_pure(t):
    """Consigne retirée ET exemples sans réponse."""
    t = a_consigne_seule(t)
    assert t.count(EX_TOUR) == 1 and t.count(EX_HEURE) == 1
    return t.replace(EX_TOUR, EX_NU).replace(EX_HEURE, EX_NU)


VARIANTES = [
    ("A · consigne « marqueur seul », exemples inchangés", a_consigne_seule),
    ("B · consigne + exemples sans réponse (détection pure)", b_detection_pure),
]

# Les MÊMES deux patches, relancés avec MICROTURN_SANS_R=1, donnent les deux
# variantes qui comptent vraiment — celles où "r" est retiré du SCHÉMA, donc
# mécaniquement impossible à produire :
#
#   C  = a_consigne_seule + MICROTURN_SANS_R=1   (détection seule, mais les
#                                                 exemples montrent encore des
#                                                 réponses)
#   B' = b_detection_pure + MICROTURN_SANS_R=1   (détection pure, imposée)
#
# La commande complète, telle qu'elle a servi le 02/09/2026 :
#
#   MICROTURN_SANS_R=1 \
#   MICROTURN_SESSIONS="sessions/20260829-032332-sherpa sessions/20260829-073852-sherpa" \
#   MICROTURN_MARQUEUR_SEUL="(réponse simulée — banc de « détection seule », 55 car)" \
#   .venv/bin/python bench/serie.py bench/variantes7.py
