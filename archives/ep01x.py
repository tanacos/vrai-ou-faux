#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VRAI OU FAUX ? #1 — Spécial foudre : 4 idées reçues (68,7 s, 1080 x 1920, 30 i/s).
Sources des faits affichés : National Weather Service et NSSL (NOAA), UCAR, service-public.gouv.fr.
  python3 ep01x.py stills OUTDIR t1 t2 ...
  python3 ep01x.py frames OUTDIR              (PNG, reprise possible)
  python3 ep01x.py audit                      (zones sûres TikTok, image par image)
"""
import multiprocessing as mp
import os
import sys
import time

sys.path.insert(0, "/home/claude/vf")
from vlib import *  # noqa: F401,F403
import ep01 as A

CORAL, CYAN, WHITE, LIGHT = A.CORAL, A.CYAN, A.WHITE, A.LIGHT
GREEN = C3(0.30, 0.88, 0.52)
SUNC = C3(1.0, 0.62, 0.22)
INK = C3(0.03, 0.035, 0.05)
TIP = A.TIP
Strike = A.Strike

# ------------------------------------------------------------------ chronologie
FL = [16.45, 33.05, 45.45, 61.45]                       # flashs de transition
CUT = [f + 0.02 for f in FL]                            # changement de décor (pendant le flash)
S = [2.40, FL[0] + 0.25, FL[1] + 0.25, FL[2] + 0.25]    # début de chaque idée reçue
S_OUT = FL[3] + 0.25
DUR = 68.70
NF = int(round(DUR * FPS))
VERDICT = ["FAUX", "FAUX", "VRAI", "FAUX"]
CLAIMS = ["« La foudre ne tombe jamais deux fois au même endroit. »",
          "« Pendant un orage, s'abriter sous un arbre, c'est sûr. »",
          "« La foudre est plus chaude que la surface du Soleil. »",
          "« Toucher une personne foudroyée est dangereux : elle est électrisée. »"]


def seg(i):
    s0 = S[i]
    return dict(i=i, claim=s0, cd=s0 + 1.20, reveal=s0 + 3.15, body=s0 + 4.30, end=FL[i])


G = [seg(i) for i in range(4)]
P1A = (G[0]["body"], G[0]["body"] + 5.20)              # compteur 23
P1B = (P1A[1], FL[0] - 0.10)                           # 3 à 4 coups
P2A = (G[1]["body"], G[1]["body"] + 4.60)              # haut, pointu, isolé
P2B = (P2A[1], P2A[1] + 3.80)                          # 2e cause
P2C = (P2B[1], FL[1] - 0.10)                           # bon réflexe
P3A = (G[2]["body"], G[2]["body"] + 3.90)              # barres de température
P3B = (P3A[1], FL[2] - 0.10)                           # deux chiffres, une conclusion
P4A = (G[3]["body"], G[3]["body"] + 4.00)              # pas d'électricité stockée
P4B = (P4A[1], P4A[1] + 3.80)                          # on peut secourir
P4C = (P4B[1], FL[3] - 0.10)                           # 112
P5A = (S_OUT + 0.20, S_OUT + 3.40)                     # score
P5B = (P5A[1], DUR)                                    # sources + épisode suivant


def scene(t):
    if t < CUT[0] or t >= CUT[3]:
        return "A"
    if t < CUT[1]:
        return "T"
    return "S" if t < CUT[2] else "V"


def scene_span(t):
    b = [0.0] + CUT + [DUR + 1.0]
    for k in range(len(b) - 1):
        if b[k] <= t < b[k + 1]:
            return b[k], min(b[k + 1], DUR)
    return b[-2], DUR


# ------------------------------------------------------------------ décor des champs (scènes T et V)
HZ = 1300.0                                             # ligne d'horizon
HZT = HZ - 3.0


def _field():
    r = np.random.default_rng(31)
    yy = np.arange(H, dtype=f32)[:, None]
    g = np.clip((yy - HZ) / (H - HZ), 0, 1)
    ground = (C3(0.016, 0.017, 0.021) * (1 - g)[..., None] + C3(0.005, 0.006, 0.008) * g[..., None])
    ground = np.broadcast_to(ground, (H, W, 3)).copy()
    grass = cv2.GaussianBlur(r.standard_normal((H, W)).astype(f32), (0, 0), sigmaX=1.2, sigmaY=6.0)
    grass = 1 + 0.35 * grass / (grass.std() + 1e-6)
    ground *= grass[..., None]
    gm = (yy >= HZ).astype(f32) * np.ones((1, W), f32)
    gm = cv2.GaussianBlur(gm, (0, 0), 1.0)
    rgb = ground * gm[..., None]
    alpha = gm.copy()
    win = np.zeros((H, W, 3), f32)
    x = -10
    while x < W:                                        # ville lointaine sur l'horizon
        w = r.uniform(18, 60)
        top = HZ - r.uniform(10, 70)
        m, b = fill_polys([np.array([(x, HZ + 2), (x + w, HZ + 2), (x + w, top), (x, top)])])
        if m is not None:
            x0, y0, x1, y1 = b
            alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], m)
            rgb[y0:y1, x0:x1] = rgb[y0:y1, x0:x1] * (1 - m[..., None]) + m[..., None] * C3(0.026, 0.023, 0.032)
            for wy in np.arange(top + 5, HZ - 3, 7):
                for wx in np.arange(x + 3, x + w - 3, 6):
                    if r.random() < 0.12:
                        win[int(wy):int(wy) + 2, int(wx):int(wx) + 2] += C3(1.0, 0.75, 0.45) * f32(r.uniform(0.3, 0.8))
        x += w + r.uniform(2, 30)
    sheen = (np.exp(-np.clip(yy - HZ, 0, None) / 140.0) * (yy >= HZ)).astype(f32) * np.ones((1, W), f32)
    return rgb, alpha, win, sheen


FIELD_RGB, FIELD_A, FIELD_WIN, FIELD_SHEEN = _field()


def _tree(x0, y0, h, seed):
    r = np.random.default_rng(seed)
    k = h / 640.0
    segs = []

    def grow(p, ang, length, thick, depth):
        if depth == 0 or length < 5:
            return
        q = p + length * np.array([math.cos(ang), math.sin(ang)])
        bend = p + (q - p) * 0.5 + np.array([-math.sin(ang), math.cos(ang)]) * r.normal(0, length * 0.06)
        segs.append((np.array([p, bend, q]), thick))
        n = 3 if depth > 3 and r.random() < 0.45 else 2
        for i in range(n):
            da = (-1 if i == 0 else 1) * r.uniform(0.25, 0.62) if n == 2 else (i - 1) * r.uniform(0.35, 0.6)
            grow(q, ang + da + r.normal(0, 0.08), length * r.uniform(0.68, 0.80), thick * 0.66, depth - 1)

    trunk_top = np.array([x0, y0 - h * 0.36])
    segs.append((np.array([(x0, y0), (x0 - 4 * k, y0 - h * 0.18), trunk_top]), 38.0 * k))
    for a in (-1.95, -1.5, -1.12):
        grow(trunk_top, a + r.normal(0, 0.05), h * 0.30, 22.0 * k, 7)
    m = np.zeros((H, W), np.uint8)
    for pts, th in segs:
        q = np.round(pts * 16).astype(np.int32)
        cv2.polylines(m, [q], False, 255, max(1, int(round(th))), cv2.LINE_AA, 4)
    cv2.fillPoly(m, [np.round(np.array([(x0 - 46 * k, y0 + 4), (x0 + 46 * k, y0 + 4), (x0 + 16 * k, y0 - 40 * k),
                                        (x0 - 16 * k, y0 - 40 * k)]) * 16).astype(np.int32)], 255, cv2.LINE_AA, 4)
    tm = m.astype(f32) / 255.0
    ys, xs = np.nonzero(tm > 0.5)
    top = np.array([float(xs[np.argmin(ys)]), float(ys.min())])
    edge = tm - cv2.erode(tm, np.ones((3, 3), np.uint8), iterations=1)
    return tm, cv2.GaussianBlur(np.clip(edge, 0, 1), (0, 0), 1.0), top, (float(xs.min()), float(xs.max()))


TREE_X, TREE_Y = 540.0, HZ + 5.0
TREE_M, TREE_EDGE, TREE_TOP, TREE_XR = _tree(TREE_X, TREE_Y, 470.0, 5)

# ------------------------------------------------------------------ pictogrammes humains (mètres, sol en y = 0)
POSES = {
    "debout": dict(head=(0.0, 1.58), limbs=[((0.0, 1.40), (0.0, 0.96), 0.30), ((-0.17, 1.36), (-0.25, 1.06), 0.11),
                                             ((-0.25, 1.06), (-0.27, 0.80), 0.10), ((0.17, 1.36), (0.25, 1.06), 0.11),
                                             ((0.25, 1.06), (0.27, 0.80), 0.10), ((-0.08, 0.95), (-0.10, 0.48), 0.13),
                                             ((-0.10, 0.48), (-0.11, 0.05), 0.12), ((0.08, 0.95), (0.10, 0.48), 0.13),
                                             ((0.10, 0.48), (0.11, 0.05), 0.12)]),
    "allonge": dict(head=(-1.56, 0.16), limbs=[((-1.38, 0.15), (-0.94, 0.15), 0.28), ((-1.32, 0.12), (-0.82, 0.08), 0.10),
                                               ((-0.92, 0.14), (-0.46, 0.10), 0.13), ((-0.46, 0.10), (-0.05, 0.07), 0.12),
                                               ((-0.92, 0.16), (-0.50, 0.20), 0.13), ((-0.50, 0.20), (-0.08, 0.14), 0.12)]),
    "genou": dict(head=(-0.26, 1.16), limbs=[((-0.10, 1.00), (0.10, 0.58), 0.28), ((0.10, 0.56), (0.02, 0.10), 0.13),
                                             ((0.02, 0.08), (0.44, 0.06), 0.12), ((0.06, 0.58), (-0.20, 0.50), 0.13),
                                             ((-0.20, 0.50), (-0.22, 0.06), 0.12), ((-0.14, 0.96), (-0.42, 0.56), 0.11),
                                             ((-0.42, 0.56), (-0.52, 0.30), 0.10), ((-0.06, 0.96), (-0.36, 0.60), 0.11),
                                             ((-0.36, 0.60), (-0.46, 0.30), 0.10)]),
}


def person_mask(pose, xf, yf, k, flip=False):
    P = POSES[pose]
    m = np.zeros((H, W), np.uint8)
    sx = -1 if flip else 1
    for (a, b, th) in P["limbs"]:
        pa = (xf + sx * a[0] * k, yf - a[1] * k)
        pb = (xf + sx * b[0] * k, yf - b[1] * k)
        q = np.round(np.array([pa, pb]) * 16).astype(np.int32)
        cv2.polylines(m, [q], False, 255, max(1, int(round(th * k))), cv2.LINE_AA, 4)
    hx, hy = xf + sx * P["head"][0] * k, yf - P["head"][1] * k
    cv2.circle(m, (int(round(hx * 16)), int(round(hy * 16))), int(round(0.125 * k * 16)), 255, -1, cv2.LINE_AA, 4)
    return m.astype(f32) / 255.0


UNDER_X = 612.0
UNDER = person_mask("debout", UNDER_X, HZ + 6, 140)
VIC_X, VIC_K = 700.0, 185.0
VICTIM = person_mask("allonge", VIC_X, HZ + 10, VIC_K)
RESC_X = 548.0
RESCUER = person_mask("genou", RESC_X, HZ + 8, 175)

# ------------------------------------------------------------------ éclairs de chaque scène
SA = [Strike(0.04, (820, 60), 3, ((0.0, 1.3), (0.07, 0.9), (0.14, 0.7)), nb=7),
      Strike(G[0]["reveal"] - 0.02, (260, 40), 8, ((0.0, 1.2), (0.06, 0.8)), nb=6)]
T23 = [P1A[0] + 0.40 + 3.6 * (k / 22) ** 0.78 for k in range(23)]
for _k, _tk in enumerate(T23):
    _xo = float(np.random.default_rng(100 + _k).uniform(90, 990))
    SA.append(Strike(_tk, (_xo, float(np.random.default_rng(200 + _k).uniform(20, 160))), 300 + _k,
                     ((0.0, 1.0), (0.05, 0.6)) if _k % 3 else ((0.0, 1.0),), nb=4))
SLOW = Strike(P1B[0] + 0.65, (330, 50), 91, ((0.0, 1.3), (0.62, 1.0), (1.24, 0.9), (1.86, 0.8)), nb=6)
SA += [SLOW,
       Strike(FL[3], (600, 40), 41, ((0.0, 1.6), (0.06, 1.0)), nb=7),
       Strike(64.70, (180, 70), 43, ((0.0, 0.9),), nb=5),
       Strike(DUR - 0.15, (820, 60), 3, ((0.0, 1.3),), nb=7)]
ST = [Strike(CUT[0], (300, 60), 51, ((0.0, 1.3), (0.07, 0.8)), nb=6, p1=(300.0, HZT)),
      Strike(G[1]["reveal"] - 0.02, (420, 40), 63, ((0.0, 1.4), (0.06, 0.9), (0.13, 0.7)), nb=6, p1=tuple(TREE_TOP)),
      Strike(P2A[0] + 2.55, (780, 60), 64, ((0.0, 1.2), (0.07, 0.7)), nb=5, p1=tuple(TREE_TOP)),
      Strike(27.40, (100, 60), 65, ((0.0, 0.8),), nb=4, p1=(60.0, HZT)),
      Strike(31.10, (990, 60), 66, ((0.0, 0.8),), nb=4, p1=(1030.0, HZT))]
SV = [Strike(CUT[2], (640, 40), 71, ((0.0, 1.6), (0.06, 1.0)), nb=7, p1=(880.0, HZT)),
      Strike(G[3]["reveal"] - 0.02, (900, 50), 72, ((0.0, 1.1),), nb=5, p1=(985.0, HZT)),
      Strike(53.10, (120, 60), 73, ((0.0, 0.8),), nb=4, p1=(70.0, HZT)),
      Strike(58.70, (980, 80), 74, ((0.0, 0.7),), nb=4, p1=(1040.0, HZT))]
STRIKES = {"A": SA, "T": ST, "V": SV}

# ------------------------------------------------------------------ scène du Soleil (idée n° 3)
SUN_CX, SUN_CY, SUN_R = 540.0, 2460.0, 1240.0          # limbe au plus haut en y = 1220
SY0 = 860


def _sun():
    r = np.random.default_rng(91)
    yy = np.arange(H, dtype=f32)[:, None]
    bg = C3(0.004, 0.004, 0.010) + (np.clip((yy - 300) / 1200, 0, 1) ** 2)[..., None] * C3(0.030, 0.012, 0.006)
    bg = np.broadcast_to(bg, (H, W, 3)).astype(f32).copy()
    n = 420
    sx, sy = r.uniform(0, W, n), r.uniform(0, 1150, n)
    st = np.zeros((H, W), f32)
    st[sy.astype(int), sx.astype(int)] = (r.uniform(0.2, 1.0, n) ** 2 * 3.0).astype(f32)
    bg += cv2.GaussianBlur(st, (0, 0), 0.8)[..., None] * C3(0.8, 0.85, 1.0)
    yy, xx = np.mgrid[SY0:H, 0:W].astype(f32)
    dx, dy = xx - f32(SUN_CX), yy - f32(SUN_CY)
    rr = np.sqrt(dx * dx + dy * dy)
    inside = np.clip(f32(SUN_R) - rr + 0.5, 0, 1)
    mu = np.sqrt(np.clip(1 - (rr / f32(SUN_R)) ** 2, 0, 1))
    limb = (0.32 + 0.68 * mu ** 0.55) * inside
    col_c, col_e = C3(1.0, 0.78, 0.42), C3(1.0, 0.36, 0.07)
    colmap = (col_e + (col_c - col_e) * (mu[..., None] ** 0.8)).astype(f32)
    out = rr - f32(SUN_R)
    corona = (np.exp(-np.maximum(out, 0) / 70.0) * 1.6 + np.exp(-np.maximum(out, 0) / 360.0) * 0.45) * (out > -1.5)
    gran = np.tanh(tile_noise(1080, (2.6, 1.1), 12) * 1.4).astype(f32)
    return bg, inside.astype(f32), mu.astype(f32), limb.astype(f32), colmap, corona.astype(f32), gran


SUN_BG, SUN_IN, SUN_MU, SUN_LIMB, SUN_COL, SUN_COR, SUN_GRAN = _sun()
PROMS = [(300.0, 150.0, 115.0, 0.0), (800.0, 105.0, 80.0, 1.7)]


def limb_y(x):
    return SUN_CY - math.sqrt(max(SUN_R ** 2 - (x - SUN_CX) ** 2, 0.0))


def sun_world(t):
    hdr = SUN_BG.copy()
    tr = G[2]["reveal"]
    pulse = 1.0 + (0.7 * math.exp(-(t - tr) / 0.6) if t >= tr else 0.0)
    M = np.array([[1, 0, -(t * 7.0) % 1080], [0, 1, -(t * 2.0) % 1080]], np.float64)
    g = cv2.warpAffine(SUN_GRAN, M, (1080, 1080), borderMode=cv2.BORDER_WRAP)[:H - SY0]
    surf = SUN_LIMB * (1.0 + 0.16 * g * SUN_MU) * f32(5.5 * pulse)
    reg = hdr[SY0:]
    reg *= (1 - SUN_IN)[..., None]
    reg += surf[..., None] * SUN_COL
    reg += (SUN_COR * f32(pulse))[..., None] * C3(1.0, 0.50, 0.18)
    lay = np.zeros((H, W), np.uint8)
    for (xc, hw, hgt, ph) in PROMS:
        xa, xb = xc - hw, xc + hw
        ya, yb = limb_y(xa), limb_y(xb)
        h = hgt * (1 + 0.08 * math.sin(t * 1.3 + ph))
        u = np.linspace(0, 1, 60)
        xs = xa + (xb - xa) * u
        ys = ya + (yb - ya) * u - h * np.sin(np.pi * u) ** 0.9 + 6 * np.sin(u * 9 + t * 2 + ph)
        q = np.round(np.stack([xs, ys], 1) * 16).astype(np.int32)
        cv2.polylines(lay, [q], False, 255, 7, cv2.LINE_AA, 4)
    m = lay[SY0 - 200:].astype(f32) / 255.0
    gm = cv2.GaussianBlur(m, (0, 0), 6.0)
    hdr[SY0 - 200:] += (m * 2.2 + gm * 2.5)[..., None] * C3(1.0, 0.36, 0.10) * f32(pulse)
    return hdr, 0.0


# ------------------------------------------------------------------ monde (HDR)
NRAIN = 800


def storm_clouds(hdr, t, lights):
    M1 = np.array([[1, 0, -(t * 14.0) % 1080], [0, 1, 0]], np.float64)
    M2 = np.array([[1, 0, -(t * 26.0) % 1080], [0, 1, 0]], np.float64)
    n1 = cv2.warpAffine(A.N1, M1, (W, H), borderMode=cv2.BORDER_WRAP)
    n2 = cv2.warpAffine(A.N2, M2, (W, H), borderMode=cv2.BORDER_WRAP)
    dens = np.clip((n1 * 0.85 + n2 * 0.35 + 0.35) * A._prof, 0, 1.6)
    hdr += (dens ** 1.4)[..., None] * C3(0.020, 0.024, 0.036)
    if lights:
        q = np.zeros((H // 8, W // 8), f32)
        xs8, ys8 = XS[::8, ::8], YS[::8, ::8]
        for v, p in lights:
            q += f32(v) * (0.75 * np.exp(-((xs8 - p[0]) ** 2 + (ys8 - p[1] - 120) ** 2) / f32(2 * 420.0 ** 2)) + 0.22)
        L = cv2.resize(q, (W, H), interpolation=cv2.INTER_LINEAR)
        hdr += (dens * L)[..., None] * C3(0.50, 0.56, 0.85) * f32(0.72)
        hdr += (L * 0.035)[..., None] * C3(0.6, 0.65, 1.0)


def rain(hdr, t, flash):
    lm = [np.zeros((H, W), np.uint8) for _ in range(3)]
    sl = slice(0, NRAIN)
    y = (A.R_Y[sl] + A.R_V[sl] * t) % (H + 200) - 100
    x = (A.R_X[sl] + 0.20 * (A.R_V[sl] * t)) % (W + 400) - 200
    cls = A.R_A[sl]
    for k in range(3):
        sel = cls == k
        p0 = np.stack([x[sel], y[sel]], 1)
        p1 = p0 - np.stack([0.20 * A.R_L[sl][sel], A.R_L[sl][sel]], 1)
        q = np.clip(np.round(np.stack([p0, p1], 1) * 16), -1e8, 1e8).astype(np.int32)
        cv2.polylines(lm[k], list(q), False, 255, 1, cv2.LINE_AA, 4)
    r_ = (lm[0].astype(f32) * 0.05 + lm[1].astype(f32) * 0.10 + lm[2].astype(f32) * 0.18) / 255.0
    hdr += r_[..., None] * (C3(0.10, 0.12, 0.16) + C3(0.45, 0.50, 0.65) * f32(flash))


def draw_person(hdr, m, flash, a=1.0):
    if a <= 0.003:
        return
    mm = (m * f32(a))[..., None]
    col = C3(0.30, 0.33, 0.40) * f32(1.0 + 1.6 * flash)
    hdr[:] = hdr * (1 - mm) + mm * col


def sparks(hdr, t, a):
    r = np.random.default_rng(int(t * 30) * 7 + 3)
    segs = []
    for _ in range(9):
        cx = r.uniform(VIC_X - 1.50 * VIC_K, VIC_X - 0.15 * VIC_K)
        cy = r.uniform(HZ - 70, HZ - 8)
        pts = [(cx, cy)]
        for _ in range(4):
            cx += r.normal(0, 14)
            cy += r.normal(-10, 10)
            pts.append((cx, cy))
        segs.append(np.array(pts))
    m, b = line_mask(segs, 2)
    if m is not None:
        x0, y0, x1, y1 = b
        hdr[y0:y1, x0:x1] += (m * f32(2.5 * a))[..., None] * C3(0.55, 0.80, 1.0)
        g = cv2.GaussianBlur(m, (0, 0), 5)
        hdr[y0:y1, x0:x1] += (g * f32(2.0 * a))[..., None] * C3(0.40, 0.65, 1.0)


def world(t):
    sc = scene(t)
    if sc == "S":
        return sun_world(t)
    hdr = A.SKY.copy()
    sts = STRIKES[sc]
    lights = [(s.level(t, 0.10), s.p0) for s in sts]
    lights = [(v, p) for v, p in lights if v > 0.01]
    flash = min(sum(v for v, _ in lights), 2.5)
    storm_clouds(hdr, t, lights)
    if sc == "A":
        a = A.CITY_A[..., None]
        hdr = hdr * (1 - a) + A.CITY_RGB * a
        hdr += A.CITY_WIN
        if flash > 0.01:
            hdr += (A.TOWER_EDGE * f32(0.9 * flash))[..., None] * C3(0.55, 0.65, 1.0)
            hdr += (A.TOWER_TOP * f32(0.6 * flash))[..., None] * C3(0.55, 0.65, 1.0)
            hdr += (A.CITY_A * f32(0.012 * flash))[..., None] * C3(0.6, 0.7, 1.0)
        if (t % 1.6) < 0.55:
            add_glow(hdr, TIP[0], TIP[1] + 3, 1.6, C3(1.0, 0.12, 0.08), core=2.2, halo=7.0, ext=70)
    else:
        a = FIELD_A[..., None]
        hdr = hdr * (1 - a) + FIELD_RGB * a
        hdr += FIELD_WIN
        hdr += (FIELD_SHEEN * f32(0.10 * flash + 0.012))[..., None] * C3(0.45, 0.50, 0.70)
        if sc == "T":
            tm = TREE_M[..., None]
            hdr = hdr * (1 - tm) + tm * C3(0.006, 0.006, 0.008)
            hdr += (TREE_EDGE * f32(0.8 * flash + 0.04))[..., None] * C3(0.55, 0.62, 1.0)
            draw_person(hdr, UNDER, flash, 1.0 - sstep(P2C[0], P2C[0] + 0.5, t))
        else:
            draw_person(hdr, VICTIM, flash)
            a_sp = sstep(S[3] + 0.3, S[3] + 0.8, t) * (1 - sstep(P4A[0] + 0.4, P4A[0] + 1.2, t))
            if a_sp > 0.01:
                sparks(hdr, t, a_sp)
            draw_person(hdr, RESCUER, flash, sstep(P4B[0] + 0.4, P4B[0] + 1.0, t))
    rain(hdr, t, flash)
    for s in sts:
        I = s.level(t)
        Ib = s.branch_level(t)
        if I > 0.02 or Ib > 0.02:
            A.draw_bolt(hdr, s.main, s.br, I, Ib)
    return hdr, flash


CAM_C = {"A": (540.0, 1250.0), "T": (540.0, 1300.0), "S": (540.0, 1150.0), "V": (540.0, 1300.0)}


def cam_params(t):
    t0, t1 = scene_span(t)
    s = 1.0 + 0.05 * smoother((t - t0) / max(t1 - t0, 1e-3))
    return s, CAM_C[scene(t)]


def camera(hdr, t):
    s, (cx, cy) = cam_params(t)
    M = np.array([[s, 0, (1 - s) * cx], [0, s, (1 - s) * cy]], np.float64)
    return cv2.warpAffine(hdr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def cam_pt(p, t):
    s, (cx, cy) = cam_params(t)
    return (cx + (p[0] - cx) * s, cy + (p[1] - cy) * s)


# ------------------------------------------------------------------ texte avec contrôle des zones sûres
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
    A.big_text(img, txt, path, size, x, baseline, scale, col, a, sh)
    w = text_width(txt, path, size) * scale
    _log(txt, x - w / 2, baseline - 0.74 * size * scale, x + w / 2, baseline + 0.05 * size * scale, a)


def PILL(img, txt, x, y, bg, fg, a, size=40, pad=26, tracking=3.0, path=F_DBLACK):
    if a <= 0.003:
        return
    A.pill(img, txt, x, y, bg, fg, a, size, pad, tracking, path)
    w = text_width(txt, path, size, tracking)
    _log(txt, x - w / 2 - pad, y - size * 0.92, x + w / 2 + pad, y + size * 0.42, a)


def ain(t, t0, d=0.35):
    return eout(sat((t - t0) / d), 3)


def section(t, t0, t1):
    return bump(t, t0, t0 + 0.35, t1 - 0.35, t1 - 0.05)


# ------------------------------------------------------------------ icônes (espace d'affichage)
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
    stroke(img, [np.array([(x - d, y - d), (x + d, y + d)]), np.array([(x - d, y + d), (x + d, y - d)])], WHITE, a, int(s * 0.18))


def icon_aid(img, x, y, s, a):
    fill_over(img, [rounded_rect(x - s, y - s, x + s, y + s, s * 0.3)], GREEN, a)
    w, L = s * 0.28, s * 0.70
    fill_over(img, [np.array([(x - w, y - L), (x + w, y - L), (x + w, y + L), (x - w, y + L)]),
                    np.array([(x - L, y - w), (x + L, y - w), (x + L, y + w), (x - L, y + w)])], WHITE, a)


def icon_phone(img, x, y, a):
    if a <= 0.003:
        return
    fill_over(img, [rounded_rect(x - 78, y - 118, x + 78, y + 118, 22)], C3(0.08, 0.10, 0.14), a)
    stroke(img, [rounded_rect(x - 78, y - 118, x + 78, y + 118, 22)], LIGHT, a, 5)
    T(img, "112", F_DBLACK, 70, x, y + 22, WHITE, a, 0, 0.0, sh=False)
    fill_over(img, [circle_pts(x, y + 90, 11, 30)], LIGHT, a * 0.8)


def icon_house(img, x, y, s, a):
    P = np.array([(x - s, y + s), (x - s, y - s * 0.2), (x, y - s), (x + s, y - s * 0.2), (x + s, y + s), (x - s, y + s)])
    fill_over(img, [P], C3(0.08, 0.10, 0.14), a * 0.9)
    stroke(img, [P], WHITE, a, 6)
    stroke(img, [np.array([(x - s * 0.25, y + s), (x - s * 0.25, y + s * 0.3), (x + s * 0.25, y + s * 0.3), (x + s * 0.25, y + s)])],
           WHITE, a, 5)


def icon_car(img, x, y, s, a):
    body = np.array([(x - s * 1.25, y + s * 0.25), (x - s * 1.2, y - s * 0.15), (x - s * 0.7, y - s * 0.25),
                     (x - s * 0.4, y - s * 0.70), (x + s * 0.45, y - s * 0.70), (x + s * 0.80, y - s * 0.25),
                     (x + s * 1.22, y - s * 0.12), (x + s * 1.25, y + s * 0.25)])
    fill_over(img, [body], C3(0.08, 0.10, 0.14), a * 0.9)
    stroke(img, [np.vstack([body, body[:1]])], WHITE, a, 6)
    for wx in (-0.68, 0.70):
        fill_over(img, [circle_pts(x + s * wx, y + s * 0.30, s * 0.28, 40)], WHITE, a)
        fill_over(img, [circle_pts(x + s * wx, y + s * 0.30, s * 0.12, 30)], C3(0.08, 0.10, 0.14), a)


def dashed_v(img, x, y0, y1, col, a, dash=12, gap=9, th=3):
    segs = []
    y = y0
    while y < y1:
        segs.append(np.array([(x, y), (x, min(y + dash, y1))]))
        y += dash + gap
    stroke(img, segs, col, a, th)


# ------------------------------------------------------------------ blocs d'interface communs
STAMPS = {"FAUX": A.STAMP, "VRAI": A.stamp_mask("VRAI")}
VCOL = {"FAUX": CORAL, "VRAI": GREEN}


def claim_block(img, t, g):
    a_c = 1 - sstep(g["body"] - 0.35, g["body"] - 0.05, t)
    if a_c > 0 and t >= g["claim"]:
        lines = wrap(CLAIMS[g["i"]], F_DXB, 80, 820)
        PARA(img, lines, F_DXB, 80, 540, 470, WHITE, a_c, 0, 1.10, t=t, t0=g["claim"])


def countdown(img, t, g):
    if g["cd"] <= t < g["reveal"] + 0.25:
        a0 = ain(t, g["cd"], 0.25) * (1 - sstep(g["reveal"] - 0.05, g["reveal"] + 0.15, t))
        cx, cy, R = 540, 1060, 128
        fill_over(img, [circle_pts(cx, cy, R + 18, 120)], INK, 0.78 * a0)
        prog = 1 - sat((t - g["cd"]) / (g["reveal"] - g["cd"]))
        if prog > 0.002:
            stroke(img, [circle_pts(cx, cy, R, 160, -math.pi / 2, -math.pi / 2 + TAU * prog)], CYAN, a0, 10)
        k = min(int((t - g["cd"]) / 0.65), 2)
        u = (t - g["cd"] - k * 0.65) / 0.22
        sc = 1.0 + 0.35 * (1 - eout(sat(u), 3))
        BIG(img, str(3 - k), F_DBLACK, 190, cx, cy + 0.36 * 190, sc, WHITE, a0 * eout(sat(u * 1.5), 2), sh=False)
        T(img, "TA RÉPONSE ?", F_DBOLD, 42, 540, 1240, LIGHT, a0, 0, 4.0)


def verdict(img, t, g):
    lab = VERDICT[g["i"]]
    col = VCOL[lab]
    if g["reveal"] <= t < g["end"]:
        u = (t - g["reveal"]) / 0.30
        moving = sstep(g["body"] - 0.45, g["body"] + 0.05, t)
        sc = (2.1 - 1.1 * back_out(sat(u), 1.4)) * (1 - 0.72 * moving)
        cy = 1040 + (392 - 1040) * smoother(moving)
        a = eout(sat(u * 3), 2) * (1 - sstep(g["end"] - 0.3, g["end"] - 0.05, t))
        if moving < 1:
            A.put_rot(img, STAMPS[lab], 540, cy, sc * 0.95, (8 if lab == "FAUX" else -6) * (1 - moving), col, a)
        else:
            PILL(img, lab, 540, 410, col, WHITE, a, size=44, pad=30, tracking=4.0)


# ------------------------------------------------------------------ interface complète
def ui(img, t):
    # bandeau de série (visible dès la 1re image) + numéro de l'idée reçue
    a_p = 1.0
    PILL(img, "VRAI OU FAUX ?", 540, 318, C3(0.06, 0.07, 0.10), WHITE, 0.92 * a_p)
    wpill = text_width("VRAI OU FAUX ?", F_DBLACK, 40, 3.0)
    for i in range(4):
        nxt = FL[i]
        ai = ain(t, S[i], 0.3) * (1 - sstep(nxt - 0.25, nxt, t))
        if ai > 0:
            fill_over(img, [rounded_rect(540 + wpill / 2 + 36, 280, 540 + wpill / 2 + 130, 330, 25)], CORAL, ai)
            T(img, f"{i + 1}/4", F_DBLACK, 32, 540 + wpill / 2 + 83, 316, WHITE, ai, 0, 0.0, sh=False)
    # titre d'ouverture (lisible dès la 1re image : c'est aussi la miniature)
    a_t = 1 - sstep(S[0] - 0.35, S[0] - 0.05, t)
    if a_t > 0:
        T(img, "4 IDÉES REÇUES", F_DBLACK, 96, 540, 590, WHITE, a_t, 0, 1.0)
        T(img, "SUR LA FOUDRE", F_DBLACK, 96, 540, 700, CYAN, a_t, 0, 1.0)
        T(img, "Compte tes bonnes réponses", F_MEDI, 46, 540, 800, LIGHT, a_t * ain(t, 0.45))
    for g in G:
        claim_block(img, t, g)
        countdown(img, t, g)
        verdict(img, t, g)

    # ---------- idée n° 1 : deux fois au même endroit
    a = section(t, *P1A)
    if a > 0:
        T(img, "L'Empire State Building", F_DXB, 70, 540, 540, WHITE, a * ain(t, P1A[0]))
        T(img, "est frappé en moyenne", F_MEDI, 54, 540, 612, LIGHT, a * ain(t, P1A[0] + 0.12))
        n = sum(1 for tk in T23 if t >= tk)
        al = a * ain(t, P1A[0] + 0.25)
        u = 9.0
        for tk in T23:
            if t >= tk:
                u = t - tk
        BIG(img, str(n), F_DBLACK, 250, 540, 905, 1 + 0.12 * math.exp(-u / 0.08), WHITE if n < 23 else CYAN, al)
        T(img, "fois par an", F_DBOLD, 64, 540, 985, WHITE, al)
        p = sat((t - T23[0] + 0.3) / (T23[-1] - T23[0] + 0.4))
        fill_over(img, [rounded_rect(300, 1040, 780, 1050, 5)], C3(0.25, 0.28, 0.34), al)
        if p > 0.01:
            fill_over(img, [rounded_rect(300, 1040, 300 + 480 * p, 1050, 5)], CYAN, al)
        T(img, "EN 1 AN", F_DBOLD, 28, 540, 1097, LIGHT, al, 0, 4.0)
    a = section(t, *P1B)
    if a > 0:
        T(img, "Encore plus fort :", F_DBOLD, 56, 540, 530, CYAN, a * ain(t, P1B[0]))
        PARA(img, wrap("un seul éclair frappe en général 3 à 4 fois au même endroit", F_DXB, 72, 820), F_DXB, 72, 540, 622,
             WHITE, a, 0, 1.10, t=t, t0=P1B[0] + 0.12)
        for k, (dt, I) in enumerate(SLOW.strokes):
            tk = SLOW.t0 + dt
            if t >= tk:
                uu = (t - tk) / 0.18
                BIG(img, str(k + 1), F_DBLACK, 110, 200 + k * 120, 1185, 1 + 0.4 * (1 - eout(sat(uu), 3)),
                    WHITE if k < 3 else CYAN, a * eout(sat(uu), 3))
        if t > SLOW.t0 - 0.3:
            T(img, "AU RALENTI", F_DBOLD, 30, 380, 1240, CYAN, a * 0.9, 0, 5.0)
        PARA(img, ["C'est ce qui le fait", "scintiller."], F_MEDI, 44, 540, 975, LIGHT, a * ain(t, SLOW.t0 + 2.3, 0.4), 0, 1.15)

    # ---------- idée n° 2 : l'arbre
    a = section(t, *P2A)
    if a > 0:
        T(img, "La foudre frappe surtout", F_DXB, 66, 540, 548, WHITE, a * ain(t, P2A[0]))
        T(img, "ce qui est :", F_DXB, 66, 540, 622, WHITE, a * ain(t, P2A[0] + 0.1))
        words = ["HAUT", "POINTU", "ISOLÉ"]
        sep = "  ·  "
        wsep = text_width(sep, F_DBLACK, 66, 1.0)
        ww = [text_width(w_, F_DBLACK, 66, 1.0) for w_ in words]
        x = 540 - (sum(ww) + 2 * wsep) / 2
        for k, w_ in enumerate(words):
            ak = a * ain(t, P2A[0] + 0.30 + 0.70 * k)
            T(img, w_, F_DBLACK, 66, x, 730, CYAN, ak, -1, 1.0)
            if k < 2:
                T(img, "·", F_DBLACK, 66, x + ww[k] + wsep / 2, 730, LIGHT, ak * 0.8, 0, 0.0)
            x += ww[k] + wsep
        # repères sur l'arbre
        top = cam_pt(TREE_TOP, t)
        ground = cam_pt((TREE_X, HZ), t)
        a1 = a * ain(t, P2A[0] + 0.30, 0.4)
        if a1 > 0:
            xa = cam_pt((TREE_XR[0] - 70, HZ), t)[0]
            yy = top[1] + (ground[1] - top[1]) * (1 - a1)
            stroke(img, [[(xa, yy), (xa, ground[1])], [(xa - 14, yy + 22), (xa, yy), (xa + 14, yy + 22)]], CYAN, a1, 4)
        a2 = a * ain(t, P2A[0] + 1.00, 0.4)
        if a2 > 0:
            stroke(img, [circle_pts(top[0], top[1] + 8, 40 + 30 * (1 - a2), 80)], CYAN, a2, 4)
        a3 = a * ain(t, P2A[0] + 1.70, 0.4)
        if a3 > 0:
            yv = ground[1] - 70
            for sgn in (-1, 1):
                xs = TREE_X + sgn * 60
                xe = xs + sgn * (140 * a3)
                stroke(img, [[(xs, yv), (xe, yv)], [(xe - sgn * 18, yv - 14), (xe, yv), (xe - sgn * 18, yv + 14)]], CYAN, a3, 4)
    a = section(t, *P2B)
    if a > 0:
        T(img, "Sous un arbre :", F_DBOLD, 56, 540, 548, CYAN, a * ain(t, P2B[0]))
        PARA(img, ["c'est la 2ᵉ cause", "de victimes", "de la foudre"], F_DXB, 78, 540, 640, WHITE, a, 0, 1.05, t=t,
             t0=P2B[0] + 0.12)
        T(img, "(chiffre du NWS, États-Unis)", F_MEDI, 32, 540, 880, LIGHT, a * ain(t, P2B[0] + 0.6))
        px, py = cam_pt((UNDER_X + 70, HZ - 250), t)
        icon_cross(img, px, py, 40, a * ain(t, P2B[0] + 0.5, 0.3))
    a = section(t, *P2C)
    if a > 0:
        T(img, "Le bon réflexe :", F_DBOLD, 56, 540, 548, CYAN, a * ain(t, P2C[0]))
        PARA(img, wrap("un bâtiment en dur ou une voiture à toit rigide", F_DXB, 68, 820), F_DXB, 68, 540, 636, WHITE, a, 0,
             1.10, t=t, t0=P2C[0] + 0.12)
        ac = a * ain(t, P2C[0] + 0.45)
        fill_over(img, [rounded_rect(200, 925, 790, 1150, 34)], INK, 0.82 * ac)
        ah, av = a * ain(t, P2C[0] + 0.6), a * ain(t, P2C[0] + 0.95)
        icon_house(img, 335, 1045, 66, ah)
        icon_check(img, 398, 978, 28, ah)
        icon_car(img, 640, 1058, 66, av)
        icon_check(img, 728, 978, 28, av)

    # ---------- idée n° 3 : plus chaude que le Soleil
    a = section(t, *P3A)
    if a > 0:
        T(img, "Combien de degrés ?", F_DXB, 76, 540, 560, WHITE, a * ain(t, P3A[0]))
        T(img, "Foudre contre surface du Soleil", F_MEDI, 44, 540, 636, LIGHT, a * ain(t, P3A[0] + 0.12))
    a = section(t, *P3B)
    if a > 0:
        T(img, "Deux pages de la NOAA", F_DBOLD, 58, 540, 548, WHITE, a * ain(t, P3B[0]))
        T(img, "donnent deux chiffres…", F_DBOLD, 58, 540, 618, WHITE, a * ain(t, P3B[0] + 0.1))
        T(img, "…mais la même conclusion :", F_MEDI, 44, 540, 696, LIGHT, a * ain(t, P3B[0] + 0.9))
        T(img, "1,8 à 5 fois plus chaude", F_DXB, 66, 540, 790, CYAN, a * ain(t, P3B[0] + 1.3))
    a = bump(t, P3A[0] + 0.1, P3A[0] + 0.45, P3B[1] - 0.35, P3B[1] - 0.05)
    if a > 0:
        bars(img, t, a)

    # ---------- idée n° 4 : toucher une victime
    a = section(t, *P4A)
    if a > 0:
        PARA(img, wrap("Le corps humain ne stocke pas l'électricité.", F_DXB, 76, 820), F_DXB, 76, 540, 560, WHITE, a, 0,
             1.10, t=t, t0=P4A[0])
    a = section(t, *P4B)
    if a > 0:
        PARA(img, wrap("Tu peux la toucher sans danger pour lui porter secours.", F_DXB, 70, 820), F_DXB, 70, 540, 556,
             WHITE, a, 0, 1.10, t=t, t0=P4B[0])
        ak = a * ain(t, P4B[0] + 0.5, 0.3)
        icon_aid(img, 540, 905, 40 * (0.6 + 0.4 * ak), ak)
    a = section(t, *P4C)
    if a > 0:
        T(img, "Le bon réflexe :", F_DBOLD, 56, 540, 548, CYAN, a * ain(t, P4C[0]))
        T(img, "appeler le 112", F_DXB, 92, 540, 652, WHITE, a * ain(t, P4C[0] + 0.15))
        T(img, "numéro d'urgence européen, gratuit", F_MEDI, 40, 540, 728, LIGHT, a * ain(t, P4C[0] + 0.45))
        icon_phone(img, 540, 975, a * ain(t, P4C[0] + 0.6))

    # ---------- fin : score, sources, épisode suivant
    a = section(t, *P5A)
    if a > 0:
        T(img, "TON SCORE ?", F_DBLACK, 96, 540, 600, WHITE, a * ain(t, P5A[0]), 0, 1.0)
        BIG(img, "?/4", F_DBLACK, 220, 540, 880, 1.0 + 0.06 * math.sin((t - S_OUT) * 6), CYAN, a * ain(t, P5A[0] + 0.25))
        T(img, "Dis-le en commentaire", F_MEDI, 44, 540, 990, LIGHT, a * ain(t, P5A[0] + 0.6))
    a = ain(t, P5B[0], 0.4) * (1 - sstep(DUR - 0.18, DUR - 0.06, t))
    if a > 0:
        T(img, "SOURCES", F_DBOLD, 30, 540, 520, LIGHT, a * 0.85, 0, 6.0)
        PARA(img, wrap("National Weather Service et NSSL (NOAA), UCAR, service-public.gouv.fr", F_SEMI, 38, 800), F_SEMI, 38,
             540, 580, WHITE, a, 0, 1.15)
        a2 = a * ain(t, P5B[0] + 0.5, 0.4)
        T(img, "PROCHAIN ÉPISODE", F_DBOLD, 30, 540, 722, CYAN, a2, 0, 6.0)
        PARA(img, wrap("« On n'utilise que 10 % de notre cerveau »", F_DXB, 56, 800), F_DXB, 56, 540, 792, WHITE, a2, 0, 1.10)
        a3 = a * ain(t, P5B[0] + 1.0, 0.4)
        PILL(img, "VRAI OU FAUX ?", 540, 1000, CYAN, C3(0.02, 0.04, 0.06), a3, size=40)
        T(img, "Abonne-toi pour la réponse", F_SEMI, 36, 540, 1100, LIGHT, a3)


ROWS = [("Surface du Soleil", "5 500 °C", 5500.0, SUNC, 0.0),
        ("Foudre (NSSL)", "10 000 °C", 9982.0, CYAN, 0.7),
        ("Foudre (NWS)", "27 800 °C", 27760.0, C3(0.85, 0.92, 1.0), 1.4)]
BX0, BLEN, Y0R, DYR = 180.0, 560.0, 905.0, 105.0


def bars(img, t, a):
    t0 = P3A[0] + 0.20
    fill_over(img, [rounded_rect(150, 845, 790, 1245, 34)], INK, 0.80 * a)
    for k, (lab, val, tv, col, d) in enumerate(ROWS):
        ak = a * ain(t, t0 + d)
        if ak <= 0:
            continue
        y = Y0R + k * DYR
        T(img, lab, F_SEMI, 30, BX0, y, LIGHT, ak, -1)
        T(img, val, F_DBOLD, 40, 760, y, WHITE, ak, 1)
        fill_over(img, [rounded_rect(BX0, y + 16, BX0 + BLEN, y + 40, 12)], C3(0.12, 0.13, 0.17), ak * 0.9)
        L = BLEN * tv / 27760.0 * eout(sat((t - t0 - d - 0.1) / 0.6), 3)
        if L > 2:
            fill_over(img, [rounded_rect(BX0, y + 16, BX0 + L, y + 40, 12)], col, ak)
    al = a * ain(t, t0 + 2.1, 0.4)
    if al > 0:
        dashed_v(img, BX0 + BLEN * 5500.0 / 27760.0, Y0R + 8, Y0R + 2 * DYR + 48, SUNC, al)
    T(img, "Sources : UCAR · NSSL et NWS (NOAA)", F_MEDI, 26, 470, 1222, LIGHT, a * ain(t, t0 + 1.6) * 0.85)


def whiteout(t):
    v = 0.0
    for tf in FL:
        u = t - tf
        if -0.06 <= u < 0:
            v = max(v, (u + 0.06) / 0.06 * 0.8)
        elif 0 <= u < 0.6:
            v = max(v, 0.85 * math.exp(-u / 0.13))
    return v


def render(t, seed=0):
    hdr, flash = world(t)
    hdr = camera(hdr, t)
    sh = (0.0, 0.0)
    for g in G:
        if g["reveal"] <= t < g["reveal"] + 0.35:
            u = (t - g["reveal"]) / 0.35
            amp = 14 * (1 - u) ** 2
            sh = (amp * math.sin(t * 97), amp * math.cos(t * 83))
    out = finalize(hdr, 1.0, seed, grain=0.0, shake=sh)
    img = out.astype(f32) / 255.0
    img *= 1 - A.SCRIM
    ui(img, t)
    wo = whiteout(t)
    if wo > 0:
        img = img * (1 - wo) + f32(wo) * C3(0.92, 0.95, 1.0)
    return np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)


def frame_png(args):
    i, outdir = args
    p = os.path.join(outdir, f"f_{i:04d}.png")
    tmp = p + ".tmp.png"
    Image.fromarray(render(i / FPS, seed=i)).save(tmp, compress_level=1)
    os.replace(tmp, p)
    return i


def audit(step=1):
    """Rejoue toute l'interface et signale le texte hors des zones sûres TikTok."""
    global LOG
    bad = {}
    img = np.zeros((H, W, 3), f32)
    for i in range(0, NF, step):
        t = i / FPS
        LOG = []
        img[:] = 0
        ui(img, t)
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


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "stills":
        outdir = sys.argv[2]
        os.makedirs(outdir, exist_ok=True)
        for ts in sys.argv[3:]:
            t = float(ts)
            t0 = time.time()
            Image.fromarray(render(t, int(round(t * FPS)))).save(os.path.join(outdir, f"f_{t:06.3f}.png"))
            print(f"t={t:.3f}  {time.time() - t0:.2f}s", flush=True)
    elif mode == "frames":
        outdir = sys.argv[2]
        os.makedirs(outdir, exist_ok=True)
        todo = [(i, outdir) for i in range(NF) if not os.path.exists(os.path.join(outdir, f"f_{i:04d}.png"))]
        t0 = time.time()
        with mp.get_context("fork").Pool(2) as pool:
            for k, i in enumerate(pool.imap_unordered(frame_png, todo, chunksize=1)):
                if k % 100 == 0:
                    print(f"{k}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
        print("done", round(time.time() - t0), "s", flush=True)
    elif mode == "audit":
        bad = audit(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
        print(f"{NF} images, durée {DUR} s, {len(bad)} problème(s)")
        for (txt, why), v in sorted(bad.items(), key=lambda kv: kv[1][0]):
            print(f"  t={v[0]:6.2f}  [{why}]  {txt!r}  bbox={v[1:]}")
