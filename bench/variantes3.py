# -*- coding: utf-8 -*-
"""La phrase sur la casse, appliquée À TORT — avec un moteur qui ponctue.

QC avant ajout (règle du 29/08) :
1. Ce que ça montre : si une affirmation FAUSSE sur l'entrée coûte autant
   qu'une vraie rapporte. On sait que la phrase vaut +0,063 quand elle est
   juste ; on ne sait pas ce qu'elle coûte quand elle ment.
2. Seuil : bruit ±0,017, effet attendu du même ordre que le gain (0,06).
3. Ce que ça rend faux ailleurs : rien, c'est un test isolé.
4. Non mesuré ailleurs : rien.
"""


def casse_a_tort(t):
    return t.replace("{casse}",
                     "Le texte que tu reçois est en majuscules et sans "
                     "ponctuation : c'est la reconnaissance vocale qui est "
                     "ainsi, pas l'utilisateur qui crie.\n\n")


VARIANTES = [("W1 · la phrase sur la casse, avec whisper qui ponctue", casse_a_tort)]
