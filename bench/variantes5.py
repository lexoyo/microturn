# -*- coding: utf-8 -*-
"""Des réponses plus courtes — donc moins de temps d'antenne.

Mesuré sur la session : 68 caractères en moyenne, soit **4,8 s de parole** à
14 car/s, et 6,3 s au pire. Pendant ce temps l'utilisateur ne peut pas reprendre
la main sans couper. C'est de la latence perçue qui ne se voit dans aucune de nos
colonnes.

QC avant ajout :
1. Ce que ça montre : si la longueur des réponses se pilote par le prompt, et ce
   que ça coûte en justesse. Le prompt dit déjà « courte et parlée » — donc on
   teste si être PLUS précis change quelque chose, pas si l'idée est neuve.
2. Seuil : la longueur se mesure directement (caractères), pas besoin du bruit
   de justesse. Pour la justesse, ±0,017 comme toujours.
3. Ce que ça rend faux ailleurs : une réponse trop courte peut cesser de
   répondre à la question. À lire dans les fins de tour, pas seulement en
   caractères.
4. Non mesuré : rien.
"""


def r1_dix_mots(t):
    return t.replace('"r": "ta phrase, courte et parlée"',
                     '"r": "ta réponse, dix mots au plus"')


def r2_une_phrase(t):
    return t.replace('"r": "ta phrase, courte et parlée"',
                     '"r": "UNE phrase parlée, sans préambule ni relance"')


VARIANTES = [
    ("R1 · dix mots au plus", r1_dix_mots),
    ("R2 · une phrase, sans préambule ni relance", r2_une_phrase),
]
