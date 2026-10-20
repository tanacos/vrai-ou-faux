# -*- coding: utf-8 -*-
"""Primitives communes du rendu des reportages : canevas, lueur, fond étoilé, texte journalisé (audit des zones
sûres TikTok), sous-titres mot à mot, en-tête et règle des puissances de dix.

Conventions : image 1080 x 1920, valeurs float32 entre 0 et 1 ; le calque de lueur « gl » est à demi-résolution et
s'ajoute après flou (compose_glow). Zones : en-tête 270-440, titre 470-620, visuel 640-1170 (centre CX, CY),
sous-titres 1150-1255 ; sous y = 840, aucun texte au-delà de x = 780 (boutons TikTok)."""
import functools
import math
import os
import re
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ICI = os.path.dirname(os.path.abspath(__file__))
MOTEUR = os.path.dirname(ICI)
sys.path.insert(0, MOTEUR)

from vf import ui as U  # noqa: E402
from vf.base import (F_DBLACK, F_DXB, F_DBOLD, F_SEMI, F_MEDI, F_DMED, text_width, SAFE_LEFT,  # noqa: E402,F401
                     SAFE_RIGHT_LOW, SAFE_BOTTOM)

cv2.setNumThreads(1)
W, H, FPS = 1080, 1920, 30
HW, HH = W // 2, H // 2
T0 = 0.30                     # avance de l'image sur la voix : la 1re image (miniature TikTok) reste lisible
CX, CY = 540, 925             # centre de la zone visuelle (objets)
R_VIS = 185                   # rayon « plein cadre » d'un objet dans la zone visuelle (720-1090)
Y_TITRE = 520                 # première ligne de titre
Y_INFO = 690                  # ligne d'information (au-dessus de l'objet : pleine largeur autorisée)

COULEURS = {
    "cyan": (0.38, 0.82, 1.00), "ambre": (1.00, 0.68, 0.26), "blanc": (1.0, 1.0, 1.0), "vert": (0.30, 1.00, 0.55),
    "corail": (1.00, 0.52, 0.42), "violet": (0.80, 0.45, 1.00), "clair": (0.80, 0.85, 0.93), "bleu": (0.30, 0.50, 1.0),
    "or": (1.00, 0.84, 0.40), "rouge": (1.00, 0.32, 0.30), "rose": (1.00, 0.55, 0.80), "gris": (0.62, 0.65, 0.72),
}
CYAN = np.array(COULEURS["cyan"], np.float32)
AMBER = np.array(COULEURS["ambre"], np.float32)
WHITE = np.array(COULEURS["blanc"], np.float32)
GREEN = np.array(COULEURS["vert"], np.float32)
WARM = np.array(COULEURS["corail"], np.float32)
VIOLET = np.array(COULEURS["violet"], np.float32)
LIGHT = np.array(COULEURS["clair"], np.float32)


def couleur(c, defaut="blanc"):
    if c is None:
        c = defaut
    if isinstance(c, str):
        return np.array(COULEURS.get(c, COULEURS[defaut]), np.float32)
    return np.array(c, np.float32)


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


def einout(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def eback(t, s=1.7):
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def lerp(a, b, t):
    return a + (b - a) * t


def fenetre(t, t0, t1, fi=0.25, fo=0.25):
    """Opacité d'un élément visible de t0 à t1 (fondus d'entrée et de sortie)."""
    return sstep(t0 - fi * 0.5, t0 + fi * 0.5, t) * (1 - sstep(t1 - fo, t1, t))


# ---------------------------------------------------------------- texte (journalisé pour l'audit des zones sûres)
SCN_A = [1.0]                 # opacité des textes de la scène en cours (fondus entre scènes)


def txt(img, s, x, yc, size, font=F_DBLACK, col=WHITE, a=1.0, align=0, track=0.0, sh=True):
    """Texte centré verticalement sur yc (hauteur des capitales) ; align 0 centré, -1 gauche, 1 droite."""
    a = a * SCN_A[0]
    if a <= 0.003 or not s:
        return 0.0
    return U.T(img, s, font, int(size), x, yc + 0.36 * size, np.asarray(col, np.float32), a, align, track, sh)


def morceaux(ligne):
    """« UN *MOT* EN AMBRE » -> [("UN ", False), ("MOT", True), (" EN AMBRE", False)]."""
    out = []
    for k, m in enumerate(re.split(r"\*", ligne)):
        if m:
            out.append((m, k % 2 == 1))
    return out


def ligne_mixte(img, ligne, x, yc, size, font, col, col_mis, a, track=0.0):
    """Ligne centrée sur x dont les passages entre astérisques prennent la couleur d'accent."""
    parts = morceaux(ligne)
    larg = [text_width(p, font, size, track) for p, _ in parts]
    tot = sum(larg)
    x0 = x - tot / 2
    if len(parts) == 1:
        return txt(img, parts[0][0], x, yc, size, font, col_mis if parts[0][1] else col, a, 0, track)
    U_LOG = U.LOG
    for (p, mis), w in zip(parts, larg):
        U.LOG = None                         # journalisé d'un seul tenant plus bas
        txt(img, p, x0, yc, size, font, col_mis if mis else col, a, -1, track)
        x0 += w
    U.LOG = U_LOG
    if a * SCN_A[0] > 0.003:
        U._log(ligne.replace("*", ""), x - tot / 2, yc - 0.40 * size, x + tot / 2, yc + 0.58 * size, a * SCN_A[0])
    return tot


def titre(img, lignes, a, y0=Y_TITRE, size=86, col=WHITE, col_mis=AMBER, font=F_DBLACK, lh=1.12, max_w=820):
    """Titre du moment (1 à 2 lignes, zone 470-620) ; la taille s'adapte à la largeur sûre ; *mot* = accent."""
    if a <= 0.003 or not lignes:
        return
    sz = size
    for s in lignes:
        while sz > 44 and text_width(s.replace("*", ""), font, sz) > max_w:
            sz -= 2
    for i, s in enumerate(lignes):
        ligne_mixte(img, s, 540, y0 + i * size * lh, sz, font, col, col_mis, a)


F_CAP = os.path.join(MOTEUR, "assets", "polices", "Anton-Regular.ttf")   # OFL, condensée : sous-titres


@functools.lru_cache(maxsize=1024)
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
    xi = (np.asarray(xs) * 0.5).astype(np.int32)
    yi = (np.asarray(ys) * 0.5).astype(np.int32)
    m = (xi >= 0) & (xi < HW) & (yi >= 0) & (yi < HH)
    buf = np.zeros((HH, HW), np.float32)
    v = val[m] if isinstance(val, np.ndarray) else np.full(m.sum(), val, np.float32)
    np.add.at(buf, (yi[m], xi[m]), v)
    gl += buf[..., None] * np.asarray(color, np.float32)


def add_pts_col(gl, xs, ys, val, cols):
    """Points de couleurs individuelles (cols : N x 3)."""
    xi = (np.asarray(xs) * 0.5).astype(np.int32)
    yi = (np.asarray(ys) * 0.5).astype(np.int32)
    m = (xi >= 0) & (xi < HW) & (yi >= 0) & (yi < HH)
    v = (val[m] if isinstance(val, np.ndarray) else np.full(m.sum(), val, np.float32))[:, None] * cols[m]
    np.add.at(gl, (yi[m], xi[m]), v.astype(np.float32))


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


def cercle_pointille(cv, cx, cy, r, color, alpha=1.0, th=3, n=72, plein=0.55, phase=0.0):
    segs = []
    for k in range(n):
        a0 = 2 * math.pi * (k + phase) / n
        a1 = a0 + 2 * math.pi * plein / n
        aa = np.linspace(a0, a1, 6)
        segs.append(np.stack([cx + r * np.cos(aa), cy + r * np.sin(aa)], 1))
    crisp_lines(cv, segs, color, alpha, th)


def rrect(x0, y0, x1, y1, r, n=8):
    pts = []
    for cx_, cy_, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx_ + r * math.cos(a), cy_ + r * math.sin(a)))
    return np.array(pts)


def coller(cv, col, masque, x0, y0):
    """Colle une image (h, w, 3) avec son masque (h, w) dans le canevas en (x0, y0), découpée aux bords."""
    hgt, wid = masque.shape[:2]
    x0, y0 = int(x0), int(y0)
    ya, yb, xa, xb = max(y0, 0), min(y0 + hgt, H), max(x0, 0), min(x0 + wid, W)
    if ya >= yb or xa >= xb:
        return
    sm = masque[ya - y0:yb - y0, xa - x0:xb - x0][..., None]
    cv[ya:yb, xa:xb] = cv[ya:yb, xa:xb] * (1 - sm) + col[ya - y0:yb - y0, xa - x0:xb - x0] * sm


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
    _cx, _cy = rng.uniform(0, HW + 300), rng.uniform(0, HH + 300)
    _r = rng.uniform(40, 150)
    _col = [CYAN, VIOLET, np.array([0.2, 0.3, 0.9], np.float32)][rng.integers(0, 3)]
    cv2.circle(_neb, (int(_cx), int(_cy)), int(_r), tuple(float(v) * rng.uniform(0.010, 0.028) for v in _col), -1)
NEB = cv2.GaussianBlur(_neb, (0, 0), 60)
STAR_N = 650
STAR_X = rng.uniform(0, W, STAR_N).astype(np.float32)
STAR_Y = rng.uniform(0, H, STAR_N).astype(np.float32)
STAR_B = (rng.uniform(0.15, 1.0, STAR_N) ** 3 * 1.6).astype(np.float32)
STAR_P = rng.uniform(0, 2 * np.pi, STAR_N).astype(np.float32)


def new_frame(t, stars=1.0, neb=1.0, flux=0.0, flux_sens=1.0):
    """Canevas et calque de lueur ; flux > 0 étire les étoiles depuis le centre (sensation de voyage)."""
    cv = BG.copy()
    gl = np.zeros((HH, HW, 3), np.float32)
    if neb > 0:
        ox, oy = int(150 + 120 * math.sin(t * 0.021)), int(150 + 110 * math.cos(t * 0.017))
        gl += NEB[oy:oy + HH, ox:ox + HW] * neb
    if stars > 0:
        tw = 0.65 + 0.35 * np.sin(STAR_P + t * 1.7)
        if flux > 0.01:
            dx, dy = STAR_X - CX, STAR_Y - CY
            k = 1 + 0.06 * flux * flux_sens
            for j in range(4):
                f = 1 + (k - 1) * j / 3
                add_pts(gl, CX + dx * f, CY + dy * f, STAR_B * tw * stars * (0.55 if j else 1.0),
                        np.array([0.8, 0.88, 1.0], np.float32))
        else:
            add_pts(gl, STAR_X, STAR_Y, STAR_B * tw * stars, np.array([0.8, 0.88, 1.0], np.float32))
    return cv, gl


# voile sombre derrière l'en-tête, les titres et les sous-titres : le texte reste lisible sur les fonds chargés
_sy = np.arange(H, dtype=np.float32)
SCRIM = (1 - 0.50 * np.clip((_sy - 120) / 140, 0, 1) * np.clip((700 - _sy) / 110, 0, 1)
         - 0.38 * np.clip((_sy - 1120) / 60, 0, 1) * np.clip((1310 - _sy) / 60, 0, 1))[:, None, None].astype(np.float32)


def compose_glow(cv, gl, k=1.0):
    b1 = cv2.GaussianBlur(gl, (0, 0), 1.6)
    b2 = cv2.GaussianBlur(gl, (0, 0), 7.0)
    b3 = cv2.GaussianBlur(gl, (0, 0), 22.0)
    g = gl * 0.55 + b1 * 1.1 + b2 * 0.9 + b3 * 0.7
    cv += cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR) * k
    cv *= SCRIM


# ---------------------------------------------------------------- en-tête : marque + règle des échelles
EXP_MIN, EXP_MAX = -15, 27          # du noyau (1 fm) au-delà du bord de l'univers observable (4,4 x 10^26 m)
SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
RX0, RX1, RY = 170.0, 910.0, 410.0


def exp_str(e):
    return "10" + str(int(round(e))).translate(SUP) + " m"


def entete(img, t, serie, numero, a_head, expo, a_rule):
    """« INFINIMENT · ÉP. N » puis la règle des puissances de dix : où en est-on entre l'infiniment petit et
    l'infiniment grand ?"""
    if a_head > 0.003:
        lab2 = f"ÉP. {numero}"
        w1 = text_width(serie, F_DBOLD, 34, 9.0)
        w2 = text_width(lab2, F_DBOLD, 30, 3.0)
        x0 = 540 - (w1 + 26 + w2) / 2
        txt(img, serie, x0, 296, 34, F_DBOLD, WHITE, 0.95 * a_head, -1, 9.0)
        txt(img, lab2, x0 + w1 + 26, 296, 30, F_DBOLD, AMBER, 0.95 * a_head, -1, 3.0)
    if a_rule <= 0.003 or expo is None:
        return
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


# ---------------------------------------------------------------- sous-titres mot à mot
CAP_SIZE, CAP_Y, CAP_W = 80, 1192, 2 * (SAFE_RIGHT_LOW - 8 - 540)     # centrés, bord droit <= 772 (boutons TikTok)
CAP_BAS = 1252                # bas de la zone sûre (1260) moins une marge
POP = 1.07                    # grossissement d'entrée d'un sous-titre (0,12 s)
MOTS_OUTILS = {"LE", "LA", "LES", "L'", "DE", "DU", "DES", "D'", "UN", "UNE", "ET", "À", "AU", "AUX", "QUE", "QUI",
               "CE", "CET", "CETTE", "CES", "TA", "TON", "TES", "SON", "SA", "SES", "DANS", "EN", "SUR", "POUR", "PAR",
               "NE", "SE", "OR", "SI", "ON", "TU", "IL", "ELLE", "PLUS", "C'EST"}


class SousTitres:
    def __init__(self, liste):
        self.liste = liste
        self._mise_en_page = {}

    def a(self, t):
        for c in self.liste:
            if c["debut"] + T0 <= t < c["fin"] + T0:
                return c
        return None

    @staticmethod
    def _largeurs(words, size):
        return [_cap_patch(w["t"], size, (255, 255, 255)).shape[1] for w in words]

    def mise_en_page(self, c):
        """Taille et coupure d'un sous-titre, fixées pour toute sa durée. Une ligne de 80 à 60 px ; sinon deux lignes
        équilibrées (68 px au plus), jamais de mot seul orphelin si possible."""
        key = (c["debut"], len(c["mots"]))
        if key in self._mise_en_page:
            return self._mise_en_page[key]
        words, n = c["mots"], len(c["mots"])
        res = None
        for size in (80, 76, 72, 68, 64, 60):
            ws = self._largeurs(words, size)
            larg = sum(ws) + int(size * 0.26) * (n - 1)
            if larg <= CAP_W:
                res = (size, [n], larg)
                break
        if res is None:
            for size in (68, 64, 60, 56, 52):
                ws = self._largeurs(words, size)
                sp = int(size * 0.26)
                best = None
                for k in range(1, n):
                    w1, w2 = sum(ws[:k]) + sp * (k - 1), sum(ws[k:]) + sp * (n - k - 1)
                    if max(w1, w2) > CAP_W:
                        continue
                    orphelin = n >= 3 and (k == 1 or k == n - 1)
                    score = (orphelin, words[k - 1]["t"].upper() in MOTS_OUTILS, max(w1, w2))
                    if best is None or score < best[0]:
                        best = (score, k)
                if best is not None:
                    res = (size, [best[1], n - best[1]], best[0][2])
                    break
        if res is None:
            res = (52, [n], CAP_W)
        self._mise_en_page[key] = res
        return res

    def dessiner(self, img, t, a=1.0):
        c = self.a(t)
        if not c or a <= 0.003:
            return
        pop = 1 + (POP - 1) * (1 - eout((t - c["debut"] - T0) / 0.12))
        size, coupe, larg = self.mise_en_page(c)
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


def format_nombre(v, dec=0):
    """12345.6 -> « 12 345,6 » (espace fine insécable des milliers, virgule décimale)."""
    s = f"{abs(v):,.{dec}f}".replace(",", "\u202f").replace(".", ",")
    return ("-" if v < 0 else "") + s
