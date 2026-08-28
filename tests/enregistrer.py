#!/usr/bin/env python3
"""Enregistrement guidé des cas de test de microturn — avec la vraie voix d'Alex.

Une voix de synthèse est trop propre : whisper la transcrit parfaitement, alors
qu'il peine sur de la parole réelle. Régler le système sur de la synthèse, ce
serait l'optimiser pour un cas qui n'arrive jamais. Donc on enregistre pour de
vrai, avec des consignes précises pour que chaque prise teste UNE chose.

    python tests/enregistrer.py          # déroule toutes les prises
    python tests/enregistrer.py 04       # refait seulement celle-là
    python tests/enregistrer.py --liste

Chaque prise produit `tests/prises/<id>.wav` (16 kHz mono) et une entrée dans
`tests/verite.json` décrivant ce qu'un système correct devrait faire.
"""
import json, os, subprocess, sys, time

ICI = os.path.dirname(os.path.abspath(__file__))
PRISES = os.path.join(ICI, "prises")
MIC = os.environ.get("MICROTURN_MIC", "default")

CAS = [
    {"id": "01-pause-milieu", "texte_impose": 'je voudrais [pause] allumer la lumière du salon', "duree": 9, "dimension": "pauses",
     "consigne": "Dis « je voudrais », TAIS-TOI 2 secondes pleines, puis enchaîne "
                 "« allumer la lumière du salon ». Puis silence jusqu'à la fin.",
     "attendu": {"reponses": 1, "aucune_reponse_pendant_la_pause": True},
     "teste": "une pause au milieu d'une phrase ne doit pas déclencher de réponse"},

    {"id": "02-phrase-suspendue", "texte_impose": 'est-ce que tu peux', "duree": 8, "dimension": "pauses",
     "consigne": "Dis seulement « est-ce que tu peux » et NE FINIS PAS. "
                 "Silence jusqu'à la fin.",
     "attendu": {"reponses": 0},
     "teste": "phrase inachevée : il doit attendre indéfiniment, pas meubler"},

    {"id": "03-monologue", "duree": 30, "dimension": "backchannel",
     "consigne": "Raconte ta journée pendant 25 secondes, sans jamais poser de "
                 "question. Parle normalement, avec tes hésitations.",
     "attendu": {"reponses_max": 2, "hmm_attendu": True},
     "teste": "long monologue : quelques signes d'écoute, pas de prise de parole"},

    {"id": "04-question-nette", "duree": 8, "dimension": "tours",
     "consigne": "Attends 1 seconde, pose UNE question courte et nette, "
                 "puis tais-toi. Par exemple « tu peux éteindre la lumière ».",
     "attendu": {"reponses": 1, "latence_max_s": 2.5},
     "teste": "le cas nominal — c'est lui qui donne la latence de référence"},

    {"id": "05-enchainement", "duree": 10, "dimension": "tours",
     "consigne": "Dis deux phrases COLLÉES, sans respirer entre les deux, en "
                 "changeant de sujet au milieu. Finis par une question.",
     "attendu": {"reponses": 1, "repond_a_la_fin": True},
     "teste": "il doit répondre une fois, à la fin, pas se jeter au milieu"},

    {"id": "06-question-courte", "texte_impose": 'quelle heure il est', "duree": 6, "dimension": "tours",
     "consigne": "Dis juste « quelle heure il est », rien d'autre.",
     "attendu": {"reponses": 1},
     "teste": "trois mots : vérifie que la porte locale ne l'étouffe pas"},

    {"id": "07-bruit-seul", "texte_impose": '', "duree": 12, "dimension": "faux positifs",
     "consigne": "Ne dis RIEN. Fais du bruit : bouge ta chaise, tape sur la table, "
                 "laisse la pièce vivre. Musique de fond si tu veux.",
     "attendu": {"reponses": 0},
     "teste": "du bruit sans parole ne doit jamais déclencher quoi que ce soit"},

    {"id": "08-loin", "duree": 10, "dimension": "conditions",
     "consigne": "Éloigne-toi à 3 mètres du micro et pose une question nette.",
     "attendu": {"reponses": 1},
     "teste": "la distance dégrade la transcription — jusqu'où ça tient"},
]

# Ces deux-là ne s'enregistrent pas seuls : ils exigent le système EN MARCHE,
# puisqu'il faut réagir à ce qu'il dit. Ils se font avec `pipeline.py --trace`.
EN_DIRECT = [
    {"id": "09-interruption", "dimension": "interruption",
     "consigne": "Pose une question qui appelle une longue réponse, puis COUPE-LE "
                 "en plein milieu : « non attends, stop ».",
     "attendu": {"coupure_max_ms": 300},
     "teste": "il doit se taire immédiatement quand tu reprends la parole"},
    {"id": "10-echo", "dimension": "écho",
     "consigne": "SANS CASQUE, pose une question et laisse-le répondre en entier "
                 "sans rien dire. Regarde s'il se répond à lui-même.",
     "attendu": {"auto_reponses": 0},
     "teste": "la porte de volume doit rejeter sa propre voix"},
]


def enregistre(cas):
    os.makedirs(PRISES, exist_ok=True)
    chemin = os.path.join(PRISES, cas["id"] + ".wav")
    print(f"\n\033[1m{cas['id']}\033[0m  ({cas['duree']} s) — {cas['teste']}")
    print(f"\n  \033[1;33m{cas['consigne']}\033[0m\n")
    input("  Entrée quand tu es prêt... ")
    for n in (3, 2, 1):
        print(f"  {n}...", end="", flush=True); time.sleep(1)
    print("  \033[1;32mPARLE\033[0m")
    subprocess.run(["arecord", "-D", MIC, "-f", "S16_LE", "-r", "16000", "-c", "1",
                    "-d", str(cas["duree"]), "-q", chemin])
    print(f"  → {os.path.relpath(chemin, os.path.dirname(ICI))}")
    # On ne redemande le texte que s'il était libre : le retaper alors qu'on vient
    # de le dicter n'apprend rien et alourdit la prise.
    if "texte_impose" in cas:
        dit = cas["texte_impose"]
    else:
        dit = input("  En une ligne, ce que tu as dit : ").strip()
    return {**{k: v for k, v in cas.items() if k != "consigne"},
            "wav": os.path.relpath(chemin, os.path.dirname(ICI)),
            "transcription_reelle": dit}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--liste" in sys.argv:
        for c in CAS + EN_DIRECT:
            print(f"{c['id']:20s} {c.get('duree', '—'):>3}  {c['teste']}")
        return
    choisis = [c for c in CAS if not args or any(a in c["id"] for a in args)]
    if not choisis:
        raise SystemExit(f"aucun cas ne correspond à {args}")

    chemin_v = os.path.join(ICI, "verite.json")
    verite = json.load(open(chemin_v)) if os.path.exists(chemin_v) else []
    for cas in choisis:
        entree = enregistre(cas)
        verite = [v for v in verite if v["id"] != cas["id"]] + [entree]
        with open(chemin_v, "w") as f:
            json.dump(sorted(verite, key=lambda v: v["id"]), f,
                      ensure_ascii=False, indent=2)
    print(f"\n{len(verite)} prise(s) dans verite.json")
    print("\nLes cas 09 et 10 se font EN DIRECT, avec le système qui tourne :")
    for c in EN_DIRECT:
        print(f"  {c['id']:20s} {c['consigne']}")


if __name__ == "__main__":
    main()
