# -*- coding: utf-8 -*-
"""Adapter le prompt à une transcription sans ponctuation (sherpa)."""


def dire_majuscules(t):
    """Le modèle voit du texte NU là où ses exemples sont ponctués."""
    return t.replace(
        '"<|no voice|>" signifie qu\'on n\'a rien entendu de l\'utilisateur',
        'Le texte que tu reçois est en majuscules et sans ponctuation : c\'est \\\n'
        'la reconnaissance vocale qui est ainsi, pas l\'utilisateur qui crie.\n\n'
        '"<|no voice|>" signifie qu\'on n\'a rien entendu de l\'utilisateur')


def exemples_nus(t):
    """Les exemples eux-mêmes en majuscules, comme ce qu'il recevra vraiment."""
    import re
    def maj(m):
        return 'entree = "' + m.group(1).upper() + '"'
    # ne pas toucher aux marqueurs <|...|>
    def rempl(m):
        e = m.group(1)
        if e.startswith("<|"):
            return m.group(0)
        return 'entree = "' + "".join(
            c.upper() for c in e if c not in "?!.,'").replace("  ", " ") + '"'
    return re.sub(r'entree = "([^"]*)"', rempl, t)


VARIANTES = [
    ("S1 · dire que le texte est en majuscules sans ponctuation", dire_majuscules),
    ("S2 · exemples eux-mêmes en majuscules sans ponctuation", exemples_nus),
]
