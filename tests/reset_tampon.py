#!/usr/bin/env python3
"""Le tampon STT doit se vider quand un tour se ferme, PORTE FERMÉE COMPRISE.

Régression du 29/08/2026 : le vidage était consommé dans le thread lecteur,
après le `continue` qui saute les blocs jetés par la porte. Or la porte jette
pendant qu'on parle — donc justement au moment où `reset()` est appelé. La
phrase à laquelle on venait de répondre restait dans le tampon, whisper la
re-transcrivait, on y répondait encore. Boucle infinie de sept réponses
identiques en trente secondes, qui survivait au micro débranché.

Le test rejoue exactement cette séquence : de la parole, un reset, puis une
porte fermée en continu. Aucun partial ne doit reparaître.
"""
import os, queue, sys, threading, time, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stt

ECHANTILLON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "samples", "01-normal.wav")


class CapPorteFermee:
    """Sert 3 s de parole, puis ne rend plus que des blocs jetés par la porte."""
    trace = None

    def __init__(self, pcm, bloc=4000):
        self.blocs = [pcm[i:i + bloc * 2] for i in range(0, len(pcm), bloc * 2)]
        self.i = 0

    def lire(self):
        time.sleep(0.05)                      # cadence approximative du micro
        if self.i < len(self.blocs):
            self.i += 1
            return self.blocs[self.i - 1]
        return b""                            # porte fermée, indéfiniment


def main():
    with wave.open(os.path.normpath(ECHANTILLON), "rb") as w:
        pcm = w.readframes(3 * w.getframerate())

    eng = stt.Whisper()
    cap = CapPorteFermee(pcm)
    q, stop = queue.Queue(), threading.Event()
    threading.Thread(target=eng.run, args=(cap, q, stop), daemon=True).start()

    # 1. attendre un premier partial : le moteur fonctionne
    debut = time.time()
    premier = None
    while time.time() - debut < 20:
        try:
            kind, txt, _ = q.get(timeout=0.2)
        except queue.Empty:
            continue
        if kind == "partial":
            premier = txt
            break
    if premier is None:
        print("ÉCHEC  aucun partial : le moteur n'a rien transcrit")
        return 1
    print(f"  partial obtenu : {premier[:60]!r}")

    # 2. fermer le tour, comme le fait _dire()
    eng.reset()

    # 3. plus rien ne doit sortir : le tampon est vide et la porte jette tout
    fin = time.time() + 6
    fuite = []
    while time.time() < fin:
        try:
            kind, txt, _ = q.get(timeout=0.2)
        except queue.Empty:
            continue
        if kind == "partial":
            fuite.append(txt)
    stop.set()

    if fuite:
        print(f"ÉCHEC  {len(fuite)} partial(s) après reset, tampon jamais vidé :")
        for t in fuite[:3]:
            print(f"         {t[:70]!r}")
        return 1
    print("  aucun partial après reset — tampon bien vidé")
    return 0


def test_exemple_silence_apres_reponse():
    """Le marqueur de silence qui SUIT une réponse doit enseigner `is thinking`.

    Ce gain (+0,025) a été perdu une fois : une série de variantes a restauré un
    catalogue pris avant son application, et la base mesurée ensuite était
    amputée sans que rien ne le signale. Un test le dit maintenant.

    Deux réparations le 04/09/2026 — il ne testait plus rien depuis un moment :

      - il cherchait `<|no voice|>`, l'ANCIEN marqueur à barres verticales. Le
        commit d721c84 l'a renommé `<no voice>` : la liste était vide, et un
        `assert` sur une liste vide dans une fonction jamais appelée ne dit
        rien à personne. Le marqueur est maintenant LU dans le catalogue ;
      - il était défini APRÈS `sys.exit(main())`, donc mort. Il est appelé
        avant, et pour les deux langues et les deux jeux d'exemples.

    Le compte exact d'exemples de silence n'est plus vérifié — il a changé le
    04/09 avec les exemples de backchannel, et ce n'était pas ce qui comptait.
    La règle testée est celle qui porte le gain : après une réponse, un silence
    est une réflexion, jamais « ça parle encore »."""
    import llm
    vus = 0
    for langue in llm.langues():
        cat = llm.catalogue(langue)
        silence = cat["divers"]["silence"]
        pense, fini = cat["jetons"]["reflechit"], cat["jetons"]["parler"]
        for moteur in (None, "sherpa"):
            ex = llm.exemples(langue, moteur)
            for i, (entree, _) in enumerate(ex):
                if i == 0 or entree != silence or fini not in ex[i - 1][1]:
                    continue
                assert pense in ex[i][1], (
                    f"{langue}/{moteur} : le silence qui suit une réponse doit "
                    f"être `{pense}`, pas : {ex[i][1]}")
                vus += 1
    assert vus, "aucun exemple « silence après réponse » dans aucun catalogue"
    print(f"  silence après réponse ({vus} exemples)       OK")


if __name__ == "__main__":
    test_exemple_silence_apres_reponse()
    sys.exit(main())
