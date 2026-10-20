# -*- coding: utf-8 -*-
"""Bibliothèque d'objets des reportages, dessinés de façon procédurale (aucune image protégée).

    dessiner(cv, gl, spec, cx, cy, R, a, t)

spec = {"type": …, "couleur": …, "taille": 1.0, …} ; R = rayon en pixels, a = opacité, t = temps (s).
Types : soleil, etoile, terre, lune, planete, cmb, galaxie, univers, trou_noir, atome, molecule, cellule, virus,
goutte, verre, sucre, fourmi, lumiere, point, icone (pictogramme de vf.icons, « nom »).

Une image est une affirmation : quand deux objets sont comparés, la scène les dessine à l'échelle (voir scenes.py) ;
les couleurs suivent la réalité quand elle est connue (Proxima du Centaure est une naine rouge, etc.)."""
import math

import cv2
import numpy as np

from .base import (W, H, HW, HH, CYAN, AMBER, WHITE, VIOLET, LIGHT, WARM, GREEN, couleur, clamp, add_pts,
                   add_pts_col, gline, gcircle, crisp_lines, crisp_fill, crisp_dot, circle_poly, coller, txt, F_DBOLD)

TYPES = ("soleil", "etoile", "terre", "lune", "planete", "cmb", "galaxie", "univers", "trou_noir", "atome",
         "molecule", "cellule", "virus", "goutte", "verre", "sucre", "fourmi", "lumiere", "point", "icone")
_r = np.random.default_rng(1234)


# ---------------------------------------------------------------- textures équirectangulaires (512 x 256)
def _bruit(seed, echelles=((28, 1.0), (10, 0.5), (4, 0.22)), w=512, h=256):
    r = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    for sg, amp in echelles:
        z = r.standard_normal((h, w)).astype(np.float32)
        z = cv2.GaussianBlur(np.pad(z, ((0, 0), (64, 64)), mode="wrap"), (0, 0), sg)[:, 64:-64]
        acc += amp * z / (z.std() + 1e-6)
    return acc / (acc.std() + 1e-6)


_LAT = np.linspace(90, -90, 256, dtype=np.float32)[:, None]
_TERRE_H = _bruit(11) - 0.9 * (np.abs(_LAT) > 72)
LAND = _TERRE_H > np.percentile(_TERRE_H, 70)
_SEC = _bruit(12, ((16, 1.0), (5, 0.4)))
NUAGES = np.clip((_bruit(13, ((3, 1.0), (1.2, 0.6))) - 0.9) * 0.55, 0, 0.75)
GLACE = np.abs(_LAT) > 70
_cr = np.zeros((256, 512), np.float32)
for _ in range(220):
    u, v, rr = _r.uniform(0, 512), _r.uniform(20, 236), _r.uniform(2, 14)
    cv2.circle(_cr, (int(u), int(v)), int(rr), -1.0, -1, cv2.LINE_AA)
    cv2.circle(_cr, (int(u - rr * 0.25), int(v - rr * 0.25)), int(rr), 0.6, 1, cv2.LINE_AA)
CRATERES = cv2.GaussianBlur(_cr, (0, 0), 1.2) * 0.12 + _bruit(14, ((20, 1.0), (6, 0.4))) * 0.07
CMB_T = _bruit(15, ((3.0, 1.0), (7.0, 0.6), (1.5, 0.35)))
BANDES = _bruit(16, ((2.0, 0.4), (8.0, 0.3)))
GRANULES = _bruit(17, ((1.4, 1.0), (4.0, 0.5)))

_SPR = {}


def halo(gl, cx, cy, r, color, i=1.0):
    """Halo gaussien de rayon r (pixels pleine résolution, ~2 sigma), ajouté au calque de lueur."""
    rh = max(int(r * 0.5), 1)
    if rh not in _SPR:
        if len(_SPR) > 200:
            _SPR.clear()
        z = np.linspace(-1, 1, 2 * rh + 1, dtype=np.float32)
        xx, yy = np.meshgrid(z, z)
        _SPR[rh] = np.exp(-(xx ** 2 + yy ** 2) * 4.0)
    g = _SPR[rh]
    x0, y0 = int(cx * 0.5) - rh, int(cy * 0.5) - rh
    hh, ww = g.shape
    ya, yb, xa, xb = max(y0, 0), min(y0 + hh, HH), max(x0, 0), min(x0 + ww, HW)
    if ya < yb and xa < xb:
        gl[ya:yb, xa:xb] += g[ya - y0:yb - y0, xa - x0:xb - x0, None] * (np.asarray(color, np.float32) * i)


L_DIR = np.array([-0.55, -0.45, 0.70], np.float32)
L_DIR /= np.linalg.norm(L_DIR)

_GR = {}


def _grille(R):
    R = max(int(round(R)), 2)
    if R not in _GR:
        if len(_GR) > 64:
            _GR.clear()
        z = np.arange(-R - 2, R + 3, dtype=np.float32)
        dx, dy = np.meshgrid(z, z)
        d = np.sqrt(dx ** 2 + dy ** 2)
        inside = np.clip(R - d + 0.5, 0, 1)
        rr = np.clip((dx ** 2 + dy ** 2) / R ** 2, 0, 1)
        nz = np.sqrt(1 - rr)
        _GR[R] = (dx / R, dy / R, nz, inside, R)
    return _GR[R]


def _lonlat(nx, ny, nz, rot, incl=0.35):
    """Longitude et latitude du point de normale (nx, ny, nz), axe incliné de incl radians, rotation rot."""
    ci, si = math.cos(incl), math.sin(incl)
    y2 = ny * ci - nz * si
    z2 = ny * si + nz * ci
    x = nx * math.cos(rot) - z2 * math.sin(rot)
    z = nx * math.sin(rot) + z2 * math.cos(rot)
    lon = np.arctan2(x, z)
    lat = np.arcsin(np.clip(-y2, -1, 1))
    return lon, lat


def _tex(T, lon, lat):
    u = ((lon / (2 * np.pi) + 0.5) * (T.shape[1] - 1)).astype(np.int32) % T.shape[1]
    v = ((0.5 - lat / np.pi) * (T.shape[0] - 1)).astype(np.int32).clip(0, T.shape[0] - 1)
    return T[v, u]


def _sphere(cv, cx, cy, R, a, couleur_fn, emissif=False, ombre=0.18):
    """Sphère éclairée : couleur_fn(nx, ny, nz) -> (h, w, 3) ; collée avec un bord lissé."""
    if a <= 0.01 or R < 1.5:
        return
    nx, ny, nz, inside, Ri = _grille(R)
    col = couleur_fn(nx, ny, nz)
    if not emissif:
        dif = np.clip(nx * L_DIR[0] + ny * L_DIR[1] + nz * L_DIR[2], 0, 1)
        col = col * (ombre + (1 - ombre) * 1.15 * dif[..., None] ** 1.1)
    coller(cv, col.astype(np.float32), inside * a, cx - Ri - 2, cy - Ri - 2)


# ---------------------------------------------------------------- astres
def soleil(cv, gl, s, cx, cy, R, a, t):
    def fn(nx, ny, nz):
        limbe = 0.38 + 0.62 * nz ** 0.6
        lon, lat = _lonlat(nx, ny, nz, t * 0.05, 0.1)
        g = _tex(GRANULES, lon + t * 0.02, lat)
        base = np.stack([np.full_like(nz, 0.98), 0.50 + 0.30 * nz, 0.10 + 0.32 * nz ** 2], -1)
        return base * (limbe * (1 + 0.10 * g))[..., None]
    orange = np.array([1.0, 0.55, 0.18], np.float32)
    halo(gl, cx, cy, R * 3.2, orange, 0.10 * a)
    halo(gl, cx, cy, R * 2.0, orange, 0.16 * a)
    _sphere(cv, cx, cy, R, a, fn, emissif=True)
    gcircle(gl, (cx, cy), R * 1.01, np.array([1.0, 0.75, 0.4], np.float32) * 0.5 * a, 3)


def etoile(cv, gl, s, cx, cy, R, a, t):
    c = couleur(s.get("couleur"), "clair")
    tw = 0.9 + 0.1 * math.sin(t * 3.1 + cx)
    halo(gl, cx, cy, R * 1.6, c, 0.10 * a * tw)
    halo(gl, cx, cy, R * 0.7, c, 0.35 * a * tw)
    halo(gl, cx, cy, R * 0.25, np.minimum(c * 0.5 + 0.6, 1.0), 1.3 * a * tw)
    ang = 0.12 * math.sin(t * 0.4)
    for k in range(4):
        th = ang + k * math.pi / 2
        for f, i in ((0.95, 0.10), (0.6, 0.18), (0.35, 0.30)):
            p1 = (cx + math.cos(th) * R * f, cy + math.sin(th) * R * f)
            gline(gl, (cx, cy), p1, c, 2, i * a * tw)
    crisp_dot(cv, cx, cy, max(R * 0.06, 2.5), np.minimum(c * 0.4 + 0.65, 1.0), a)


def terre(cv, gl, s, cx, cy, R, a, t):
    rot = t * 0.18 + s.get("phase", 0.0)

    def fn(nx, ny, nz):
        lon, lat = _lonlat(nx, ny, nz, rot)
        land = _tex(LAND, lon, lat)
        sec = _tex(_SEC, lon, lat)
        ice = _tex(GLACE, lon, lat)
        cl = _tex(NUAGES, lon + t * 0.01, lat)
        ocean = np.array([0.03, 0.13, 0.36], np.float32)
        vert = np.array([0.10, 0.26, 0.09], np.float32)
        desert = np.array([0.42, 0.34, 0.19], np.float32)
        col = np.where(land[..., None], np.where((sec > 0.6)[..., None], desert, vert), ocean)
        col = np.where(ice[..., None], np.array([0.85, 0.88, 0.92], np.float32), col)
        col = col * (1 - cl[..., None]) + np.array([0.92, 0.94, 0.97], np.float32) * cl[..., None]
        return col
    _sphere(cv, cx, cy, R, a, fn, ombre=0.06)
    gcircle(gl, (cx, cy), R + 3, CYAN * 0.55 * a, 3)
    gcircle(gl, (cx, cy), R + 12, CYAN * 0.14 * a, 7)


def lune(cv, gl, s, cx, cy, R, a, t):
    def fn(nx, ny, nz):
        lon, lat = _lonlat(nx, ny, nz, t * 0.05)
        v = 0.52 + _tex(CRATERES, lon, lat)
        return np.stack([v, v, v * 1.03], -1)
    _sphere(cv, cx, cy, R, a, fn, ombre=0.04)
    gcircle(gl, (cx, cy), R + 4, LIGHT * 0.12 * a, 4)


def planete(cv, gl, s, cx, cy, R, a, t):
    c = couleur(s.get("couleur"), "or")
    anneau = s.get("anneau", False)
    if anneau:
        _anneau(cv, gl, cx, cy, R, a, c, devant=False)

    def fn(nx, ny, nz):
        lon, lat = _lonlat(nx, ny, nz, t * 0.08, 0.2)
        b = np.sin(lat * 9.0 + _tex(BANDES, lon, lat) * 0.8)
        return c[None, None, :] * (0.78 + 0.18 * b)[..., None]
    _sphere(cv, cx, cy, R, a, fn)
    if anneau:
        _anneau(cv, gl, cx, cy, R, a, c, devant=True)
    gcircle(gl, (cx, cy), R + 4, c * 0.15 * a, 5)


def _anneau(cv, gl, cx, cy, R, a, c, devant):
    th = np.linspace(0, np.pi, 90) if devant else np.linspace(np.pi, 2 * np.pi, 90)
    for k, (f, al) in enumerate(((1.30, 0.45), (1.45, 0.75), (1.62, 0.45), (1.75, 0.25))):
        pts = np.stack([cx + R * f * np.cos(th), cy + R * f * 0.30 * np.sin(th)], 1)
        crisp_lines(cv, [pts], np.minimum(c * 0.9 + 0.15, 1), al * a, 6 if k == 1 else 4)


def cmb(cv, gl, s, cx, cy, R, a, t):
    """Fond diffus cosmologique : la plus vieille lumière, carte marbrée (fluctuations de température, illustratives)."""
    def fn(nx, ny, nz):
        lon, lat = _lonlat(nx, ny, nz, t * 0.06, 0.3)
        v = np.clip(_tex(CMB_T, lon, lat) * 0.42, -1, 1)
        froid = np.array([0.10, 0.28, 0.85], np.float32)
        tiede = np.array([0.95, 0.92, 0.80], np.float32)
        chaud = np.array([1.00, 0.45, 0.10], np.float32)
        w = (v[..., None] + 1) / 2
        col = np.where(w < 0.5, froid + (tiede - froid) * (w / 0.5), tiede + (chaud - tiede) * ((w - 0.5) / 0.5))
        return col * (0.55 + 0.45 * nz[..., None])
    _sphere(cv, cx, cy, R, a, fn, emissif=True)
    gcircle(gl, (cx, cy), R + 4, np.array([1.0, 0.6, 0.3], np.float32) * 0.45 * a, 4)
    gcircle(gl, (cx, cy), R + 16, np.array([1.0, 0.6, 0.3], np.float32) * 0.10 * a, 10)


# galaxie spirale : particules (bras logarithmiques, bulbe), rotation lente
_GN = 26000
_gr = np.random.default_rng(21)
_g_bras = _gr.integers(0, 2, _GN)
_g_rad = (_gr.gamma(2.3, 0.26, _GN)).clip(0, 1.15).astype(np.float32)
_g_ang = (_g_bras * np.pi + np.log(_g_rad + 0.05) * 2.6 + _gr.normal(0, 0.32, _GN)).astype(np.float32)
_bulbe = _gr.uniform(0, 1, _GN) < 0.22
_g_rad[_bulbe] = np.abs(_gr.normal(0, 0.12, _bulbe.sum())).astype(np.float32)
_g_ang[_bulbe] = _gr.uniform(0, 2 * np.pi, _bulbe.sum()).astype(np.float32)
_g_z = _gr.normal(0, 0.025, _GN).astype(np.float32)
_g_col = np.where(_bulbe[:, None], np.array([1.0, 0.82, 0.55], np.float32),
                  np.where((_gr.uniform(0, 1, _GN) < 0.06)[:, None], np.array([1.0, 0.45, 0.65], np.float32),
                           np.array([0.62, 0.76, 1.0], np.float32))).astype(np.float32)
_g_b = np.where(_bulbe, 0.12, 0.13).astype(np.float32) * _gr.uniform(0.5, 1.4, _GN).astype(np.float32)


def galaxie(cv, gl, s, cx, cy, R, a, t):
    incl = float(s.get("inclinaison", 0.25))           # 0 : vue de face ; 0,8 : très inclinée (Andromède ≈ 0,75)
    rot = t * 0.05 + s.get("phase", 0.0)
    ang = _g_ang + rot
    x = _g_rad * np.cos(ang)
    y = _g_rad * np.sin(ang)
    pa = s.get("angle", -0.5)                           # orientation du grand axe à l'écran
    ci = math.cos(incl * math.pi / 2)
    yy = y * ci + _g_z * math.sin(incl * math.pi / 2)
    X = cx + (x * math.cos(pa) - yy * math.sin(pa)) * R
    Y = cy + (x * math.sin(pa) + yy * math.cos(pa)) * R
    ec = float(s.get("eclat", 1.0))
    surf = min(1.0, max((R / 150.0) ** 2, 0.02))         # petite galaxie : même éclat de surface, pas un point saturé
    add_pts_col(gl, X, Y, _g_b * a * ec * surf, _g_col)
    for f, i in ((0.30, 0.10 * ec), (0.14, 0.25 * ec), (0.06, 0.6 * ec)):
        cv2.ellipse(gl, (int(cx * 0.5), int(cy * 0.5)), (max(int(R * f * 0.5), 1), max(int(R * f * 0.5 * max(ci, 0.3)), 1)),
                    math.degrees(pa), 0, 360, tuple(float(v) * i * a for v in (1.0, 0.85, 0.6)), -1, cv2.LINE_AA)


# toile cosmique : filaments entre des nœuds, dans une sphère
def _toile(n_noeuds=70, seed=31):
    r = np.random.default_rng(seed)
    nodes = []
    while len(nodes) < n_noeuds:
        p = r.uniform(-1, 1, 3)
        if np.linalg.norm(p) < 0.95:
            nodes.append(p)
    nodes = np.array(nodes, np.float32)
    pts, cols = [], []
    for i in range(n_noeuds):
        d = np.linalg.norm(nodes - nodes[i], axis=1)
        for j in np.argsort(d)[1:4]:
            if j > i and d[j] < 0.7:
                k = int(140 * d[j])
                u = r.uniform(0, 1, k)[:, None]
                p = nodes[i] * (1 - u) + nodes[j] * u + r.normal(0, 0.018, (k, 3))
                pts.append(p)
                cols.append(np.repeat([[0.70, 0.62, 1.0]], k, 0))
        k = 60
        pts.append(nodes[i] + r.normal(0, 0.035, (k, 3)))
        cols.append(np.repeat([[1.0, 0.80, 0.55]], k, 0))
    pts.append(r.uniform(-1, 1, (2500, 3)) * 0.95)
    cols.append(np.repeat([[0.45, 0.60, 1.0]], 2500, 0))
    P = np.concatenate(pts).astype(np.float32)
    C = np.concatenate(cols).astype(np.float32)
    m = np.linalg.norm(P, axis=1) < 1.0
    return P[m], C[m]


TOILE_P, TOILE_C = _toile()


def univers(cv, gl, s, cx, cy, R, a, t, bord=True):
    rot = t * 0.06
    x = TOILE_P[:, 0] * math.cos(rot) + TOILE_P[:, 2] * math.sin(rot)
    z = -TOILE_P[:, 0] * math.sin(rot) + TOILE_P[:, 2] * math.cos(rot)
    y = TOILE_P[:, 1]
    b = (0.09 + 0.08 * (z + 1)) * a * min(1.0, max((R / 150.0) ** 2, 0.05))
    add_pts_col(gl, cx + x * R, cy + y * R, b.astype(np.float32), TOILE_C)
    if bord and s.get("bord", True):
        gcircle(gl, (cx, cy), R, np.array([0.55, 0.75, 1.0], np.float32) * 0.55 * a, 3)
        gcircle(gl, (cx, cy), R + 10, np.array([0.55, 0.75, 1.0], np.float32) * 0.12 * a, 8)


def trou_noir(cv, gl, s, cx, cy, R, a, t):
    """Trou noir : ombre noire, anneau de photons, disque d'accrétion vu presque par la tranche et sa partie arrière
    déviée au-dessus de l'ombre (illustration)."""
    disque = np.array([1.0, 0.62, 0.25], np.float32)
    def ell(f, ry, i, th, a0, a1):
        cv2.ellipse(gl, (int(cx * 0.5), int(cy * 0.5)), (int(R * f * 0.5), max(int(R * f * 0.5 * ry), 1)), 0, a0, a1,
                    tuple(float(v) * i * a for v in disque), th, cv2.LINE_AA)
    for f, i, th in ((1.55, 0.25, 9), (1.25, 0.55, 6), (0.95, 0.9, 4)):
        ell(f, 0.22, i, th, 180, 360)                    # moitié arrière du disque
        ell(f * 0.62, 0.95, i * 0.6, th - 1, 180, 360)   # lumière déviée par-dessus l'ombre
    halo(gl, cx, cy, R * 1.6, disque, 0.10 * a)
    gcircle(gl, (cx, cy), R * 0.5, np.array([1.0, 0.85, 0.6], np.float32) * 0.9 * a, 3)
    crisp_dot(cv, cx, cy, R * 0.46, (0.0, 0.0, 0.0), a)
    for f, i, th in ((1.55, 0.25, 9), (1.25, 0.55, 6), (0.95, 0.9, 4)):
        ell(f, 0.22, i, th, 0, 180)                      # moitié avant, devant l'ombre


# ---------------------------------------------------------------- matière
_CN = 90000
_cr2 = np.random.default_rng(41)
_c_r = _cr2.gamma(3.0, 0.5, _CN).astype(np.float32)
_c_v = _cr2.standard_normal((_CN, 3)).astype(np.float32)
_c_v /= np.linalg.norm(_c_v, axis=1, keepdims=True)
CLOUD = _c_v * _c_r[:, None]


def atome(cv, gl, s, cx, cy, R, a, t):
    """Nuage d'électrons (densité de probabilité) et noyau minuscule (pas à l'échelle : il serait invisible)."""
    idx = np.random.default_rng(int(t * 30) * 7).integers(0, _CN, 16000)
    p = CLOUD[idx]
    an = t * 0.25
    x = p[:, 0] * math.cos(an) + p[:, 2] * math.sin(an)
    add_pts(gl, cx + x * R * 0.55, cy + p[:, 1] * R * 0.55, 0.12 * a, couleur(s.get("couleur"), "cyan"))
    gcircle(gl, (cx, cy), R * 0.5, CYAN * 0.02 * a, -1)
    gcircle(gl, (cx, cy), 6, AMBER * 2.0 * a, -1)
    crisp_dot(cv, cx, cy, 3.2, (1.0, 0.85, 0.6), a)


def _boule(cv, gl, cx, cy, R, a, c):
    def fn(nx, ny, nz):
        spec = np.clip(nx * L_DIR[0] + ny * L_DIR[1] + nz * L_DIR[2], 0, 1) ** 24
        return c[None, None, :] * 0.95 + spec[..., None] * 0.6
    _sphere(cv, cx, cy, R, a, fn, ombre=0.22)
    gcircle(gl, (cx, cy), R * 1.05, c * 0.18 * a, 4)


def molecule(cv, gl, s, cx, cy, R, a, t):
    """Molécule d'eau H₂O : un oxygène (rouge, convention des modèles moléculaires) et deux hydrogènes (blancs),
    angle d'environ 104,5° ; tailles relatives illustratives."""
    rot = 0.25 * math.sin(t * 0.5) + s.get("angle", 0.0)
    ro, rh = R * 0.52, R * 0.34
    d = R * 0.62
    O = (cx, cy - R * 0.12)
    hs = []
    for sgn in (-1, 1):
        th = math.pi / 2 + sgn * math.radians(104.5 / 2) + rot
        hs.append((O[0] + d * math.cos(th), O[1] + d * math.sin(th)))
    for h in hs:
        crisp_lines(cv, [[O, h]], LIGHT, 0.5 * a, 6)
    _boule(cv, gl, O[0], O[1], ro, a, np.array([0.92, 0.22, 0.22], np.float32))
    for h in hs:
        _boule(cv, gl, h[0], h[1], rh, a, np.array([0.92, 0.94, 0.98], np.float32))


def cellule(cv, gl, s, cx, cy, R, a, t):
    c = couleur(s.get("couleur"), "vert")
    wob = [R * (1 + 0.03 * math.sin(k * 0.9 + t * 1.3)) for k in range(72)]
    pts = np.array([(cx + wob[k] * math.cos(2 * math.pi * k / 72), cy + wob[k] * math.sin(2 * math.pi * k / 72))
                    for k in range(72)])
    crisp_fill(cv, [pts], c * 0.10, a)
    crisp_lines(cv, [pts], c, 0.85 * a, 4, True)
    gcircle(gl, (cx, cy), R, c * 0.4 * a, 4)
    crisp_fill(cv, [circle_poly(cx + R * 0.15, cy - R * 0.1, R * 0.33)], VIOLET * 0.35, a)
    crisp_lines(cv, [circle_poly(cx + R * 0.15, cy - R * 0.1, R * 0.33)], VIOLET, 0.9 * a, 3, True)
    rr = np.random.default_rng(5)
    for _ in range(9):
        ang, dist = rr.uniform(0, 2 * np.pi), rr.uniform(0.45, 0.8)
        ex, ey = cx + R * dist * math.cos(ang), cy + R * dist * math.sin(ang)
        cv2.ellipse(gl, (int(ex * 0.5), int(ey * 0.5)), (max(int(R * 0.09), 1), max(int(R * 0.04), 1)),
                    math.degrees(ang) + t * 10, 0, 360, tuple(float(v) * 0.5 * a for v in c), 1, cv2.LINE_AA)


def virus(cv, gl, s, cx, cy, R, a, t):
    c = couleur(s.get("couleur"), "rouge")
    rot = t * 0.2
    for k in range(20):
        th = rot + 2 * math.pi * k / 20
        p0 = (cx + R * 0.95 * math.cos(th), cy + R * 0.95 * math.sin(th))
        p1 = (cx + R * 1.28 * math.cos(th), cy + R * 1.28 * math.sin(th))
        crisp_lines(cv, [[p0, p1]], c * 0.9, 0.9 * a, 5)
        crisp_dot(cv, p1[0], p1[1], R * 0.07, c, a)
    _boule(cv, gl, cx, cy, R, a, c * 0.85)


def goutte(cv, gl, s, cx, cy, R, a, t):
    th = np.linspace(0, 2 * np.pi, 120)
    x = np.sin(th) * (1 - np.cos(th)) * 0.5
    y = -np.cos(th)
    pts = np.stack([cx + x * R * 1.6, cy + 0.25 * R - y * R * 1.25 + R * 0.0], 1)
    pts[:, 1] = cy + R * 0.35 - (np.cos(th) * R * 1.05)
    pts[:, 0] = cx + np.sin(th) * R * 0.85 * np.clip((1 - np.cos(th)) / 1.2, 0, 1) ** 0.6
    col = np.array([0.25, 0.55, 0.98], np.float32)
    crisp_fill(cv, [pts], col * 0.55, 0.9 * a)
    crisp_lines(cv, [pts], np.array([0.6, 0.85, 1.0], np.float32), 0.8 * a, 3, True)
    crisp_fill(cv, [circle_poly(cx - R * 0.3, cy + R * 0.55, R * 0.16)], (0.9, 0.97, 1.0), 0.65 * a)
    gcircle(gl, (cx, cy + R * 0.4), R * 1.1, col * 0.10 * a, -1)


def verre(cv, gl, s, cx, cy, R, a, t):
    """Verre d'eau vu de côté (contenance illustrative)."""
    hh, wt, wb = R * 1.15, R * 0.78, R * 0.60
    top, bot = cy - hh, cy + hh
    niveau = top + (bot - top) * (1 - float(s.get("remplissage", 0.75)))
    wl = wb + (wt - wb) * (bot - niveau) / (bot - top)
    eau = np.array([[cx - wl, niveau], [cx + wl, niveau], [cx + wb, bot], [cx - wb, bot]])
    crisp_fill(cv, [eau], np.array([0.22, 0.48, 0.92], np.float32) * 0.55, 0.85 * a)
    th = np.linspace(0, 2 * np.pi, 80)
    surf = np.stack([cx + wl * np.cos(th), niveau + wl * 0.12 * np.sin(th)], 1)
    crisp_fill(cv, [surf], np.array([0.45, 0.72, 1.0], np.float32) * 0.7, 0.8 * a)
    bord = [[(cx - wt, top), (cx - wb, bot)], [(cx + wt, top), (cx + wb, bot)]]
    crisp_lines(cv, bord, (0.86, 0.92, 1.0), 0.85 * a, 4)
    crisp_lines(cv, [np.stack([cx + wt * np.cos(th), top + wt * 0.12 * np.sin(th)], 1)], (0.86, 0.92, 1.0), 0.7 * a, 3,
                True)
    crisp_lines(cv, [np.stack([cx + wb * np.cos(th[:41]), bot + wb * 0.12 * np.sin(th[:41])], 1)], (0.86, 0.92, 1.0),
                0.85 * a, 4)
    crisp_lines(cv, [[(cx - wt * 0.62, top + hh * 0.25), (cx - wb * 0.62, bot - hh * 0.25)]], (1, 1, 1), 0.35 * a, 6)
    rr = np.random.default_rng(3)
    for k in range(7):
        ph = (t * 0.25 + rr.uniform(0, 1)) % 1.0
        bx = cx + rr.uniform(-0.7, 0.7) * wb
        by = bot - (bot - niveau) * ph
        gcircle(gl, (bx, by), 5, np.array([0.7, 0.9, 1.0], np.float32) * 0.5 * a * (1 - ph), 1)
    gcircle(gl, (cx, (niveau + bot) / 2), R * 0.9, np.array([0.3, 0.6, 1.0], np.float32) * 0.06 * a, -1)


def sucre(cv, gl, s, cx, cy, R, a, t):
    th = 0.25 + 0.05 * math.sin(t * 0.8)
    s_ = R * 1.15
    aa = s_ / 2
    ct, st = math.cos(th), math.sin(th)

    def P(x, y, z):
        x2, z2 = x * ct - z * st, x * st + z * ct
        return (cx + (x2 - z2) * 0.866, cy + aa * 0.5 + (x2 + z2) * 0.5 - y)
    top = [P(-aa, aa, -aa), P(aa, aa, -aa), P(aa, aa, aa), P(-aa, aa, aa)]
    right = [P(aa, aa, -aa), P(aa, aa, aa), P(aa, -aa, aa), P(aa, -aa, -aa)]
    front = [P(-aa, aa, aa), P(aa, aa, aa), P(aa, -aa, aa), P(-aa, -aa, aa)]
    for f, sh in zip((top, right, front), ((0.96, 0.96, 0.98), (0.62, 0.65, 0.72), (0.80, 0.82, 0.87))):
        crisp_fill(cv, [np.array(f)], sh, a)
    crisp_lines(cv, [np.array(top), np.array(right), np.array(front)], (1, 1, 1), 0.35 * a, 2, True)


def fourmi(cv, gl, s, cx, cy, R, a, t):
    """Fourmi de profil, en marche (pattes animées), silhouette claire sur fond sombre."""
    c = couleur(s.get("couleur"), "clair")
    ph = t * 9.0 * float(s.get("vitesse_pattes", 1.0))
    sx = -1 if s.get("sens", 1) < 0 else 1
    def X(u):
        return cx + sx * u * R
    def Y(v):
        return cy + v * R
    corps = [(0.55, -0.05, 0.22, 0.18), (0.18, -0.06, 0.24, 0.14), (-0.35, -0.02, 0.42, 0.27)]
    for k in range(6):
        cote = 1 if k < 3 else -1
        base_u = (0.28, 0.16, 0.04)[k % 3]
        phi = ph + (k % 3) * 2.1 + (math.pi if cote < 0 else 0)
        genou = (base_u + 0.10 * math.sin(phi), 0.16 + 0.06 * math.cos(phi))
        pied = (base_u + (0.18 * math.sin(phi) + (0.12 if k % 3 == 0 else -0.08 if k % 3 == 2 else 0.0)), 0.36)
        col = c * (1.0 if cote > 0 else 0.55)
        crisp_lines(cv, [[(X(base_u), Y(-0.02)), (X(genou[0]), Y(genou[1])), (X(pied[0]), Y(pied[1]))]], col,
                    0.9 * a, max(int(R * 0.05), 2))
    for (u, v, rx, ry) in corps:
        th = np.linspace(0, 2 * np.pi, 40)
        pts = np.stack([X(u) + sx * rx * R * np.cos(th), Y(v) + ry * R * np.sin(th)], 1)
        crisp_fill(cv, [pts], c * 0.82, a)
    crisp_lines(cv, [[(X(0.66), Y(-0.15)), (X(0.86), Y(-0.42)), (X(0.98), Y(-0.38))],
                     [(X(0.62), Y(-0.16)), (X(0.76), Y(-0.44)), (X(0.88), Y(-0.46))]], c, 0.9 * a,
                max(int(R * 0.035), 2))
    halo(gl, cx, cy, R * 1.2, c, 0.05 * a)


def lumiere(cv, gl, s, cx, cy, R, a, t):
    c = couleur(s.get("couleur"), "blanc")
    halo(gl, cx, cy, R * 2.2, c, 0.25 * a)
    halo(gl, cx, cy, R * 0.9, c, 0.9 * a)
    crisp_dot(cv, cx, cy, max(R * 0.18, 3), (1, 1, 1), a)


def point(cv, gl, s, cx, cy, R, a, t):
    c = couleur(s.get("couleur"), "ambre")
    ph = (t % 1.6) / 1.6
    gcircle(gl, (cx, cy), R * (0.4 + 1.6 * ph), c * (1 - ph) * 0.9 * a, 2)
    gcircle(gl, (cx, cy), R * 0.6, c * 0.4 * a, -1)
    crisp_dot(cv, cx, cy, max(R * 0.28, 3), np.minimum(c + 0.25, 1), a)


def icone(cv, gl, s, cx, cy, R, a, t):
    from vf import icons as IC
    n = int(R * 2)
    m = IC.mask(s["nom"], n)
    c = couleur(s.get("couleur"), "blanc")
    col = np.broadcast_to(c, (n, n, 3)).astype(np.float32)
    coller(cv, col, m * a, cx - n / 2, cy - n / 2)
    small = cv2.resize(m, (max(n // 2, 1), max(n // 2, 1)), interpolation=cv2.INTER_AREA)
    x0, y0 = int((cx - n / 2) * 0.5), int((cy - n / 2) * 0.5)
    hh, ww = small.shape
    ya, yb, xa, xb = max(y0, 0), min(y0 + hh, HH), max(x0, 0), min(x0 + ww, HW)
    if ya < yb and xa < xb:
        gl[ya:yb, xa:xb] += small[ya - y0:yb - y0, xa - x0:xb - x0, None] * c * 0.25 * a


FONCTIONS = dict(soleil=soleil, etoile=etoile, terre=terre, lune=lune, planete=planete, cmb=cmb, galaxie=galaxie,
                 univers=univers, trou_noir=trou_noir, atome=atome, molecule=molecule, cellule=cellule, virus=virus,
                 goutte=goutte, verre=verre, sucre=sucre, fourmi=fourmi, lumiere=lumiere, point=point, icone=icone)


def dessiner(cv, gl, spec, cx, cy, R, a, t):
    if not spec or a <= 0.005 or R < 0.5:
        return
    f = FONCTIONS.get(spec.get("type"))
    if f is None:
        raise KeyError(f"objet inconnu : {spec.get('type')!r} (types : {', '.join(TYPES)})")
    R = R * float(spec.get("taille", 1.0))
    x, y = cx + spec.get("dx", 0) * R_SCALE[0], cy + spec.get("dy", 0) * R_SCALE[0]
    f(cv, gl, spec, x, y, R, a, t)
    if spec.get("mention"):
        # « ILLUSTRATION », « PAS À L'ÉCHELLE »… : ce que l'image n'affirme pas, écrit sous l'objet (audité comme
        # tout texte : zones sûres, chevauchements)
        txt(cv, str(spec["mention"]).upper(), x, y + R + 28, 24, F_DBOLD, LIGHT, 0.85 * a, 0, 4.0)


R_SCALE = [1.0]               # les décalages dx/dy sont en pixels de référence
