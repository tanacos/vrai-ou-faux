# -*- coding: utf-8 -*-
"""Interface commune de la série VRAI OU FAUX ? (vertical 1080 x 1920) : bandeau, question, compte à rebours,
tampon du verdict, textes avec contrôle des zones sûres TikTok, barres comparatives, flash de transition."""
import math

import numpy as np
import cv2

from vlib import *  # noqa: F401,F403

CORAL = C3(1.0, 0.30, 0.27)
CYAN = C3(0.40, 0.85, 1.0)
WHITE = C3(1.0, 1.0, 1.0)
LIGHT = C3(0.86, 0.90, 0.96)
GREEN = C3(0.30, 0.88, 0.52)
INK = C3(0.03, 0.035, 0.05)
SUNC = C3(1.0, 0.62, 0.22)

_sy = np.arange(H, dtype=f32)
SCRIM = (np.clip((_sy - 150) / 200, 0, 1) * np.clip((1290 - _sy) / 260, 0, 1) * 0.42)[:, None, None].astype(f32)


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
    fr = np.zeros_like(S, np.uint8)
    cv2.rectangle(fr, (8, 8), (S.shape[1] - 9, S.shape[0] - 9), 255, 12, cv2.LINE_AA)
    cv2.rectangle(fr, (26, 26), (S.shape[1] - 27, S.shape[0] - 27), 255, 4, cv2.LINE_AA)
    S = np.maximum(S, fr.astype(f32) / 255.0)
    r = np.random.default_rng(7)
    nz = cv2.GaussianBlur(r.random(S.shape).astype(f32), (0, 0), 2.0)
    nz = (nz - nz.mean()) / (nz.std() + 1e-6)
    S *= np.clip(0.88 + 0.22 * nz, 0.45, 1.0)
    return S


def put_rot(img, m, cx, cy, scale, ang, col, a):
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
    roi += mm * col


def big_text_raw(img, txt, path, size, x, baseline, scale, col, a, sh=True):
    if a <= 0.003:
        return
    m, w, asc, lh = text_patch(txt, path, size, 0.0)
    h = m.shape[0]
    vis = baseline - 0.36 * size
    cy_mask = baseline - asc + h / 2
    cy = vis + (cy_mask - vis) * scale
    if sh:
        shadow(img, m, x - w / 2 - 8, baseline - asc, a, blur=size * 0.06, dy=size * 0.04)
    put_rot(img, m, x, cy, scale, 0.0, col, a)


STAMPS = {"FAUX": stamp_mask("FAUX"), "VRAI": stamp_mask("VRAI")}
VCOL = {"FAUX": CORAL, "VRAI": GREEN}

# ------------------------------------------------------------------ texte avec journal (contrôle des zones sûres)
LOG = None


def _log(txt, x0, y0, x1, y1, a):
    if LOG is not None and a > 0.05:
        LOG.append((txt, x0, y0, x1, y1))


def T(img, txt, path, size, x, y, col, a=1.0, align=0, tracking=0.0, sh=True):
    if a <= 0.003 or not txt:
        return 0.0
    w = text(img, txt, path, size, x, y, col, a, align, tracking, sh=sh)
    x0 = x - w / 2 if align == 0 else (x if align < 0 else x - w)
    _log(txt, x0, y - 0.76 * size, x0 + w, y + 0.22 * size, a)
    return w


def PARA(img, lines, path, size, x, y, col, a=1.0, align=0, lh=1.10, tracking=0.0, t=None, t0=None, step=0.09):
    for i, ln in enumerate(lines):
        ai, dy = a, 0.0
        if t is not None and t0 is not None:
            u = sat((t - t0 - i * step) / 0.35)
            ai, dy = a * eout(u, 3), 24 * (1 - eout(u, 3))
        T(img, ln, path, size, x, y + i * size * lh + dy, col, ai, align, tracking)
    return y + len(lines) * size * lh


def BIG(img, txt, path, size, x, baseline, scale, col, a, sh=True):
    if a <= 0.003:
        return
    big_text_raw(img, txt, path, size, x, baseline, scale, col, a, sh)
    w = text_width(txt, path, size) * scale
    _log(txt, x - w / 2, baseline - 0.74 * size * scale, x + w / 2, baseline + 0.05 * size * scale, a)


def PILL(img, txt, x, y, bg, fg, a, size=40, pad=26, tracking=3.0, path=F_DBLACK):
    if a <= 0.003:
        return
    pill_raw(img, txt, x, y, bg, fg, a, size, pad, tracking, path)
    w = text_width(txt, path, size, tracking)
    _log(txt, x - w / 2 - pad, y - size * 0.92, x + w / 2 + pad, y + size * 0.42, a)


def ain(t, t0, d=0.35):
    return eout(sat((t - t0) / d), 3)


def section(t, t0, t1):
    return bump(t, t0, t0 + 0.35, t1 - 0.35, t1 - 0.05)


def stroke(img, segs, col, a, th=6):
    m, b = line_mask(segs, th)
    if m is None or a <= 0:
        return
    x0, y0, x1, y1 = b
    mm = (m * f32(a))[..., None]
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - mm) + mm * col


def icon_check(img, x, y, s, a, col=GREEN):
    fill_over(img, [circle_pts(x, y, s, 60)], col, a)
    stroke(img, [np.array([(x - s * 0.45, y + s * 0.02), (x - s * 0.12, y + s * 0.34), (x + s * 0.48, y - s * 0.32)])],
           C3(0.02, 0.06, 0.03), a, int(s * 0.2))


def icon_cross(img, x, y, s, a, col=CORAL):
    fill_over(img, [circle_pts(x, y, s, 60)], col, a)
    d = s * 0.38
    stroke(img, [np.array([(x - d, y - d), (x + d, y + d)]), np.array([(x - d, y + d), (x + d, y - d)])], WHITE, a,
           int(s * 0.18))


def dashed_v(img, x, y0, y1, col, a, dash=12, gap=9, th=3):
    segs = []
    y = y0
    while y < y1:
        segs.append(np.array([(x, y), (x, min(y + dash, y1))]))
        y += dash + gap
    stroke(img, segs, col, a, th)


# ------------------------------------------------------------------ chronologie d'un épisode à 4 idées reçues
class Timeline:
    def __init__(self, FL, dur, first=2.40):
        self.FL = list(FL)
        self.CUT = [f + 0.02 for f in FL]
        self.S = [first] + [f + 0.25 for f in FL[:3]]
        self.S_OUT = FL[3] + 0.25
        self.DUR = dur
        self.NF = int(round(dur * FPS))
        self.G = [dict(i=i, claim=s0, cd=s0 + 1.20, reveal=s0 + 3.15, body=s0 + 4.30, end=FL[i])
                  for i, s0 in enumerate(self.S)]

    def scene_index(self, t):
        """0 : avant la 1re coupe, 1..3 : idées 2 à 4, 4 : conclusion."""
        k = 0
        for c in self.CUT:
            if t >= c:
                k += 1
        return k

    def scene_span(self, t):
        b = [0.0] + self.CUT + [self.DUR + 1.0]
        k = self.scene_index(t)
        return b[k], min(b[k + 1], self.DUR)


def claim_block(img, t, g, claim, y0=470, size=80, maxw=820):
    a_c = 1 - sstep(g["body"] - 0.35, g["body"] - 0.05, t)
    if a_c > 0 and t >= g["claim"]:
        lines = wrap(claim, F_DXB, size, maxw)
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
        T(img, "TA RÉPONSE ?", F_DBOLD, 42, 540, cy + 180, LIGHT, a0, 0, 4.0)


def verdict(img, t, g, lab, cy0=1040):
    col = VCOL[lab]
    if g["reveal"] <= t < g["end"]:
        u = (t - g["reveal"]) / 0.30
        moving = sstep(g["body"] - 0.45, g["body"] + 0.05, t)
        sc = (2.1 - 1.1 * back_out(sat(u), 1.4)) * (1 - 0.72 * moving)
        cy = cy0 + (392 - cy0) * smoother(moving)
        a = eout(sat(u * 3), 2) * (1 - sstep(g["end"] - 0.3, g["end"] - 0.05, t))
        if moving < 1:
            put_rot(img, STAMPS[lab], 540, cy, sc * 0.95, (8 if lab == "FAUX" else -6) * (1 - moving), col, a)
        else:
            PILL(img, lab, 540, 410, col, WHITE, a, size=44, pad=30, tracking=4.0)


def header(img, t, TL, badge0=None):
    """Bandeau « VRAI OU FAUX ? » + numéro de l'idée reçue (ou badge d'épisode pendant l'ouverture)."""
    PILL(img, "VRAI OU FAUX ?", 540, 318, C3(0.06, 0.07, 0.10), WHITE, 0.92)
    wpill = text_width("VRAI OU FAUX ?", F_DBLACK, 40, 3.0)
    xb = 540 + wpill / 2 + 83
    if badge0:
        ab = 1 - sstep(TL.S[0] - 0.3, TL.S[0], t)
        if ab > 0:
            wb = text_width(badge0, F_DBLACK, 30, 1.0)
            fill_over(img, [rounded_rect(xb - wb / 2 - 18, 280, xb + wb / 2 + 18, 330, 25)], CYAN, ab)
            T(img, badge0, F_DBLACK, 30, xb, 316, C3(0.02, 0.04, 0.06), ab, 0, 1.0, sh=False)
    for i in range(4):
        nxt = TL.FL[i]
        ai = ain(t, TL.S[i], 0.3) * (1 - sstep(nxt - 0.25, nxt, t))
        if ai > 0:
            fill_over(img, [rounded_rect(xb - 47, 280, xb + 47, 330, 25)], CORAL, ai)
            T(img, f"{i + 1}/4", F_DBLACK, 32, xb, 316, WHITE, ai, 0, 0.0, sh=False)


def bars(img, t, a, t0, rows, tmax, ref, src, box=(150, 845, 790, 1245), y0r=905.0, dyr=105.0, bx0=180.0, blen=560.0):
    """Barres comparatives : rows = [(libellé, valeur affichée, valeur, couleur, retard)] ; ref = (valeur, couleur)."""
    fill_over(img, [rounded_rect(*box, 34)], INK, 0.80 * a)
    for k, (lab, val, tv, col, d) in enumerate(rows):
        ak = a * ain(t, t0 + d)
        if ak <= 0:
            continue
        y = y0r + k * dyr
        T(img, lab, F_SEMI, 30, bx0, y, LIGHT, ak, -1)
        T(img, val, F_DBOLD, 40, bx0 + blen + 20, y, WHITE, ak, 1)
        fill_over(img, [rounded_rect(bx0, y + 16, bx0 + blen, y + 40, 12)], C3(0.12, 0.13, 0.17), ak * 0.9)
        L = blen * tv / tmax * eout(sat((t - t0 - d - 0.1) / 0.6), 3)
        if L > 2:
            fill_over(img, [rounded_rect(bx0, y + 16, bx0 + L, y + 40, 12)], col, ak)
    if ref is not None:
        al = a * ain(t, t0 + 2.1, 0.4)
        if al > 0:
            xs_ = bx0 + blen * ref[0] / tmax
            for k in range(len(rows)):
                dashed_v(img, xs_, y0r + k * dyr + 10, y0r + k * dyr + 46, ref[1], al)
    T(img, src, F_MEDI, 26, (box[0] + box[2]) / 2, box[3] - 23, LIGHT, a * ain(t, t0 + 1.6) * 0.85)


def whiteout(t, FL, col=None):
    v = 0.0
    for tf in FL:
        u = t - tf
        if -0.06 <= u < 0:
            v = max(v, (u + 0.06) / 0.06 * 0.8)
        elif 0 <= u < 0.6:
            v = max(v, 0.85 * math.exp(-u / 0.13))
    return v


def audit(ui_fn, NF, step=1):
    """Rejoue l'interface image par image et signale le texte hors des zones sûres TikTok."""
    global LOG
    bad = {}
    img = np.zeros((H, W, 3), f32)
    for i in range(0, NF, step):
        t = i / FPS
        LOG = []
        img[:] = 0
        ui_fn(img, t)
        for (txt, x0, y0, x1, y1) in LOG:
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
