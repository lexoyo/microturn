# -*- coding: utf-8 -*-
"""Candidats 55, 57, 58 — issus des sessions réelles. QC dans CANDIDATS.md."""


def v55_backchannel(t):
    """Offrir `<|assistant_backchannel|>` comme porte de sortie.

    Cinq réponses sur seize étaient des relances vides. Le modèle prend la
    parole parce qu'il n'a que deux options. Ce marqueur est fait pour ça, et
    n'est jamais sorti."""
    return t.replace(
        "  <|assistant_backchannel|> (tu as compris ce qu'il dit mais tu attends plus d'informations)",
        "  <|assistant_backchannel|> (tu as compris, mais tu n'as rien à dire encore : "
        "utilise-le plutôt que de relancer avec « je t'écoute » ou « vas-y »)")


def v57_identite(t):
    """Une identité, à nouveau. Rejeté en rejeu (−0,022), mais le tic
    « je suis un grand modèle linguistique » y est invisible."""
    return t.replace(
        "Tu es en train d'avoir une conversation avec un utilisateur.",
        "Tu es un compagnon de conversation. Tu n'es ni un assistant ni un "
        "moteur de recherche, et tu ne parles jamais de ce que tu es.\n\n"
        "Tu es en train d'avoir une conversation avec un utilisateur.")


def v58_tutoiement(t):
    """Il alterne « Je t'écoute » et « Je peux vous aider » — 6 sur 16."""
    return t.replace(
        '"r": "ta phrase, courte et parlée"',
        '"r": "ta phrase, courte et parlée, en tutoyant"')


VARIANTES = [
    ("55 · assistant_backchannel comme porte de sortie", v55_backchannel),
    ("57 · une identité, sans parler de ce qu'il est", v57_identite),
    ("58 · tutoiement imposé", v58_tutoiement),
]
