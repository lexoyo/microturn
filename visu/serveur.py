#!/usr/bin/env python3
"""Sert le visualiseur de traces et expose le `session.jsonl` en flux.

CONSOMMATEUR EN LECTURE SEULE. Rien ici n'est importé par le pipeline, et rien
ici n'ouvre un fichier en écriture : on peut lancer ce serveur sur la trace
d'une session EN COURS sans risquer de la corrompre, et la CLI reste l'outil de
débogage de référence. C'est la contrainte qui a dicté toute la forme du
dossier `visu/` : zéro ligne ajoutée au chemin critique de l'audio.

Le suivi en direct se fait à l'OCTET, pas à la ligne : `journal.py` ne flushe
que quand sa queue se vide, donc la dernière ligne du fichier est régulièrement
incomplète. On ne rend que les lignes terminées par \n et on renvoie l'offset
juste après la dernière — le client redemande à partir de là. Un `tail -f` naïf
sur les lignes rendrait un JSON tronqué toutes les quelques secondes.

    python3 visu/serveur.py <dossier-de-trace> [--port 8731]
"""
import argparse, http.server, json, os, sys, urllib.parse

RACINE = os.path.dirname(os.path.abspath(__file__))
LOCALES = os.path.join(os.path.dirname(RACINE), "locales")


def resoudre(srv):
    """`--trace sessions/` crée `sessions/<horodatage>/` : on accepte les deux.

    Le résultat est VERROUILLÉ dès qu'un session.jsonl existe. Rechercher à
    chaque requête laisserait le suivi basculer sur une session démarrée entre
    temps, avec un offset en octets hérité de l'autre fichier — on relirait
    n'importe où. On tolère seulement l'attente initiale : lancer le
    visualiseur AVANT le pipeline, et le voir s'accrocher quand il démarre."""
    if srv.resolu:
        return srv.resolu
    dossier = srv.trace
    if os.path.exists(os.path.join(dossier, "session.jsonl")):
        srv.resolu = dossier
        return dossier
    jsonl = lambda d: os.path.join(d, "session.jsonl")
    sous = [os.path.join(dossier, d) for d in os.listdir(dossier)]
    sous = [d for d in sous if os.path.exists(jsonl(d))]
    if not sous:
        return dossier          # session à peine lancée : le fichier arrivera
    # mtime du FICHIER, pas du dossier : c'est lui qu'on suit, et c'est lui
    # que le pipeline touche à chaque flush.
    srv.resolu = max(sous, key=lambda d: os.path.getmtime(jsonl(d)))
    return srv.resolu


def jetons(langue):
    """Les marqueurs viennent de `locales/<langue>.toml`, JAMAIS d'une copie.

    Les noms exacts ont bougé le 04/09/2026 (alignement sur le papier § 3.2) :
    une liste recopiée ici aurait menti dès ce jour-là. Le fallback ne lit que
    les deux sections utiles, au cas où le TOML deviendrait illisible."""
    chemin = os.path.join(LOCALES, "%s.toml" % os.path.basename(langue or "fr"))
    if not os.path.exists(chemin):
        return {}
    try:
        import tomllib
        with open(chemin, "rb") as f:
            d = tomllib.load(f)
        return {"jetons": d.get("jetons", {}), "divers": d.get("divers", {}),
                "backchannels": d.get("backchannels", {})}
    except Exception:
        import re
        out, sect = {"jetons": {}, "divers": {}, "backchannels": {}}, None
        for ligne in open(chemin, encoding="utf-8"):
            if ligne.startswith("["):
                sect = ligne.strip().strip("[]")
            elif sect in out:
                m = re.match(r'\s*(\w+)\s*=\s*"([^"]*)"', ligne)
                if m:
                    out[sect][m.group(1)] = m.group(2)
        return out


class Poste(http.server.BaseHTTPRequestHandler):
    def _envoi(self, corps, mime="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(RACINE, "index.html"), "rb") as f:
                return self._envoi(f.read(), "text/html")
        if u.path == "/locale":
            return self._envoi(json.dumps(jetons(q.get("langue", ["fr"])[0])).encode())
        if u.path == "/evenements":
            dos = resoudre(self.server)
            jsonl, lignes = os.path.join(dos, "session.jsonl"), []
            depuis = int(q.get("depuis", ["0"])[0])
            if os.path.exists(jsonl):
                with open(jsonl, "rb") as f:
                    f.seek(depuis)
                    brut = f.read()
                coupe = brut.rfind(b"\n") + 1      # 0 si aucune ligne complète
                depuis += coupe
                lignes = brut[:coupe].decode("utf-8", "replace").splitlines()
            meta = None                            # écrit seulement en FIN de
            mj = os.path.join(dos, "meta.json")    # session : son absence est
            if os.path.exists(mj):                 # le cas NORMAL en direct
                try:
                    meta = json.load(open(mj, encoding="utf-8"))
                except Exception:
                    pass                           # écriture en cours, on repassera
            return self._envoi(json.dumps({"depuis": depuis, "lignes": lignes,
                                           "meta": meta, "dossier": dos}).encode())
        self.send_error(404)

    def log_message(self, *a):
        pass                                       # un log par ligne polluerait


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", help="dossier contenant session.jsonl")
    p.add_argument("--port", type=int, default=8731)
    a = p.parse_args()
    if not os.path.isdir(a.trace):
        sys.exit("dossier introuvable : %s" % a.trace)
    # 127.0.0.1 et pas 0.0.0.0 : une trace contient le prompt entier et tout ce
    # qui a été dit au micro. Ça ne sort pas de la machine.
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Poste)
    srv.trace, srv.resolu = os.path.abspath(a.trace), None
    print("visu  http://127.0.0.1:%d/   trace : %s" % (a.port, resoudre(srv)))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
