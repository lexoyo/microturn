#!/usr/bin/env python3
"""Trace de session de microturn — pour rejouer et comprendre après coup.

Sans `--trace`, ce module n'est même pas importé par la boucle : rien n'est
ouvert, rien n'est sérialisé, aucun thread ne tourne. C'est la condition pour
qu'on puisse le laisser dans le code sans peser sur la cible.

Avec, on écrit trois fichiers dans DOSSIER/<horodatage>/ :
    entree.wav     le flux micro COMPLET (avant la porte de volume), 16 kHz mono
                   S16 — rejouable tel quel par `pipeline.py .../entree.wav`
    session.jsonl  un événement par ligne, horodaté depuis le début de session
    meta.json      configuration, durée, résumé chiffré

Tout passe par UNE queue et UN thread d'écriture. Les appelants — thread audio,
boucle d'état, thread décideur — ne font qu'un `put_nowait` : ils ne touchent
jamais au disque et ne sérialisent rien, donc un `write` lent ne peut pas les
retenir. C'est la règle qui tient tout le projet : personne ne bloque sur de
l'I/O, sinon le tube audio (65536 octets, 2,048 s) déborde et ALSA perd du son.

La queue est bornée à 1024 entrées (~4 Mo dans le pire cas, ~2 min d'audio) :
si le disque décroche, on perd des événements — comptés dans meta.json — plutôt
que de faire gonfler la RAM d'une machine qui n'a que 905 Mio.
"""
import json, os, queue, threading, time, wave
import audio

TAILLE_QUEUE = 1024


class Journal:
    def __init__(self, dossier, meta=None):
        self.dir = os.path.join(dossier, time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        self.t0 = time.time()
        self.meta = dict(meta or {})
        self.meta["date"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.perdus = 0
        self.res = {"decisions": {},
                    "blocs_transmis": 0, "blocs_jetes": 0, "_lat": []}
        self.q = queue.Queue(maxsize=TAILLE_QUEUE)
        self._meta_sur_disque()          # écrit dès le départ : une session tuée
        self.th = threading.Thread(target=self._boucle, daemon=True)  # au -9 garde
        self.th.start()                  # quand même sa configuration

    # ---------- côté appelants : jamais plus qu'un put ----------
    def ev(self, type, **champs):
        """Range un événement. La sérialisation JSON se fait dans l'autre thread."""
        rec = {"t": round(time.time() - self.t0, 3), "type": type}
        rec.update(champs)
        try:
            self.q.put_nowait(("ev", rec))
        except queue.Full:
            self.perdus += 1

    def pcm(self, data):
        """Range un bloc audio brut pour entree.wav."""
        try:
            self.q.put_nowait(("pcm", data))
        except queue.Full:
            self.perdus += 1

    # ---------- thread d'écriture ----------
    def _boucle(self):
        wav = wave.open(os.path.join(self.dir, "entree.wav"), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(audio.RATE)
        f = open(os.path.join(self.dir, "session.jsonl"), "w", encoding="utf-8")
        try:
            while True:
                genre, charge = self.q.get()
                if genre == "fin":
                    break
                if genre == "pcm":
                    wav.writeframes(charge)
                    continue
                self._compter(charge)
                f.write(json.dumps(charge, ensure_ascii=False) + "\n")
                if self.q.empty():
                    f.flush()    # trace lisible en direct (`tail -f`) sans payer
        finally:                 # un flush par ligne quand ça afflue
            f.close()
            wav.close()

    def _compter(self, rec):
        """Le résumé se calcule ici, dans le seul thread qui touche `res`."""
        t = rec["type"]
        if t == "decision":
            d = self.res["decisions"]
            d[rec["action"]] = d.get(rec["action"], 0) + 1
        elif t == "llm_reponse":
            self.res["_lat"].append(rec["latence"])
        elif t == "niveaux":
            self.res["blocs_transmis"] += rec["transmis"]
            self.res["blocs_jetes"] += rec["jetes"]

    # ---------- fin de session ----------
    def close(self, **extra):
        try:
            self.q.put(("fin", None), timeout=2)
        except queue.Full:
            pass
        self.th.join(timeout=5)
        lat = self.res.pop("_lat")
        self.res["latence_reseau_moy"] = round(sum(lat) / len(lat), 3) if lat else None
        self.res["appels_reseau"] = len(lat)
        self.meta.update(extra)
        self.meta["duree_s"] = round(time.time() - self.t0, 2)
        self.meta["evenements_perdus"] = self.perdus
        self.meta["resume"] = self.res
        self._meta_sur_disque()
        return self.dir

    def _meta_sur_disque(self):
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)
            f.write("\n")
