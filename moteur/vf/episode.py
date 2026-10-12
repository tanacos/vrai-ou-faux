# -*- coding: utf-8 -*-
"""Épisode « Vrai ou faux ? » décrit par un script JSON : validation, chronologie automatique, rendu des images.

Structure du script (clés en français) :
{
  "numero": 3, "slug": "espace", "titre": ["4 IDÉES REÇUES", "SUR L'ESPACE"], "fond": "espace", "ambiance": "espace",
  "idees": [ {"affirmation": "« … »", "verdict": "FAUX", "scene": {...}, "panneaux": [{...}, ...],
              "sources": [{"editeur": "NASA", "titre": "…", "url": "https://…", "extrait": "…"}]} x 4 ],
  "sources_ecran": "NASA · ESA · …",
  "prochain": {"affirmation": "« … »"},
  "publication": {"legende": "…", "hashtags": ["#vraioufaux", …]}
}"""
import json
import math
import re

import cv2
import numpy as np

from . import ui as U
from . import scenes as SC
from .base import (C3, W, H, FPS, f32, sat, sstep, smoother, finalize, text_width, wrap, F_DBLACK, F_DXB, F_DBOLD,
                   F_MEDI, F_SEMI)
from .ui import T, PARA, BIG, PILL, ain, section, fr, CYAN, WHITE, LIGHT, CORAL, DARK

MIN_DUR, MAX_DUR = 61.0, 90.0


def sources_block(src, sizes, max_w, max_lines, path=F_SEMI):
    """Lignes des sources de fin : on ne coupe qu'entre deux éditeurs (« ESA · NASA » / « Scientific American »),
    jamais au milieu d'un nom ; un nom plus large qu'une ligne est coupé entre ses mots en dernier recours."""
    items = [p.strip() for p in src.replace(" ·", " ·").split("·") if p.strip()]
    for sz in sizes:
        lines = []
        for it in items:
            if text_width(it, path, sz) > max_w:
                lines += wrap(it, path, sz, max_w)
                continue
            if lines and text_width(lines[-1] + " · " + it, path, sz) <= max_w:
                lines[-1] = lines[-1] + " · " + it
            else:
                lines.append(it)
        if len(lines) <= max_lines and all(text_width(x, path, sz) <= max_w + 1 for x in lines):
            return sz, lines
    return None


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _chars(*xs):
    return sum(len(x or "") for x in xs)


def panel_duration(p):
    """Durée d'affichage d'un panneau, calibrée sur le rythme des épisodes 1 et 2 (environ 22 caractères/s)."""
    k = p.get("type", "texte")
    if "duree" in p:
        return float(np.clip(float(p["duree"]), 2.0, 7.0))
    if k == "texte":
        c = _chars(p.get("titre"), p.get("texte")) + 0.7 * _chars(p.get("sous_texte"))
        return float(np.clip(1.0 + c / 22.0, 2.4, 5.0))
    if k == "chiffre":
        c = _chars(p.get("titre"), p.get("legende"))
        return float(np.clip(1.0 + float(p.get("duree_comptage", 1.6)) + c / 22.0, 2.8, 4.8))
    if k == "duo":
        g, d = p.get("gauche") or {}, p.get("droite") or {}
        c = _chars(p.get("titre"), g.get("legende"), d.get("legende")) + 8
        return float(np.clip(1.4 + c / 20.0, 2.8, 4.4))
    if k == "barres":
        rows = p.get("lignes") or []
        c = _chars(p.get("titre"), p.get("sous_texte"), *[r.get("libelle") for r in rows])
        return float(np.clip(2.2 + 0.6 * len(rows) + c / 26.0, 3.8, 6.0))
    if k == "citation":
        c = _chars(p.get("texte"), p.get("auteur"))
        return float(np.clip(1.2 + c / 18.0, 2.8, 5.0))
    return 3.5


class Timeline:
    """Chronologie : ouverture (2,4 s), 4 idées (question, 3-2-1, verdict, panneaux), conclusion."""

    def __init__(self, spec, stretch=1.0):
        self.S, self.FL, self.G = [], [], []
        s = 2.40
        self.panels_t = []
        for i, idee in enumerate(spec["idees"]):
            g = dict(i=i, claim=s, cd=s + 1.20, reveal=s + 3.15, body=s + 4.30)
            t = g["body"]
            spans = []
            for p in idee.get("panneaux", []):
                d = panel_duration(p) * stretch
                spans.append((t, t + d))
                t += d
            g["end"] = t + 0.10
            self.S.append(s)
            self.FL.append(g["end"])
            self.G.append(g)
            self.panels_t.append(spans)
            s = g["end"] + 0.25
        self.CUT = [f + 0.02 for f in self.FL]
        self.S_OUT = self.FL[-1] + 0.25
        self.P5A = (self.S_OUT + 0.20, self.S_OUT + 3.40)
        self.P5B = (self.P5A[1], self.P5A[1] + 4.80)
        self.DUR = round(self.P5B[1] * FPS) / FPS
        self.NF = int(round(self.DUR * FPS))

    def scene_index(self, t):
        k = 0
        for c in self.CUT:
            if t >= c:
                k += 1
        return k

    def scene_span(self, t):
        b = [0.0] + self.CUT + [self.DUR + 1.0]
        k = self.scene_index(t)
        return b[k], min(b[k + 1], self.DUR)


def make_timeline(spec):
    tl = Timeline(spec)
    if tl.DUR < MIN_DUR + 1.0:
        base = Timeline(spec, 1.0)
        fixed = base.DUR - sum(e - s for sp in base.panels_t for (s, e) in sp)
        var = sum(e - s for sp in base.panels_t for (s, e) in sp)
        need = (MIN_DUR + 1.0 - fixed) / max(var, 1e-6)
        tl = Timeline(spec, float(min(max(need, 1.0), 1.30)))
    return tl


class Episode:
    def __init__(self, spec):
        self.spec = spec
        self.errors, self.warnings = [], []
        self._validate_top()
        if self.errors:
            raise ValueError("\n".join(self.errors))
        self.TL = make_timeline(spec)
        TL = self.TL
        self.num = int(spec.get("numero", 0))
        self.verdicts = [idee["verdict"].upper() for idee in spec["idees"]]
        self.claims = [fr(idee["affirmation"]) for idee in spec["idees"]]
        self.claim_layout = [U.claim_layout(c) for c in self.claims]
        for i, (sz, ln) in enumerate(self.claim_layout):
            if len(ln) > 4 or sz < 60:
                self.errors.append(f"idée {i + 1} : affirmation trop longue ({len(self.claims[i])} caractères)")
        # panneaux
        self.panels = []
        for i, idee in enumerate(spec["idees"]):
            row = []
            for p, (t0, t1) in zip(idee.get("panneaux", []), TL.panels_t[i]):
                P = U.make_panel(p, t0, t1)
                for e in P.errors:
                    self.errors.append(f"idée {i + 1}, panneau {len(row) + 1} : {e}")
                row.append(P)
            self.panels.append(row)
        # scènes
        self.scenes = []
        for i, idee in enumerate(spec["idees"]):
            ctx = dict(g=TL.G[i], verdict=self.verdicts[i], fond=spec.get("fond", "nuit"),
                       visual_busy=self._busy_fn(i))
            sc = SC.make_scene(idee.get("scene") or {"type": "pictogramme", "icone": "question"}, ctx)
            for e in sc.errors:
                self.errors.append(f"idée {i + 1}, scène : {e}")
            self.scenes.append(sc)
        self._layout_outro()
        self._validate_timing()

    # ------------------------------------------------------------------ validation
    def _validate_top(self):
        s = self.spec
        idees = s.get("idees")
        if not isinstance(idees, list) or len(idees) != 4:
            self.errors.append("il faut exactement 4 idées reçues (« idees »)")
            return
        nv = 0
        for i, idee in enumerate(idees):
            a = (idee.get("affirmation") or "").strip()
            if not a:
                self.errors.append(f"idée {i + 1} : affirmation manquante")
            elif not (a.startswith("«") and a.endswith("»")):
                self.errors.append(f"idée {i + 1} : l'affirmation doit être entre guillemets « … »")
            v = (idee.get("verdict") or "").upper()
            if v not in ("VRAI", "FAUX"):
                self.errors.append(f"idée {i + 1} : verdict VRAI ou FAUX attendu")
            nv += v == "VRAI"
            pn = idee.get("panneaux") or []
            if not 2 <= len(pn) <= 4:
                self.errors.append(f"idée {i + 1} : 2 à 4 panneaux attendus (il y en a {len(pn)})")
            srcs = idee.get("sources") or []
            good = [x for x in srcs if re.match(r"https?://", str(x.get("url", ""))) and x.get("editeur")]
            if len(good) < 2:
                self.errors.append(f"idée {i + 1} : au moins 2 sources avec « editeur » et « url » sont exigées")
            if len({x.get("editeur", "").strip().lower() for x in good}) < 2:
                self.errors.append(f"idée {i + 1} : les 2 sources doivent venir de 2 éditeurs différents")
        if nv == 0 or nv == 4:
            self.warnings.append("les 4 verdicts sont identiques : la série alterne d'habitude VRAI et FAUX")
        t = s.get("titre")
        if not (isinstance(t, list) and len(t) == 2):
            self.errors.append("« titre » : deux lignes attendues, ex. [\"4 IDÉES REÇUES\", \"SUR L'ESPACE\"]")
        if not s.get("sources_ecran"):
            self.errors.append("« sources_ecran » manquant (liste courte des sources affichée à la fin)")
        if not (s.get("prochain") or {}).get("affirmation"):
            self.errors.append("« prochain.affirmation » manquant (annonce de l'épisode suivant)")
        pub = s.get("publication") or {}
        leg = pub.get("legende", "")
        if not leg:
            self.errors.append("« publication.legende » manquante")
        elif "Sources" not in leg and "sources" not in leg:
            self.errors.append("la légende doit citer les sources (« Sources : … »)")
        if len(leg) > 2000:
            self.errors.append("légende trop longue (> 2000 caractères)")

    def _validate_timing(self):
        d = self.TL.DUR
        if d < MIN_DUR:
            self.errors.append(f"durée {d:.1f} s < {MIN_DUR} s : ajouter un panneau (la rémunération exige > 1 min)")
        if d > MAX_DUR:
            self.errors.append(f"durée {d:.1f} s > {MAX_DUR} s : raccourcir les panneaux")

    def _busy_fn(self, i):
        """Opacité des panneaux qui occupent la zone visuelle (barres) : les étiquettes de la scène s'effacent."""
        def busy(t):
            v = 0.0
            for P in self.panels[i]:
                if P.uses_visual_zone():
                    v = max(v, section(t, P.t0 - 0.1, P.t1 + 0.1))
            return v
        return busy

    def _layout_outro(self):
        s = self.spec
        t1, t2 = s["titre"]
        self.t1s = U.fit_size(t1, F_DBLACK, 96, 800, 60, tracking=1.0)
        self.t2s = U.fit_size(t2, F_DBLACK, 96, 800, 60, tracking=1.0)
        if self.t2s < 64:
            self.errors.append(f"titre trop long : {t2!r}")
        src = fr(s["sources_ecran"])
        # 2 lignes de sources de préférence (l'annonce du prochain épisode reste ainsi haut dans l'écran), 3 au plus
        r = sources_block(src, (34, 32, 30, 28, 26), 800, 2) or sources_block(src, (30, 28, 26), 800, 3)
        if r is None:
            self.errors.append("« sources_ecran » trop long (3 lignes maximum) : garder les éditeurs principaux")
            r = (26, wrap(src, F_SEMI, 26, 800)[:3])
        self.src_sz, self.src_ln = r
        y = 556 + (len(self.src_ln) - 1) * self.src_sz * 1.18
        self.y_nlab = max(722.0, y + 70)
        self.y_nx = self.y_nlab + 68
        nxt = fr(s["prochain"]["affirmation"])
        # sous y = 840, le bord droit est occupé par les boutons TikTok : une ligne centrée y reste étroite
        w_low = 2 * (U.SAFE_RIGHT_LOW - 8 - 540)
        r = None
        for sz in (54, 50, 46, 42):
            for wmax in (800, 720, 640, 560, w_low):
                ln = wrap(nxt, F_DXB, sz, wmax)
                if len(ln) > 3:
                    continue
                ok = True
                for i, x_ in enumerate(ln):
                    w_ = text_width(x_, F_DXB, sz)
                    low = self.y_nx + i * sz * 1.10 + 0.22 * sz > 840
                    if w_ > 801 or (low and w_ > w_low):
                        ok = False
                if ok:
                    r = (sz, ln)
                    break
            if r:
                break
        if r is None:
            self.errors.append("annonce du prochain épisode trop longue (elle doit tenir en 3 lignes, les lignes du "
                               "bas étant plus étroites à cause des boutons TikTok)")
            r = (42, wrap(nxt, F_DXB, 42, w_low)[:3])
        self.nx_sz, self.nx_ln = r
        y2 = self.y_nx + (len(self.nx_ln) - 1) * self.nx_sz * 1.10
        self.y_pill = max(1000.0, y2 + 95)
        self.y_abo = self.y_pill + 100
        if self.y_abo > 1230:
            self.errors.append("conclusion trop chargée (sources + annonce) : raccourcir")

    # ------------------------------------------------------------------ interface
    def cam_params(self, t):
        TL = self.TL
        t0, t1 = TL.scene_span(t)
        s = 1.0 + 0.05 * smoother((t - t0) / max(t1 - t0, 1e-3))
        return s, SC.CENTER

    def cam_pt(self, p, t):
        s, (cx, cy) = self.cam_params(t)
        return (cx + (p[0] - cx) * s, cy + (p[1] - cy) * s)

    def ui(self, img, t):
        TL, G = self.TL, self.TL.G
        U.header(img, t, TL, badge0=f"ÉP.{U.NB}{self.num}" if self.num else None)
        a_t = 1 - sstep(TL.S[0] - 0.35, TL.S[0] - 0.05, t)
        if a_t > 0:
            t1, t2 = self.spec["titre"]
            T(img, t1, F_DBLACK, self.t1s, 540, 590, WHITE, a_t, 0, 1.0)
            T(img, t2, F_DBLACK, self.t2s, 540, 700, CYAN, a_t, 0, 1.0)
            T(img, "Compte tes bonnes réponses", F_MEDI, 46, 540, 800, LIGHT, a_t * ain(t, 0.45))
        for g in G:
            U.claim_block(img, t, g, self.claim_layout[g["i"]], 470)
            U.countdown(img, t, g)
            U.verdict(img, t, g, self.verdicts[g["i"]])
        for row in self.panels:
            for P in row:
                if P.t0 - 0.1 <= t <= P.t1 + 0.1:
                    P.draw(img, t)
        sc = TL.scene_index(t)
        if sc < 4:
            self.scenes[sc].ui(img, t, lambda p: self.cam_pt(p, t))
        # conclusion
        a = section(t, *TL.P5A)
        if a > 0:
            T(img, "TON SCORE" + U.NB + "?", F_DBLACK, 96, 540, 600, WHITE, a * ain(t, TL.P5A[0]), 0, 1.0)
            BIG(img, "?/4", F_DBLACK, 220, 540, 880, 1.0 + 0.06 * math.sin((t - TL.S_OUT) * 6), CYAN,
                a * ain(t, TL.P5A[0] + 0.25))
            T(img, "Dis-le en commentaire", F_MEDI, 44, 540, 990, LIGHT, a * ain(t, TL.P5A[0] + 0.6))
        a = ain(t, TL.P5B[0], 0.4) * (1 - sstep(TL.DUR - 0.18, TL.DUR - 0.06, t))
        if a > 0:
            T(img, "SOURCES", F_DBOLD, 30, 540, 500, LIGHT, a * 0.85, 0, 6.0)
            PARA(img, self.src_ln, F_SEMI, self.src_sz, 540, 556, WHITE, a, 0, 1.18)
            a2 = a * ain(t, TL.P5B[0] + 0.5, 0.4)
            T(img, "PROCHAIN ÉPISODE", F_DBOLD, 30, 540, self.y_nlab, CYAN, a2, 0, 6.0)
            PARA(img, self.nx_ln, F_DXB, self.nx_sz, 540, self.y_nx, WHITE, a2, 0, 1.10)
            a3 = a * ain(t, TL.P5B[0] + 1.0, 0.4)
            PILL(img, "VRAI OU FAUX" + U.NB + "?", 540, self.y_pill, CYAN, DARK, a3, size=40)
            T(img, "Abonne-toi pour la réponse", F_SEMI, 36, 540, self.y_abo, LIGHT, a3)

    # ------------------------------------------------------------------ image
    def world(self, t):
        sc = self.TL.scene_index(t)
        if sc < 4:
            return self.scenes[sc].world(t)
        dim = 1.0 - 0.45 * sstep(self.TL.S_OUT, self.TL.S_OUT + 0.6, t)
        return self.scenes[0].world(t, neutral=True) * f32(dim)

    def camera(self, hdr, t):
        s, (cx, cy) = self.cam_params(t)
        M = np.array([[s, 0, (1 - s) * cx], [0, s, (1 - s) * cy]], np.float64)
        return cv2.warpAffine(hdr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    def render(self, t, seed=0):
        TL = self.TL
        hdr = self.world(t)
        hdr = self.camera(hdr, t)
        sh = (0.0, 0.0)
        for g in TL.G:
            if g["reveal"] <= t < g["reveal"] + 0.35:
                u = (t - g["reveal"]) / 0.35
                amp = 14 * (1 - u) ** 2
                sh = (amp * math.sin(t * 97), amp * math.cos(t * 83))
        out = finalize(hdr, 1.0, seed, grain=0.0, shake=sh)
        img = out.astype(f32) / 255.0
        img *= 1 - U.SCRIM
        self.ui(img, t)
        wo = max(U.whiteout(t, TL.FL), U.loop_flash(t, TL.DUR))
        if wo > 0:
            img = img * (1 - wo) + f32(wo) * C3(0.90, 0.95, 1.0)
        return np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)

    # ------------------------------------------------------------------ événements sonores
    def events(self):
        ev = []
        for row in self.panels:
            for P in row:
                ev.append((P.t0 - 0.06, "entree", {}))
                ev += P.events
        for sc in self.scenes:
            ev += sc.events
        return sorted(ev, key=lambda e: e[0])

    def summary(self):
        TL = self.TL
        lines = [f"Épisode {self.num} — durée {TL.DUR:.2f} s ({TL.NF} images)"]
        for i, g in enumerate(TL.G):
            lines.append(f"  idée {i + 1} [{self.verdicts[i]}] {g['claim']:6.2f} → {g['end']:6.2f} s  "
                         f"({len(self.panels[i])} panneaux, scène {self.scenes[i].kind})")
        lines.append(f"  conclusion {TL.S_OUT:6.2f} → {TL.DUR:6.2f} s")
        return "\n".join(lines)
