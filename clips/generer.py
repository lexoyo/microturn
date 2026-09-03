#!/usr/bin/env python3
"""Régénère les clips de `<system backchannel>`, un WAV par phrase et par langue.

    .venv/bin/python clips/generer.py            # toutes les langues
    .venv/bin/python clips/generer.py fr

Les phrases vivent dans les catalogues (`locales/<langue>.toml`, section
`[backchannels]`), pas ici : c'est de la langue, et la langue est au catalogue.
Ce script n'est que le moyen de les rendre audibles.

Pourquoi un fichier plutôt qu'un `say()` au moment voulu — c'est le seul point
qui compte : un signal d'écoute synthétisé à la volée arriverait après le moment
où il voulait dire quelque chose. Sur un Pi 3B, une passe de piper coûte de une
à trois secondes, le tick en dure 1,2. Les chercheurs font pareil (papier § 3.2).

La voix est celle du projet, celle du catalogue : `fr_FR-siwis-medium` et
`en_US-amy-medium`. Un backchannel dans une autre voix que la réponse s'entend
comme une deuxième personne dans la pièce.

Les WAV produits sont versionnés (quelques dizaines de kilo-octets en tout) —
c'est ce script qui fait qu'ils ne sont pas des binaires opaques.
"""
import os
import subprocess
import sys
import wave

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ICI))

import llm    # noqa: E402
import tts    # noqa: E402


def rogner(chemin, seuil=0.02, marge_s=0.02):
    """Ôte le silence de tête et de queue du WAV, en place.

    Le silence de TÊTE est le seul qui compte vraiment : piper en pose une
    fraction de seconde devant chaque phrase, et un signal d'écoute qui commence
    par un blanc arrive après le moment où il voulait dire quelque chose. La
    queue, elle, ne s'entend pas — on la coupe pour ne pas garder du vide dans
    le dépôt.

    Rend la nouvelle durée en secondes.
    """
    import numpy as np
    with wave.open(chemin) as w:
        params, brut = w.getparams(), w.readframes(w.getnframes())
    a = np.frombuffer(brut, dtype=np.int16)
    if len(a) == 0:
        return 0.0
    fort = np.nonzero(np.abs(a) > seuil * 32767)[0]
    if len(fort):
        marge = int(marge_s * params.framerate)
        a = a[max(0, fort[0] - marge):min(len(a), fort[-1] + marge)]
    with wave.open(chemin, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(a.tobytes())
    return len(a) / params.framerate


def generer(langue):
    cat = llm.catalogue(langue)
    phrases = cat.get("backchannels") or []
    if not phrases:
        print(f"{langue} : aucune phrase dans [backchannels], rien à faire")
        return 0
    voix = tts.voix_pour(cat["divers"].get("voix_piper"))
    if not os.path.exists(voix):
        raise SystemExit(f"voix piper absente : {voix} (cf. install.sh)")
    dossier = os.path.join(ICI, langue)
    os.makedirs(dossier, exist_ok=True)
    # Les anciens WAV sont effacés : sinon un clip retiré du catalogue
    # continuerait d'être tiré au hasard, sans plus figurer nulle part.
    for vieux in os.listdir(dossier):
        if vieux.endswith(".wav"):
            os.unlink(os.path.join(dossier, vieux))
    faits = 0
    for i, phrase in enumerate(phrases):
        # Numérotés, pas nommés d'après la phrase : le nom d'un fichier ne doit
        # pas dépendre d'une apostrophe ou d'un accent.
        cible = os.path.join(dossier, f"{i:02d}.wav")
        p = subprocess.run([tts.PIPER, "-m", voix, "-f", cible, "-q"],
                           input=(" ".join(phrase.split()) + "\n").encode(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode != 0 or not os.path.exists(cible):
            raise SystemExit(f"piper a échoué sur « {phrase} »")
        duree = rogner(cible)
        print(f"  {os.path.relpath(cible, os.path.dirname(ICI))}  "
              f"« {phrase} »  {duree:.2f} s  "
              f"{os.path.getsize(cible)/1024:.0f} Kio")
        faits += 1
    return faits


if __name__ == "__main__":
    langues = sys.argv[1:] or llm.langues()
    total = 0
    for lg in langues:
        print(f"{lg} :")
        total += generer(lg)
    print(f"{total} clip(s)")
