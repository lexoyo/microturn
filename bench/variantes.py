# -*- coding: utf-8 -*-
"""Une variante = la base + UN changement. Rien d'autre."""

EX_NOVOICE = '''[[exemples]]
entree = "<|no voice|>"
sortie = \'\'\'{"m": "<|user is talking|>"}\'\'\''''

EX_THINKING = '''[[exemples]]
entree = "<|no voice|>"
sortie = \'\'\'{"m": "<|user is thinking|>"}\'\'\''''


def novoice_thinking(t):
    """n°22 — le silence qui SUIT une réponse enseigne aujourd'hui « il parle »."""
    # le second <|no voice|> du jeu d'exemples est celui qui suit la réponse
    i = t.find(EX_NOVOICE)
    j = t.find(EX_NOVOICE, i + 1)
    return t[:j] + EX_THINKING + t[j + len(EX_NOVOICE):]


def identite(t):
    """n°36 — il répondait « je suis un grand modèle linguistique »."""
    return t.replace(
        "Tu es en train d'avoir une conversation avec un utilisateur.",
        "Tu es Marcel, un compagnon de conversation. Tu parles avec un utilisateur.")


def transcription_fausse(t):
    """n°37 — la phrase avait disparu à la réécriture du prompt."""
    return t.replace(
        '"<|no voice|>" signifie qu\'on n\'a rien entendu de l\'utilisateur',
        'Ce que tu lis vient d\'une reconnaissance vocale : c\'est souvent \\\n'
        'approximatif, parfois faux.\n\n'
        '"<|no voice|>" signifie qu\'on n\'a rien entendu de l\'utilisateur')


def pas_de_meta(t):
    """n°38 — cinq réponses sur treize étaient « je ne comprends pas »."""
    return t.replace(
        '{"m": "<|user finish talking|>", "r": "ta phrase, courte et parlée"}\n"""',
        '{"m": "<|user finish talking|>", "r": "ta phrase, courte et parlée"}\n\n'
        'Ne commente jamais ce que tu as mal entendu : réponds au sens, ou \\\n'
        'passe.\n"""')


def fragments_normaux(t):
    """n°39 — la plupart des tours sont des bouts de phrase."""
    return t.replace(
        "Voici une liste de marqueurs",
        "Tu reçois des bouts de phrase : c'est normal, la plupart n'appellent \\\npas de réponse.\n\nVoici une liste de marqueurs")


def sans_parentheses(t):
    """n°44 — tester la nudité maximale, comme leur design."""
    for a, b in (("(sa phrase n'est pas finie)", "sa phrase n'est pas finie"),
                 ("(sa phrase est finie)", "sa phrase est finie"),
                 ("(il se tait, mais il réfléchit)", "il se tait, mais il réfléchit"),
                 ("(il reprend la parole alors que tu es en train de lui répondre)",
                  "il reprend la parole alors que tu es en train de lui répondre"),
                 ("(un signal d'écoute, pas une prise de parole)",
                  "un signal d'écoute, pas une prise de parole"),
                 ("(tu as compris ce qu'il dit mais tu attends plus d'informations)",
                  "tu as compris ce qu'il dit mais tu attends plus d'informations")):
        t = t.replace(a, b)
    return t


def ratio_exemples(t):
    """n°23 — 5 `is talking` pour 2 `finish talking`, le réel est à 171/13."""
    bloc = '''[[exemples]]
entree = "me dire la"
sortie = \'\'\'{"m": "<|user is talking|>"}\'\'\'
'''
    return t.replace(bloc, "")


VARIANTES = [
    ("22 · <|no voice|> après réponse → is thinking", novoice_thinking),
    ("36 · une identité (Marcel)", identite),
    ("37 · dire que la transcription est approximative", transcription_fausse),
    ("38 · interdire de commenter ce qu'il a mal entendu", pas_de_meta),
    ("39 · dire que les fragments sont normaux", fragments_normaux),
    ("44 · retirer les parenthèses explicatives", sans_parentheses),
    ("23 · un exemple `is talking` de moins", ratio_exemples),
]
