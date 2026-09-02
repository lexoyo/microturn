#!/usr/bin/env python3
"""Enchaîne des variantes de prompt et mesure chacune, sans surveillance.

Chaque variante ne diffère de la base que par UNE chose — c'est la règle de la
boucle, et la seule façon d'attribuer un écart. Le catalogue est copié dans un
bac à sable, patché, mesuré ; le dépôt n'est jamais touché, donc deux séries
peuvent tourner en parallèle sans se disputer `locales/fr.toml`.

    MICROTURN_SESSIONS="sessions/xxx-sherpa" python bench/serie.py variantes.py
"""
import importlib.util, os, re, shutil, subprocess, sys, tempfile, time

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAC = tempfile.mkdtemp(prefix="locales_")
shutil.copytree(os.path.join(ICI, "locales"), BAC, dirs_exist_ok=True)
TOML = os.path.join(BAC, "fr.toml")
SESSIONS = os.environ.get(
    "MICROTURN_SESSIONS",
    "sessions/20260829-032332 sessions/20260829-073852").split()


def mesure(note):
    env = dict(os.environ, MICROTURN_LOCALES=BAC)
    r = subprocess.run(
        [sys.executable, os.path.join(ICI, "bench", "sessions.py"),
         "--sessions", *SESSIONS, "--note", note],
        cwd=ICI, capture_output=True, text=True, env=env)
    # Les DEUX dimensions, et le détail par session — pas seulement l'agrégat.
    # Un système muet et un système bavard rendent tous les deux 0,500 : la
    # justesse seule ne permet pas de les distinguer, et c'est exactement le
    # risque d'une variante qui touche à la prise de parole.
    for l in r.stdout.splitlines():
        if "JUSTESSE" in l or "TOR " in l or "  justesse " in l:
            yield l.strip()


def derniere_trace():
    import glob
    t = sorted(glob.glob("/tmp/rejeu_*/*/session.jsonl"), key=os.path.getmtime)
    return os.path.dirname(t[-1]) if t else None


def apres_mesure(nom):
    """Ce que la justesse ne voit pas : le prompt réel, et les travers de forme.

    Les variantes qui touchent à ce que le modèle DIT — une identité, un
    registre, une relance — ne déplacent aucun marqueur et rendent donc le même
    score au millième. Les juger sur la justesse revient à les déclarer nulles
    sans les avoir regardées."""
    tr = derniere_trace()
    if not tr:
        return
    slug = re.sub(r"[^a-z0-9]+", "-", nom.lower()).strip("-")[:60]
    dst = os.path.join(ICI, "bench", "prompts")
    os.makedirs(dst, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(ICI, "bench", "extraire_prompts.py"),
                    tr, "--combien", "1",
                    "--sortie", os.path.join(dst, f"{slug}.txt")],
                   cwd=ICI, capture_output=True, text=True)
    c = subprocess.run([sys.executable, os.path.join(ICI, "bench", "compter_travers.py"), tr],
                       cwd=ICI, capture_output=True, text=True)
    for l in c.stdout.splitlines():
        print("   " + l.strip(), flush=True)


def main():
    spec = importlib.util.spec_from_file_location("variantes", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    origine = open(TOML, encoding="utf-8").read()
    resultats = []
    for nom, patch in mod.VARIANTES:
        open(TOML, "w", encoding="utf-8").write(origine)
        try:
            nouveau = patch(origine)
        except Exception as e:
            print(f"✗ {nom} : patch impossible ({e})", flush=True)
            continue
        if nouveau == origine:
            print(f"✗ {nom} : le patch n'a rien changé", flush=True)
            continue
        # Le catalogue porte plusieurs prompts (`systeme`, `systeme_sherpa`).
        # Patcher celui que la session n'utilise PAS ne change rien au score, et
        # ne se voit qu'à des mesures identiques au millième — j'ai perdu trois
        # mesures là-dessus. On le dit tout de suite.
        for cle in ("systeme_sherpa",):
            a, b = origine.split(cle + ' = """'), nouveau.split(cle + ' = """')
            if len(a) > 1 and len(b) > 1 and a[1] == b[1]:
                print(f"   ⚠ `{cle}` inchangé — sans effet sur une session sherpa",
                      flush=True)
        open(TOML, "w", encoding="utf-8").write(nouveau)
        t0 = time.time()
        lignes = list(mesure(nom))
        print(f"● {nom}   [{time.time()-t0:.0f}s]", flush=True)
        for l in lignes:
            print(f"    {l}", flush=True)
        apres_mesure(nom)
        resultats.append((nom, next((l for l in lignes if "JUSTESSE" in l), "—")))

    print("\n=== récapitulatif ===")
    for nom, just in resultats:
        print(f"  {just:<58} {nom}")
    shutil.rmtree(BAC, ignore_errors=True)


if __name__ == "__main__":
    main()
