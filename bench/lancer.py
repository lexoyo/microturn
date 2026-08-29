#!/usr/bin/env python3
"""Fait tourner microturn sur tout un corpus Full-Duplex-Bench.

Chaque dossier d'échantillon contient un `input.wav` ; on y écrit un
`output.wav` de la même durée, prêt pour l'alignement puis l'évaluation.

Le corpus est en anglais : `--langue en` bascule le prompt, les jetons, la
langue de whisper ET la voix piper. Sans porte par défaut — le corpus est un
fichier propre, il n'y a ni écho ni bruit de pièce à filtrer, et la porte ne
ferait qu'ajouter du bruit de mesure.

    python bench/lancer.py --corpus DOSSIER [--porte 0] [--modele ...]
"""
import argparse, os, subprocess, sys, time, wave
from glob import glob

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def duree(chemin):
    """Durée en secondes, quel que soit le format.

    Une partie des corpus est en float32 (`pcm_f32le`), que le module `wave` de
    la bibliothèque standard refuse. Le pipeline lui-même s'en moque — il passe
    par ffmpeg — mais l'outillage du banc doit accepter ce que le banc contient.
    """
    try:
        with wave.open(chemin, "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of",
                            "default=nw=1:nk=1", chemin],
                           capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            return 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--langue", default="en")
    ap.add_argument("--porte", default="0")
    ap.add_argument("--modele", default=None)
    ap.add_argument("--sortie", default="output.wav")
    ap.add_argument("--refaire", action="store_true",
                    help="retraiter les échantillons déjà rendus")
    ap.add_argument("--echantillon", type=int, default=0, metavar="N",
                    help="ne traiter que N échantillons, choisis de façon "
                         "DÉTERMINISTE (un sur k, après tri par nom). Le même "
                         "sous-ensemble d'une itération à l'autre : sans ça on "
                         "comparerait deux corpus différents et l'écart ne "
                         "voudrait rien dire.")
    a = ap.parse_args()

    entrees = sorted(glob(os.path.join(a.corpus, "*", "input.wav")))
    if not entrees:
        raise SystemExit(f"aucun input.wav sous {a.corpus}/*/")
    if a.echantillon and a.echantillon < len(entrees):
        pas = len(entrees) / a.echantillon
        entrees = [entrees[int(i * pas)] for i in range(a.echantillon)]

    # Les rendus qui ne font PAS partie du sous-ensemble courant sont effacés.
    # L'évaluateur note tout dossier contenant un output.json : un fichier laissé
    # par une itération précédente serait noté avec les nouveaux, sans que rien
    # ne le signale. Une mesure fausse et silencieuse est pire qu'une erreur.
    gardes = {os.path.dirname(e) for e in entrees}
    efface = 0
    for vieux in glob(os.path.join(a.corpus, "*", a.sortie)):
        if os.path.dirname(vieux) not in gardes:
            os.remove(vieux)
            js = vieux.rsplit(".", 1)[0] + ".json"
            if os.path.exists(js):
                os.remove(js)
            efface += 1
    if efface:
        print(f"{efface} rendu(s) hors sous-ensemble effacé(s)")

    total = sum(duree(e) for e in entrees)
    print(f"{len(entrees)} échantillons, {total/60:.1f} min d'audio")
    print("le pipeline lit en temps réel : compter au moins autant\n")

    t0 = time.time()
    faits = sautes = 0
    for i, entree in enumerate(entrees, 1):
        sortie = os.path.join(os.path.dirname(entree), a.sortie)
        if os.path.exists(sortie) and not a.refaire:
            sautes += 1
            continue
        cmd = [sys.executable, os.path.join(ICI, "pipeline.py"), entree,
               "--langue", a.langue, "--porte", a.porte, "--rendu", sortie]
        if a.modele:
            cmd += ["--modele", a.modele]
        r = subprocess.run(cmd, cwd=ICI, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        etat = "ok" if r.returncode == 0 else f"ÉCHEC {r.returncode}"
        faits += r.returncode == 0
        ecoule = time.time() - t0
        reste = ecoule / max(1, i - sautes) * (len(entrees) - i)
        print(f"  [{i:4}/{len(entrees)}] {etat:9} "
              f"{os.path.basename(os.path.dirname(entree))[:40]:42} "
              f"reste ~{reste/60:.0f} min", flush=True)

    print(f"\n{faits} rendus, {sautes} déjà présents, "
          f"{(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
