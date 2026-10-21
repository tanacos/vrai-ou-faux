# -*- coding: utf-8 -*-
"""INFINIMENT — épisode 1 : « L'humanité dans un sucre ». Rendu procédural 1080 x 1920 piloté par la voix.

Toutes les animations sont calées sur les mots de la narration (fichier chrono.json produit par la couche voix :
moteur/vf/voix.py). Les textes passent par vf.ui (journal des boîtes) pour l'audit des zones sûres TikTok.

  python3 rendu.py images  chrono.json t1 t2 …          -> images de contrôle (dossier courant)
  python3 rendu.py planche chrono.json sortie.png        -> planche des moments clés
  python3 rendu.py video   chrono.json sortie.mkv f0 f1  -> tronçon vidéo (images f0..f1-1), quasi sans perte
  python3 rendu.py audit   chrono.json                   -> textes hors zone sûre ou superposés (JSON)
"""
import functools
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, "moteur"))

from vf import ui as U  # noqa: E402
from vf.base import (F_DBLACK, F_DXB, F_DBOLD, F_SEMI, F_MEDI, F_DMED, text_width, SAFE_LEFT,  # noqa: E402
                     SAFE_RIGHT_LOW, SAFE_BOTTOM)

cv2.setNumThreads(1)
W, H, FPS = 1080, 1920, 30
HW, HH = W // 2, H // 2
T0 = 0.30                     # avance de l'image sur la voix : la 1re image (miniature TikTok) reste lisible
CX, CY = 540, 905             # centre de la zone visuelle (y 640 à 1170)

CYAN = np.array([0.38, 0.82, 1.00], np.float32)
AMBER = np.array([1.00, 0.68, 0.26], np.float32)
WHITE = np.array([1.0, 1.0, 1.0], np.float32)
GREEN = np.array([0.30, 1.00, 0.55], np.float32)
WARM = np.array([1.00, 0.52, 0.42], np.float32)
VIOLET = np.array([0.80, 0.45, 1.00], np.float32)
LIGHT = np.array([0.80, 0.85, 0.93], np.float32)

CH = None                     # chronologie de la voix (chrono.json)
SC = {}                       # bornes des scènes
DUR = 0.0


# ---------------------------------------------------------------- utilitaires
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def sstep(a, b, x):
    if b == a:
        return 1.0 if x >= b else 0.0
    t = clamp((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def eout(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def eback(t, s=1.9):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def lerp(a, b, t):
    return a + (b - a) * t


def cue(key, n=0, default=None):
    """Instant (temps vidéo) du n-ième mot « bloc:mot » de la narration."""
    v = CH["reperes"].get(key)
    if v and len(v) > n:
        return v[n] + T0
    if default is None:
        raise KeyError(key)
    return default


def bloc(name):
    s, e = CH["blocs"][name]
    return s + T0, e + T0


# ---------------------------------------------------------------- texte (journalisé pour l'audit des zones sûres)
SCN_A = [1.0]                 # opacité des textes de la scène en cours (fondus entre scènes)


def txt(img, s, x, yc, size, font=F_DBLACK, col=WHITE, a=1.0, align=0, track=0.0, sh=True):
    """Texte centré verticalement sur yc (hauteur des capitales) ; align 0 centré, -1 gauche, 1 droite."""
    a = a * SCN_A[0]
    if a <= 0.003 or not s:
        return 0.0
    return U.T(img, s, font, int(size), x, yc + 0.36 * size, np.asarray(col, np.float32), a, align, track, sh)


F_CAP = os.path.join(RACINE, "moteur", "assets", "polices", "Anton-Regular.ttf")   # OFL, condensée : sous-titres


@functools.lru_cache(maxsize=512)
def _cap_patch(word, size, rgb):
    """Mot de sous-titre : lettres pleines avec contour noir (lisible sur tout fond), en RGBA float."""
    f = ImageFont.truetype(F_CAP, size)
    st = max(4, size // 11)
    w = int(f.getlength(word)) + 2 * st + 8
    asc, desc = f.getmetrics()
    h = asc + desc + 2 * st + 8
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((st + 4, st + 4), word, font=f, fill=rgb + (255,), stroke_width=st, stroke_fill=(0, 0, 0, 255))
    a = np.asarray(im).astype(np.float32) / 255.0
    rows = np.where(a[..., 3].max(axis=1) > 0.01)[0]
    return a[rows[0]:rows[-1] + 1] if len(rows) else a


def blit_rgba(img, p, x0, y0, alpha=1.0):
    h, w = p.shape[:2]
    x0, y0 = int(round(x0)), int(round(y0))
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb or alpha <= 0.003:
        return
    sub = p[ya - y0:yb - y0, xa - x0:xb - x0]
    m = sub[..., 3:4] * alpha
    img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - m) + sub[..., :3] * m


# ---------------------------------------------------------------- dessin
def c255(c):
    return tuple(int(255 * clamp(float(v))) for v in c)


def add_pts(gl, xs, ys, val, color):
    xi = (xs * 0.5).astype(np.int32)
    yi = (ys * 0.5).astype(np.int32)
    m = (xi >= 0) & (xi < HW) & (yi >= 0) & (yi < HH)
    buf = np.zeros((HH, HW), np.float32)
    v = val[m] if isinstance(val, np.ndarray) else np.full(m.sum(), val, np.float32)
    np.add.at(buf, (yi[m], xi[m]), v)
    gl += buf[..., None] * color


def gline(gl, p0, p1, color, th=2, a=1.0):
    cv2.line(gl, (int(p0[0] * 0.5), int(p0[1] * 0.5)), (int(p1[0] * 0.5), int(p1[1] * 0.5)),
             tuple(float(c * a) for c in color), th, cv2.LINE_AA)


def gcircle(gl, c, r, color, th=2, a=1.0):
    cv2.circle(gl, (int(c[0] * 0.5), int(c[1] * 0.5)), max(int(r * 0.5), 1), tuple(float(v * a) for v in color), th,
               cv2.LINE_AA)


def _mask_bbox(m):
    rows = np.where(m.any(axis=1))[0]
    if not len(rows):
        return None
    cols = np.where(m[rows[0]:rows[-1] + 1].any(axis=0))[0]
    return rows[0], rows[-1] + 1, cols[0], cols[-1] + 1


def crisp_lines(cv, polys, color, alpha=1.0, th=4, closed=False):
    if alpha <= 0.003 or not polys:
        return
    m = np.zeros((H, W), np.uint8)
    pts = [np.round(np.asarray(p) * 16).astype(np.int32) for p in polys if len(p) >= 2]
    if not pts:
        return
    cv2.polylines(m, pts, closed, 255, th, cv2.LINE_AA, shift=4)
    bb = _mask_bbox(m)
    if bb is None:
        return
    y0, y1, x0, x1 = bb
    a = (m[y0:y1, x0:x1].astype(np.float32) / 255.0 * alpha)[..., None]
    cv[y0:y1, x0:x1] = cv[y0:y1, x0:x1] * (1 - a) + np.asarray(color, np.float32) * a


def crisp_fill(cv, polys, color, alpha=1.0):
    if alpha <= 0.003:
        return
    m = np.zeros((H, W), np.uint8)
    pts = [np.round(np.asarray(p) * 16).astype(np.int32) for p in polys]
    cv2.fillPoly(m, pts, 255, cv2.LINE_AA, shift=4)
    bb = _mask_bbox(m)
    if bb is None:
        return
    y0, y1, x0, x1 = bb
    a = (m[y0:y1, x0:x1].astype(np.float32) / 255.0 * alpha)[..., None]
    cv[y0:y1, x0:x1] = cv[y0:y1, x0:x1] * (1 - a) + np.asarray(color, np.float32) * a


def circle_poly(x, y, r, n=64):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.stack([x + r * np.cos(a), y + r * np.sin(a)], 1)


def crisp_dot(cv, x, y, r, color, alpha=1.0):
    crisp_fill(cv, [circle_poly(x, y, r, 28)], color, alpha)


def rrect(x0, y0, x1, y1, r, n=8):
    pts = []
    for cx_, cy_, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx_ + r * math.cos(a), cy_ + r * math.sin(a)))
    return np.array(pts)


# ---------------------------------------------------------------- fond commun
rng = np.random.default_rng(7)
_y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
BG = (np.array([0.006, 0.009, 0.022], np.float32) * (1 - _y) + np.array([0.016, 0.020, 0.048], np.float32) * _y)
BG = np.repeat(BG, W, axis=1)
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = np.clip(1 - 0.55 * (((_xx - W / 2) / (W * 0.72)) ** 2 + ((_yy - H / 2) / (H * 0.62)) ** 2), 0.3, 1)[..., None]
VIG = VIG.astype(np.float32)
del _yy, _xx
GRAIN = [(rng.standard_normal((H, W, 1)).astype(np.float32) * 0.010) for _ in range(4)]
_neb = np.zeros((HH + 300, HW + 300, 3), np.float32)
for _ in range(26):
    cx, cy = rng.uniform(0, HW + 300), rng.uniform(0, HH + 300)
    r = rng.uniform(40, 150)
    col = [CYAN, VIOLET, np.array([0.2, 0.3, 0.9], np.float32)][rng.integers(0, 3)]
    cv2.circle(_neb, (int(cx), int(cy)), int(r), tuple(float(v) * rng.uniform(0.010, 0.028) for v in col), -1)
NEB = cv2.GaussianBlur(_neb, (0, 0), 60)
STAR_N = 650
STAR_X = rng.uniform(0, W, STAR_N).astype(np.float32)
STAR_Y = rng.uniform(0, H, STAR_N).astype(np.float32)
STAR_B = (rng.uniform(0.15, 1.0, STAR_N) ** 3 * 1.6).astype(np.float32)
STAR_P = rng.uniform(0, 2 * np.pi, STAR_N).astype(np.float32)


def new_frame(t, stars=1.0, neb=1.0):
    cv = BG.copy()
    gl = np.zeros((HH, HW, 3), np.float32)
    if neb > 0:
        ox, oy = int(150 + 120 * math.sin(t * 0.021)), int(150 + 110 * math.cos(t * 0.017))
        gl += NEB[oy:oy + HH, ox:ox + HW] * neb
    if stars > 0:
        tw = 0.65 + 0.35 * np.sin(STAR_P + t * 1.7)
        add_pts(gl, STAR_X, STAR_Y, STAR_B * tw * stars, np.array([0.8, 0.88, 1.0], np.float32))
    return cv, gl


def compose_glow(cv, gl, k=1.0):
    b1 = cv2.GaussianBlur(gl, (0, 0), 1.6)
    b2 = cv2.GaussianBlur(gl, (0, 0), 7.0)
    b3 = cv2.GaussianBlur(gl, (0, 0), 22.0)
    g = gl * 0.55 + b1 * 1.1 + b2 * 0.9 + b3 * 0.7
    cv += cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR) * k
    cv *= SCRIM


TOPFADE = (0.25 + 0.75 * np.clip((np.arange(HH, dtype=np.float32) - 300) / 60, 0, 1))[:, None, None]


# voile sombre derrière l'en-tête, les titres et les sous-titres : le texte reste lisible sur les fonds chargés
_sy = np.arange(H, dtype=np.float32)
SCRIM = (1 - 0.50 * np.clip((_sy - 120) / 140, 0, 1) * np.clip((700 - _sy) / 110, 0, 1)
         - 0.38 * np.clip((_sy - 1120) / 60, 0, 1) * np.clip((1310 - _sy) / 60, 0, 1))[:, None, None].astype(np.float32)


# ---------------------------------------------------------------- objets : cubes, nuages
def cube_polys(cx, cy, s, theta=0.0, tilt=1.0):
    a = s / 2
    ct, st = math.cos(theta), math.sin(theta)

    def P(x, y, z):
        x2, z2 = x * ct - z * st, x * st + z * ct
        return (cx + (x2 - z2) * 0.866, cy + (x2 + z2) * 0.5 * tilt - y)
    top = [P(-a, a, -a), P(a, a, -a), P(a, a, a), P(-a, a, a)]
    right = [P(a, a, -a), P(a, a, a), P(a, -a, a), P(a, -a, -a)]
    front = [P(-a, a, a), P(a, a, a), P(a, -a, a), P(-a, -a, a)]
    return top, right, front


SUGAR_SPECK = rng.uniform(0, 1, (3, 900, 2)).astype(np.float32)
SUGAR_SPECK_V = rng.uniform(-1, 1, (3, 900)).astype(np.float32)


def bilin(quad, uv):
    q = np.asarray(quad, np.float32)
    u, v = uv[:, 0:1], uv[:, 1:2]
    return q[0] * (1 - u) * (1 - v) + q[1] * u * (1 - v) + q[2] * u * v + q[3] * (1 - u) * v


def draw_sugar(cv, gl, cx, cy, s, alpha=1.0, theta=0.25, glass=0.0):
    """Morceau de sucre ; glass > 0 le rend translucide (pour montrer ce qu'il contient)."""
    if alpha <= 0.01:
        return
    faces = cube_polys(cx, cy, s, theta)
    shades = [np.array([0.96, 0.96, 0.98], np.float32), np.array([0.62, 0.65, 0.72], np.float32),
              np.array([0.80, 0.82, 0.87], np.float32)]
    fa = alpha * (1 - 0.72 * glass)
    for f, sh in zip(faces, shades):
        crisp_fill(cv, [f], sh, fa)
    for i, f in enumerate(faces):
        p = bilin(f, SUGAR_SPECK[i])
        xi, yi = p[:, 0].astype(int), p[:, 1].astype(int)
        m = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        cv[yi[m], xi[m]] += (SUGAR_SPECK_V[i][m] * 0.13 * fa)[:, None]
    crisp_lines(cv, [faces[0], faces[1], faces[2]], (1, 1, 1), (0.35 + 0.5 * glass) * alpha, 2, True)
    gcircle(gl, (cx, cy - s * 0.1), s * 0.9, WHITE * 0.05 * alpha, -1)


def draw_hot_cube(cv, gl, cx, cy, s, alpha=1.0, theta=0.3, intensity=1.0):
    if alpha <= 0.01:
        return
    faces = cube_polys(cx, cy, s, theta)
    shades = [np.array([1.0, 0.92, 0.70], np.float32), np.array([1.0, 0.55, 0.18], np.float32),
              np.array([1.0, 0.72, 0.32], np.float32)]
    for f, sh in zip(faces, shades):
        crisp_fill(cv, [f], sh, alpha)
        hp = (np.asarray(f) * 0.5).astype(np.int32)
        cv2.fillPoly(gl, [hp], tuple(float(v) * 0.35 * alpha * intensity for v in sh))
    gcircle(gl, (cx, cy - s * 0.15), s * 1.1, AMBER * 0.10 * alpha * intensity, -1)


POOL = 90000
_r = rng.gamma(3.0, 0.5, POOL).astype(np.float32)
_v = rng.standard_normal((POOL, 3)).astype(np.float32)
_v /= np.linalg.norm(_v, axis=1, keepdims=True)
CLOUD = _v * _r[:, None]


def draw_cloud(gl, cx, cy, scale, t, n=9000, bright=0.055, color=CYAN, squash=1.0, seed=0):
    idx = np.random.default_rng(int(t * FPS) * 7 + seed).integers(0, POOL, n)
    p = CLOUD[idx]
    a = t * 0.25
    x = p[:, 0] * math.cos(a) + p[:, 2] * math.sin(a)
    y = p[:, 1] * squash
    add_pts(gl, cx + x * scale, cy + y * scale, bright, color)


# ---------------------------------------------------------------- en-tête : marque + règle des échelles
EXP_MIN, EXP_MAX = -15, 26          # du noyau (1 fm) au bord de l'univers observable (~10^26 m)
SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
RX0, RX1, RY = 170.0, 910.0, 410.0


def exp_str(e):
    """Règle française de l'ordre de grandeur : a × 10ⁿ avec a ≤ 5 → 10ⁿ, sinon 10ⁿ⁺¹ (comme moteur/rp/base.py)."""
    n = math.floor(e + 1e-9)
    return "10" + str(int(n + (1 if e - n > math.log10(5) + 1e-9 else 0))).translate(SUP) + " m"


def header(img, t, a_head, expo, a_rule):
    """« INFINIMENT · ÉP. 1 » puis la règle des puissances de dix : où en est-on entre l'infiniment petit et
    l'infiniment grand ?"""
    if a_head > 0.003:
        w1 = text_width("INFINIMENT", F_DBOLD, 34, 9.0)
        w2 = text_width("ÉP. 1", F_DBOLD, 30, 3.0)
        x0 = 540 - (w1 + 26 + w2) / 2
        txt(img, "INFINIMENT", x0, 296, 34, F_DBOLD, WHITE, 0.95 * a_head, -1, 9.0)
        txt(img, "ÉP. 1", x0 + w1 + 26, 296, 30, F_DBOLD, AMBER, 0.95 * a_head, -1, 3.0)
    if a_rule <= 0.003 or expo is None:
        return
    # graduation discrète : une marque par puissance de dix, plus longue toutes les 5
    segs = []
    for e in range(EXP_MIN, EXP_MAX + 1):
        x = RX0 + (e - EXP_MIN) / (EXP_MAX - EXP_MIN) * (RX1 - RX0)
        L = 13 if e % 5 == 0 else 7
        segs.append([(x, RY - L), (x, RY + L)])
    crisp_lines(img, [[(RX0, RY), (RX1, RY)]], LIGHT, 0.30 * a_rule, 2)
    crisp_lines(img, segs, LIGHT, 0.32 * a_rule, 2)
    txt(img, "PETIT", RX0 - 8, RY + 34, 22, F_DBOLD, LIGHT, 0.55 * a_rule, -1, 3.0, sh=False)
    txt(img, "GRAND", RX1 + 8, RY + 34, 22, F_DBOLD, LIGHT, 0.55 * a_rule, 1, 3.0, sh=False)
    x = RX0 + (clamp((expo - EXP_MIN) / (EXP_MAX - EXP_MIN))) * (RX1 - RX0)
    crisp_dot(img, x, RY, 9, AMBER, a_rule)
    crisp_lines(img, [[(x, RY - 9), (x, RY - 24)]], AMBER, a_rule, 3)
    lab = exp_str(expo)
    wl = text_width(lab, F_DBLACK, 34)
    xl = clamp(x, RX0 + wl / 2 - 30, RX1 - wl / 2 + 30)
    txt(img, lab, xl, RY - 46, 34, F_DBLACK, AMBER, a_rule)


def label(img, lines, a, y0=520, size=86, cols=None, font=F_DBLACK, track=0.0, lh=1.12):
    """Titre du moment (1 à 2 lignes) dans la zone y 470-610 ; la taille s'adapte à la largeur sûre (820 px)."""
    if a <= 0.003:
        return
    for i, s in enumerate(lines):
        sz = size
        while sz > 40 and text_width(s, font, sz, track) > 820:
            sz -= 2
        col = cols[i] if cols else WHITE
        txt(img, s, 540, y0 + i * size * lh, sz, font, col, a, 0, track)


# ---------------------------------------------------------------- sous-titres mot à mot
CAP_SIZE, CAP_Y, CAP_W = 80, 1192, 2 * (SAFE_RIGHT_LOW - 8 - 540)     # centrés, bord droit <= 772 (boutons TikTok)


def caption_at(t):
    for c in CH["sous_titres"]:
        if c["debut"] + T0 <= t < c["fin"] + T0:
            return c
    return None


POP = 1.07                    # grossissement d'entrée d'un sous-titre (0,12 s)
MOTS_OUTILS = {"LE", "LA", "LES", "L'", "DE", "DU", "DES", "D'", "UN", "UNE", "ET", "À", "AU", "AUX", "QUE", "QUI",
               "CE", "CET", "CETTE", "CES", "TA", "TON", "TES", "SON", "SA", "SES", "DANS", "EN", "SUR", "POUR", "PAR",
               "NE", "SE", "OR", "SI", "ON", "TU", "IL", "ELLE", "PLUS", "C'EST"}
_MISE_EN_PAGE = {}


def _cap_largeurs(words, size):
    return [_cap_patch(w["t"], size, (255, 255, 255)).shape[1] for w in words]


def _cap_layout(c):
    """Taille et coupure d'un sous-titre, fixées pour toute sa durée (la mise en page ne saute pas pendant
    l'animation d'entrée). Une ligne de 80 à 60 px ; sinon deux lignes équilibrées (68 px au plus), la première ne
    finissant pas sur un mot-outil quand c'est possible : jamais de mot seul orphelin. Renvoie aussi la largeur de la
    ligne la plus longue (le grossissement d'entrée est limité pour ne jamais dépasser CAP_W)."""
    key = (c["debut"], len(c["mots"]))
    if key in _MISE_EN_PAGE:
        return _MISE_EN_PAGE[key]
    words, n = c["mots"], len(c["mots"])
    res = None
    for size in (80, 76, 72, 68, 64, 60):
        ws = _cap_largeurs(words, size)
        larg = sum(ws) + int(size * 0.26) * (n - 1)
        if larg <= CAP_W:
            res = (size, [n], larg)
            break
    if res is None:
        for size in (68, 64, 60, 56, 52):
            ws = _cap_largeurs(words, size)
            sp = int(size * 0.26)
            best = None
            for k in range(1, n):
                w1, w2 = sum(ws[:k]) + sp * (k - 1), sum(ws[k:]) + sp * (n - k - 1)
                if max(w1, w2) > CAP_W:
                    continue
                orphelin = n >= 3 and (k == 1 or k == n - 1)          # un mot seul sur une ligne
                score = (orphelin, words[k - 1]["t"].upper() in MOTS_OUTILS, max(w1, w2))
                if best is None or score < best[0]:
                    best = (score, k)
            if best is not None:
                res = (size, [best[1], n - best[1]], best[0][2])
                break
    if res is None:
        res = (52, [n], CAP_W)
    _MISE_EN_PAGE[key] = res
    return res


CAP_BAS = 1252                # bas de la zone sûre (1260) moins une marge


def draw_captions(img, t, a=1.0):
    c = caption_at(t)
    if not c or a <= 0.003:
        return
    pop = 1 + (POP - 1) * (1 - eout((t - c["debut"] - T0) / 0.12))
    size, coupe, larg = _cap_layout(c)
    sz = int(size * min(pop, max(1.0, CAP_W / max(larg, 1))))
    imgs = [_cap_patch(w["t"], sz, c255(AMBER) if (w["s"] + T0 <= t < w["e"] + T0 + 0.04) else (255, 255, 255))
            for w in c["mots"]]
    space = int(sz * 0.26)
    lines, i = [], 0
    for m in coupe:
        lines.append(imgs[i:i + m])
        i += m
    hmax_all = max(p.shape[0] for ln in lines for p in ln)
    lh = hmax_all + 6
    y_top = (CAP_Y - lh / 2) if len(lines) == 1 else (CAP_BAS - len(lines) * lh)
    for li, ln in enumerate(lines):
        tw = sum(p.shape[1] for p in ln) + space * (len(ln) - 1)
        x = 540 - tw / 2
        hmax = max(p.shape[0] for p in ln)
        y0 = y_top + li * lh + (lh - hmax) / 2
        for p in ln:
            blit_rgba(img, p, x, y0 + (hmax - p.shape[0]) / 2, a)
            x += p.shape[1] + space
        U._log(" ".join(w["t"] for w in c["mots"]) + (f" [{li + 1}]" if len(lines) > 1 else ""),
               540 - tw / 2, y0, 540 + tw / 2, y0 + hmax, a)


# ================================================================= scènes
# 1. accroche : 8,2 milliards de points qui se rassemblent dans un morceau de sucre
SW_N = 14000
_sw = np.random.default_rng(3)
SW_ANG = _sw.uniform(0, 2 * np.pi, SW_N).astype(np.float32)
SW_RAD = (_sw.uniform(0, 1, SW_N) ** 0.6 * 420).astype(np.float32)
SW_ARM = (SW_ANG + SW_RAD * 0.012).astype(np.float32)
SW_COL = _sw.uniform(0, 1, SW_N) > 0.5


def sc_hook(t):
    cv, gl = new_frame(t)
    t_hum = cue("hook:lhumanite", 0, 0.6)
    t_huit = cue("hook:huit", 0, 2.1)
    t_tenir = cue("hook:tiendrait", 0, cue("hook:pourrait", 0, 3.9))
    t_sucre = cue("hook:sucre", 0, 5.6)
    t_phys = cue("hook:physique", 0, 6.8)
    t_cond = cue("hook:retirait", 0, None)            # narration v6 : la condition est dite dès l'accroche
    # l'essaim des humains jaillit du sucre, puis y retourne
    expand = eout((t - t_hum + 0.15) / 1.3) * (1 - eout((t - t_tenir) / max(t_sucre - t_tenir + 0.2, 0.4)))
    spin = 0.16 * t + (1 - expand) * 1.6
    k = 0.04 + 0.96 * expand
    x = CX + np.cos(SW_ARM + spin) * SW_RAD * k
    y = CY + np.sin(SW_ARM + spin) * SW_RAD * 0.58 * k
    ap = sstep(t_hum - 0.2, t_hum + 0.5, t) * (1 - 0.85 * sstep(t_sucre, t_sucre + 0.6, t))
    add_pts(gl, x[SW_COL], y[SW_COL], 0.30 * ap, AMBER)
    add_pts(gl, x[~SW_COL], y[~SW_COL], 0.24 * ap, CYAN)
    # le sucre : visible dès la 1re image (miniature), s'efface pendant l'essaim, revient avec « sucre »
    sa = max(1 - sstep(t_hum - 0.1, t_hum + 0.5, t), sstep(t_sucre - 0.5, t_sucre + 0.2, t))
    pulse = 1 + 0.06 * math.exp(-max(t - t_sucre, 0) * 3) * (t > t_sucre)
    draw_sugar(cv, gl, CX, CY + 40, 200 * pulse, sa, 0.25 + 0.05 * math.sin(t * 0.8))
    if t > t_sucre - 0.2:
        gcircle(gl, (CX, CY), 160 + 260 * eout((t - t_sucre) / 0.9), AMBER * 0.9 * (1 - eout((t - t_sucre) / 0.9)), 3)
    compose_glow(cv, gl)
    # titre de la miniature, puis le compteur
    a_cov = 1 - sstep(t_hum + 0.2, t_hum + 0.6, t)
    label(cv, ["L'HUMANITÉ", "DANS UN SUCRE ?"], a_cov, y0=500, size=92, cols=[WHITE, AMBER])
    a_cnt = sstep(t_huit - 0.35, t_huit + 0.1, t) * (1 - sstep(t_tenir - 0.35, t_tenir - 0.1, t))
    if a_cnt > 0:
        prog = (t - t_huit + 0.3) / 0.8                   # comptage en 0,8 s : le chiffre final reste lisible
        kk = eout(prog)
        s = f"{8.2 * kk:.1f}".replace(".", ",")          # arrondi de l'ONU (2024) : pas de fausse précision
        txt(cv, s, 540, 492, 150, F_DBLACK, WHITE, a_cnt)
        txt(cv, "MILLIARDS D'HUMAINS", 540, 608, 40, F_DBOLD, CYAN, a_cnt, 0, 10.0)
        # la source n'apparaît qu'une fois le compte arrivé à 8,2 (une capture en cours de comptage ne doit pas
        # attribuer « 7,8 » à l'ONU)
        txt(cv, "ONU, 2024", 540, 662, 28, F_SEMI, LIGHT, 0.8 * a_cnt * sstep(1.0, 1.25, prog), 0, 4.0)
    fin_q = t_cond if t_cond is not None else t_phys
    a_q = sstep(t_tenir - 0.02, t_tenir + 0.25, t) * (1 - sstep(fin_q - 0.45, fin_q - 0.2, t))
    label(cv, ["DANS UN SUCRE ?"], a_q, y0=520, size=92, cols=[AMBER])
    if t_cond is not None:
        a_c = sstep(t_cond - 0.1, t_cond + 0.2, t) * (1 - sstep(t_phys - 0.45, t_phys - 0.2, t))
        label(cv, ["SI ON RETIRAIT", "LE VIDE DES ATOMES"], a_c, y0=505, size=80, cols=[WHITE, CYAN])
    a_ph = sstep(t_phys - 0.1, t_phys + 0.2, t)
    label(cv, ["UN VRAI CALCUL", "DE PHYSIQUE"], a_ph, y0=500, size=86, cols=[WHITE, CYAN])
    return cv


# 2. descente : peau -> cellule -> ADN -> atome
_hex = []
for gy in range(-30, 31):
    for gx in range(-18, 19):
        cx = gx * 104 + (52 if gy % 2 else 0)
        cy = gy * 90
        pts = []
        for k in range(6):
            a = math.pi / 6 + k * math.pi / 3
            j = rng.uniform(0.85, 1.12)
            pts.append((cx + 58 * j * math.cos(a), cy + 58 * j * math.sin(a)))
        _hex.append(np.array(pts, np.float32))
HEX = np.stack(_hex)
ORG = [(rng.uniform(-300, 300), rng.uniform(-300, 300), rng.uniform(14, 34), rng.uniform(0, 180)) for _ in range(26)]
ORG = [o for o in ORG if math.hypot(o[0] - 70, o[1] + 50) > 190 and math.hypot(o[0], o[1]) < 360]
LAYERS = [("PEAU", -3), ("CELLULE", -5), ("ADN", -9), ("ATOME", -10)]


def layer_alpha(sc):
    return sstep(0.25, 0.55, sc) * (1 - sstep(2.0, 3.6, sc))


def draw_skin(gl, sc, a):
    if a <= 0.01:
        return
    P = HEX * sc + np.array([CX, CY], np.float32)
    vis = (P[:, :, 0].max(1) > -50) & (P[:, :, 0].min(1) < W + 50) & (P[:, :, 1].max(1) > -50) & (P[:, :, 1].min(1) < H + 50)
    P = P[vis]
    hp = [(p * 0.5).astype(np.int32) for p in P]
    cv2.polylines(gl, hp, True, tuple(float(v) * 0.55 * a for v in WARM), 1, cv2.LINE_AA)
    for p in hp[::3]:
        c = p.mean(0).astype(int)
        cv2.circle(gl, (int(c[0]), int(c[1])), max(int(8 * sc), 1), tuple(float(v) * 0.25 * a for v in WARM), -1)


def draw_cellv(gl, sc, a, t):
    if a <= 0.01:
        return
    c = np.array([CX, CY], np.float32)
    col = np.array([0.35, 1.0, 0.75], np.float32)
    gcircle(gl, c, 400 * sc, col * 0.8 * a, 3)
    gcircle(gl, c, 410 * sc, col * 0.25 * a, 2)
    gcircle(gl, c + np.array([70, -50]) * sc, 150 * sc, VIOLET * 0.9 * a, 3)
    gcircle(gl, c + np.array([95, -70]) * sc, 40 * sc, VIOLET * 0.5 * a, -1)
    for (ox, oy, r, ang) in ORG:
        e = (int((CX + ox * sc) * 0.5), int((CY + oy * sc) * 0.5))
        cv2.ellipse(gl, e, (max(int(r * sc * 0.5), 1), max(int(r * 0.45 * sc * 0.5), 1)), ang + t * 8, 0, 360,
                    tuple(float(v) * 0.6 * a for v in col), 1, cv2.LINE_AA)


def draw_dna(gl, sc, a, t):
    if a <= 0.01:
        return
    A, lam = 170 * sc, 560 * sc
    ys = np.arange(-H, H, 6, dtype=np.float32)
    ph = 2 * np.pi * ys / lam + t * 1.4
    x1, z1 = CX + A * np.sin(ph), np.cos(ph)
    x2, z2 = CX + A * np.sin(ph + 2.3), np.cos(ph + 2.3)
    yy = CY + ys
    for xs, zs, col in ((x1, z1, CYAN), (x2, z2, VIOLET)):
        for i in range(len(ys) - 1):
            if -40 < yy[i] < H + 40:
                b = 0.35 + 0.65 * (zs[i] * 0.5 + 0.5)
                gline(gl, (xs[i], yy[i]), (xs[i + 1], yy[i + 1]), col, max(int(3 * sc), 2), 0.9 * a * b)
    step = max(int(lam / 10 / 6), 1)
    for i in range(0, len(ys), step):
        if -40 < yy[i] < H + 40:
            b = 0.25 + 0.4 * ((z1[i] + z2[i]) * 0.25 + 0.5)
            col = AMBER if (i // step) % 2 else GREEN
            gline(gl, (x1[i], yy[i]), (x2[i], yy[i]), col, max(int(2 * sc), 1), a * b)


def draw_atom_core(gl, t, scale=150, a=1.0, cx=CX, cy=CY, nucleus=True):
    draw_cloud(gl, cx, cy, scale * 1.2, t, n=20000, bright=0.13 * a)
    gcircle(gl, (cx, cy), scale * 0.55, CYAN * 0.025 * a, -1)
    if nucleus:
        gcircle(gl, (cx, cy), 6, AMBER * 2.0 * a, -1)


def descent_z(t):
    s0 = SC["descente"][0]
    keys = [cue("descente:peau", 0, s0 + 2.5), cue("descente:cellules", 0, s0 + 4.5),
            cue("descente:adn", 0, s0 + 6.5), cue("descente:atomes", 0, s0 + 8.5)]
    pts_t = [s0 - 0.2] + keys
    pts_z = [-0.6, 0.0, 1.0, 2.0, 3.0]
    z = float(np.interp(t, pts_t, pts_z))
    return min(3.0, z + 0.25)


def sc_descente(t):
    cv, gl = new_frame(t)
    z = descent_z(t)
    for k in range(4):
        sc = 2.6 ** ((z - k) * 1.6)
        a = layer_alpha(sc) if k < 3 else sstep(0.25, 0.6, sc)
        if k == 0:
            draw_skin(gl, sc, a)
        elif k == 1:
            draw_cellv(gl, sc, a, t)
        elif k == 2:
            draw_dna(gl, sc, a, t)
        elif a > 0.01:
            draw_atom_core(gl, t, 150 * min(sc, 1.0), a)
    compose_glow(cv, gl)
    s0 = SC["descente"][0]
    keys = [cue("descente:peau", 0, s0 + 2.5), cue("descente:cellules", 0, s0 + 4.5),
            cue("descente:adn", 0, s0 + 6.5), cue("descente:atomes", 0, s0 + 8.5)]
    for k, (name, _) in enumerate(LAYERS):
        a_in = sstep(keys[k] - 0.15, keys[k] + 0.15, t)
        a_out = 1 - sstep(keys[k + 1] - 0.30, keys[k + 1] - 0.10, t) if k < 3 else 1.0
        label(cv, [name], a_in * a_out, y0=540, size=104, cols=[[WARM, GREEN, VIOLET, CYAN][k]])
    a_d = sstep(s0 + 0.2, s0 + 0.6, t) * (1 - sstep(keys[0] - 0.30, keys[0] - 0.10, t))
    label(cv, ["ON DESCEND"], a_d, y0=540, size=96)
    return cv


def expo_at(t):
    """Puissance de dix affichée par la règle, d'après la scène en cours."""
    if t < SC["descente"][0] + 0.8:
        return -2.0
    if t < SC["atome"][0]:
        s0 = SC["descente"][0]
        k = [cue("descente:peau", 0, s0 + 2.5), cue("descente:cellules", 0, s0 + 4.5),
             cue("descente:adn", 0, s0 + 6.5), cue("descente:atomes", 0, s0 + 8.5)]
        return float(np.interp(t, [s0 + 0.8, k[0], k[1] - 0.45, k[1], k[2] - 0.45, k[2], k[3] - 0.45, k[3]],
                               [-2.0, -3, -3, -5, -5, -9, -9, -10]))
    if t < SC["stade"][0]:
        tn = cue("atome:noyau", 0, SC["atome"][0] + 6)
        return lerp(-10, -15, eout((t - tn) / 1.4)) if t > tn else -10.0
    if t < SC["experience"][0]:
        return -15.0
    if t < SC["etoile"][0]:
        # (v3, contre-vérification du 20/10) la Terre (1,3 × 10⁷ m) est à 10⁷ tant qu'elle est à l'écran ; on
        # redescend au sucre (10⁻² m) une fois les noyaux tassés
        s0 = SC["experience"][0]
        tp = cue("experience:prend", 0, s0 + 1.8)
        tr = cue("experience:tasse", 0, s0 + 5)
        if t < tp:
            return float(np.interp(t, [s0, max(tp, s0 + 0.3)], [-15, 7]))
        return float(np.interp(t, [tr, tr + 2.0], [7, -2]))
    if t < SC["chaise"][0]:
        return 4.3
    if t < SC["outro"][0]:
        # l'étoile (≈ 2 × 10⁴ m) garde 10⁴ pendant le fondu ; la chaise (≈ 1 m) 10⁰ ; les électrons 10⁻¹⁰
        c0 = SC["chaise"][0]
        te = cue("chaise:electrons", 0, cue("chaise:repoussent", 0, c0 + 4.1))
        return float(np.interp(t, [c0, c0 + XF, c0 + XF + 0.5, te - 0.2, te + 0.4], [4.3, 4.3, 0.0, 0.0, -10.0]))
    tb = cue("outro:bord", 0, SC["outro"][0] + 3)
    return float(np.interp(t, [SC["outro"][0], tb + 0.8], [-10, 26.64]))   # bord : rayon ≈ 4,4 × 10²⁶ m


# 3. l'atome : presque entièrement du vide
def sc_atome(t):
    s0, s1 = SC["atome"]
    cv, gl = new_frame(t)
    zoom = 1.0 + 0.25 * sstep(s0, s1, t)
    draw_atom_core(gl, t, 150 * zoom)
    t_vide = cue("atome:vide", 0, s0 + 4)
    t_noyau = cue("atome:noyau", 0, s0 + 6)
    t_cent = cue("atome:cent", 0, s0 + 7)
    pulse = sstep(t_noyau - 0.2, t_noyau + 0.2, t)
    if pulse > 0:
        ph = ((t - t_noyau) % 1.3) / 1.3
        gcircle(gl, (CX, CY), 12 + 90 * ph, AMBER * (1 - ph) * 1.2 * pulse, 2)
    compose_glow(cv, gl)
    crisp_dot(cv, CX, CY, 3.2, (1.0, 0.85, 0.6), 1.0)
    a_s = sstep(s0 + 0.2, s0 + 0.6, t) * (1 - sstep(t_vide - 0.5, t_vide - 0.2, t))
    label(cv, ["PREMIÈRE", "SURPRISE"], a_s, y0=500, size=86, cols=[WHITE, CYAN])
    va = sstep(t_vide - 0.15, t_vide + 0.25, t) * (1 - sstep(t_noyau - 0.4, t_noyau, t))
    label(cv, ["DU VIDE"], va, y0=530, size=120, cols=[CYAN])
    if pulse > 0:
        crisp_lines(cv, [[(CX + 10, CY - 10), (CX + 120, CY - 120), (CX + 190, CY - 120)]], AMBER, pulse, 3)
        txt(cv, "NOYAU", CX + 200, CY - 120, 52, F_DBLACK, AMBER, pulse, -1)
    ca = sstep(t_cent - 0.1, t_cent + 0.35, t)
    label(cv, ["≈ 100 000 ×", "PLUS PETIT QUE L'ATOME"], ca, y0=500, size=96, cols=[WHITE, CYAN])
    return cv


# 4. le stade : le noyau serait un moustique au milieu
def stadium_polys(cx, cy, k):
    """Stade vu de dessus : terrain (105 x 68) et gradins ovales, k = pixels par mètre."""
    def P(x, y):
        return (cx + x * k, cy + y * k)
    L2, W2 = 52.5, 34.0
    polys = [[P(-W2, -L2), P(W2, -L2), P(W2, L2), P(-W2, L2), P(-W2, -L2)], [P(-W2, 0), P(W2, 0)]]
    polys.append([P(9.15 * math.cos(a), 9.15 * math.sin(a)) for a in np.linspace(0, 2 * np.pi, 90)])
    for sgn in (-1, 1):
        y0 = sgn * L2
        polys.append([P(-20.16, y0), P(-20.16, y0 - sgn * 16.5), P(20.16, y0 - sgn * 16.5), P(20.16, y0)])
        polys.append([P(-9.16, y0), P(-9.16, y0 - sgn * 5.5), P(9.16, y0 - sgn * 5.5), P(9.16, y0)])
    rings = []
    for rr in (0, 1, 2, 3):
        ax, ay = (W2 + 9 + rr * 5.0) * k, (L2 + 10 + rr * 5.0) * k
        a = np.linspace(0, 2 * np.pi, 160)
        rings.append(np.stack([cx + ax * np.cos(a), cy + ay * np.sin(a)], 1))
    return polys, rings


def draw_mosquito(cv, x, y, s, a, t):
    """Moustique stylisé (corps, ailes, pattes), s = longueur du corps en pixels."""
    if a <= 0.01:
        return
    flap = 0.25 * math.sin(t * 60)
    body = [np.array([(x + s * 0.5 * math.cos(u), y + s * 0.11 * math.sin(u)) for u in np.linspace(0, 2 * np.pi, 24)])]
    crisp_fill(cv, body, (0.95, 0.92, 0.85), a)
    crisp_dot(cv, x + s * 0.55, y, s * 0.11, (0.95, 0.92, 0.85), a)
    wings = []
    for sg in (-1, 1):
        ang = sg * (0.9 + flap)
        wings.append([(x - s * 0.05, y), (x - s * 0.05 - s * 0.55 * math.cos(ang) * 0.6, y + sg * s * 0.55)])
    crisp_lines(cv, wings, (0.80, 0.90, 1.0), 0.8 * a, max(2, int(s * 0.05)))
    legs = []
    for k in (-0.2, 0.05, 0.3):
        for sg in (-1, 1):
            legs.append([(x + s * k, y), (x + s * k - s * 0.12, y + sg * s * 0.42), (x + s * k - s * 0.25, y + sg * s * 0.6)])
    crisp_lines(cv, legs, (0.85, 0.85, 0.80), 0.7 * a, max(1, int(s * 0.02)))


def sc_stade(t):
    s0, s1 = SC["stade"]
    cv, gl = new_frame(t, stars=0.3, neb=0.5)
    t_stade = cue("stade:stade", 0, s0 + 1)
    t_moust = cue("stade:moustique", 0, s0 + 2.6)
    t_rien = cue("stade:rien", 0, s0 + 5.6)
    t_nuage = cue("stade:nuage", 0, s0 + 6.9)
    zin = eout((t - t_moust + 0.3) / 1.4) * (1 - eout((t - t_rien + 0.2) / 1.2))
    k = lerp(4.2, 11.0, zin)
    sx_, sy_ = CX, CY + 55                      # centre du stade, un peu bas : les titres restent dégagés
    pa = sstep(s0 - 0.1, s0 + 0.6, t)
    polys, rings = stadium_polys(sx_, sy_, k)
    # pelouse
    L2, W2 = 52.5, 34.0
    for i in range(14):
        y0 = sy_ + (-L2 + i * 105 / 14) * k
        y1 = y0 + 105 / 14 * k
        col = (0.040, 0.12, 0.060) if i % 2 else (0.050, 0.145, 0.070)
        x0, x1 = sx_ - W2 * k, sx_ + W2 * k
        ya, yb, xa, xb = int(max(y0, 0)), int(min(y1, H)), int(max(x0, 0)), int(min(x1, W))
        if ya < yb and xa < xb:
            cv[ya:yb, xa:xb] = cv[ya:yb, xa:xb] * (1 - pa) + np.array(col, np.float32) * pa
    crisp_lines(cv, polys, (0.92, 0.95, 0.92), 0.80 * pa, max(int(0.14 * k), 2))
    crisp_lines(cv, rings, (0.55, 0.65, 0.85), 0.30 * pa, 2, True)
    for fx, fy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):     # projecteurs
        gcircle(gl, (sx_ + fx * (W2 + 16) * k, sy_ + fy * (L2 + 18) * k), 10, np.array([1.0, 0.97, 0.9], np.float32) * 1.5 * pa, -1)
    ha = sstep(t_nuage - 0.3, t_nuage + 0.9, t)
    if ha > 0:
        draw_cloud(gl, sx_, sy_, 300, t, n=22000, bright=0.12 * ha)
    ma = sstep(t_moust - 0.25, t_moust + 0.3, t)
    if ma > 0:
        ph = ((t - t_moust) % 1.2) / 1.2
        gcircle(gl, (sx_, sy_), 34 + 80 * ph, AMBER * (1 - ph) * ma, 2)
    compose_glow(cv, gl)
    if ma > 0:
        draw_mosquito(cv, sx_, sy_, 26 + 12 * zin, ma, t)
        xr = SAFE_LEFT + 14 + max(text_width("NOYAU", F_DBLACK, 50), text_width("= un moustique", F_SEMI, 36))
        crisp_lines(cv, [[(sx_ - 24, sy_ - 20), (sx_ - 110, sy_ - 150), (xr + 12, sy_ - 150)]], AMBER, ma, 3)
        txt(cv, "NOYAU", xr, sy_ - 172, 50, F_DBLACK, AMBER, ma, 1)
        txt(cv, "= un moustique", xr, sy_ - 122, 36, F_SEMI, WHITE, ma, 1)
        # sous l'étiquette, hors de la zone des sous-titres (qui peuvent passer sur 2 lignes)
        # (v3, contre-vérification du 21/10) la mention reste tant que l'étiquette NOYAU est là : quand l'image
        # recule, le moustique dessiné grossit par rapport au terrain
        txt(cv, "(agrandi pour être visible)", SAFE_LEFT + 14, sy_ - 86, 24, F_MEDI, LIGHT, ma * 0.9, -1)
    la = sstep(t_stade - 0.3, t_stade + 0.3, t) * (1 - sstep(t_nuage - 0.4, t_nuage, t))
    label(cv, ["SI L'ATOME", "ÉTAIT UN STADE"], la, y0=500, size=86, cols=[WHITE, CYAN])
    label(cv, ["TOUT AUTOUR :", "DES ÉLECTRONS"], ha, y0=500, size=80, cols=[WHITE, CYAN])
    return cv


# 5. la masse : 99,9 % dans le noyau
def sc_masse(t):
    s0, s1 = SC["masse"]
    cv, gl = new_frame(t, stars=0.5)
    t99 = cue("masse:999%", 0, s0 + 2.0)
    k = eout((t - t99 + 0.2) / 1.0)
    draw_cloud(gl, CX, CY + 160, 110, t, n=4000, bright=0.04)
    gcircle(gl, (CX, CY + 160), 7, AMBER * 2.0, -1)
    compose_glow(cv, gl)
    crisp_dot(cv, CX, CY + 160, 4, (1, 0.85, 0.6), 1)
    a = sstep(t99 - 0.4, t99, t)
    txt(cv, f"{99.9 * k:.1f}".replace(".", ",") + " %", 540, 540, 190, F_DBLACK, AMBER, a)
    txt(cv, "DE LA MASSE DE L'ATOME", 540, 665, 46, F_DBOLD, WHITE, a, 0, 4.0)
    txt(cv, "EST DANS LE NOYAU", 540, 722, 46, F_DBOLD, CYAN, a, 0, 4.0)
    x0, x1, y = 150, 930, 775
    crisp_fill(cv, [rrect(x0, y - 14, x1, y + 14, 14)], (0.12, 0.14, 0.2), a)
    xf = x0 + (x1 - x0) * k * 0.999
    if xf > x0 + 28:
        crisp_fill(cv, [rrect(x0, y - 14, xf, y + 14, 14)], AMBER, a)
    txt(cv, "électrons : moins de 0,1 %", 930, 816, 32, F_MEDI, LIGHT, a * k, 1)
    return cv


# 6. l'expérience : tous les humains, sans le vide
EARTH_N = 2200
_ll = rng.standard_normal((EARTH_N, 3)).astype(np.float32)
EARTH_P = _ll / np.linalg.norm(_ll, axis=1, keepdims=True)


def _land_map():
    """Carte équirectangulaire (512 x 256) de continents procéduraux (bruit lissé, ~30 % de terres)."""
    r = np.random.default_rng(11)
    acc = np.zeros((256, 512), np.float32)
    for sg, amp in ((28, 1.0), (10, 0.5), (4, 0.22)):
        z = r.standard_normal((256, 512)).astype(np.float32)
        z = cv2.GaussianBlur(np.pad(z, ((0, 0), (64, 64)), mode="wrap"), (0, 0), sg)[:, 64:-64]
        acc += amp * z / (z.std() + 1e-6)
    lat = np.linspace(90, -90, 256)[:, None]
    acc -= 0.9 * (np.abs(lat) > 72)                  # pas de grandes terres aux pôles
    return acc > np.percentile(acc, 70)


LAND = _land_map()
_ez = np.arange(-260, 261, dtype=np.float32)
EDX, EDY = np.meshgrid(_ez, _ez)


def _lonlat(nx, ny, nz, rot):
    """Coordonnées géographiques du point de normale (nx, ny, nz) pour une rotation de la Terre rot (radians)."""
    x = nx * math.cos(rot) - nz * math.sin(rot)
    z = nx * math.sin(rot) + nz * math.cos(rot)
    lon = np.arctan2(x, z)
    lat = np.arcsin(np.clip(-ny, -1, 1))
    return lon, lat


def draw_earth(cv, gl, cx, cy, R, a, t):
    """Terre de nuit vue de l'espace : océans sombres, continents, croissant éclairé à droite, atmosphère."""
    if a <= 0.01:
        return
    s = R / 250.0
    dx, dy = EDX * s, EDY * s
    rr = (dx ** 2 + dy ** 2) / R ** 2
    inside = rr < 1
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    nx, ny = dx / R, dy / R
    lon, lat = _lonlat(nx, ny, nz, t * 0.22)
    u = ((lon / (2 * np.pi) + 0.5) * 511).astype(np.int32) % 512
    v = ((0.5 - lat / np.pi) * 255).astype(np.int32).clip(0, 255)
    land = LAND[v, u]
    L = np.array([0.72, -0.35, 0.60], np.float32)
    L /= np.linalg.norm(L)
    dif = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    ocean = np.array([0.012, 0.035, 0.090], np.float32)
    terre = np.array([0.040, 0.055, 0.035], np.float32)
    base = np.where(land[..., None], terre, ocean)
    col = base * (0.35 + 2.6 * dif[..., None] ** 1.3)
    col += np.array([0.10, 0.22, 0.45], np.float32) * (np.clip(1 - nz, 0, 1) ** 3 * 0.8)[..., None]   # limbe bleuté
    m = (inside * a).astype(np.float32)[..., None]
    x0, y0 = int(cx - 260 * s), int(cy - 260 * s)
    hgt, wid = col.shape[:2]
    ya, yb, xa, xb = max(y0, 0), min(y0 + hgt, H), max(x0, 0), min(x0 + wid, W)
    if ya < yb and xa < xb:
        sub_c = col[ya - y0:yb - y0, xa - x0:xb - x0]
        sub_m = m[ya - y0:yb - y0, xa - x0:xb - x0]
        cv[ya:yb, xa:xb] = cv[ya:yb, xa:xb] * (1 - sub_m) + sub_c * sub_m
    gcircle(gl, (cx, cy), R + 4, CYAN * 0.55 * a, 3)
    gcircle(gl, (cx, cy), R + 14, CYAN * 0.12 * a, 6)


def human_lights(t, R, cx, cy):
    """Lumières des villes (les humains) : points sur les terres émergées, côté visible ; (x, y, visible)."""
    a = t * 0.22
    P = HUM_P
    x = P[:, 0] * math.cos(a) + P[:, 2] * math.sin(a)
    z = -P[:, 0] * math.sin(a) + P[:, 2] * math.cos(a)
    y = P[:, 1]
    return cx + x * R, cy + y * R, z > 0.05


def _human_points(n=2600):
    r = np.random.default_rng(5)
    out = []
    while len(out) < n:
        p = r.standard_normal(3)
        p /= np.linalg.norm(p)
        lon, lat = math.atan2(p[0], p[2]), math.asin(-p[1])
        u = int((lon / (2 * math.pi) + 0.5) * 511) % 512
        v = int(np.clip((0.5 - lat / math.pi) * 255, 0, 255))
        if LAND[v, u] and abs(lat) < 1.15:
            out.append(p)
    return np.array(out, np.float32)


HUM_P = _human_points()


S_SUC = 160                   # arête (unités de cube_polys) du sucre de la comparaison


def sc_experience(t):
    s0, s1 = SC["experience"]
    cv, gl = new_frame(t)
    t_prend = cue("experience:prend", 0, s0 + 1.8)
    t_retire = cue("experience:retire", 0, s0 + 3.4)
    t_tasse = cue("experience:tasse", 0, s0 + 4.7)
    t_dense = cue("experience:dense", 0, s0 + 8.6)
    t_nasa = cue("experience:nasa", 0, s0 + 11.6)
    t_milliard = cue("experience:milliard", 0, s0 + 14.6)
    t_hum = cue("experience:lhumanite", 0, s0 + 16.4)
    t_tiend = cue("experience:tiendrait", 0, s0 + 19.6)
    t_sucre2 = cue("experience:sucre", 1, s0 + 21.8)
    R = 250
    flow = eout((t - t_retire) / max(t_dense - t_retire, 0.5))
    ea = sstep(s0 - 0.1, s0 + 0.5, t) * (1 - sstep(t_retire + 0.2, t_tasse + 0.6, t))
    draw_earth(cv, gl, CX, CY, R, ea, t)
    # les lumières des villes = les humains ; elles quittent la Terre et se tassent au centre
    x, y, vis = human_lights(t, R, CX, CY)
    sw = np.sin(np.arange(len(x)) * 1.7 + t * 3) * 50 * flow * (1 - flow)
    xs = lerp(x, CX, flow) + sw
    ys = lerp(y, CY, flow)
    show = vis | (flow > 0.05)
    pa = sstep(t_prend - 0.3, t_prend + 0.3, t) * (1 - sstep(t_dense, t_dense + 0.6, t))
    add_pts(gl, xs[show], ys[show], (0.35 + 0.3 * flow) * pa, AMBER)
    # cube de matière nucléaire : l'humanité sans le vide
    ca = sstep(t_tasse + 0.6, t_dense, t)
    side = sstep(t_nasa - 0.4, t_nasa + 0.4, t)                    # part à gauche pour la comparaison
    nest = eout((t - t_tiend) / max(t_sucre2 - t_tiend, 0.6))      # entre dans le vrai sucre
    sug_x = lerp(760, CX, nest)
    hx = lerp(lerp(CX, 320, side), sug_x, nest)
    cy_c = CY - 5                                # (v2) plus haut : un sous-titre sur 2 lignes ne touche pas les cubes
    hy = cy_c + 10 * nest
    # (v2) proportions honnêtes : à la même densité, l'humanité (≈ 0,5 milliard de t) fait environ la moitié du
    # volume d'un sucre de matière d'étoile à neutrons (≈ 1 milliard de t) : arête ≈ 0,8 fois celle du sucre
    hs = lerp(lerp(90 + 25 * ca, 0.80 * S_SUC, side), 0.78 * S_SUC, nest)
    sa = sstep(t_nasa - 0.3, t_nasa + 0.3, t)
    glass = sstep(t_tiend - 0.4, t_tiend + 0.4, t)
    if sa > 0:
        draw_sugar(cv, gl, sug_x, cy_c, S_SUC, sa, 0.25 + 0.05 * math.sin(t * 0.7), glass)
    draw_hot_cube(cv, gl, hx, hy, hs, ca, 0.3 + 0.1 * math.sin(t))
    if nest > 0.98:
        u = eout((t - t_sucre2) / 0.8)
        gcircle(gl, (sug_x, cy_c), 120 + 240 * u, AMBER * 0.9 * (1 - u), 3)
    compose_glow(cv, gl)
    # titres (zone haute) : un seul à la fois
    a1 = sstep(t_prend - 0.2, t_prend + 0.3, t) * (1 - sstep(t_retire - 0.25, t_retire - 0.05, t))
    label(cv, ["TOUS LES HUMAINS"], a1, y0=540, size=92)
    a2 = sstep(t_retire - 0.1, t_retire + 0.2, t) * (1 - sstep(t_tasse - 0.25, t_tasse - 0.05, t))
    label(cv, ["ON RETIRE", "LE VIDE"], a2, y0=505, size=92, cols=[WHITE, AMBER])
    a3 = sstep(t_tasse - 0.1, t_tasse + 0.2, t) * (1 - sstep(t_dense - 0.35, t_dense - 0.1, t))
    label(cv, ["ON TASSE", "LES NOYAUX"], a3, y0=505, size=92, cols=[WHITE, AMBER])
    a4 = sstep(t_dense - 0.2, t_dense + 0.2, t) * (1 - sstep(t_nasa - 0.4, t_nasa - 0.15, t))
    label(cv, ["UNE DENSITÉ", "D'ÉTOILE À NEUTRONS"], a4, y0=510, size=76, cols=[WHITE, CYAN])
    a5 = sstep(t_nasa - 0.2, t_nasa + 0.2, t) * (1 - sstep(t_hum - 0.35, t_hum - 0.1, t))
    label(cv, ["1 SUCRE D'ÉTOILE À NEUTRONS", "≈\u202f1 MILLIARD DE TONNES"], a5, y0=510, size=66, cols=[WHITE, AMBER])
    a6 = sstep(t_hum - 0.2, t_hum + 0.2, t) * (1 - sstep(t_tiend - 0.4, t_tiend - 0.15, t))
    label(cv, ["L'HUMANITÉ PÈSE", "ENVIRON 2 FOIS MOINS"], a6, y0=505, size=80, cols=[WHITE, CYAN])
    a7 = sstep(t_tiend - 0.2, t_tiend + 0.2, t) * (1 - sstep(t_sucre2 - 0.35, t_sucre2 - 0.1, t))
    label(cv, ["ELLE TIENDRAIT DONC…"], a7, y0=540, size=80)
    a8 = sstep(t_sucre2 - 0.25, t_sucre2 + 0.15, t)
    label(cv, ["TOUTE L'HUMANITÉ", "DANS UN SUCRE"], a8, y0=505, size=92, cols=[WHITE, AMBER])
    # légendes au-dessus des deux cubes pendant la comparaison (au-dessus de y = 840 : pas de boutons TikTok)
    a_r = sstep(t_hum - 0.2, t_hum + 0.3, t) * (1 - sstep(t_tiend - 0.4, t_tiend - 0.1, t))
    if a_r > 0:
        txt(cv, "1 sucre d'étoile à neutrons", 760, CY - 248, 30, F_SEMI, LIGHT, a_r)
        txt(cv, "≈\u202f1 milliard de t", 760, CY - 201, 44, F_DBLACK, WHITE, a_r)
    a_l = sstep(t_hum - 0.2, t_hum + 0.3, t) * (1 - sstep(t_tiend - 0.4, t_tiend - 0.1, t))
    if a_l > 0:
        txt(cv, "toute l'humanité", 320, CY - 248, 30, F_SEMI, LIGHT, a_l)
        txt(cv, "≈\u202f0,5 milliard de t", 320, CY - 201, 44, F_DBLACK, AMBER, a_l)
    return cv


# 7. l'étoile à neutrons
def draw_neutron_star(gl, t, cx, cy, R, a):
    if a <= 0.01:
        return
    ang = t * 2.2
    axis = np.array([math.sin(ang) * 0.9, -math.cos(ang * 0.3) * 0.4 - 0.6])
    axis /= np.linalg.norm(axis)
    perp = np.array([-axis[1], axis[0]])
    for L in (1.6, 2.2, 3.1, 4.4, 6.2):
        for side in (-1, 1):
            th = np.linspace(0.08, np.pi - 0.08, 80)
            r = L * R * np.sin(th) ** 2
            px = cx + (r * np.sin(th) * side) * perp[0] + (r * np.cos(th)) * axis[0]
            py = cy + (r * np.sin(th) * side) * perp[1] + (r * np.cos(th)) * axis[1]
            pts = (np.stack([px, py], 1) * 0.5).astype(np.int32)
            cv2.polylines(gl, [pts], False, tuple(float(v) * 0.22 * a / (L ** 0.4) for v in CYAN), 1, cv2.LINE_AA)
    for sgn in (-1, 1):
        base = np.array([cx, cy]) + axis * R * sgn
        for wdt, inten in ((90, 0.10), (45, 0.18), (18, 0.35)):
            tip = base + axis * 640 * sgn
            poly = np.array([base, tip + perp * wdt * 3, tip - perp * wdt * 3]) * 0.5
            cv2.fillPoly(gl, [poly.astype(np.int32)], tuple(float(v) * inten * a for v in np.array([0.75, 0.9, 1.0])))
    cv2.circle(gl, (int(cx) // 2, int(cy) // 2), int(R * 0.55), tuple(float(v) * 1.2 * a for v in np.array([0.75, 0.88, 1.0])), -1)
    gcircle(gl, (cx, cy), R * 1.05, CYAN * 0.6 * a, 4)


def sc_etoile(t):
    s0, s1 = SC["etoile"]
    cv, gl = new_frame(t)
    t_et = cue("etoile:etoile", 0, s0 + 1.6)
    t_sol = cue("etoile:masse", 0, s0 + 3.6)
    t_km = cue("etoile:kilometres", 0, s0 + 5.9)
    a = sstep(s0 - 0.2, s0 + 0.6, t)
    R = 140 * (1 + 0.03 * math.sin(t * 9))
    draw_neutron_star(gl, t, CX, CY - 10, R, a)
    gl *= TOPFADE
    compose_glow(cv, gl)
    a1 = sstep(s0 + 0.1, s0 + 0.5, t) * (1 - sstep(t_et - 0.35, t_et - 0.1, t))
    label(cv, ["ELLE EXISTE"], a1, y0=540, size=92)
    a2 = sstep(t_et - 0.2, t_et + 0.2, t) * (1 - sstep(t_sol - 0.35, t_sol - 0.1, t))
    label(cv, ["ÉTOILE", "À NEUTRONS"], a2, y0=505, size=96, cols=[WHITE, CYAN])
    a3 = sstep(t_sol - 0.2, t_sol + 0.2, t)
    label(cv, ["PLUS QUE LA MASSE", "DU SOLEIL"], a3, y0=505, size=86, cols=[WHITE, AMBER])
    ka = sstep(t_km - 0.25, t_km + 0.25, t)
    if ka > 0:
        yd = CY + 140
        crisp_lines(cv, [[(CX - R, yd), (CX + R, yd)], [(CX - R, yd - 12), (CX - R, yd + 12)],
                         [(CX + R, yd - 12), (CX + R, yd + 12)]], AMBER, ka, 3)
        txt(cv, "≈\u202f20\u202fkm", 540, yd + 50, 52, F_DBLACK, AMBER, ka)
    return cv


# 8. la chaise
CHAIR = [[(380, 700), (380, 980)], [(380, 980), (720, 980)], [(395, 980), (395, 1150)], [(705, 980), (705, 1150)],
         [(380, 700), (420, 700)]]


def partial(polys, p):
    out = []
    lens = [sum(math.dist(a, b) for a, b in zip(q, q[1:])) for q in polys]
    rem = sum(lens) * clamp(p)
    for q, L in zip(polys, lens):
        if rem <= 0:
            break
        if rem >= L:
            out.append(q)
            rem -= L
            continue
        acc, pts = 0, [q[0]]
        for a, b in zip(q, q[1:]):
            d = math.dist(a, b)
            if acc + d >= rem:
                f = (rem - acc) / d
                pts.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                break
            pts.append(b)
            acc += d
        out.append(pts)
        rem = 0
    return out


def draw_two_clouds(gl, t, gap_k, glow_k):
    rr = np.random.default_rng(int(t * FPS) * 3 + 11)
    n = 9000
    inter = CY
    gap = lerp(260, 14, gap_k) + 4 * math.sin(t * 9) * gap_k
    for sgn, col in ((-1, CYAN), (1, WARM)):
        x = rr.normal(0, 170, n)
        y = rr.normal(0, 88, n)
        cy = inter + sgn * (gap / 2 + 140)
        yy = cy + y
        lim = inter + sgn * gap / 2
        over = (yy > lim) if sgn < 0 else (yy < lim)
        yy[over] = 2 * lim - yy[over]
        add_pts(gl, CX + x, yy, 0.34, col)
    if glow_k > 0:
        xs = rr.uniform(330, 750, 900)
        ys = inter + rr.normal(0, 4, 900)
        add_pts(gl, xs, ys, 0.30 * glow_k, np.array([1.0, 0.95, 0.85], np.float32))


def sc_chaise(t):
    s0, s1 = SC["chaise"]
    cv, gl = new_frame(t, stars=0.6)
    t_parce = cue("chaise:parce", 0, s0 + 3.0)
    t_rep = cue("chaise:repoussent", 0, s0 + 4.1)
    t_quant = cue("chaise:quantique", 0, s0 + 5.6)
    t_touch = cue("chaise:toucher", 0, s0 + 8.4)
    t_au = cue("chaise:au", 0, 1e9)              # chute « tu n'as jamais touché ta chaise » : retirée en v2
    wipe = sstep(t_parce - 0.2, t_parce + 0.5, t)
    if wipe < 1:
        for q in partial(CHAIR, eout((t - s0) / 1.6)):
            for a_, b_ in zip(q, q[1:]):
                gline(gl, a_, b_, WHITE, 3, 0.5 * (1 - wipe))
    if wipe > 0:
        gap_k = sstep(t_parce, t_rep + 0.3, t)
        glow_k = sstep(t_rep, t_rep + 0.6, t) * (1 + 0.6 * sstep(t_touch, t_touch + 0.5, t))
        draw_two_clouds(gl, t, gap_k, glow_k * wipe)
    final = sstep(t_au + 0.02, t_au + 0.35, t)
    gone = sstep(t_au - 0.40, t_au - 0.10, t)
    compose_glow(cv, gl, 1.0 - 0.65 * final)
    if wipe < 1:
        crisp_lines(cv, partial(CHAIR, eout((t - s0) / 1.6)), (1, 1, 1), 0.95 * (1 - wipe), 6)
        label(cv, ["ET TA CHAISE ?"], (1 - wipe) * sstep(s0 + 0.3, s0 + 0.8, t), y0=530, size=92)
    if wipe > 0 and gone < 1:
        k = wipe * (1 - gone)
        ak = k * sstep(t_parce - 0.2, t_parce + 0.3, t)
        txt(cv, "TES ÉLECTRONS", 150, CY - 150, 42, F_DBLACK, CYAN, ak, -1)
        txt(cv, "CEUX DE LA CHAISE", 150, CY + 135, 42, F_DBLACK, WARM, ak, -1)   # au-dessus des sous-titres sur 2 lignes
        ra = sstep(t_rep - 0.1, t_rep + 0.4, t) * k
        crisp_lines(cv, [[(900, CY - 40), (900, CY - 110)], [(880, CY - 90), (900, CY - 110), (920, CY - 90)],
                         [(900, CY + 40), (900, CY + 110)], [(880, CY + 90), (900, CY + 110), (920, CY + 90)]],
                    (1, 1, 1), ra, 4)
        label(cv, ["RÉPULSION", "ÉLECTRIQUE"], ra * (1 - sstep(t_quant - 0.2, t_quant + 0.1, t)), y0=500, size=84,
              cols=[WHITE, CYAN])
        qa = sstep(t_quant - 0.1, t_quant + 0.3, t) * k
        label(cv, ["+ EXCLUSION", "DE PAULI"], qa * (1 - sstep(t_touch - 0.2, t_touch + 0.1, t)), y0=500, size=84,
              cols=[WHITE, VIOLET])
        ta = sstep(t_touch - 0.1, t_touch + 0.3, t) * k
        label(cv, ["TOUCHER =", "SENTIR CETTE RÉPULSION"], ta, y0=500, size=70, cols=[WHITE, AMBER])
    if final > 0:
        y = 560
        for i, line in enumerate(["TU N'AS JAMAIS", "VRAIMENT TOUCHÉ", "TA CHAISE*"]):
            label(cv, [line], final, y0=y + i * 99, size=88, cols=[WHITE if i < 2 else AMBER])
        txt(cv, "*au sens où tu l'imagines", 540, y + 2 * 99 + 82, 38, F_MEDI, LIGHT, final)
    return cv


# 9. fin : on repart vers l'infiniment grand
WARP_N = 1400
WX = rng.uniform(-1, 1, WARP_N).astype(np.float32)
WY = rng.uniform(-1, 1, WARP_N).astype(np.float32)
WZ = rng.uniform(0.05, 1.0, WARP_N).astype(np.float32)


def sc_outro(t):
    s0, s1 = SC["outro"]
    cv, gl = new_frame(t, stars=0.3)
    u = t - s0
    speed = 0.08 + 0.55 * sstep(0, 3.0, u)
    z = (WZ - (u * speed) % 1.0) % 1.0 + 0.02
    z_prev = z + 0.035 * speed / 0.6
    x, y = CX + WX / z * 140, CY + WY / z * 140
    xp, yp = CX + WX / z_prev * 140, CY + WY / z_prev * 140
    b = np.clip(0.9 - z, 0, 1)
    for i in range(0, WARP_N, 2):
        if 0 <= x[i] < W and 0 <= y[i] < H:
            gline(gl, (xp[i], yp[i]), (x[i], y[i]), np.array([0.8, 0.9, 1.0], np.float32), 1, float(b[i]) * 0.9)
    compose_glow(cv, gl)
    a = sstep(s0, s0 + 0.6, t)
    txt(cv, "PROCHAIN ÉPISODE", 540, 500, 44, F_DBOLD, CYAN, a, 0, 10.0)
    t_bord = cue("outro:bord", 0, s0 + 2.8)
    b2 = sstep(t_bord - 0.4, t_bord + 0.2, t)
    label(cv, ["LE BORD DE", "L'UNIVERS", "OBSERVABLE"], b2, y0=578, size=88, cols=[WHITE, WHITE, AMBER])
    t_src = cue("outro:sources", 0, s0 + 5.4)
    txt(cv, "Sources en description ↓", 540, 1000, 34, F_SEMI, WHITE, sstep(t_src - 0.2, t_src + 0.3, t))
    return cv


SCENES = [("hook", sc_hook), ("descente", sc_descente), ("atome", sc_atome), ("stade", sc_stade), ("masse", sc_masse),
          ("experience", sc_experience), ("etoile", sc_etoile), ("chaise", sc_chaise), ("outro", sc_outro)]
XF = 0.28


def setup(chrono_path):
    global CH, SC, DUR, BOUNDS
    CH = json.load(open(chrono_path, encoding="utf-8"))
    names = [n for n, _ in SCENES]
    b = [0.0]
    for i in range(1, len(names)):
        pe = CH["blocs"][names[i - 1]][1] + T0
        ns = CH["blocs"][names[i]][0] + T0
        b.append((pe + ns) / 2 - 0.05)
    DUR = round((CH["duree"] + T0 + 0.25) * FPS) / FPS
    b.append(DUR + 1)
    BOUNDS = b
    SC = {n: (b[i], b[i + 1]) for i, n in enumerate(names)}


def nframes():
    return int(round(DUR * FPS))


def scene_index(t):
    return max(j for j in range(len(SCENES)) if BOUNDS[j] <= t + 1e-9)


def ui_layer(img, t):
    """Calque d'interface commun (en-tête, règle, sous-titres) ; sert aussi à l'audit des zones sûres."""
    i = scene_index(t)
    name = SCENES[i][0]
    t_wm = cue("hook:physique", 0, 6.8)
    a_head = 1.0
    a_rule = sstep(SC["descente"][0] - 0.2, SC["descente"][0] + 0.5, t)
    if name == "chaise":
        a_rule *= 1 - sstep(cue("chaise:au", 0, 1e9) - 0.3, cue("chaise:au", 0, 1e9), t)
    if name == "stade":
        a_rule *= 0.0
    if name == "stade" or (name == "atome" and t > SC["atome"][1] - XF):
        pass
    header(img, t, a_head, expo_at(t), a_rule)
    a_cap = 1.0
    if name == "chaise":
        a_cap = 1 - sstep(cue("chaise:au", 0, 1e9) - 0.4, cue("chaise:au", 0, 1e9) - 0.1, t)
    if name == "outro":
        a_cap = 0.0
    draw_captions(img, t, a_cap)


def scene_text_alpha(k, t):
    """Les textes d'une scène s'effacent juste avant la coupe et ceux de la suivante n'arrivent qu'après :
    jamais deux titres superposés pendant le fondu enchaîné des images."""
    b = BOUNDS
    a = 1.0
    if k > 0:
        a *= sstep(b[k] + 0.12, b[k] + 0.40, t)
    if k + 1 < len(SCENES):
        a *= 1 - sstep(b[k + 1] - 0.40, b[k + 1] - 0.12, t)
    return a


def render_scene(k, t):
    SCN_A[0] = scene_text_alpha(k, t)
    try:
        return SCENES[k][1](t)
    finally:
        SCN_A[0] = 1.0


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
    cv *= VIG
    cv += GRAIN[fi % len(GRAIN)]
    out = (np.clip(cv, 0, 1) * 255 + 0.5).astype(np.uint8)
    return out


def audit(step=2):
    """Rejoue tout le texte (scènes comprises) et signale ce qui sort des zones sûres ou se superpose."""
    bad = {}
    for fi in range(0, nframes(), step):
        t = fi / FPS
        U.LOG = []
        frame(t, fi)
        for a, b in U.overlaps(U.LOG):
            key = (a[0], f"chevauchement avec {b[0]!r}")
            bad.setdefault(key, round(t, 2))
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
    ts = [0.0, cue("hook:huit") + 0.6, cue("hook:sucre") + 0.4, cue("hook:retirait", 0, cue("hook:sucre") + 1.2) + 0.6,
          cue("hook:physique") + 0.6,
          cue("descente:peau") + 0.3, cue("descente:cellules") + 0.3, cue("descente:adn") + 0.3,
          cue("descente:atomes") + 0.6, cue("atome:vide") + 0.5, cue("atome:cent") + 0.8,
          cue("stade:stade") + 0.6, cue("stade:moustique") + 1.0, cue("stade:nuage") + 0.9,
          cue("masse:999%") + 1.2, cue("experience:prend") + 0.4, cue("experience:retire") + 0.6,
          cue("experience:dense") + 0.6, cue("experience:milliard") + 0.6, cue("experience:lhumanite") + 0.9,
          cue("experience:sucre", 1) + 0.6, cue("etoile:etoile") + 0.6, cue("etoile:kilometres") + 0.6,
          cue("chaise:pourquoi") + 0.4, cue("chaise:repoussent") + 0.5, cue("chaise:quantique") + 0.6,
          cue("chaise:repulsion") + 0.2, cue("chaise:touche", 0, bloc("chaise")[1]) + 0.5, cue("outro:observable") + 0.4,
          DUR - 0.2]
    return [min(x, DUR - 1 / FPS) for x in ts]


def planche(path, ts=None, cols=6, tw=360, th=640):
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


def main():
    mode, chrono = sys.argv[1], sys.argv[2]
    setup(chrono)
    if mode == "images":
        for ts in sys.argv[3:]:
            t = float(ts)
            Image.fromarray(frame(t, int(t * FPS))).save(f"image_{t:06.2f}.png")
    elif mode == "planche":
        print(planche(sys.argv[3]))
    elif mode == "audit":
        bad = audit(int(sys.argv[3]) if len(sys.argv) > 3 else 2)
        print(json.dumps([dict(texte=k[0], probleme=k[1], t=v) for k, v in bad.items()], ensure_ascii=False, indent=1))
    elif mode == "video":
        out, f0, f1 = sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
        p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                              "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "8",
                              "-pix_fmt", "yuv444p", out], stdin=subprocess.PIPE)
        for fi in range(f0, f1):
            p.stdin.write(frame(fi / FPS, fi).tobytes())
            if fi % 150 == 0:
                print(f"{out}: {fi}/{f1}", flush=True)
        p.stdin.close()
        if p.wait() != 0:
            raise SystemExit("échec de l'encodage")
    elif mode == "duree":
        print(DUR, nframes())


if __name__ == "__main__":
    main()
