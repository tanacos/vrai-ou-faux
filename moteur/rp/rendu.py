# -*- coding: utf-8 -*-
"""Rendu générique d'un mini-reportage : episode.json (scènes) + chrono.json (voix montée, mots horodatés).

    python3 -m rp.rendu valider DOSSIER            -> repères introuvables, scènes manquantes, durée (JSON)
    python3 -m rp.rendu images  DOSSIER t1 t2 …    -> images de contrôle dans DOSSIER/sortie/
    python3 -m rp.rendu planche DOSSIER            -> DOSSIER/sortie/planche.png (moments clés)
    python3 -m rp.rendu audit   DOSSIER            -> textes hors zone sûre ou superposés (JSON)

Même interface que les rendu.py sur mesure (setup, frame, nframes, planche, audit, DUR) : la fabrication
(series/infiniment/fabriquer.py) prend ce moteur quand le dossier de l'épisode n'a pas de rendu.py."""
import json
import os
import re
import sys

import numpy as np
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "rp"

from vf import ui as U  # noqa: E402
from vf.voix import nettoyer_mot  # noqa: E402

from . import base as B  # noqa: E402
from . import scenes as S  # noqa: E402
from .base import W, H, FPS, T0, SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT_LOW, sstep, einout  # noqa: E402,F401

CH = None
EP = None
SCENES = []                   # [(bloc, scène)]
BOUNDS = []
SC = {}
DUR = 0.0
XF = 0.28
CAP = None
EXPO_K = []
ERREURS = []


class Ctx:
    """Accès aux repères de la voix pour les scènes."""

    def bloc(self, b):
        s, e = CH["blocs"][b]
        return s + T0, e + T0

    def scene(self, b):
        return SC[b]

    def cue(self, b, mot, n=0):
        w = nettoyer_mot(str(mot)).replace("'", "")
        v = CH["reperes"].get(f"{b}:{w}")
        if not v:
            # mot élidé dans la narration (« d'années », « l'univers ») : on accepte la forme sans l'élision
            cands = [(k, vv) for k, vv in CH["reperes"].items() if k.startswith(b + ":")
                     and k.split(":", 1)[1].endswith(w) and 0 < len(k.split(":", 1)[1]) - len(w) <= 3]
            if len(cands) == 1:
                v = cands[0][1]
        if v and len(v) > n:
            return v[n] + T0
        return None

    _RX = re.compile(r"^(?P<mot>.+?)(?:#(?P<n>\d+))?(?P<off>[+-]\d+(?:[.,]\d+)?)?$")

    def quand(self, b, q):
        """Repère : nombre (secondes après le premier mot du bloc), « debut », « fin », ou un mot de la narration
        (« mot », « mot#2 » pour la 2e occurrence, « mot+0.4 » avec un décalage en secondes)."""
        s, e = self.bloc(b)
        if isinstance(q, (int, float)):
            return s + float(q)
        q = str(q).strip()
        m = self._RX.match(q)
        if not m:
            return None
        mot, n, off = m.group("mot"), int(m.group("n") or 1) - 1, float((m.group("off") or "0").replace(",", "."))
        if mot == "debut":
            return s + off
        if mot == "fin":
            return e + off
        v = self.cue(b, mot, n)
        return None if v is None else v + off


def setup(chrono_path, episode_path=None):
    global CH, EP, SCENES, BOUNDS, SC, DUR, CAP, EXPO_K, ERREURS
    CH = json.load(open(chrono_path, encoding="utf-8"))
    episode_path = episode_path or os.path.join(os.path.dirname(os.path.abspath(chrono_path)), "episode.json")
    EP = json.load(open(episode_path, encoding="utf-8"))
    ids = EP["blocs"]
    ERREURS = []
    manquants = [b for b in ids if b not in (EP.get("scenes") or {})]
    if manquants:
        ERREURS.append(f"blocs sans scène : {', '.join(manquants)}")
    b = [0.0]
    for i in range(1, len(ids)):
        pe = CH["blocs"][ids[i - 1]][1] + T0
        ns = CH["blocs"][ids[i]][0] + T0
        b.append((pe + ns) / 2 - 0.05)
    DUR = round((CH["duree"] + T0 + 0.25) * FPS) / FPS
    b.append(DUR + 1)
    SC = {n: (b[i], b[i + 1]) for i, n in enumerate(ids)}
    ctx = Ctx()
    SCENES = []
    BOUNDS = []
    for bl in ids:
        sp = (EP.get("scenes") or {}).get(bl, {"type": "heros"})
        plans = sp if isinstance(sp, list) else [sp]          # plusieurs plans dans un même bloc
        b0, b1 = SC[bl]
        coupes = [b0]
        for k, pl in enumerate(plans[1:], 1):
            tq = ctx.quand(bl, pl.get("a_partir_de", ""))
            if tq is None:
                ERREURS.append(f"bloc {bl} : plan {k + 1}, repère « a_partir_de » introuvable "
                               f"{pl.get('a_partir_de')!r}")
                tq = b0 + (b1 - b0) * k / len(plans)
            coupes.append(min(max(tq - 0.25, coupes[-1] + 0.6), b1 - 0.6))
        coupes.append(b1)
        for k, pl in enumerate(plans):
            sc = S.creer(ctx, bl, pl)
            sc.bornes = (coupes[k], coupes[k + 1])
            sc.preparer()
            ERREURS += sc.erreurs
            SCENES.append((bl, sc))
            BOUNDS.append(coupes[k])
    BOUNDS.append(DUR + 1)
    CAP = B.SousTitres(CH["sous_titres"])
    # puissance de dix : images clés de toutes les scènes, transitions lissées
    EXPO_K = []
    for _, sc in SCENES:
        EXPO_K += list(sc.expos)
    EXPO_K.sort(key=lambda x: x[0])


def nframes():
    return int(round(DUR * FPS))


def scene_index(t):
    return max(j for j in range(len(SCENES)) if BOUNDS[j] <= t + 1e-9)


def expo_at(t):
    if not EXPO_K:
        return None
    v = EXPO_K[0][1]
    for k in range(1, len(EXPO_K)):
        tk, ek = EXPO_K[k]
        v = v + (ek - EXPO_K[k - 1][1]) * einout((t - tk + 0.45) / 0.9)
    return v


def _melange(fn, t):
    """Valeur d'un réglage d'interface par scène (règle, sous-titres), fondue au passage d'une scène à l'autre."""
    i = scene_index(t)
    v = fn(SCENES[i][1], t)
    b = BOUNDS
    if i + 1 < len(SCENES) and t > b[i + 1] - XF:
        w = sstep(b[i + 1] - XF, b[i + 1] + XF, t)
        v = v * (1 - w) + fn(SCENES[i + 1][1], t) * w
    if i > 0 and t < b[i] + XF:
        w = sstep(b[i] - XF, b[i] + XF, t)
        v = fn(SCENES[i - 1][1], t) * (1 - w) + v * w
    return v


def ui_layer(img, t):
    """Calque d'interface commun (en-tête, règle, sous-titres) ; sert aussi à l'audit des zones sûres."""
    a_rule = _melange(lambda s, tt: s.regle(tt), t)
    B.entete(img, t, EP.get("serie", "INFINIMENT"), EP.get("numero", 1), 1.0, expo_at(t), a_rule)
    a_cap = _melange(lambda s, tt: s.sous_titres(tt), t)
    CAP.dessiner(img, t, a_cap)


def scene_text_alpha(k, t):
    """Les textes d'une scène s'effacent juste avant la coupe et ceux de la suivante n'arrivent qu'après."""
    b = BOUNDS
    a = 1.0
    if k > 0:
        a *= sstep(b[k] + 0.12, b[k] + 0.40, t)
    if k + 1 < len(SCENES):
        a *= 1 - sstep(b[k + 1] - 0.40, b[k + 1] - 0.12, t)
    return a


def render_scene(k, t):
    B.SCN_A[0] = scene_text_alpha(k, t)
    try:
        return SCENES[k][1].rendre(t)
    finally:
        B.SCN_A[0] = 1.0


def frame(t, fi=0):
    i = scene_index(t)
    cv = render_scene(i, t)
    b = BOUNDS
    if i + 1 < len(SCENES) and t > b[i + 1] - XF:
        w = sstep(b[i + 1] - XF, b[i + 1] + XF, t)
        cv = cv * (1 - w) + render_scene(i + 1, t) * w
    if i > 0 and t < b[i] + XF:
        w = sstep(b[i] - XF, b[i] + XF, t)
        cv = render_scene(i - 1, t) * (1 - w) + cv * w
    ui_layer(cv, t)
    cv *= B.VIG
    cv += B.GRAIN[fi % len(B.GRAIN)]
    return (np.clip(cv, 0, 1) * 255 + 0.5).astype(np.uint8)


def audit(step=3):
    """Rejoue tout le texte (scènes comprises) et signale ce qui sort des zones sûres ou se superpose."""
    bad = {}
    for fi in range(0, nframes(), step):
        t = fi / FPS
        U.LOG = []
        frame(t, fi)
        for a, b in U.overlaps(U.LOG):
            bad.setdefault((a[0], f"chevauchement avec {b[0]!r}"), round(t, 2))
        for (s, x0, y0, x1, y1, _a) in U.LOG:
            why = []
            if y0 < 240:
                why.append("haut")
            if y1 > SAFE_BOTTOM:
                why.append("bas")
            if x0 < SAFE_LEFT:
                why.append("gauche")
            if x1 > W - 120:
                why.append("droite")
            if y1 > 840 and x1 > SAFE_RIGHT_LOW:
                why.append("boutons à droite")
            if why:
                bad.setdefault((s, "/".join(why)), round(t, 2))
    U.LOG = None
    return bad


def key_times():
    ts = [0.0]
    for _, sc in SCENES:
        ts += sc.moments()
    ts.append(DUR - 0.2)
    ts = sorted(min(max(x, 0.0), DUR - 1 / FPS) for x in ts)
    out = []
    for x in ts:
        if not out or x - out[-1] > 0.45:
            out.append(x)
    return out


def planche(path, ts=None, cols=6, tw=360, th=640):
    import cv2
    ts = ts or key_times()
    rows = (len(ts) + cols - 1) // cols
    sheet = np.zeros((rows * (th + 10), cols * (tw + 10), 3), np.uint8)
    for k, t in enumerate(ts):
        r, c = divmod(k, cols)
        im = cv2.resize(frame(t, int(t * FPS)), (tw, th), interpolation=cv2.INTER_AREA)
        sheet[r * (th + 10) + 5:r * (th + 10) + 5 + th, c * (tw + 10) + 5:c * (tw + 10) + 5 + tw] = im
        cv2.putText(sheet, f"{t:.1f}s", (c * (tw + 10) + 12, r * (th + 10) + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 0), 2)
    Image.fromarray(sheet).save(path)
    return path


def valider():
    """Erreurs bloquantes (repères introuvables, blocs sans scène, objets inconnus) et avertissements."""
    from . import objets as O
    from vf import icons as IC
    err = list(ERREURS)
    warn = []
    communs = {"type", "titre", "titres", "titre_quand", "couverture", "infos", "chiffre", "chiffres", "expo",
               "ambiance", "impacts", "a_partir_de", "note"}
    propres = {"heros": {"objet", "objet_quand", "objet_jusqua", "objets", "echelle", "zoom_lent"},
               "zoom": {"sens", "objet", "expo_depart", "paliers"},
               "anneaux": {"centre", "anneaux", "remplissage", "remplissage_quand", "au_dela"},
               "trajet": {"depart", "arrivee", "mobile", "debut", "fin", "etirement", "support", "couleur_support",
                          "mesures", "compteur"},
               "fin": {"prochain", "quand", "sources_quand", "objet", "sens"}}
    for bl, sc in SCENES:
        sp = sc.spec
        k = {"objet": "heros", "titre": "heros", "chiffre": "heros"}.get(sp.get("type", "heros"), sp.get("type", "heros"))
        inconnus = set(sp) - communs - propres.get(k, set())
        if inconnus:
            warn.append(f"bloc {bl} : clés ignorées par une scène « {k} » : {', '.join(sorted(inconnus))}")
        for t in sp.get("titres", []):
            if not isinstance(t, dict) or not isinstance(t.get("lignes"), list):
                err.append(f"bloc {bl} : « titres » attend des objets {{\"quand\", \"lignes\": [...]}}")
        for c in sp.get("chiffres", []) + ([sp["chiffre"]] if sp.get("chiffre") else []):
            if "valeur" not in c:
                err.append(f"bloc {bl} : chiffre sans « valeur »")
        for p in sp.get("paliers", []):
            if not p.get("objet") or "quand" not in p:
                err.append(f"bloc {bl} : palier sans « objet » ou sans « quand »")
        for a in sp.get("anneaux", []):
            if "rayon" not in a:
                err.append(f"bloc {bl} : anneau sans « rayon »")
        for lignes in [sp.get("titre"), sp.get("couverture"), sp.get("prochain")] + \
                [t.get("lignes") for t in sp.get("titres", []) if isinstance(t, dict)] + \
                [p.get("titre") for p in sp.get("paliers", [])]:
            if lignes and len(lignes) > (3 if k == "fin" else 2):
                err.append(f"bloc {bl} : titre de {len(lignes)} lignes (2 au plus)")
        objs = [sp.get("objet"), sp.get("remplissage"), sp.get("mobile")]
        objs += [o.get("objet") for o in sp.get("objets", [])] + [p.get("objet") for p in sp.get("paliers", [])]
        objs += [(sp.get(k) or {}).get("objet") for k in ("centre", "depart", "arrivee")]
        for o in objs:
            if o is None:
                continue
            if not isinstance(o, dict) or o.get("type") not in O.TYPES:
                err.append(f"bloc {bl} : objet inconnu {o!r}")
            elif o["type"] == "icone" and not IC.exists(o.get("nom", "")):
                err.append(f"bloc {bl} : pictogramme inconnu {o.get('nom')!r}")
            elif o["type"] == "icone" and IC.credits([o.get("nom", "")]):
                # la légende ne porte plus de crédit (décision du 28/10/2026) et le reportage n'en affiche pas
                err.append(f"bloc {bl} : pictogramme {o.get('nom')!r} refusé : sa licence (game-icons, CC BY 3.0) "
                           "exige un crédit ; prends-en un d'un autre jeu (pi:, md:, ri:, io:, bs:)")
    if not 61 <= DUR <= 95:
        warn.append(f"durée {DUR:.1f} s hors de 61-95 s")
    return dict(ok=not err, erreurs=err, avertissements=warn, duree=round(DUR, 2), scenes=len(SCENES))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    mode, d = argv[0], os.path.abspath(argv[1])
    setup(os.path.join(d, "chrono.json"), os.path.join(d, "episode.json"))
    out = os.path.join(d, "sortie")
    os.makedirs(out, exist_ok=True)
    if mode == "valider":
        r = valider()
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["ok"] else 2
    if mode == "images":
        for ts in argv[2:]:
            t = float(ts)
            p = os.path.join(out, f"image_{t:06.2f}.png")
            Image.fromarray(frame(t, int(t * FPS))).save(p)
            print(p)
        return 0
    if mode == "planche":
        print(planche(os.path.join(out, "planche.png")))
        return 0
    if mode == "audit":
        bad = audit(int(argv[2]) if len(argv) > 2 else 3)
        print(json.dumps([dict(texte=k[0], probleme=k[1], t=v) for k, v in bad.items()], ensure_ascii=False, indent=1))
        return 0 if not bad else 2
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
