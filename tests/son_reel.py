#!/usr/bin/env python3
"""Exerce `Speaker` POUR DE VRAI — la classe que le rejeu n'exécute jamais.

Le rejeu et les tests de fumée tournent en `--muet` : ils utilisent
`tts.Silencieux`, qui simule la parole. `Speaker`, le vrai locuteur, n'est donc
couvert par aucune de nos mesures — et c'est justement la classe la plus
modifiée du 29/08 (piper résident, préchauffage, découpage, fermeture d'aplay).

Un bug y est passé jusqu'en session réelle : `aplay` ne se terminait plus, donc
`speaking()` répondait vrai pour le reste de la session, et le système se croyait
en train de parler en permanence. Neuf « coupures » sur treize prises de parole,
dont huit après la fin de la phrase.

Ce que ce fichier vérifie ne se voit dans AUCUNE autre mesure.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tts  # noqa: E402


# Le Pi synthétise trois fois plus lentement que ce PC : un test calibré ici
# échoue là-bas sans qu'il y ait de bug. `MICROTURN_TEST_LENT` allonge les
# attentes. C'est le même travers que `ATTAQUE_S`, calibré sur la mauvaise
# machine et faux d'un facteur trois sur la cible.
LENT = float(os.environ.get("MICROTURN_TEST_LENT", "1"))


def profil(sp, phrase, duree=7.0 * LENT, pas=0.4):
    """Suit `speaking()` dans le temps pendant qu'une phrase est prononcée."""
    sp.say(phrase)
    vus = []
    for _ in range(int(duree / pas)):
        time.sleep(pas)
        vus.append(sp.speaking())
    return vus


def test_speaking_suit_la_parole():
    """Vrai pendant la phrase, faux après. Les deux erreurs sont graves :
    toujours vrai, le système croit parler pour toujours ; toujours faux, il ne
    se protège plus de son propre écho."""
    sp = tts.Speaker()
    try:
        time.sleep(2.0 * LENT)                # laisser le préchauffage finir
        attendu = tts.Silencieux.ATTAQUE_S + 42 / tts.Silencieux.DEBIT_CAR_S
        vus = profil(sp, "Bonjour, ceci est un test un peu plus long.")
        parle = 0.4 * sum(vus)
        assert any(vus), "speaking() n'a JAMAIS été vrai — le son ne part pas"
        assert not vus[-1], (
            "speaking() est encore vrai à la fin — `aplay` ne se termine pas, "
            "le système se croira en train de parler pour toujours")
        assert parle >= 0.5 * attendu, (
            f"parole trop courte : {parle:.1f}s pour ~{attendu:.1f}s attendues")
        print(f"  speaking() suit la parole ({parle:.1f}s / ~{attendu:.1f}s)   OK")
    finally:
        sp.stop()


def test_stop_libere_vraiment():
    """Couper doit rendre `speaking()` faux tout de suite."""
    sp = tts.Speaker()
    try:
        time.sleep(2.0 * LENT)
        sp.say("Une phrase assez longue pour être coupée en plein milieu.")
        time.sleep(2.0 * LENT)
        sp.stop()
        time.sleep(0.3)
        assert not sp.speaking(), "speaking() encore vrai après stop()"
        print("  stop() rend speaking() faux                     OK")
    finally:
        sp.stop()


def test_deux_phrases_ne_se_chevauchent_pas():
    """Le PCM d'une phrase coupée ne doit pas sortir au début de la suivante."""
    sp = tts.Speaker()
    try:
        time.sleep(2.0 * LENT)
        sp.say("Première phrase, longue, qui va être interrompue avant la fin.")
        time.sleep(1.5 * LENT)
        sp.say("Deuxième.")
        time.sleep(4.0 * LENT)
        assert not sp.speaking(), "la seconde phrase ne s'est jamais terminée"
        print("  pas de chevauchement entre deux phrases         OK")
    finally:
        sp.stop()


if __name__ == "__main__":
    if not os.path.exists(tts.PIPER):
        print("  piper absent — test ignoré")
        sys.exit(0)
    test_speaking_suit_la_parole()
    test_stop_libere_vraiment()
    test_deux_phrases_ne_se_chevauchent_pas()
