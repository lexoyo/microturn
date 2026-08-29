#!/usr/bin/env python3
"""Évalue une session de microturn selon les métriques de Full-Duplex-Bench.

Full-Duplex-Bench (arXiv 2503.04721) évalue **quand** un système parle, pas ce
qu'il dit. On reprend ses métriques telles quelles : ça rend nos chiffres
comparables à Moshi, Gemini Live ou DuplexCascade, ce qui vaut mieux qu'un
tableau maison.

    python tests/evaluer.py sessions/20260829-011754
    python tests/evaluer.py sessions/A sessions/B      # comparer deux sessions

Trois dimensions sont mesurées, chacune avec son taux de prise de parole (TOR,
*takeover rate*), dont la lecture s'inverse selon le cas :

  PAUSES          la personne s'interrompt au milieu de sa phrase.
                  Le système doit se taire → TOR bas = bon.
                  C'est la métrique reine : DuplexCascade est à 0,058.

  FINS DE TOUR    elle a réellement fini et attend.
                  Le système doit répondre → TOR haut = bon.
                  Et on mesure la latence, mais SEULEMENT quand il a répondu —
                  sinon on moyennerait avec des silences.

  INTERRUPTIONS   elle reprend la parole pendant qu'il parle.
                  Il doit se taire → taux de coupure haut = bon.

La justesse moyenne agrège le tout, comme leur *Averaged Turn-Taking Accuracy*.

## D'où viennent les frontières

Full-Duplex-Bench annote un corpus à la main. Ici on les dérive de l'audio, avec
les seuils de leur article : un silence de **0,4 à 1,0 s** entre deux passages
parlés est une PAUSE — c'est la zone qu'ils désignent comme le cas difficile,
celle où un détecteur de parole ne peut pas trancher. Au-delà de **1,5 s**, c'est
une FIN DE TOUR. Entre les deux, c'est ambigu et on l'écarte plutôt que de
compter faux.

Ces frontières sont écrites dans `frontieres.json` à côté de la session. Corrige
ce fichier à la main si le découpage automatique se trompe : c'est lui qui fait
foi, et c'est le seul travail manuel du dispositif.
"""
import json, os, sys, wave
import numpy as np

# Seuils tirés de Full-Duplex-Bench : leur sous-ensemble « pause handling »
# sélectionne les pauses internes de 0,4 à 1,0 s, et la littérature qu'ils citent
# donne un « standard maximum » d'environ 1 s de silence toléré en conversation.
PAUSE_MIN, PAUSE_MAX = 0.4, 1.0
FIN_MIN = 1.5                 # au-delà, la personne a rendu la parole
BLOC = 0.05                   # résolution de l'analyse d'énergie
PARLE_MIN = 0.3               # un passage parlé plus court est du bruit


def zones_parlees(wav):
    """Découpe l'audio en passages parlés, par énergie. Rend [(début, fin)]."""
    with wave.open(wav) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    n = int(rate * BLOC)
    blocs = [x[i:i + n] for i in range(0, len(x) - n, n)]
    rms = np.array([float(np.sqrt(np.mean(b * b))) for b in blocs])
    # seuil relatif : le plancher de la pièce plus une marge. Un seuil absolu
    # dépendrait du micro et du gain, qui changent d'une session à l'autre.
    plancher = np.percentile(rms, 20)
    seuil = max(plancher * 3, np.percentile(rms, 60) * 0.25, 50.0)
    actif = rms > seuil
    zones, debut = [], None
    for i, a in enumerate(actif):
        if a and debut is None:
            debut = i * BLOC
        elif not a and debut is not None:
            if i * BLOC - debut >= PARLE_MIN:
                zones.append((debut, i * BLOC))
            debut = None
    if debut is not None:
        zones.append((debut, len(actif) * BLOC))
    return zones


def frontieres(zones):
    """Classe les silences entre passages parlés : pause, fin de tour, ou ambigu."""
    out = []
    for (_, fin), (suivant, _) in zip(zones, zones[1:]):
        duree = suivant - fin
        if PAUSE_MIN <= duree <= PAUSE_MAX:
            genre = "pause"
        elif duree >= FIN_MIN:
            genre = "fin"
        else:
            genre = "ambigu"
        out.append({"t": round(fin, 2), "duree": round(duree, 2), "genre": genre})
    if zones:                      # la fin de l'enregistrement clôt le dernier tour
        out.append({"t": round(zones[-1][1], 2), "duree": None, "genre": "fin"})
    return out


def charger(session):
    ev = []
    with open(os.path.join(session, "session.jsonl")) as f:
        for ligne in f:
            try:
                ev.append(json.loads(ligne))
            except ValueError:
                pass
    meta = json.load(open(os.path.join(session, "meta.json")))
    return ev, meta


def evaluer(session):
    ev, meta = charger(session)
    wav = os.path.join(session, "entree.wav")

    chemin_f = os.path.join(session, "frontieres.json")
    if os.path.exists(chemin_f):
        fr = json.load(open(chemin_f))          # annotation corrigée à la main
    else:
        fr = frontieres(zones_parlees(wav))
        json.dump(fr, open(chemin_f, "w"), indent=1)

    paroles = [e["t"] for e in ev if e["type"] == "parole_debut"]
    coupures = [e["t"] for e in ev if e["type"] == "coupure"]
    decisions = [e for e in ev if e["type"] == "decision"]

    def parle_apres(t, fenetre):
        """Le système a-t-il pris la parole dans la fenêtre suivant t ?"""
        return next((p for p in paroles if t <= p <= t + fenetre), None)

    pauses = [f for f in fr if f["genre"] == "pause"]
    fins = [f for f in fr if f["genre"] == "fin"]

    # PAUSES — il ne doit PAS parler. Fenêtre = la durée de la pause elle-même.
    pause_pris = sum(1 for f in pauses if parle_apres(f["t"], f["duree"] or PAUSE_MAX))
    pause_tor = pause_pris / len(pauses) if pauses else None

    # FINS — il DOIT parler. Fenêtre de 4 s : au-delà, la personne a renoncé.
    lat = []
    fin_pris = 0
    for f in fins:
        p = parle_apres(f["t"], 4.0)
        if p is not None:
            fin_pris += 1
            lat.append(p - f["t"])
    fin_tor = fin_pris / len(fins) if fins else None
    latence = float(np.median(lat)) if lat else None

    # INTERRUPTIONS — mesurées seulement s'il y en a eu
    inter_tor = len(coupures) / len(paroles) if paroles else None

    # Justesse moyenne, à la manière de leur Averaged Turn-Taking Accuracy
    parts = [x for x in ((1 - pause_tor) if pause_tor is not None else None,
                         fin_tor) if x is not None]
    justesse = sum(parts) / len(parts) if parts else None

    # Nos propres pannes, que Full-Duplex-Bench ne mesure pas mais qui nous ont
    # déjà fait prendre du bruit pour un progrès.
    par_action = {}
    for d in decisions:
        par_action[d.get("action", "?")] = par_action.get(d.get("action", "?"), 0) + 1
    total = sum(par_action.values()) or 1

    return {
        "session": os.path.basename(session.rstrip("/")),
        "modele": meta.get("llm"), "code": meta.get("version_code", {}).get("git"),
        "duree_s": meta.get("duree_s"),
        "pauses": len(pauses), "fins": len(fins),
        "pause_TOR": pause_tor, "fin_TOR": fin_tor,
        "latence_med_s": latence, "interruption_TOR": inter_tor,
        "justesse": justesse,
        "hors_format": par_action.get("format", 0) / total,
        "done_sans_texte": par_action.get("parler_sans_texte", 0) / total,
        "erreurs": par_action.get("error", 0) / total,
        "decisions": total, "prises_de_parole": len(paroles),
    }


def _f(x, n=3):
    return "—" if x is None else f"{x:.{n}f}"


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    res = [evaluer(s.rstrip("/")) for s in sys.argv[1:]]

    lignes = [
        ("session", "session", 0), ("modèle", "modele", 0), ("durée (s)", "duree_s", 1),
        ("", "", -1),
        ("pauses détectées", "pauses", 0), ("fins de tour détectées", "fins", 0),
        ("", "", -1),
        ("TOR pauses ↓ (coupe pendant une pause)", "pause_TOR", 3),
        ("TOR fins ↑ (répond quand on lui parle)", "fin_TOR", 3),
        ("latence médiane (s) ↓", "latence_med_s", 2),
        ("TOR interruption ↑", "interruption_TOR", 3),
        ("**justesse moyenne ↑**", "justesse", 3),
        ("", "", -1),
        ("sorties hors format ↓", "hors_format", 3),
        ("DONE sans réponse ↓", "done_sans_texte", 3),
        ("erreurs réseau ↓", "erreurs", 3),
        ("décisions", "decisions", 0), ("prises de parole", "prises_de_parole", 0),
    ]
    larg = max(len(l[0]) for l in lignes) + 2
    for libelle, cle, dec in lignes:
        if dec < 0:
            print()
            continue
        vals = []
        for r in res:
            v = r[cle]
            vals.append(str(v) if isinstance(v, str) or dec == 0 and v is not None
                        else _f(v, dec) if isinstance(v, float) else str(v))
        print(f"  {libelle:<{larg}}" + "".join(f"{v:>22}" for v in vals))
    print(f"\n  Métriques de Full-Duplex-Bench (arXiv 2503.04721). Repères : "
          f"DuplexCascade obtient 0,058 de TOR sur les pauses et 0,858 de justesse,\n"
          f"  pour 1,72 s de latence ; Gemini Live 0,255 et 0,778 pour 1,30 s. "
          f"Un humain enchaîne en 0,2 à 0,25 s.")
    print(f"  Frontières dérivées de l'audio (pause 0,4–1,0 s, fin ≥ 1,5 s) et "
          f"écrites dans frontieres.json — corrige-les à la main si besoin.")


if __name__ == "__main__":
    main()
