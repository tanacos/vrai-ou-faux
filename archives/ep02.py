#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VRAI OU FAUX ? #2 — Spécial cerveau : 4 idées reçues (70 s, 1080 x 1920, 30 i/s).
Sources des faits affichés : Santé.fr (SPIS), Raichle & Gusnard 2002 (PNAS), BrainFacts/SfN 2021,
Université de l'Utah 2013 (PLOS ONE), Azevedo et al. 2009 (via MIT CBMM), NASA (Blueshift 2015), UCLA BRI.
  python3 ep02.py stills OUTDIR t1 t2 ...
  python3 ep02.py frames OUTDIR              (PNG, reprise possible)
  python3 ep02.py audit [pas]                (zones sûres TikTok)
"""
import math
import multiprocessing as mp
import os
import sys
import time

sys.path.insert(0, "/home/claude/vf")
from vlib import *  # noqa: F401,F403
import vui as U
from vui import T, PARA, BIG, PILL, ain, section, stroke, CORAL, CYAN, WHITE, LIGHT, GREEN, INK
import brain2 as BR

NB = " "


def fr(s):
    """Espaces insécables de la typographie française (guillemets, %, :, ?, !, milliers)."""
    s = s.replace("« ", "«" + NB).replace(" »", NB + "»").replace(" %", NB + "%")
    s = s.replace(" :", NB + ":").replace(" ?", NB + "?").replace(" !", NB + "!")
    for a, b in (("1 011", "1" + NB + "011"), ("100 000", "100" + NB + "000"), ("10 000", "10" + NB + "000")):
        s = s.replace(a, b)
    return s


# ------------------------------------------------------------------ chronologie
TL = U.Timeline([16.45, 32.30, 46.80, 62.75], 70.0)
DUR, NF, FL, CUT, S, G = TL.DUR, TL.NF, TL.FL, TL.CUT, TL.S, TL.G
VERDICT = ["FAUX", "VRAI", "FAUX", "FAUX"]
CLAIMS = [fr("« On n'utilise que 10 % de notre cerveau. »"),
          fr("« Le cerveau ne ressent pas la douleur. »"),
          fr("« Les logiques utilisent le cerveau gauche, les créatifs le droit. »"),
          fr("« Il y a plus de neurones dans ton cerveau que d'étoiles dans la Voie lactée. »")]
CLAIM_SIZE = [80, 80, 72, 76]
P1A = (G[0]["body"], G[0]["body"] + 4.40)
P1B = (P1A[1], P1A[1] + 2.70)
P1C = (P1B[1], FL[0] - 0.10)
P2A = (G[1]["body"], G[1]["body"] + 3.80)
P2B = (P2A[1], P2A[1] + 3.80)
P2C = (P2B[1], FL[1] - 0.10)
P3A = (G[2]["body"], G[2]["body"] + 3.30)
P3B = (P3A[1], P3A[1] + 2.90)
P3C = (P3B[1], FL[2] - 0.10)
P4A = (G[3]["body"], G[3]["body"] + 4.10)
P4B = (P4A[1], P4A[1] + 3.60)
P4C = (P4B[1], FL[3] - 0.10)
P5A = (TL.S_OUT + 0.20, TL.S_OUT + 3.40)
P5B = (P5A[1], DUR)

# ------------------------------------------------------------------ décors précalculés
BL = BR.lateral_brain(505.0, 1075.0, 650.0, seed=8)
HS = BR.head_scene(540.0, 1015.0, 470.0, seed=8)
DB = BR.dorsal_brain(540.0, 1075.0, 560.0, seed=5)
GT = BR.galaxy_texture()


def _background(top, bot, glow_xy, glow_col, glow_r, seed):
    yy = (np.arange(H, dtype=f32) / H)[:, None, None]
    bg = (top * (1 - yy) + bot * yy) * np.ones((1, W, 1), f32)
    d2 = (XS - f32(glow_xy[0])) ** 2 + (YS - f32(glow_xy[1])) ** 2
    bg += np.exp(-d2 / f32(2 * glow_r ** 2))[..., None] * glow_col
    return bg.astype(f32)


BG_BRAIN = _background(C3(0.004, 0.005, 0.014), C3(0.010, 0.012, 0.030), (505, 1075), C3(0.020, 0.040, 0.110), 420, 1)
BG_HEAD = _background(C3(0.004, 0.005, 0.014), C3(0.012, 0.010, 0.026), (540, 1000), C3(0.022, 0.030, 0.080), 400, 2)
BG_TOP = _background(C3(0.004, 0.005, 0.014), C3(0.010, 0.012, 0.030), (540, 1075), C3(0.020, 0.040, 0.110), 380, 3)


def _particles(n, seed, size=(2160, 1080), blur=2.2, inten=0.25):
    r = np.random.default_rng(seed)
    P = np.zeros((size[0], size[1], 3), f32)
    BR.splat2(P, r.uniform(0, size[1], n), r.uniform(0, size[0], n), r.uniform(0.3, 1.0, n) ** 2 * 6.0,
              np.broadcast_to(C3(0.45, 0.70, 1.0), (n, 3)).astype(f32))
    return (cv2.GaussianBlur(P, (0, 0), blur) * f32(inten)).astype(f32)


DUST_NEAR = _particles(260, 4, blur=3.0, inten=0.30)
DUST_FAR = _particles(700, 5, blur=1.2, inten=0.18)


def _stars(n, seed):
    r = np.random.default_rng(seed)
    P = np.zeros((H, W, 3), f32)
    cols = np.where((r.random(n) < 0.3)[:, None], C3(1.0, 0.85, 0.7), C3(0.75, 0.82, 1.0)).astype(f32)
    BR.splat2(P, r.uniform(0, W, n), r.uniform(0, H, n), r.uniform(0.2, 1.0, n) ** 3 * 4.0, cols)
    return cv2.GaussianBlur(P, (0, 0), 0.7).astype(f32)


STARS = _stars(1600, 9)


def drift(layer, t, vx, vy):
    h, w = layer.shape[:2]
    M = np.array([[1, 0, -(t * vx) % w], [0, 1, -(t * vy) % h]], np.float64)
    return cv2.warpAffine(layer, M, (w, h), borderMode=cv2.BORDER_WRAP)[:H, :W]


# ------------------------------------------------------------------ activité du cerveau de profil (idée n° 1)
_rng = np.random.default_rng(77)
NC = len(BL.cells)
_order_x = np.argsort(BL.seeds[:, 0] + 0.6 * BL.seeds[:, 1])      # zone frontale d'abord
_frac = BL.cell_area / BL.area
TEN = []
acc = 0.0
for k in _order_x:
    if acc + _frac[k] <= 0.10 + 1e-9:
        TEN.append((k, 1.0))
        acc += _frac[k]
    else:
        TEN.append((k, (0.10 - acc) / _frac[k]))
        acc = 0.10
        break
TEN_SET = {k for k, _ in TEN}
REST = [k for k in _rng.permutation(NC) if k not in TEN_SET or dict(TEN)[k] < 1.0]
T_CASCADE0, T_CASCADE1 = P1A[0] + 0.45, P1A[0] + 3.55


def activity(t):
    """Activation de chaque région (0..1) et fraction de cortex active."""
    a = np.zeros(NC, f32)
    sc = TL.scene_index(t)
    if sc == 4:
        a[:] = 1.0
    else:
        for k, v in TEN:
            a[k] = v
        for j, k in enumerate(REST):
            tk = T_CASCADE0 + (T_CASCADE1 - T_CASCADE0) * j / max(len(REST) - 1, 1)
            a[k] = max(a[k], sstep(tk, tk + 0.30, t))
    frac = float((a * _frac).sum())
    return a, frac


# réseau de neurones : influx qui voyagent sur les liaisons
_E = BL.edges
_N = BL.nodes
_rp = np.random.default_rng(91)
PULSES = []
for e_i in range(len(_E)):
    tt = _rp.uniform(-2, 0)
    while tt < DUR + 2:
        dur = _rp.uniform(0.35, 0.9)
        PULSES.append((e_i, tt, dur, _rp.random() < 0.5))
        tt += dur + _rp.exponential(1.6)
PULSES = np.array(PULSES, dtype=float)


def node_activity(a):
    x0, y0, x1, y1 = BL.box
    lab = BL.labels[np.clip((_N[:, 1] - y0).astype(int), 0, BL.labels.shape[0] - 1),
                    np.clip((_N[:, 0] - x0).astype(int), 0, BL.labels.shape[1] - 1)]
    return a[lab]


def draw_network(hdr, t, a, gain=1.0):
    na = node_activity(a)
    ea = np.minimum(na[_E[:, 0]], na[_E[:, 1]])
    m = np.zeros((H, W), np.uint8)
    segs = [np.round(np.array([_N[i], _N[j]]) * 16).astype(np.int32) for (i, j), v in zip(_E, ea) if v > 0.3]
    if segs:
        cv2.polylines(m, segs, False, 255, 1, cv2.LINE_AA, 4)
        hdr += (m.astype(f32) / 255.0 * f32(0.16 * gain))[..., None] * C3(0.35, 0.80, 1.0)
    on = (PULSES[:, 1] <= t) & (t < PULSES[:, 1] + PULSES[:, 2])
    for e_i, t0, du, rev in PULSES[on]:
        e_i = int(e_i)
        if ea[e_i] < 0.5:
            continue
        u = (t - t0) / du
        if rev:
            u = 1 - u
        i, j = _E[e_i]
        p = _N[i] + (_N[j] - _N[i]) * u
        add_glow(hdr, float(p[0]), float(p[1]), 1.8 * gain * math.sin(math.pi * min(max((t - t0) / du, 0), 1)),
                 C3(0.60, 0.95, 1.0), core=2.6, halo=8.0, ext=40)


def outline_glow(hdr, pts, col, I, th=2, blur=5.0, closed=True):
    m = np.zeros((H, W), np.uint8)
    cv2.polylines(m, [np.round(np.asarray(pts) * 16).astype(np.int32)], closed, 255, th, cv2.LINE_AA, 4)
    mm = m.astype(f32) / 255.0
    hdr += (mm * f32(I))[..., None] * col
    if blur > 0:
        hdr += (cv2.GaussianBlur(mm, (0, 0), blur) * f32(I * 1.2))[..., None] * col


_hh, _ww = BL.labels.shape
SPARK1 = BR.dog_noise((_hh, _ww), 0.010 * 650, 31)
SPARK2 = BR.dog_noise((_hh, _ww), 0.010 * 650, 32)


def cortex_glow(hdr, B, a, t, I=1.0, col=None):
    col = C3(0.22, 0.85, 1.0) if col is None else col
    img = a[B.labels]
    img = cv2.GaussianBlur(img, (0, 0), 0.022 * B.L) * B.mask_cer
    w = 7.0
    sp = 0.5 + 0.5 * np.tanh(1.3 * (SPARK1 * math.cos(w * t) + SPARK2 * math.sin(w * t)))
    em = img * (0.10 + 0.90 * B.g * B.g) * (0.35 + 0.65 * sp) * f32(I)
    halo = cv2.GaussianBlur(img, (0, 0), 0.05 * B.L) * f32(0.14 * I)
    BR.place(hdr, B, em[..., None] * col * f32(1.5))
    BR.place(hdr, B, halo[..., None] * col)


# ------------------------------------------------------------------ scènes
def world_brain(t):
    hdr = BG_BRAIN.copy()
    hdr += drift(DUST_FAR, t, 6, -9)
    hdr += drift(DUST_NEAR, t, -10, -16)
    fg = np.zeros_like(hdr)
    BR.composite(fg, BL, 1.0)
    a, frac = activity(t)
    outline_glow(fg, BL.outline, C3(0.30, 0.75, 1.0), 0.22, 2, 6.0)
    cortex_glow(fg, BL, a, t, 1.0)
    draw_network(fg, t, a, 1.0)
    dim = 1.0
    if TL.scene_index(t) == 4:
        dim = 1 - 0.50 * sstep(P5A[0] - 0.4, P5A[0] + 0.3, t)
    m = BL.mask
    x0, y0, x1, y1 = BL.box
    hdr[y0:y1, x0:x1] *= (1 - m)[..., None]
    hdr += fg * f32(dim)
    return hdr


def world_head(t):
    hdr = BG_HEAD.copy()
    hdr += drift(DUST_FAR, t, 5, -8) * f32(0.7)
    hdr += (HS.fill * 0.035)[..., None] * C3(0.30, 0.50, 0.95)
    B = HS.brain
    BR.composite(hdr, B, 1.0)
    outline_glow(hdr, B.outline, C3(0.30, 0.75, 1.0), 0.18, 2, 5.0)
    hb = 0.5 + 0.5 * math.sin(TAU * 1.15 * t) ** 8                  # battement (mal de tête)
    pain = sstep(P2C[0] + 0.2, P2C[0] + 0.8, t) * (1 - sstep(FL[1] - 0.4, FL[1], t))
    outline_glow(hdr, HS.head, C3(0.45, 0.85, 1.0), 0.75, 3, 5.0)
    outline_glow(hdr, HS.skull, C3(0.80, 0.85, 0.95), 0.16, 2, 0.0)
    dura_I = 0.10 + 0.45 * sstep(P2A[0], P2A[0] + 0.6, t) + pain * (0.6 + 0.9 * hb)
    outline_glow(hdr, HS.dura, C3(1.0, 0.25, 0.20), dura_I, 2, 4.0)
    if pain > 0.01:
        outline_glow(hdr, HS.head, C3(1.0, 0.25, 0.20), pain * (0.25 + 0.55 * hb), 3, 9.0)
    # balayage : les récepteurs s'allument sur les méninges et le crâne, jamais dans le cerveau
    x_scan = None
    if P2A[0] + 0.5 <= t < P2A[0] + 2.4:
        u = (t - P2A[0] - 0.5) / 1.9
        x_scan = 200 + 680 * smoother(u)
        m = np.exp(-((XS[700:1340, :] - f32(x_scan)) / 6.0) ** 2) * (HS.fill[700:1340] > 0.2)
        hdr[700:1340] += (m * 0.35)[..., None] * C3(0.35, 0.85, 1.0)
    rec_on = sstep(P2A[0] + 0.4, P2A[0] + 0.8, t)
    if rec_on > 0 or pain > 0:
        for (x, y), dl in zip(HS.receptors, HS.rec_delay):
            seen = 1.0 if (x_scan is None or x <= x_scan) else 0.0
            if t >= P2A[0] + 2.4:
                seen = 1.0
            I = rec_on * seen * (0.9 + 0.3 * math.sin(t * 3 + dl * 6)) + pain * hb * 1.4
            if I > 0.02:
                add_glow(hdr, float(x), float(y), 1.1 * I, C3(1.0, 0.18, 0.12), core=2.3, halo=5.0, ext=24)
    # opération éveillée : sonde + stimulation
    ap = section(t, *P2B)
    if ap > 0:
        tip = B.tr([(-0.255, -0.035)])[0] + [B.box[0], B.box[1]]
        top = (tip[0] + 170, tip[1] - 205)
        reach = ain(t, P2B[0] + 0.2, 0.8)
        p_end = (top[0] + (tip[0] - top[0]) * reach, top[1] + (tip[1] - top[1]) * reach)
        m = np.zeros((H, W), np.uint8)
        cv2.polylines(m, [np.round(np.array([top, p_end]) * 16).astype(np.int32)], False, 255, 5, cv2.LINE_AA, 4)
        hdr += (m.astype(f32) / 255.0 * f32(0.9 * ap))[..., None] * C3(0.85, 0.90, 1.0)
        if reach > 0.98:
            ph = (t - P2B[0] - 1.0) % 0.8
            add_glow(hdr, float(tip[0]), float(tip[1]), 1.6 * ap, C3(0.4, 0.95, 1.0), core=4, halo=14, ext=90)
            R_ = 10 + 70 * ph / 0.8
            m2 = np.zeros((H, W), np.uint8)
            cv2.circle(m2, (int(tip[0] * 16), int(tip[1] * 16)), int(R_ * 16), 255, 2, cv2.LINE_AA, 4)
            hdr += (m2.astype(f32) / 255.0 * f32(0.8 * ap * (1 - ph / 0.8)))[..., None] * C3(0.4, 0.95, 1.0)
    return hdr


def world_top(t):
    hdr = BG_TOP.copy()
    hdr += drift(DUST_FAR, t, 6, -9)
    hdr += drift(DUST_NEAR, t, -10, -16) * f32(0.8)
    BR.composite(hdr, DB, 1.0)
    g = G[2]
    tint = 1 - sstep(g["reveal"], g["reveal"] + 0.5, t)
    same = sstep(g["reveal"] + 0.2, g["reveal"] + 0.9, t)
    pul = 0.75 + 0.25 * math.sin(t * 4.0)
    emL = (DB.mL * (0.30 + 0.70 * DB.g))
    emR = (DB.mR * (0.30 + 0.70 * DB.g))
    if tint > 0.01:
        BR.place(hdr, DB, emL[..., None] * CYAN * f32(0.55 * tint * pul))
        BR.place(hdr, DB, emR[..., None] * CORAL * f32(0.55 * tint * pul))
    if same > 0.01:
        BR.place(hdr, DB, (emL + emR)[..., None] * C3(0.30, 0.80, 1.0) * f32(0.45 * same * pul))
    outline_glow(hdr, DB.outline_l, C3(0.30, 0.75, 1.0), 0.22, 2, 5.0)
    outline_glow(hdr, DB.outline_r, C3(0.30, 0.75, 1.0), 0.22, 2, 5.0)
    # IRM : bandes de balayage
    asc = section(t, *P3A)
    if asc > 0:
        x0, y0, x1, y1 = DB.box
        ys = y0 + (y1 - y0) * (((t - P3A[0]) * 0.55) % 1.0)
        band = np.exp(-((YS[y0:y1, x0:x1] - f32(ys)) / 10.0) ** 2) * DB.mask
        hdr[y0:y1, x0:x1] += (band * f32(0.55 * asc))[..., None] * C3(0.35, 0.90, 1.0)
    # latéralisation : langage (gauche), attention (droite)
    al = section(t, *P3C)
    if al > 0:
        for (px, py), col in ((LANG, CYAN), (ATTN, GREEN)):
            add_glow(hdr, px, py, 2.4 * al * pul, col, core=12, halo=26, ext=160)
    return hdr


LANG = (DB.cx - 0.31 * DB.L, DB.cy - 0.05 * DB.L)
ATTN = (DB.cx + 0.24 * DB.L, DB.cy + 0.14 * DB.L)

# champ de galaxies (façon « champ profond ») : 256 galaxies pour figurer « des centaines de Voies lactées »
GX0, GX1, GY0, GY1 = 140.0, 940.0, 860.0, 1250.0
_mini = cv2.resize(GT, (96, 96), interpolation=cv2.INTER_AREA)
_mini = (np.clip(_mini, 0, None) ** 0.75).astype(f32)
_mini /= _mini.max()
_gr = np.random.default_rng(12)
GRID = []
_tries = 0
while len(GRID) < 256 and _tries < 200000:
    _tries += 1
    x, y = _gr.uniform(GX0, GX1), _gr.uniform(GY0, GY1)
    if all((x - q[0]) ** 2 + ((y - q[1]) * 1.9) ** 2 > 33.0 ** 2 for q in GRID):
        d = math.hypot((x - 540) / 400, (y - 1055) / 195)
        size = _gr.uniform(30, 58)
        ang = _gr.uniform(0, TAU)
        sq = _gr.uniform(0.30, 0.95)
        GRID.append((x, y, d, size, ang, sq))
SPRITES = []
for (x, y, d, size, ang, sq) in GRID:
    sc = size / 96
    c, s_ = math.cos(ang), math.sin(ang)
    M = np.array([[sc * c, -sc * s_], [sc * sq * s_, sc * sq * c]])
    A = np.zeros((2, 3))
    A[:, :2] = M
    A[:, 2] = np.array([40.0, 40.0]) - M @ np.array([48.0, 48.0])
    SPRITES.append(cv2.warpAffine(_mini, A, (80, 80), flags=cv2.INTER_LINEAR))


def place_galaxy(hdr, cx, cy, width, ang, squash, gain):
    n = GT.shape[0]
    sc = width / n
    c, s_ = math.cos(ang), math.sin(ang)
    M = np.array([[sc * c, -sc * s_], [sc * squash * s_, sc * squash * c]])
    A = np.zeros((2, 3))
    A[:, :2] = M
    A[:, 2] = np.array([cx, cy]) - M @ np.array([n / 2, n / 2])
    hdr += cv2.warpAffine(GT, A, (W, H), flags=cv2.INTER_LINEAR) * f32(gain)


def world_galaxy(t):
    hdr = np.zeros((H, W, 3), f32) + C3(0.003, 0.004, 0.010)
    hdr += STARS * f32(0.9)
    grid = sstep(P4C[0] + 0.2, P4C[0] + 1.6, t)
    big_w = 1500 * (1 - 0.97 * smoother(grid))
    if grid < 0.995:
        place_galaxy(hdr, 540, 1060 + 20 * grid, big_w, math.radians(20) + t * 0.025, 0.45, 2.1 * (1 - 0.6 * grid))
    if grid > 0.01:
        for (x, y, d, size, ang, sq), spr in zip(GRID, SPRITES):
            ak = sstep(0.10 + 0.55 * min(d, 1.4) / 1.4, 0.30 + 0.55 * min(d, 1.4) / 1.4, grid)
            if ak <= 0.01:
                continue
            xi, yi = int(round(x)) - 40, int(round(y)) - 40
            hdr[yi:yi + 80, xi:xi + 80] += spr * f32(2.4 * ak)
    return hdr


SC_CENTER = [(505.0, 1075.0), (540.0, 1015.0), (540.0, 1075.0), (540.0, 1060.0), (505.0, 1075.0)]
WORLDS = [world_brain, world_head, world_top, world_galaxy, world_brain]


def cam_params(t):
    t0, t1 = TL.scene_span(t)
    s = 1.0 + 0.05 * smoother((t - t0) / max(t1 - t0, 1e-3))
    return s, SC_CENTER[TL.scene_index(t)]


def camera(hdr, t):
    s, (cx, cy) = cam_params(t)
    M = np.array([[s, 0, (1 - s) * cx], [0, s, (1 - s) * cy]], np.float64)
    return cv2.warpAffine(hdr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def cam_pt(p, t):
    s, (cx, cy) = cam_params(t)
    return (cx + (p[0] - cx) * s, cy + (p[1] - cy) * s)


# ------------------------------------------------------------------ interface
def bubble(img, x, y, a, t):
    """Bulle de parole « … » (le patient parle pendant l'opération)."""
    if a <= 0.003:
        return
    fill_over(img, [U.rounded_rect(x - 70, y - 44, x + 70, y + 44, 30)], C3(0.92, 0.95, 1.0), a)
    fill_over(img, [np.array([(x + 30, y + 40), (x + 62, y + 76), (x + 52, y + 36)])], C3(0.92, 0.95, 1.0), a)
    for k in range(3):
        ph = (t * 2.2 - k * 0.25) % 1.0
        up = 6 * math.exp(-((ph - 0.25) / 0.12) ** 2)
        fill_over(img, [circle_pts(x - 34 + 34 * k, y - up, 9, 24)], C3(0.08, 0.10, 0.14), a)


def eq_sign(img, x, y, a):
    if a <= 0.003:
        return
    fill_over(img, [circle_pts(x, y, 44, 60)], INK, 0.85 * a)
    for dy in (-11, 11):
        fill_over(img, [U.rounded_rect(x - 24, y + dy - 5, x + 24, y + dy + 5, 4)], WHITE, a)


def ui(img, t):
    U.header(img, t, TL, badge0="ÉP. 2")
    a_t = 1 - sstep(S[0] - 0.35, S[0] - 0.05, t)
    if a_t > 0:
        T(img, "4 IDÉES REÇUES", F_DBLACK, 96, 540, 590, WHITE, a_t, 0, 1.0)
        T(img, "SUR LE CERVEAU", F_DBLACK, 96, 540, 700, CYAN, a_t, 0, 1.0)
        T(img, "Compte tes bonnes réponses", F_MEDI, 46, 540, 800, LIGHT, a_t * ain(t, 0.45))
    for g in G:
        U.claim_block(img, t, g, CLAIMS[g["i"]], 470, CLAIM_SIZE[g["i"]])
        U.countdown(img, t, g)
        U.verdict(img, t, g, VERDICT[g["i"]])

    # ---------- idée n° 1 : 10 %
    a = section(t, *P1A)
    if a > 0:
        PARA(img, [fr("L'imagerie montre de l'activité"), "dans tout le cerveau…"], F_DXB, 58, 540, 540, WHITE, a, 0,
             1.10, t=t, t0=P1A[0])
        T(img, "…même pendant le sommeil.", F_MEDI, 46, 540, 700, LIGHT, a * ain(t, P1A[0] + 1.6))
        _, frac = activity(t)
        BIG(img, fr(f"{int(round(frac * 100))} %"), F_DBLACK, 120, 540, 868, 1.0, CYAN if frac > 0.995 else WHITE,
            a * ain(t, P1A[0] + 0.3))
    a = section(t, *P1B)
    if a > 0:
        T(img, "Le cerveau, c'est environ :", F_DBOLD, 54, 540, 540, CYAN, a * ain(t, P1B[0]))
        a1, a2 = a * ain(t, P1B[0] + 0.25), a * ain(t, P1B[0] + 0.85)
        BIG(img, fr("2 %"), F_DBLACK, 150, 330, 720, 1.0, WHITE, a1)
        T(img, "du poids du corps", F_MEDI, 36, 330, 790, LIGHT, a1)
        BIG(img, fr("20 %"), F_DBLACK, 150, 750, 720, 1.0, CYAN, a2)
        T(img, fr("de l'énergie"), F_MEDI, 36, 750, 790, LIGHT, a2)
    a = section(t, *P1C)
    if a > 0:
        PARA(img, [fr("Pourquoi l'évolution aurait gardé"), "un organe aussi gourmand", fr("s'il ne servait qu'à 10 % ?")],
             F_DXB, 54, 540, 545, WHITE, a, 0, 1.14, t=t, t0=P1C[0])

    # ---------- idée n° 2 : la douleur
    a = section(t, *P2A)
    if a > 0:
        PARA(img, wrap(fr("Le cerveau n'a aucun récepteur de la douleur."), F_DXB, 70, 820), F_DXB, 70, 540, 548, WHITE,
             a, 0, 1.10, t=t, t0=P2A[0])
        T(img, fr("Ils sont autour : méninges, crâne, peau…"), F_MEDI, 42, 540, 720, LIGHT, a * ain(t, P2A[0] + 2.0))
    a = section(t, *P2B)
    if a > 0:
        PARA(img, wrap(fr("C'est pour ça qu'on peut opérer certains patients éveillés,"), F_DXB, 62, 820), F_DXB, 62,
             540, 545, WHITE, a, 0, 1.10, t=t, t0=P2B[0])
        T(img, fr("pour repérer les zones à préserver."), F_MEDI, 44, 540, 765, LIGHT, a * ain(t, P2B[0] + 1.0))
        mouth = (HS.cx - 0.60 * HS.L, HS.cy + 0.56 * HS.L)
        bx, by = cam_pt((mouth[0] - 0.0, mouth[1] - 0.0), t)
        bubble(img, max(bx - 10, 205), by - 120, a * ain(t, P2B[0] + 1.4), t)
    a = section(t, *P2C)
    if a > 0:
        T(img, fr("Et le mal de tête ?"), F_DBOLD, 58, 540, 548, CYAN, a * ain(t, P2C[0]))
        PARA(img, wrap(fr("Il vient des méninges, des vaisseaux, des muscles et des nerfs autour du cerveau."), F_DXB,
                       58, 820), F_DXB, 58, 540, 630, WHITE, a, 0, 1.10, t=t, t0=P2C[0] + 0.15)

    # ---------- idée n° 3 : gauche / droite
    g = G[2]
    a_lab = ain(t, g["claim"] + 0.4) * (1 - sstep(g["reveal"] - 0.1, g["reveal"] + 0.2, t))
    if a_lab > 0 and t < g["end"]:
        PILL(img, "LOGIQUE", 410, 880, CYAN, C3(0.02, 0.04, 0.06), a_lab, size=34, pad=20)
        PILL(img, "CRÉATIF", 670, 880, CORAL, WHITE, a_lab, size=34, pad=20)
    a = section(t, *P3A)
    if a > 0:
        T(img, "Une étude a observé le cerveau de", F_DXB, 50, 540, 548, WHITE, a * ain(t, P3A[0]))
        n = int(round(1011 * eout(sat((t - P3A[0] - 0.3) / 1.6), 2)))
        BIG(img, fr(f"{n:,}".replace(",", " ")), F_DBLACK, 150, 540, 710, 1.0, CYAN if n == 1011 else WHITE,
            a * ain(t, P3A[0] + 0.2))
        T(img, fr("personnes (7 à 29 ans)"), F_MEDI, 44, 540, 790, LIGHT, a * ain(t, P3A[0] + 0.5))
    a = section(t, *P3B)
    if a > 0:
        PARA(img, ["Aucune n'utilisait un côté", fr("plus que l'autre.")], F_DXB, 68, 540, 560, WHITE, a, 0, 1.10, t=t,
             t0=P3B[0])
        T(img, "Université de l'Utah, 2013", F_MEDI, 36, 540, 730, LIGHT, a * ain(t, P3B[0] + 0.8) * 0.9)
        x_eq, y_eq = cam_pt((DB.cx, DB.cy - 0.02 * DB.L), t)
        eq_sign(img, x_eq, y_eq, a * ain(t, P3B[0] + 0.4, 0.3))
    a = section(t, *P3C)
    if a > 0:
        T(img, fr("Certaines fonctions ont un côté :"), F_DBOLD, 48, 540, 532, CYAN, a * ain(t, P3C[0]))
        T(img, fr("le langage à gauche, l'attention à droite…"), F_MEDI, 40, 540, 594, LIGHT, a * ain(t, P3C[0] + 0.3))
        PARA(img, wrap(fr("…mais personne n'a de côté dominant."), F_DXB, 56, 820), F_DXB, 56,
             540, 684, WHITE, a, 0, 1.10, t=t, t0=P3C[0] + 1.1)
        for (px, py), lab, col in ((LANG, "langage", CYAN), (ATTN, "attention", GREEN)):
            qx, qy = cam_pt((px, py), t)
            PILL(img, lab, qx, qy - 52, C3(0.05, 0.06, 0.09), col, a * ain(t, P3C[0] + 0.5), size=32, pad=18, tracking=1.0,
                 path=F_DBOLD)

    # ---------- idée n° 4 : neurones et étoiles
    a = section(t, *P4A)
    if a > 0:
        T(img, fr("Combien ?"), F_DXB, 76, 540, 560, WHITE, a * ain(t, P4A[0]))
        T(img, "en milliards", F_MEDI, 44, 540, 636, LIGHT, a * ain(t, P4A[0] + 0.12))
    a = section(t, *P4B)
    if a > 0:
        PARA(img, wrap(fr("Et les « 100 milliards de neurones » souvent cités ?"), F_DBOLD, 50, 820), F_DBOLD, 50, 540,
             540, LIGHT, a, 0, 1.10, t=t, t0=P4B[0])
        T(img, "Un chiffre jamais démontré.", F_DXB, 62, 540, 690, WHITE, a * ain(t, P4B[0] + 0.7))
        T(img, fr("Premier vrai comptage (2009) : 86 milliards"), F_MEDI, 36, 540, 760, CYAN, a * ain(t, P4B[0] + 1.3))
    a = bump(t, P4A[0] + 0.1, P4A[0] + 0.45, P4B[1] - 0.35, P4B[1] - 0.05)
    if a > 0:
        U.bars(img, t, a, P4A[0] + 0.20, ROWS4, 400.0, (86.0, CYAN), "Sources : Azevedo et al. 2009 · NASA")
    a = section(t, *P4C)
    if a > 0:
        T(img, fr("Mais tes connexions, si !"), F_DBOLD, 58, 540, 540, CYAN, a * ain(t, P4C[0]))
        T(img, fr("≈ 100 000 milliards"), F_DBLACK, 84, 540, 650, WHITE, a * ain(t, P4C[0] + 0.25))
        T(img, "de synapses (estimation)", F_MEDI, 40, 540, 714, LIGHT, a * ain(t, P4C[0] + 0.45))
        T(img, "= les étoiles de centaines de Voies lactées", F_DBOLD, 40, 540, 800, CYAN, a * ain(t, P4C[0] + 1.6))

    # ---------- fin
    a = section(t, *P5A)
    if a > 0:
        T(img, fr("TON SCORE ?"), F_DBLACK, 96, 540, 600, WHITE, a * ain(t, P5A[0]), 0, 1.0)
        BIG(img, "?/4", F_DBLACK, 220, 540, 880, 1.0 + 0.06 * math.sin((t - TL.S_OUT) * 6), CYAN, a * ain(t, P5A[0] + 0.25))
        T(img, "Dis-le en commentaire", F_MEDI, 44, 540, 990, LIGHT, a * ain(t, P5A[0] + 0.6))
    a = ain(t, P5B[0], 0.4) * (1 - sstep(DUR - 0.18, DUR - 0.06, t))
    if a > 0:
        T(img, "SOURCES", F_DBOLD, 30, 540, 500, LIGHT, a * 0.85, 0, 6.0)
        PARA(img, wrap("Santé.fr · PNAS 2002 · BrainFacts (SfN) · Université de l'Utah · Azevedo et al. 2009 · NASA · UCLA",
                       F_SEMI, 34, 800), F_SEMI, 34, 540, 556, WHITE, a, 0, 1.18)
        a2 = a * ain(t, P5B[0] + 0.5, 0.4)
        T(img, "PROCHAIN ÉPISODE", F_DBOLD, 30, 540, 700, CYAN, a2, 0, 6.0)
        PARA(img, wrap(fr("« La Grande Muraille de Chine se voit depuis l'espace »"), F_DXB, 52, 800), F_DXB, 52, 540, 764,
             WHITE, a2, 0, 1.10)
        a3 = a * ain(t, P5B[0] + 1.0, 0.4)
        PILL(img, fr("VRAI OU FAUX ?"), 540, 960, CYAN, C3(0.02, 0.04, 0.06), a3, size=40)
        T(img, "Abonne-toi pour la réponse", F_SEMI, 36, 540, 1050, LIGHT, a3)


ROWS4 = [("Neurones (ton cerveau)", "86", 86.0, CYAN, 0.0),
         ("Étoiles : estimation basse", "100", 100.0, C3(0.85, 0.92, 1.0), 0.7),
         ("Étoiles : estimation haute", "400", 400.0, C3(1.0, 0.85, 0.55), 1.4)]


def loop_flash(t):
    """Flash de bouclage : la fin rejoint le début."""
    v = 0.0
    if t >= DUR - 0.12:                                 # la fin s'éclaire ; l'image 0 reste nette (miniature)
        v = (t - (DUR - 0.12)) / 0.12 * 0.85
    return v


def render(t, seed=0):
    sc = TL.scene_index(t)
    hdr = WORLDS[sc](t)
    hdr = camera(hdr, t)
    sh = (0.0, 0.0)
    for g in G:
        if g["reveal"] <= t < g["reveal"] + 0.35:
            u = (t - g["reveal"]) / 0.35
            amp = 14 * (1 - u) ** 2
            sh = (amp * math.sin(t * 97), amp * math.cos(t * 83))
    out = finalize(hdr, 1.0, seed, grain=0.0, shake=sh)
    img = out.astype(f32) / 255.0
    img *= 1 - U.SCRIM
    ui(img, t)
    wo = max(U.whiteout(t, FL), loop_flash(t))
    if wo > 0:
        img = img * (1 - wo) + f32(wo) * C3(0.90, 0.95, 1.0)
    return np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)


def frame_png(args):
    i, outdir = args
    p = os.path.join(outdir, f"f_{i:04d}.png")
    tmp = p + ".tmp.png"
    Image.fromarray(render(i / FPS, seed=i)).save(tmp, compress_level=1)
    os.replace(tmp, p)
    return i


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
        bad = U.audit(ui, NF, int(sys.argv[2]) if len(sys.argv) > 2 else 1)
        print(f"{NF} images, durée {DUR} s, {len(bad)} problème(s)")
        for (txt, why), v in sorted(bad.items(), key=lambda kv: kv[1][0]):
            print(f"  t={v[0]:6.2f}  [{why}]  {txt!r}  bbox={v[1:]}")
