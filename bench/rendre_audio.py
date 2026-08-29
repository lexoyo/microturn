#!/usr/bin/env python3
"""Fabrique l'audio de ce qu'on VIENT de mesurer, pour l'écouter.

Le rejeu est muet : il rejoue la transcription et n'appelle pas la synthèse. On
ne peut donc pas entendre ce que le système ferait — seulement lire des chiffres.
Ce script comble le trou : il reprend la voix d'origine d'Alex, synthétise les
réponses décidées par le rejeu, et les place à l'instant EXACT où elles ont été
décidées (plus la latence de l'appel, qui est un vrai délai vécu).

    python bench/rendre_audio.py /tmp/rejeu_<session> sessions/<session> \
        --sortie /tmp/ecoute.wav

Une réponse posée sur la voix d'Alex qui parle encore n'est pas un défaut du
rendu : c'est le système qui a coupé la parole, et c'est ce qu'on veut entendre.
"""
import argparse, glob, json, os, subprocess, sys, tempfile

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ICI)
import tts  # noqa: E402


def reponses(trace):
    """(instant en secondes depuis le début, phrase) pour chaque prise de parole."""
    fichiers = sorted(glob.glob(os.path.join(trace, "*", "session.jsonl"))) or \
               sorted(glob.glob(os.path.join(trace, "session.jsonl")))
    out, t0 = [], None
    for f in fichiers:
        for ligne in open(f, encoding="utf-8"):
            try:
                ev = json.loads(ligne)
            except ValueError:
                continue
            if t0 is None and ev.get("t") is not None:
                t0 = ev["t"]
            if ev.get("type") != "llm_reponse" or not ev.get("brut"):
                continue
            try:
                o = json.loads(ev["brut"])
            except ValueError:
                continue
            if o.get("r"):
                # `t` est l'instant de la RÉPONSE du modèle : la phrase sort à ce
                # moment-là, pas au moment de la question.
                out.append((ev["t"] - t0, o["r"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("session", help="dossier de la session d'origine (entree.wav)")
    ap.add_argument("--sortie", default="/tmp/ecoute.wav")
    a = ap.parse_args()

    voix = os.path.join(a.session, "entree.wav")
    if not os.path.exists(voix):
        sys.exit(f"pas de {voix}")
    rep = reponses(a.trace)
    if not rep:
        sys.exit("aucune réponse dans la trace")

    tmp = tempfile.mkdtemp(prefix="ecoute_")
    pistes, filtres = [voix], []
    for i, (t, phrase) in enumerate(rep):
        w = os.path.join(tmp, f"r{i}.wav")
        subprocess.run([tts.PIPER, "-m", tts.VOICE, "-f", w],
                       input=phrase.encode("utf-8"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True)
        pistes.append(w)
        # `adelay` est en millisecondes et veut une valeur par canal.
        filtres.append(f"[{len(pistes)-1}:a]adelay={int(t*1000)}|{int(t*1000)},"
                       f"volume=1.6[v{i}]")
        print(f"  {t:6.1f}s  {phrase}")

    entrees = []
    for p in pistes:
        entrees += ["-i", p]
    mix = "".join(f"[v{i}]" for i in range(len(rep)))
    filtre = ";".join(filtres) + \
        f";[0:a]{mix}amix=inputs={len(rep)+1}:duration=first:normalize=0[out]"
    subprocess.run(["ffmpeg", "-y", *entrees, "-filter_complex", filtre,
                    "-map", "[out]", a.sortie],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"\n{len(rep)} réponses mixées sur la voix d'origine → {a.sortie}")


if __name__ == "__main__":
    main()
