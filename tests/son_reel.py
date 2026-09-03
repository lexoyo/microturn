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
# attentes. C'était le même travers que l'ancien `ATTAQUE_S`, calibré sur la
# mauvaise machine ; le rapport de puissance y est désormais un réglage nommé
# (`MICROTURN_TTS_RTF`), pas une constante muette.
LENT = float(os.environ.get("MICROTURN_TEST_LENT", "1"))

# Phrases de longueurs étagées, pour confronter l'estimation par caractères aux
# WAV réellement produits. Tolérance : la synthèse de piper est bruitée
# (noise_scale 0,667), la même phrase varie de ±0,16 s d'une fois sur l'autre.
ETALON = [
    "Oui, je t'écoute.",
    "D'accord, je m'en occupe tout de suite.",
    "La lumière du salon est maintenant allumée, comme tu me l'as demandé.",
    "Alors, si j'ai bien compris ta question, tu voudrais savoir combien de "
    "temps il reste avant que le train parte de la gare.",
]


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
        phrase = "Bonjour, ceci est un test un peu plus long."
        attendu = tts.Silencieux(voice=sp.voice).duree(phrase)
        vus = profil(sp, phrase)
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


def test_duree_parole_colle_au_wav():
    """L'estimation par caractères doit rester proche du WAV réellement produit.

    C'est le garde-fou de `PAROLE_PAR_VOIX` : une constante de temps sans sa
    mesure redevient fausse à la première voix, au premier `length_scale` ou au
    premier changement de moteur. Ici la mesure est rejouable en une seconde.

    On compare des durées de PAROLE (l'en-tête du WAV), jamais des durées de
    SYNTHÈSE — celles-là dépendent de la machine et n'ont rien à faire dans un
    seuil de test.
    """
    import wave
    sp = tts.Speaker()
    try:
        time.sleep(2.0 * LENT)
        pires = []
        for phrase in ETALON:
            chemin = sp._synthetiser(phrase)
            assert chemin, f"piper n'a rien produit pour : {phrase[:30]}"
            with wave.open(chemin) as w:
                reel = w.getnframes() / w.getframerate()
            os.unlink(chemin)
            estime = tts.duree_parole(phrase, sp.voice)
            ecart = estime - reel
            pires.append((abs(ecart), phrase, reel, estime))
            # 0,6 s ou 15 % : au-delà, la table de débits ne décrit plus la voix.
            assert abs(ecart) <= max(0.6, 0.15 * reel), (
                f"estimation à {ecart:+.2f}s du WAV ({estime:.2f} vs "
                f"{reel:.2f}) pour {len(phrase)} caractères — "
                f"`tts.PAROLE_PAR_VOIX` est à remesurer")
        pire = max(pires)
        print(f"  durée estimée ≈ durée du WAV (pire écart {pire[0]:.2f}s)  OK")
    finally:
        sp.close()


if __name__ == "__main__":
    if not os.path.exists(tts.PIPER):
        print("  piper absent — test ignoré")
        sys.exit(0)
    test_duree_parole_colle_au_wav()
    test_speaking_suit_la_parole()
    test_stop_libere_vraiment()
    test_deux_phrases_ne_se_chevauchent_pas()
