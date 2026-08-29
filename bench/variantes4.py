# -*- coding: utf-8 -*-
"""Ne pas prendre la parole quand la phrase n'est pas finie.

Défaut visé : 5 pauses ratées sur 22 (TOR pauses 0,310, notre pire dimension).
Alex : « il ne faut pas qu'il prenne la parole si je n'ai pas fini ma phrase ».

QC avant ajout (règle du 29/08) :
1. Ce que ça montre : si le modèle peut être rendu plus prudent sans devenir
   muet. Jamais testé sur CE prompt — les cinq règles essayées ce matin
   portaient sur autre chose (identité, transcription, fragments).
2. Seuil : bruit ±0,017. Passer de 5/22 à 2/22 vaut +0,068 : mesurable.
3. Ce que ça rend faux ailleurs : le risque est de casser les fins de tour
   (6/8 aujourd'hui). Un système muet obtient 0 pause ratée ET 0 fin détectée,
   pour un score de 0,5. On lit donc le COUPLE, jamais l'agrégat seul.
4. Non mesuré : rien.

Les trois variantes sont exclusives : une règle, une donnée, une définition.
"""

FIN_EXEMPLES = '''[[exemples]]
entree = "me dire quelle heure il est"'''


def p1_regle(t):
    """Une règle de prudence, appliquée au doute et pas à une définition."""
    return t.replace(
        'Cas particulier : avec <|user finish talking|>',
        'Dans le doute, sa phrase n\'est pas finie.\n\n'
        'Cas particulier : avec <|user finish talking|>', 1)


def p2_exemple(t):
    """Une donnée : un fragment, puis un silence, qui reste `is talking`.

    Les gains mesurés sont tous venus d'exemples, jamais de règles — sauf celui
    qui décrivait l'entrée. C'est la variante sur laquelle je parierais."""
    ajout = '''[[exemples]]
entree = "et est-ce que tu pourrais aussi"
sortie = \'\'\'{"m": "<|user is talking|>"}\'\'\'
[[exemples]]
entree = "<|no voice|>"
sortie = \'\'\'{"m": "<|user is talking|>"}\'\'\'
'''
    return t.replace(FIN_EXEMPLES, ajout + FIN_EXEMPLES, 1)


def p3_definition(t):
    """Resserrer ce que « finie » veut dire, au lieu d'ajouter une règle."""
    return t.replace(
        "  <|user finish talking|>   (sa phrase est finie)",
        "  <|user finish talking|>   (sa phrase est finie : une question ou une "
        "demande complète, à laquelle on peut répondre)")


VARIANTES = [
    ("P1 · une règle : dans le doute, il n'a pas fini", p1_regle),
    ("P2 · une donnée : un fragment puis un silence", p2_exemple),
    ("P3 · resserrer la définition de « finie »", p3_definition),
]
