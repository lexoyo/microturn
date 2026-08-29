#!/usr/bin/env python3
"""Enchaîne des variantes de prompt et mesure chacune, sans surveillance.

Chaque variante ne diffère de la base que par UNE chose — c'est la règle de la
boucle, et la seule façon d'attribuer un écart. Le catalogue est sauvegardé,
patché, mesuré, restauré ; une variante qui plante ne contamine pas la suivante.

    python bench/serie.py variantes.py
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, time

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Chaque série travaille sur SA copie du catalogue : deux séries peuvent alors
# tourner en parallèle sans que l'une mesure le prompt de l'autre.
BAC = tempfile.mkdtemp(prefix="locales_")
shutil.copytree(os.path.join(ICI, "locales"), BAC, dirs_exist_ok=True)
TOML = os.path.join(BAC, "fr.toml")
SESSIONS = ["sessions/20260829-032332", "sessions/20260829-073852"]


def mesure(note):
    env = dict(os.environ, MICROTURN_LOCALES=BAC)
    r = subprocess.run(
        [sys.executable, os.path.join(ICI, "bench", "sessions.py"),
         "--sessions", *SESSIONS, "--note", note],
        cwd=ICI, capture_output=True, text=True, env=env)
    for l in r.stdout.splitlines():
        if "JUSTESSE" in l or "TOR " in l:
            yield l.strip()


def main():
    spec = importlib.util.spec_from_file_location("variantes", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    sauve = TOML + ".sauve"
    shutil.copy2(TOML, sauve)   # dans le bac, pas dans le dépôt
    resultats = []
    try:
        for nom, patch in mod.VARIANTES:
            shutil.copy2(sauve, TOML)
            texte = open(TOML, encoding="utf-8").read()
            try:
                nouveau = patch(texte)
            except Exception as e:
                print(f"✗ {nom} : patch impossible ({e})", flush=True)
                continue
            if nouveau == texte:
                print(f"✗ {nom} : le patch n'a rien changé", flush=True)
                continue
            open(TOML, "w", encoding="utf-8").write(nouveau)
            t0 = time.time()
            lignes = list(mesure(nom))
            just = next((l for l in lignes if "JUSTESSE" in l), "—")
            print(f"● {nom}\n    {just}   [{time.time()-t0:.0f}s]", flush=True)
            resultats.append((nom, just))
    finally:
        shutil.copy2(sauve, TOML)
        os.remove(sauve)
    print("\n=== récapitulatif ===")
    for nom, just in resultats:
        print(f"  {just:<60} {nom}")


if __name__ == "__main__":
    main()
