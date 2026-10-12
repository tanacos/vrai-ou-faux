# -*- coding: utf-8 -*-
"""Interface commune de la série VRAI OU FAUX ? (vertical 1080 x 1920) : bandeau, question, compte à rebours, tampon
du verdict, panneaux d'explication, ouverture et conclusion. Tout texte passe par T/BIG/PILL, qui journalisent leur
boîte englobante pour l'audit des zones sûres TikTok."""
import math

import cv2
import numpy as np

from .base import *  # noqa: F401,F403
from .base import (C3, F_DBLACK, F_DXB, F_DBOLD, F_MEDI, F_SEMI, W, H, FPS, f32, TAU, sat, sstep, eout, bump,
                   smoother, back_out, text, text_patch, text_width, wrap, fill_over, rounded_rect, circle_pts,
                   line_mask, shadow, SAFE_TOP, SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT, SAFE_RIGHT_LOW)

CORAL = C3(1.0, 0.30, 0.27)
CYAN = C3(0.40, 0.85, 1.0)
WHITE = C3(1.0, 1.0, 1.0)
LIGHT = C3(0.86, 0.90, 0.96)
GREEN = C3(0.30, 0.88, 0.52)
INK = C3(0.03, 0.035, 0.05)
GOLD = C3(1.0, 0.78, 0.30)
VIOLET = C3(0.68, 0.55, 1.0)
DARK = C3(0.02, 0.04, 0.06)
COULEURS = {"cyan": CYAN, "corail": CORAL, "vert": GREEN, "or": GOLD, "violet": VIOLET, "blanc": WHITE,
            "clair": LIGHT}

_sy = np.arange(H, dtype=f32)
SCRIM = (np.clip((_sy - 150) / 200, 0, 1) * np.clip((1290 - _sy) / 260, 0, 1) * 0.42)[:, None, None].astype(f32)

NB = " "


def fr(s):
    """Espaces insécables de la typographie française (guillemets, %, :, ?, !, ; et milliers)."""
    if not s:
        return s
    import re
    s = s.replace("« ", "«" + NB).replace(" »", NB + "»").replace(" %", NB + "%")
    s = s.replace(" :", NB + ":").replace(" ?", NB + "?").replace(" !", NB + "!").replace(" ;", NB + ";")
    s = re.sub(r"(?<=\d) (?=\d{3}\b)", NB, s)
    s = re.sub(r"(?<=\d) (?=(km|m|cm|mm|kg|g|t|°C|°|h|min|s|ans|an|%|€|km/h|m/s|W|kW|MW|GW|L|ml|mL)\b)", NB, s)
    return s


def col(name, default=None):
    if name is None:
        return default if default is not None else CYAN
    if isinstance(name, (list, tuple)):
        return C3(*name)
    return COULEURS.get(str(name).lower(), default if default is not None else CYAN)


def pill_raw(img, txt, x, y, col_bg, col_fg, a, size=40, pad=26, tracking=3.0, path=F_DBLACK):
    if a <= 0.003:
        return
    w = text_width(txt, path, size, tracking)
    x0, x1 = x - w / 2 - pad, x + w / 2 + pad
    y0, y1 = y - size * 0.92, y + size * 0.42
    fill_over(img, [rounded_rect(x0, y0, x1, y1, (y1 - y0) / 2)], col_bg, a)
    text(img, txt, path, size, x, y, col_fg, a, 0, tracking, sh=False)


def stamp_mask(txt, size=200):
    m, w, asc, lh = text_patch(txt, F_DBLACK, size, 6.0)
    h, ww = m.shape
    pad = 34
    S = np.zeros((h + 2 * pad, ww + 2 * pad), f32)
    S[pad:pad + h, pad:pad + ww] = m
    frm = np.zeros_like(S, np.uint8)
    cv2.rectangle(frm, (8, 8), (S.shape[1] - 9, S.shape[0] - 9), 255, 12, cv2.LINE_AA)
    cv2.rectangle(frm, (26, 26), (S.shape[1] - 27, S.shape[0] - 27), 255, 4, cv2.LINE_AA)
    S = np.maximum(S, frm.astype(f32) / 255.0)
    r = np.random.default_rng(7)
    nz = cv2.GaussianBlur(r.random(S.shape).astype(f32), (0, 0), 2.0)
    nz = (nz - nz.mean()) / (nz.std() + 1e-6)
    S *= np.clip(0.88 + 0.22 * nz, 0.45, 1.0)
    return S


def put_rot(img, m, cx, cy, scale, ang, col_, a):
    if a <= 0.003:
        return
    h, w = m.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, scale)
    M[0, 2] += cx - w / 2
    M[1, 2] += cy - h / 2
    out = cv2.warpAffine(m, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    ys, xs = np.nonzero(out > 0.002)
    if len(xs) == 0:
        return
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    mm = (out[y0:y1, x0:x1] * f32(a))[..., None]
    roi = img[y0:y1, x0:x1]
    roi *= 1 - mm
    roi += mm * col_


def big_text_raw(img, txt, path, size, x, baseline, scale, col_, a, sh=True):
    if a <= 0.003:
        return
    m, w, asc, lh = text_patch(txt, path, size, 0.0)
    h = m.shape[0]
    vis = baseline - 0.36 * size
    cy_mask = baseline - asc + h / 2
    cy = vis + (cy_mask - vis) * scale
    if sh:
        shadow(img, m, x - w / 2 - 8, baseline - asc, a, blur=size * 0.06, dy=size * 0.04)
    put_rot(img, m, x, cy, scale, 0.0, col_, a)


_STAMPS = {}


def stamp(lab):
    if lab not in _STAMPS:
        _STAMPS[lab] = stamp_mask(lab)
    return _STAMPS[lab]


VCOL = {"FAUX": CORAL, "VRAI": GREEN}

# ------------------------------------------------------------------ texte avec journal (contrôle des zones sûres)
LOG = None


def _log(txt, x0, y0, x1, y1, a):
    if LOG is not None and a > 0.05:
        LOG.append((txt, x0, y0, x1, y1, a))


def T(img, txt, path, size, x, y, col_, a=1.0, align=0, tracking=0.0, sh=True):
    if a <= 0.003 or not txt:
        return 0.0
    w = text(img, txt, path, size, x, y, col_, a, align, tracking, sh=sh)
    x0 = x - w / 2 if align == 0 else (x if align < 0 else x - w)
    _log(txt, x0, y - 0.76 * size, x0 + w, y + 0.22 * size, a)
    return w


def PARA(img, lines, path, size, x, y, col_, a=1.0, align=0, lh=1.10, tracking=0.0, t=None, t0=None, step=0.09):
    for i, ln in enumerate(lines):
        ai, dy = a, 0.0
        if t is not None and t0 is not None:
            u = sat((t - t0 - i * step) / 0.35)
            ai, dy = a * eout(u, 3), 24 * (1 - eout(u, 3))
        T(img, ln, path, size, x, y + i * size * lh + dy, col_, ai, align, tracking)
    return y + len(lines) * size * lh


def BIG(img, txt, path, size, x, baseline, scale, col_, a, sh=True):
    if a <= 0.003:
        return
    big_text_raw(img, txt, path, size, x, baseline, scale, col_, a, sh)
    w = text_width(txt, path, size) * scale
    _log(txt, x - w / 2, baseline - 0.74 * size * scale, x + w / 2, baseline + 0.05 * size * scale, a)


def PILL(img, txt, x, y, bg, fg, a, size=40, pad=26, tracking=3.0, path=F_DBLACK):
    if a <= 0.003:
        return
    pill_raw(img, txt, x, y, bg, fg, a, size, pad, tracking, path)
    w = text_width(txt, path, size, tracking)
    _log(txt, x - w / 2 - pad, y - size * 0.92, x + w / 2 + pad, y + size * 0.42, a)


def safe_cx(x, w, y_bottom):
    """Centre horizontal corrigé pour qu'un texte de largeur w reste dans la zone sûre (boutons à droite sous y=840)."""
    right = (SAFE_RIGHT_LOW if y_bottom > 840 else SAFE_RIGHT) - 6
    left = SAFE_LEFT + 6
    return float(min(max(x, left + w / 2), right - w / 2))


def pill_w(txt, size=40, pad=26, tracking=3.0, path=F_DBLACK):
    return text_width(txt, path, size, tracking) + 2 * pad


def ain(t, t0, d=0.35):
    return eout(sat((t - t0) / d), 3)


def section(t, t0, t1):
    return bump(t, t0, t0 + 0.35, t1 - 0.35, t1 - 0.05)


def stroke(img, segs, col_, a, th=6):
    m, b = line_mask(segs, th)
    if m is None or a <= 0:
        return
    x0, y0, x1, y1 = b
    mm = (m * f32(a))[..., None]
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - mm) + mm * col_


def dashed_v(img, x, y0, y1, col_, a, dash=12, gap=9, th=3):
    segs = []
    y = y0
    while y < y1:
        segs.append(np.array([(x, y), (x, min(y + dash, y1))]))
        y += dash + gap
    stroke(img, segs, col_, a, th)


def fit_size(txt, path, size, max_w, min_size=24, tracking=0.0):
    """Plus grande taille <= size pour laquelle le texte tient sur une ligne de largeur max_w."""
    s = size
    while s > min_size and text_width(txt, path, s, tracking) > max_w:
        s -= 2
    return s


def fit_block(txt, path, sizes, max_w, max_lines):
    """Première taille de la liste pour laquelle le texte tient en max_lines lignes ; (taille, lignes) ou None."""
    for s in sizes:
        ln = wrap(txt, path, s, max_w)
        if len(ln) <= max_lines and all(text_width(x, path, s) <= max_w + 1 for x in ln):
            return s, ln
    return None


# ------------------------------------------------------------------ éléments récurrents
def claim_layout(claim):
    """Taille et lignes de l'affirmation (zone y 470 à ~880, au-dessus du compte à rebours)."""
    r = fit_block(claim, F_DXB, (80, 76, 72, 68, 64, 60), 820, 4)
    if r is None:
        r = (60, wrap(claim, F_DXB, 60, 820))
    return r


def claim_block(img, t, g, layout, y0=470):
    size, lines = layout
    a_c = 1 - sstep(g["body"] - 0.35, g["body"] - 0.05, t)
    if a_c > 0 and t >= g["claim"]:
        PARA(img, lines, F_DXB, size, 540, y0, WHITE, a_c, 0, 1.10, t=t, t0=g["claim"])


def countdown(img, t, g, cx=540, cy=1060, R=128):
    if g["cd"] <= t < g["reveal"] + 0.25:
        a0 = ain(t, g["cd"], 0.25) * (1 - sstep(g["reveal"] - 0.05, g["reveal"] + 0.15, t))
        fill_over(img, [circle_pts(cx, cy, R + 18, 120)], INK, 0.78 * a0)
        prog = 1 - sat((t - g["cd"]) / (g["reveal"] - g["cd"]))
        if prog > 0.002:
            stroke(img, [circle_pts(cx, cy, R, 160, -math.pi / 2, -math.pi / 2 + TAU * prog)], CYAN, a0, 10)
        k = min(int((t - g["cd"]) / 0.65), 2)
        u = (t - g["cd"] - k * 0.65) / 0.22
        sc = 1.0 + 0.35 * (1 - eout(sat(u), 3))
        BIG(img, str(3 - k), F_DBLACK, 190, cx, cy + 0.36 * 190, sc, WHITE, a0 * eout(sat(u * 1.5), 2), sh=False)
        T(img, "TA RÉPONSE ?".replace(" ?", NB + "?"), F_DBOLD, 42, 540, cy + 180, LIGHT, a0, 0, 4.0)


def verdict(img, t, g, lab, cy0=1040):
    c = VCOL[lab]
    if g["reveal"] <= t < g["end"]:
        u = (t - g["reveal"]) / 0.30
        moving = sstep(g["body"] - 0.45, g["body"] + 0.05, t)
        sc = (2.1 - 1.1 * back_out(sat(u), 1.4)) * (1 - 0.72 * moving)
        cy = cy0 + (392 - cy0) * smoother(moving)
        a = eout(sat(u * 3), 2) * (1 - sstep(g["end"] - 0.3, g["end"] - 0.05, t))
        if moving < 1:
            put_rot(img, stamp(lab), 540, cy, sc * 0.95, (8 if lab == "FAUX" else -6) * (1 - moving), c, a)
        else:
            PILL(img, lab, 540, 410, c, WHITE, a, size=44, pad=30, tracking=4.0)


def header(img, t, TL, badge0=None):
    """Bandeau « VRAI OU FAUX ? » + numéro de l'idée reçue (ou badge d'épisode pendant l'ouverture)."""
    lab = "VRAI OU FAUX" + NB + "?"
    PILL(img, lab, 540, 318, C3(0.06, 0.07, 0.10), WHITE, 0.92)
    wpill = text_width(lab, F_DBLACK, 40, 3.0)
    xb = 540 + wpill / 2 + 83
    if badge0:
        ab = 1 - sstep(TL.S[0] - 0.3, TL.S[0], t)
        if ab > 0:
            wb = text_width(badge0, F_DBLACK, 30, 1.0)
            fill_over(img, [rounded_rect(xb - wb / 2 - 18, 280, xb + wb / 2 + 18, 330, 25)], CYAN, ab)
            T(img, badge0, F_DBLACK, 30, xb, 316, DARK, ab, 0, 1.0, sh=False)
    for i in range(4):
        nxt = TL.FL[i]
        ai = ain(t, TL.S[i], 0.3) * (1 - sstep(nxt - 0.25, nxt, t))
        if ai > 0:
            fill_over(img, [rounded_rect(xb - 47, 280, xb + 47, 330, 25)], CORAL, ai)
            T(img, f"{i + 1}/4", F_DBLACK, 32, xb, 316, WHITE, ai, 0, 0.0, sh=False)


def whiteout(t, FL):
    v = 0.0
    for tf in FL:
        u = t - tf
        if -0.06 <= u < 0:
            v = max(v, (u + 0.06) / 0.06 * 0.8)
        elif 0 <= u < 0.6:
            v = max(v, 0.85 * math.exp(-u / 0.13))
    return v


def loop_flash(t, DUR):
    """Flash de bouclage en toute fin de vidéo. La première image reste nette (titre de l'épisode), car TikTok s'en
    sert de miniature par défaut."""
    v = 0.0
    if t >= DUR - 0.06:
        v = (t - (DUR - 0.06)) / 0.06 * 0.8
    return v


# ------------------------------------------------------------------ panneaux d'explication
ZONE_Y0, ZONE_Y1 = 548, 830        # zone de texte des panneaux (lignes de base)


def fmt_num(v, dec=0):
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",").replace(" ", NB)
    return s


class Panel:
    """Panneau générique ; la mise en page est calculée une fois (et validée) à la construction."""
    kind = "texte"

    def __init__(self, spec, t0, t1):
        self.s = spec
        self.t0, self.t1 = t0, t1
        self.events = []          # (t, nom du son, paramètres) pour la bande-son
        self.errors = []
        self.layout()

    def layout(self):
        pass

    def draw(self, img, t):
        pass

    def uses_visual_zone(self):
        return False


class PTexte(Panel):
    kind = "texte"

    def layout(self):
        s = self.s
        self.titre = fr(s.get("titre", "") or "")
        self.texte = fr(s.get("texte", "") or "")
        self.sous = fr(s.get("sous_texte", "") or "")
        self.ct = col(s.get("couleur_titre"), CYAN)
        self.items = []
        blocks = []
        if self.titre:
            r = fit_block(self.titre, F_DBOLD, (54, 50, 46, 42), 840, 2)
            if r is None:
                self.errors.append(f"titre trop long : {self.titre!r}")
                r = (42, wrap(self.titre, F_DBOLD, 42, 840))
            blocks.append(("titre", r[1], r[0], 1.10))
        if self.texte:
            n_max = 4 if not self.titre else 3
            if self.sous:
                n_max -= 1
            r = fit_block(self.texte, F_DXB, (70, 66, 62, 58, 54), 820, n_max)
            if r is None:
                self.errors.append(f"texte trop long ({len(self.texte)} caractères) : {self.texte!r}")
                r = (54, wrap(self.texte, F_DXB, 54, 820))
            blocks.append(("texte", r[1], r[0], 1.10))
        if self.sous:
            r = fit_block(self.sous, F_MEDI, (46, 44, 42, 40, 38), 840, 2)
            if r is None:
                self.errors.append(f"sous-texte trop long : {self.sous!r}")
                r = (38, wrap(self.sous, F_MEDI, 38, 840))
            blocks.append(("sous", r[1], r[0], 1.15))
        y = ZONE_Y0
        prev = None
        for kind, ln, sz, lh in blocks:
            if prev is not None:
                pk, psz = prev
                y += psz * (0.30 if kind != "sous" else 0.35) + sz * (1.05 if kind != "sous" else 1.35)
            self.items.append((kind, ln, sz, y))
            y += (len(ln) - 1) * sz * lh
            prev = (kind, sz)
        self.y_end = y
        if y > ZONE_Y1 + 10:
            self.errors.append(f"panneau trop haut (fin y={y:.0f} > {ZONE_Y1}) : raccourcir les textes")

    def draw(self, img, t):
        a = section(t, self.t0, self.t1)
        if a <= 0:
            return
        d = 0.0
        for kind, ln, sz, yb in self.items:
            if kind == "titre":
                PARA(img, ln, F_DBOLD, sz, 540, yb, self.ct, a, 0, 1.10, t=t, t0=self.t0)
                d = 0.15
            elif kind == "texte":
                PARA(img, ln, F_DXB, sz, 540, yb, WHITE, a, 0, 1.10, t=t, t0=self.t0 + d)
                d += 0.25 + 0.09 * len(ln)
            else:
                t1 = self.t0 + max(d + 0.35, 0.7)
                PARA(img, ln, F_MEDI, sz, 540, yb, LIGHT, a * ain(t, t1), 0, 1.15)


class PChiffre(Panel):
    """Grand nombre qui se compte : {"titre", "valeur", "depart", "decimales", "prefixe", "suffixe", "legende"}."""
    kind = "chiffre"

    def layout(self):
        s = self.s
        self.titre = fr(s.get("titre", "") or "")
        self.leg = fr(s.get("legende", "") or "")
        self.v = float(s.get("valeur", 0))
        self.v0 = float(s.get("depart", 0))
        self.dec = int(s.get("decimales", 0))
        self.pre = s.get("prefixe", "") or ""
        self.suf = fr(s.get("suffixe", "") or "")
        if self.suf and not self.suf.startswith((NB, " ")) and self.suf[0].isalpha():
            self.suf = NB + self.suf
        self.suf = self.suf.replace(" ", NB) if self.suf.startswith(" ") else self.suf
        self.cfin = col(s.get("couleur"), CYAN)
        final = self.fmt(self.v)
        self.big = fit_size(final, F_DBLACK, 150, 840, 80)
        self.items = []
        if self.titre:
            r = fit_block(self.titre, F_DXB, (60, 56, 52, 48), 840, 2)
            if r is None:
                self.errors.append(f"titre trop long : {self.titre!r}")
                r = (48, wrap(self.titre, F_DXB, 48, 840))
            self.tsz, self.tln = r
        else:
            self.tsz, self.tln = 56, []
        if self.leg:
            r = fit_block(self.leg, F_MEDI, (44, 42, 40, 38), 840, 2)
            if r is None:
                self.errors.append(f"légende trop longue : {self.leg!r}")
                r = (38, wrap(self.leg, F_MEDI, 38, 840))
            self.lsz, self.lln = r
        else:
            self.lsz, self.lln = 44, []
        y = ZONE_Y0
        self.y_t = y
        y += max(len(self.tln) - 1, 0) * self.tsz * 1.10
        self.y_big = (y + 40 + self.big * 0.74) if self.tln else 548 + self.big * 0.55
        self.y_leg = self.y_big + 18 + self.lsz * 1.05
        self.y_end = self.y_leg + max(len(self.lln) - 1, 0) * self.lsz * 1.15
        if self.y_end > ZONE_Y1 + 10:
            self.errors.append(f"panneau chiffre trop haut (fin y={self.y_end:.0f})")
        self.t_count = self.t0 + 0.30
        self.d_count = float(s.get("duree_comptage", 1.6))
        self.events.append((self.t_count, "compteur", {"duree": self.d_count}))
        self.events.append((self.t_count + self.d_count, "ding", {}))

    def fmt(self, v):
        return fr(self.pre + fmt_num(v, self.dec) + self.suf)

    def draw(self, img, t):
        a = section(t, self.t0, self.t1)
        if a <= 0:
            return
        if self.tln:
            PARA(img, self.tln, F_DXB, self.tsz, 540, self.y_t, WHITE, a, 0, 1.10, t=t, t0=self.t0)
        u = eout(sat((t - self.t_count) / self.d_count), 2)
        v = self.v0 + (self.v - self.v0) * u
        if self.dec == 0:
            v = round(v)
        done = u >= 0.999
        BIG(img, self.fmt(v), F_DBLACK, self.big, 540, self.y_big, 1.0, self.cfin if done else WHITE,
            a * ain(t, self.t0 + 0.2))
        if self.lln:
            PARA(img, self.lln, F_MEDI, self.lsz, 540, self.y_leg, LIGHT, a * ain(t, self.t0 + 0.5), 0, 1.15)


class PDuo(Panel):
    """Deux valeurs côte à côte : {"titre", "gauche": {"valeur", "legende", "couleur"}, "droite": {...}}."""
    kind = "duo"

    def layout(self):
        s = self.s
        self.titre = fr(s.get("titre", "") or "")
        self.sides = []
        for k, x in (("gauche", 330), ("droite", 750)):
            d = s.get(k, {}) or {}
            v = fr(str(d.get("valeur", "")))
            leg = fr(d.get("legende", "") or "")
            sz = fit_size(v, F_DBLACK, 140, 380, 70)
            r = fit_block(leg, F_MEDI, (36, 34, 32, 30), 380, 2) if leg else (36, [])
            if r is None:
                self.errors.append(f"légende trop longue : {leg!r}")
                r = (30, wrap(leg, F_MEDI, 30, 380))
            self.sides.append((x, v, sz, r[0], r[1], col(d.get("couleur"), WHITE if k == "gauche" else CYAN)))
        if self.titre:
            r = fit_block(self.titre, F_DBOLD, (54, 50, 46), 840, 1)
            if r is None:
                self.errors.append(f"titre trop long : {self.titre!r}")
                r = (46, [self.titre])
            self.tsz = r[0]
        self.y_big = 720 if self.titre else 680
        self.y_end = self.y_big + 70 + 40
        self.events.append((self.t0 + 0.25, "pop", {"f": 520}))
        self.events.append((self.t0 + 0.85, "pop", {"f": 700}))

    def draw(self, img, t):
        a = section(t, self.t0, self.t1)
        if a <= 0:
            return
        if self.titre:
            T(img, self.titre, F_DBOLD, self.tsz, 540, 540, CYAN, a * ain(t, self.t0))
        for k, (x, v, sz, lsz, lln, c) in enumerate(self.sides):
            ak = a * ain(t, self.t0 + 0.25 + 0.6 * k)
            BIG(img, v, F_DBLACK, sz, x, self.y_big, 1.0, c, ak)
            PARA(img, lln, F_MEDI, lsz, x, self.y_big + 70, LIGHT, ak, 0, 1.12)


class PCitation(Panel):
    kind = "citation"

    def layout(self):
        s = self.s
        self.txt = fr(s.get("texte", "") or "")
        self.aut = fr(s.get("auteur", "") or "")
        r = fit_block(self.txt, F_DXB, (62, 58, 54, 50), 820, 4)
        if r is None:
            self.errors.append(f"citation trop longue : {self.txt!r}")
            r = (50, wrap(self.txt, F_DXB, 50, 820))
        self.sz, self.ln = r
        self.y_aut = ZONE_Y0 + (len(self.ln) - 1) * self.sz * 1.12 + 70
        if self.y_aut > ZONE_Y1 + 10:
            self.errors.append("citation trop haute")

    def draw(self, img, t):
        a = section(t, self.t0, self.t1)
        if a <= 0:
            return
        PARA(img, self.ln, F_DXB, self.sz, 540, ZONE_Y0, WHITE, a, 0, 1.12, t=t, t0=self.t0)
        if self.aut:
            T(img, "— " + self.aut, F_MEDI, 38, 540, self.y_aut, CYAN, a * ain(t, self.t0 + 0.7))


class PBarres(Panel):
    """Barres comparatives dans la zone visuelle : {"titre", "lignes": [{"libelle", "valeur", "affichage", "couleur"}],
    "reference": {"valeur", "couleur"}, "source", "max"}."""
    kind = "barres"

    def uses_visual_zone(self):
        return True

    def layout(self):
        s = self.s
        self.titre = fr(s.get("titre", "") or "")
        self.sous = fr(s.get("sous_texte", "") or "")
        rows = s.get("lignes", [])
        if not 2 <= len(rows) <= 4:
            self.errors.append("barres : 2 à 4 lignes attendues")
        self.rows = []
        vmax = float(s.get("max", 0) or 0) or max(float(r.get("valeur", 0)) for r in rows) * 1.0
        self.vmax = vmax if vmax > 0 else 1.0
        pal = [CYAN, C3(0.85, 0.92, 1.0), GOLD, CORAL]
        for k, r in enumerate(rows):
            lab = fr(r.get("libelle", ""))
            if text_width(lab, F_SEMI, 30) > 600:
                self.errors.append(f"libellé de barre trop long : {lab!r}")
            aff = fr(str(r.get("affichage", fmt_num(float(r.get("valeur", 0))))))
            self.rows.append((lab, aff, float(r.get("valeur", 0)), col(r.get("couleur"), pal[k % 4]), 0.7 * k))
        ref = s.get("reference")
        self.ref = (float(ref["valeur"]), col(ref.get("couleur"), CYAN)) if ref else None
        self.src = fr(s.get("source", "") or "")
        if self.src and text_width(self.src, F_MEDI, 26) > 600:
            self.errors.append(f"source des barres trop longue : {self.src!r}")
        n = max(len(rows), 1)
        self.dyr = 105.0 if n <= 3 else 82.0
        self.box = (150, 845, 790, 845 + 60 + n * self.dyr + 70)
        if self.titre:
            r = fit_block(self.titre, F_DXB, (62, 58, 54, 50), 820, 2)
            if r is None:
                self.errors.append(f"titre trop long : {self.titre!r}")
                r = (50, wrap(self.titre, F_DXB, 50, 820))
            self.tsz, self.tln = r
        else:
            self.tsz, self.tln = 60, []
        if self.sous:
            r = fit_block(self.sous, F_MEDI, (42, 40, 38), 840, 2)
            if r is None:
                self.errors.append(f"sous-texte trop long : {self.sous!r}")
                r = (38, wrap(self.sous, F_MEDI, 38, 840))
            self.ssz, self.sln = r
        else:
            self.ssz, self.sln = 40, []
        for k in range(len(self.rows)):
            self.events.append((self.t0 + 0.30 + 0.7 * k, "glisse", {"niveau": self.rows[k][2] / self.vmax}))

    def draw(self, img, t):
        a = section(t, self.t0, self.t1)
        if a <= 0:
            return
        y = ZONE_Y0
        if self.tln:
            PARA(img, self.tln, F_DXB, self.tsz, 540, y, WHITE, a, 0, 1.10, t=t, t0=self.t0)
            y += len(self.tln) * self.tsz * 1.10
        if self.sln:
            PARA(img, self.sln, F_MEDI, self.ssz, 540, y + 10, LIGHT, a * ain(t, self.t0 + 0.4), 0, 1.15)
        bars(img, t, a, self.t0 + 0.20, self.rows, self.vmax, self.ref, self.src, box=self.box,
             y0r=self.box[1] + 60, dyr=self.dyr)


def bars(img, t, a, t0, rows, tmax, ref, src, box=(150, 845, 790, 1245), y0r=905.0, dyr=105.0, bx0=180.0, blen=560.0):
    """Barres comparatives : rows = [(libellé, valeur affichée, valeur, couleur, retard)] ; ref = (valeur, couleur)."""
    fill_over(img, [rounded_rect(*box, 34)], INK, 0.80 * a)
    for k, (lab, val, tv, c, d) in enumerate(rows):
        ak = a * ain(t, t0 + d)
        if ak <= 0:
            continue
        y = y0r + k * dyr
        T(img, lab, F_SEMI, 30, bx0, y, LIGHT, ak, -1)
        T(img, val, F_DBOLD, 40, bx0 + blen + 20, y, WHITE, ak, 1)
        fill_over(img, [rounded_rect(bx0, y + 16, bx0 + blen, y + 40, 12)], C3(0.12, 0.13, 0.17), ak * 0.9)
        L = blen * min(tv / tmax, 1.0) * eout(sat((t - t0 - d - 0.1) / 0.6), 3)
        if L > 2:
            fill_over(img, [rounded_rect(bx0, y + 16, bx0 + max(L, 24), y + 40, 12)], c, ak)
    if ref is not None:
        al = a * ain(t, t0 + 2.1, 0.4)
        if al > 0:
            xs_ = bx0 + blen * min(ref[0] / tmax, 1.0)
            for k in range(len(rows)):
                dashed_v(img, xs_, y0r + k * dyr + 10, y0r + k * dyr + 46, ref[1], al)
    if src:
        T(img, src, F_MEDI, 26, (box[0] + box[2]) / 2, box[3] - 23, LIGHT, a * ain(t, t0 + 1.6) * 0.85)


PANELS = {"texte": PTexte, "chiffre": PChiffre, "duo": PDuo, "barres": PBarres, "citation": PCitation}


def make_panel(spec, t0, t1):
    k = spec.get("type", "texte")
    if k not in PANELS:
        p = PTexte({"texte": "?"}, t0, t1)
        p.errors.append(f"type de panneau inconnu : {k!r} (attendus : {', '.join(PANELS)})")
        return p
    return PANELS[k](spec, t0, t1)


# ------------------------------------------------------------------ audit des zones sûres et des chevauchements
CHEVAUCHEMENT = "chevauchement"
OVERLAP_A = 0.30            # deux textes visibles au moins à 30 % chacun…
OVERLAP_PX = 6.0            # … dont les boîtes se recouvrent de plus de 6 px dans les deux directions


def overlaps(entries):
    """Paires de textes visibles en même temps dont les boîtes se recouvrent (illisible à l'écran)."""
    vis = [e for e in entries if e[5] >= OVERLAP_A]
    out = []
    for i in range(len(vis)):
        a = vis[i]
        for b in vis[i + 1:]:
            ix = min(a[3], b[3]) - max(a[1], b[1])
            iy = min(a[4], b[4]) - max(a[2], b[2])
            if ix > OVERLAP_PX and iy > OVERLAP_PX:
                out.append((a, b))
    return out


def audit(ui_fn, NF, step=1):
    """Rejoue l'interface image par image et signale le texte hors des zones sûres TikTok, ainsi que les textes qui
    se superposent (clé (texte, "chevauchement avec « autre »"))."""
    global LOG
    bad = {}
    img = np.zeros((H, W, 3), f32)
    for i in range(0, NF, step):
        t = i / FPS
        LOG = []
        img[:] = 0
        ui_fn(img, t)
        for a, b in overlaps(LOG):
            key = (a[0], f"{CHEVAUCHEMENT} avec {b[0]!r}")
            if key not in bad:
                bad[key] = (t, round(a[1]), round(a[2]), round(a[3]), round(a[4]))
        for (txt, x0, y0, x1, y1, _a) in LOG:
            why = []
            if y0 < SAFE_TOP:
                why.append("haut")
            if y1 > SAFE_BOTTOM:
                why.append("bas")
            if x0 < SAFE_LEFT:
                why.append("gauche")
            if x1 > SAFE_RIGHT:
                why.append("droite")
            if y1 > 840 and x1 > SAFE_RIGHT_LOW:
                why.append("boutons à droite")
            if why:
                key = (txt, "/".join(why))
                if key not in bad:
                    bad[key] = (t, round(x0), round(y0), round(x1), round(y1))
    LOG = None
    return bad
