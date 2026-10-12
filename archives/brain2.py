# -*- coding: utf-8 -*-
"""Cerveaux procéduraux pour VRAI OU FAUX ? #2 : vue de profil (latérale) et vue de dessus (deux hémisphères).
Chaque cerveau est précalculé une fois (relief des circonvolutions, ombrage, régions) puis éclairé à chaque image."""
import math

import numpy as np
import cv2
from scipy.spatial import cKDTree

from vlib import *  # noqa: F401,F403


def cr_closed(P, n=24):
    P = np.asarray(P, float)
    N = len(P)
    t = np.linspace(0, 1, n, endpoint=False)[:, None]
    out = []
    for i in range(N):
        p0, p1, p2, p3 = P[(i - 1) % N], P[i], P[(i + 1) % N], P[(i + 2) % N]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.vstack(out)


def cr_open(P, n=24):
    P = np.asarray(P, float)
    P = np.vstack([P[:1] * 2 - P[1:2], P, P[-1:] * 2 - P[-2:-1]])
    t = np.linspace(0, 1, n, endpoint=False)[:, None]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2:-1])
    return np.vstack(out)


def poly_fill(shape, pts, ss=4):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(pts) * (1 << ss)).astype(np.int32)], 255, cv2.LINE_AA, ss)
    return m.astype(f32) / 255.0


def poly_lines(shape, polylines, thick, ss=4):
    m = np.zeros(shape, np.uint8)
    for p in polylines:
        cv2.polylines(m, [np.round(np.asarray(p) * (1 << ss)).astype(np.int32)], False, 255, max(1, int(round(thick))),
                      cv2.LINE_AA, ss)
    return m.astype(f32) / 255.0


def dog_noise(shape, s, seed, warp=0.0):
    r = np.random.default_rng(seed)
    z = r.standard_normal(shape).astype(f32)
    n = cv2.GaussianBlur(z, (0, 0), s) - cv2.GaussianBlur(z, (0, 0), s * 1.7)
    n /= n.std() + 1e-6
    if warp > 0:                                        # déformation du domaine : plis plus organiques
        h, w = shape
        wx = cv2.GaussianBlur(r.standard_normal(shape).astype(f32), (0, 0), s * 5)
        wy = cv2.GaussianBlur(r.standard_normal(shape).astype(f32), (0, 0), s * 5)
        wx *= warp / (wx.std() + 1e-6)
        wy *= warp / (wy.std() + 1e-6)
        gx, gy = np.meshgrid(np.arange(w, dtype=f32), np.arange(h, dtype=f32))
        n = cv2.remap(n, gx + wx, gy + wy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return n


def dome(mask, R):
    """Hauteur d'un volume arrondi : profil circulaire de rayon R depuis le bord du masque."""
    b = (mask > 0.5).astype(np.uint8)
    d = cv2.distanceTransform(b, cv2.DIST_L2, 5).astype(f32)
    d = np.minimum(d, R)
    return np.sqrt(np.maximum(2 * R * d - d * d, 0)).astype(f32)


def shade(Hh, mask, base, dark, g, groove, light=(-0.45, -0.65, 0.62), spec=0.22, rim_col=None, rim=0.0):
    gy, gx = np.gradient(Hh)
    nx, ny, nz = -gx, -gy, np.ones_like(Hh)
    nn = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / nn, ny / nn, nz / nn
    L = np.array(light, float)
    L /= np.linalg.norm(L)
    dif = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    Hv = L + np.array([0, 0, 1.0])
    Hv /= np.linalg.norm(Hv)
    sp = np.clip(nx * Hv[0] + ny * Hv[1] + nz * Hv[2], 0, 1) ** 36
    ao = (0.22 + 0.78 * g) * (1 - 0.85 * groove)
    col = dark + (base - dark) * (ao[..., None] ** 0.8)
    out = col * (0.18 + 0.82 * dif)[..., None] + (sp * spec * ao)[..., None]
    if rim_col is not None and rim > 0:
        out += ((1 - nz) ** 2.5 * rim)[..., None] * rim_col
    return (out * mask[..., None]).astype(f32), nz.astype(f32)


# ------------------------------------------------------------------ cerveau de profil (lobe frontal à gauche)
CEREBRUM = [(-0.500, 0.030), (-0.478, -0.105), (-0.415, -0.212), (-0.315, -0.290), (-0.185, -0.336), (-0.035, -0.352),
            (0.115, -0.340), (0.248, -0.298), (0.352, -0.228), (0.432, -0.135), (0.484, -0.025), (0.500, 0.058),
            (0.476, 0.112), (0.412, 0.138), (0.300, 0.158), (0.182, 0.184), (0.062, 0.214), (-0.048, 0.228),
            (-0.140, 0.216), (-0.204, 0.182), (-0.236, 0.128), (-0.232, 0.090), (-0.258, 0.072), (-0.302, 0.092),
            (-0.382, 0.106), (-0.452, 0.090)]
CEREBELLUM = [(0.150, 0.170), (0.265, 0.150), (0.385, 0.150), (0.462, 0.178), (0.468, 0.232), (0.420, 0.285),
              (0.320, 0.312), (0.215, 0.300), (0.150, 0.262), (0.128, 0.215)]
STEM = [(0.040, 0.190), (0.150, 0.190), (0.172, 0.262), (0.168, 0.345), (0.150, 0.470), (0.098, 0.470),
        (0.088, 0.360), (0.060, 0.300), (0.034, 0.240)]
MAJOR = {   # grands sillons, en coordonnées normalisées
    "sylvien": [(-0.255, 0.074), (-0.170, 0.050), (-0.060, 0.030), (0.060, 0.010), (0.150, -0.020), (0.215, -0.075)],
    "central": [(0.030, -0.350), (0.012, -0.290), (0.020, -0.230), (-0.010, -0.160), (-0.002, -0.100), (-0.040, -0.040),
                (-0.050, 0.020)],
    "precentral": [(-0.090, -0.345), (-0.100, -0.270), (-0.110, -0.200), (-0.135, -0.110), (-0.140, -0.030)],
    "postcentral": [(0.105, -0.338), (0.096, -0.270), (0.090, -0.200), (0.070, -0.120), (0.060, -0.050)],
    "temp_sup": [(-0.200, 0.150), (-0.080, 0.122), (0.050, 0.100), (0.170, 0.072), (0.262, 0.020), (0.300, -0.040)],
    "front_sup": [(-0.120, -0.240), (-0.230, -0.230), (-0.330, -0.200), (-0.420, -0.140)],
    "front_inf": [(-0.150, -0.110), (-0.250, -0.090), (-0.350, -0.060), (-0.445, -0.020)],
    "intrapar": [(0.110, -0.200), (0.200, -0.180), (0.290, -0.140), (0.380, -0.080)],
    "temp_inf": [(-0.150, 0.195), (-0.020, 0.180), (0.120, 0.150), (0.250, 0.115)],
    "parieto_occ": [(0.360, -0.226), (0.380, -0.150), (0.420, -0.100)],
}


class Brain:
    pass


def lateral_brain(cx, cy, Lpx, seed=3, base=None, dark=None, rim_col=None):
    """Construit le cerveau de profil : longueur fronto-occipitale Lpx pixels, centre (cx, cy)."""
    B = Brain()
    pad = 30
    x0 = int(cx - 0.52 * Lpx) - pad
    x1 = int(cx + 0.52 * Lpx) + pad
    y0 = int(cy - 0.37 * Lpx) - pad
    y1 = int(cy + 0.49 * Lpx) + pad
    B.box = (x0, y0, x1, y1)
    hgt, wid = y1 - y0, x1 - x0
    sh = (hgt, wid)

    def tr(P):
        P = np.asarray(P, float)
        return np.stack([cx - x0 + P[:, 0] * Lpx, cy - y0 + P[:, 1] * Lpx], 1)

    cer_pts = cr_closed(tr(CEREBRUM), 20)
    cb_pts = cr_closed(tr(CEREBELLUM), 16)
    st_pts = cr_closed(tr(STEM), 14)
    B.outline = cer_pts + [x0, y0]                     # contour en coordonnées écran
    m_cer = poly_fill(sh, cer_pts)
    m_cb = poly_fill(sh, cb_pts) * (1 - m_cer)
    m_st = poly_fill(sh, st_pts) * (1 - m_cer) * (1 - poly_fill(sh, cb_pts))
    s = 0.0135 * Lpx                                    # taille des circonvolutions
    n = dog_noise(sh, s, seed, warp=1.6 * s)
    g = (1 - np.exp(-(n / 0.62) ** 2)).astype(f32)      # sommets des circonvolutions = 1, fond des sillons = 0
    major = [cr_open(tr(p), 10) for p in MAJOR.values()]
    groove = poly_lines(sh, major, 0.0075 * Lpx)
    groove = np.clip(cv2.GaussianBlur(groove, (0, 0), 0.006 * Lpx) * 1.6, 0, 1)
    g = g * (1 - 0.7 * groove)
    Hd = dome(m_cer, 0.20 * Lpx)
    Hc = Hd + g * (0.020 * Lpx) - groove * (0.028 * Lpx)
    base = C3(0.36, 0.40, 0.78) if base is None else base
    dark = C3(0.020, 0.022, 0.060) if dark is None else dark
    rim_col = C3(0.25, 0.75, 1.0) if rim_col is None else rim_col
    col_cer, nz = shade(cv2.GaussianBlur(Hc, (0, 0), 0.8), m_cer, base, dark, g, groove, rim_col=rim_col, rim=0.55)
    # cervelet : lamelles parallèles
    yy, xx = np.mgrid[0:hgt, 0:wid].astype(f32)
    c0 = tr([(0.16, 0.05)])[0]
    rr = np.sqrt((xx - c0[0]) ** 2 + ((yy - c0[1]) * 1.25) ** 2)
    fol = (0.5 + 0.5 * np.cos(rr / (0.0095 * Lpx) * TAU * 0.5) ** 2).astype(f32)
    fol = fol * (0.75 + 0.25 * np.tanh(dog_noise(sh, s * 0.8, seed + 5)))
    Hcb = dome(m_cb, 0.09 * Lpx) + fol * 0.010 * Lpx
    col_cb, _ = shade(Hcb, m_cb, base * f32(0.72), dark, fol, np.zeros_like(fol), rim_col=rim_col, rim=0.4)
    Hst = dome(m_st, 0.05 * Lpx)
    col_st, _ = shade(Hst, m_st, base * f32(0.55), dark, np.ones_like(Hst), np.zeros_like(Hst), rim_col=rim_col, rim=0.35)
    B.color = (col_cer + col_cb + col_st).astype(f32)
    B.mask_cer, B.mask_cb, B.mask_st = m_cer, m_cb, m_st
    B.mask = np.clip(m_cer + m_cb + m_st, 0, 1).astype(f32)
    B.g, B.groove, B.nz = g, groove, nz
    B.L, B.cx, B.cy, B.tr = Lpx, cx, cy, tr
    # régions (cellules de Voronoï dans le cortex) pour les activations
    r = np.random.default_rng(seed + 11)
    ys, xs = np.nonzero(m_cer > 0.5)
    pts = []
    while len(pts) < 42:
        k = r.integers(0, len(xs))
        p = (xs[k], ys[k])
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > (0.085 * Lpx) ** 2 for q in pts):
            pts.append(p)
    pts = np.array(pts, float)
    tree = cKDTree(pts)
    _, lab = tree.query(np.stack([xx.ravel(), yy.ravel()], 1))
    B.labels = lab.reshape(sh).astype(np.int32)
    B.seeds = pts
    B.cells = []
    for k in range(len(pts)):
        cm = ((B.labels == k).astype(f32) * m_cer)
        B.cells.append(cm)
    B.area = float(m_cer.sum())
    B.cell_area = np.array([c.sum() for c in B.cells])
    # réseau de neurones (nœuds dans le cortex, liaisons aux plus proches voisins)
    nn_ = 230
    sel = r.choice(len(xs), nn_ * 4, replace=False)
    cand = np.stack([xs[sel], ys[sel]], 1).astype(float)
    nodes = []
    for p in cand:
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > (0.032 * Lpx) ** 2 for q in nodes):
            nodes.append(p)
        if len(nodes) >= nn_:
            break
    nodes = np.array(nodes)
    t2 = cKDTree(nodes)
    edges = set()
    for i, p in enumerate(nodes):
        d, j = t2.query(p, 4)
        for jj in j[1:]:
            edges.add((min(i, jj), max(i, jj)))
    B.nodes = nodes + [x0, y0]
    B.edges = np.array(sorted(edges))
    return B


def place(hdr, B, layer, gain=1.0):
    x0, y0, x1, y1 = B.box
    ys0, xs0 = max(0, -y0), max(0, -x0)
    X0, Y0 = max(x0, 0), max(y0, 0)
    X1, Y1 = min(x1, W), min(y1, H)
    if X1 <= X0 or Y1 <= Y0:
        return
    sub = layer[ys0:ys0 + (Y1 - Y0), xs0:xs0 + (X1 - X0)]
    if sub.ndim == 2:
        sub = sub[..., None]
    hdr[Y0:Y1, X0:X1] += sub * f32(gain)


def composite(hdr, B, gain=1.0):
    """Pose le cerveau opaque sur le fond."""
    x0, y0, x1, y1 = B.box
    X0, Y0, X1, Y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    m = B.mask[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0][..., None]
    hdr[Y0:Y1, X0:X1] = hdr[Y0:Y1, X0:X1] * (1 - m) + B.color[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0] * f32(gain)
