# -*- coding: utf-8 -*-
"""Chronologie provisoire, sans voix : chaque mot reçoit une durée estimée (débit d'Estelle, ≈ 2,9 mots/s, pauses
selon la ponctuation). Sert à régler les scènes et la mise en page AVANT de générer la voix (≈ 30 min de calcul) ;
« fabriquer.py voix » la remplace ensuite par la vraie chronologie.

    python3 -m rp.provisoire DOSSIER      -> DOSSIER/chrono.json (marqué "provisoire": true)"""
import json
import os
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "rp"

from vf import voix as V  # noqa: E402

CAR_PAR_S = 17.6              # calé sur la prise réelle de l’épisode 1 (89,8 s montées pour 252 mots)


def duree_mot(mot):
    from vf.nombres import parlable
    lu = parlable(re.sub(r"[«»]", "", mot))
    return max(0.14, len(re.sub(r"[^\w]", "", lu)) / CAR_PAR_S)


def chrono(texte, ids, respirations=None):
    narr = V.Narration(texte, ids=ids)
    W = narr.mots
    t = 0.0
    mots = []
    for i, w in enumerate(W):
        if w["pause_avant"]:
            t += w["pause_avant"]
        d = duree_mot(w["texte"])
        mots.append(dict(texte=w["texte"], bloc=w["bloc"], idx=w["idx"], s=round(t, 3), e=round(t + d, 3)))
        t += d
        fin_bloc = i + 1 < len(W) and W[i + 1]["bloc"] != w["bloc"]
        pause = V.pause_cible(w["texte"], fin_bloc, 0.0)
        if pause <= 0.121:                       # pas de ponctuation : simple enchaînement
            pause = 0.02
        if fin_bloc and respirations:
            pause = max(pause, float(respirations.get(ids[w["bloc"]], 0.0)))
        t += pause
    blocs = {}
    for w in mots:
        k = ids[w["bloc"]]
        s, e = blocs.get(k, (w["s"], w["e"]))
        blocs[k] = (min(s, w["s"]), max(e, w["e"]))
    reperes = {}
    for w in mots:
        key = ids[w["bloc"]] + ":" + V.nettoyer_mot(w["texte"]).replace("'", "")
        reperes.setdefault(key, []).append(round(w["s"], 3))
    duree = mots[-1]["e"] + 0.35
    return dict(duree=round(duree, 3), duree_prise=round(duree, 3), taux_alignement=1.0, respirations=[], tempo=1.0,
                coupes=[], blocs=blocs, reperes=reperes, sous_titres=V.sous_titres(mots),
                mots=[dict(t=w["texte"], b=ids[w["bloc"]], s=w["s"], e=w["e"]) for w in mots], provisoire=True)


def main(d):
    c = json.load(open(os.path.join(d, "episode.json"), encoding="utf-8"))
    texte = open(os.path.join(d, c["narration"]), encoding="utf-8").read()
    ch = chrono(texte, c["blocs"], (c.get("voix") or {}).get("respirations"))
    json.dump(ch, open(os.path.join(d, "chrono.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(dict(duree=ch["duree"], blocs={k: [round(a, 2), round(b, 2)] for k, (a, b) in ch["blocs"].items()},
                          provisoire=True), ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(os.path.abspath(sys.argv[1]))
