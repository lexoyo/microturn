#!/usr/bin/env python3
"""`Session._delta` — la fonction la plus subtile du projet, et la moins couverte.

Elle répond à « qu'est-ce qui vient d'être dit depuis le tick précédent ? ».
Deux pièges l'ont déjà cassée en session réelle, chacun documenté ci-dessous.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pipeline


class Faux(pipeline.Session):
    """Une `Session` réduite à ce que `_delta` lit : `vu` et `transcript`."""
    def __init__(self):
        self.silence = "<|no voice|>"
    def _muet_mesure(self):
        return False
    def _rien(self):
        return self.silence


CAS = [
    # (vu au tick precedent, transcript courant, delta attendu, pourquoi)
    ("", "SALUT",
     "SALUT", "premier mot du tour"),
    ("SALUT", "SALUT",
     "<|no voice|>", "rien de neuf : silence, pas une repetition"),
    ("EST CE QUE TU PEUX", "EST CE QUE TU PEUX ME DIRE",
     "ME DIRE", "cas nominal : des mots s'ajoutent, le reste est stable"),

    # Piege 1 — le dernier mot se COMPLETE. Un ASR en flux le fait sans arret,
    # et en francais les elisions le rendent permanent. Avant le 03/09,
    # l'ancrage ratait et le repli rendait ZERO : le systeme devenait sourd
    # pour le reste du tour (quarante secondes mesurees en session).
    ("SALUT TU M'", "SALUT TU M'ENTENDS",
     "M'ENTENDS", "le dernier mot vu s'est complete"),
    ("BONJOUR JE VOU", "BONJOUR JE VOUDRAIS SAVOIR",
     "VOUDRAIS SAVOIR", "complete ET suivi de nouveaux mots"),
    ("JE VAIS AU", "JE VAIS AUX TOILETTES",
     "AUX TOILETTES", "complete en changeant d'orthographe"),

    # Piege 3 — un mot se REPETE. L'ancrage cherche en partant de la fin
    # s'accrochait a la mauvaise occurrence et rendait zero.
    ("correspondance ou", "correspondance oui ou",
     "oui", "le mot d'ancrage se repete plus loin"),
    ("oui oui", "oui oui oui",
     "oui", "repetition pure"),
    ("je veux je", "je veux je veux",
     "veux", "groupe repete"),
    ("de sept heures p", "de sept heures pour p",
     "pour", "insertion avant un mot identique"),
    ("peux me dire s y l", "peux me dire si le train",
     "si le train", "plusieurs mots partiels recolles"),
    ("je peux venir", "je ne peux pas venir",
     "ne pas", "insertions au milieu"),

    # Piege 5 — tout le texte neuf arrive AVANT l'ancre. Ecarter les
    # insertions en tete par leur POSITION rendait zero ici, c'est-a-dire le
    # mode sourd qui a coute quarante secondes de conversation. C'est le filtre
    # d'artefacts qui distingue une hallucination de la parole, pas la place.
    ("OUI", "JE NE SAIS PAS OUI",
     "JE NE SAIS PAS", "parole neuve devant une ancre d'un mot"),
    ("LA", "JE SUIS LA",
     "JE SUIS", "l'ancre est le dernier mot de la phrase"),
    ("NON", "MAIS NON",
     "MAIS", "un seul mot insere en tete"),

    # Piege 4 — whisper hallucine un generique EN TETE (« Sous-titrage… »).
    # Ce n'est pas de la parole neuve : ne rien rendre.
    ("merci beaucoup", "sous-titrage merci beaucoup",
     "<|no voice|>", "hallucination de prefixe"),

    # Piege 2 — l'ASR se CORRIGE en amont. Un ancrage par le prefixe tombe a
    # zero et renvoie toute la phrase comme si elle venait d'etre dite : le
    # modele la lit comme un enonce neuf et complet, et repond au milieu.
    ("BONJOUR JE VOUDRAIS", "BONSOIR JE VOUDRAIS SAVOIR",
     "SAVOIR", "un mot du debut a ete corrige"),

    # Invariants a epingler : le comportement est bon, rien ne le protegeait.
    # Celui du milieu a casse deux fois — renvoyer tout le tour comme neuf fait
    # repondre le modele au milieu du propos.
    ("BONJOUR JE VOUDRAIS SAVOIR", "BONJOUR JE VOUDRAIS",
     "<|no voice|>", "l'ASR a RACCOURCI sa transcription"),
    ("BONJOUR", "",
     "<|no voice|>", "transcript vide"),
    ("   ", "BONJOUR",
     "BONJOUR", "vu ne contient que du blanc"),
]


def main():
    s, echecs = Faux(), 0
    for vu, courant, attendu, pourquoi in CAS:
        s.vu, s.transcript = vu, courant
        obtenu = s._delta()
        if obtenu != attendu:
            echecs += 1
            print(f"  ECHEC  {pourquoi}")
            print(f"         vu={vu!r} courant={courant!r}")
            print(f"         attendu {attendu!r}, obtenu {obtenu!r}")
    print(f"  delta : {len(CAS) - echecs}/{len(CAS)}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
