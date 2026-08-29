#!/usr/bin/env python3
"""Adaptateur pour `eval_user_interruption.py`, sans clé OpenAI.

Leur script exige un client OpenAI en argument, mais ne s'en sert QUE pour une
note de qualité produite par GPT-4o (ligne 127). Les deux métriques qui nous
concernent — le taux de prise de parole après interruption (TOR) et la latence
— sont purement calculatoires.

Or le `PROTOCOLE.md` dit explicitement qu'on n'évalue pas la pertinence des
réponses : « la bêtise des réponses tient à la taille du modèle, ce n'est pas
le sujet ». Payer un appel GPT-4o par échantillon pour une note qu'on ne
regardera pas serait absurde.

On passe donc un client factice qui renvoie une note nulle, et on ne rapporte
que TOR et latence. `Average rating` est délibérément absent de la sortie : un
zéro publié serait pris pour un résultat.

    python bench/eval_interrupt.py --root_dir CORPUS
"""
import argparse, io, os, re, sys
from contextlib import redirect_stdout

EVAL = os.path.expanduser("~/_/fdbench/v1_v1.5/evaluation")


class ClientFactice:
    """Répond ce que leur code attend, sans réseau. La note vaut 0 et n'est
    jamais rapportée — elle ne doit pas pouvoir être confondue avec une mesure."""

    class _Completions:
        @staticmethod
        def create(*a, **kw):
            class M:
                content = '{"rating": 0, "reason": "non évalué (pas de clé OpenAI)"}'
            class C:
                message = M()
            class R:
                choices = [C()]
            return R()

    class _Chat:
        completions = None

    def __init__(self):
        self.chat = self._Chat()
        self.chat.completions = self._Completions()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root_dir", required=True)
    a = ap.parse_args()

    sys.path.insert(0, EVAL)
    import eval_user_interruption as m

    tampon = io.StringIO()
    with redirect_stdout(tampon):
        m.eval_user_interruption(a.root_dir, ClientFactice())
    sortie = tampon.getvalue()

    print("---------------------------------------------------")
    print("[Result]")
    for cle in ("Average take turn", "Average latency"):
        found = re.search(rf"{re.escape(cle)}:\s*([0-9.eE+-]+)", sortie)
        if found:
            print(f"{cle}:  {found.group(1)}")
    print("  (note GPT-4o non calculée : hors périmètre du protocole)")
    print("---------------------------------------------------")


if __name__ == "__main__":
    main()
