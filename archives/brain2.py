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


def aniso_noise(sh, s, theta, seed, ratio=2.4):
    """Bruit passe-bande étiré dans la direction theta (radians) : circonvolutions allongées."""
    r = np.random.default_rng(seed)
    h, w = sh
    D = int(math.hypot(h, w)) + 8
    z = r.standard_normal((D, D)).astype(f32)
    a = cv2.GaussianBlur(z, (0, 0), sigmaX=s * ratio, sigmaY=s)
    b = cv2.GaussianBlur(z, (0, 0), sigmaX=s * ratio * 1.8, sigmaY=s * 1.8)
    n = a - b
    M = cv2.getRotationMatrix2D((D / 2, D / 2), -math.degrees(theta), 1.0)
    M[0, 2] += w / 2 - D / 2
    M[1, 2] += h / 2 - D / 2
    n = cv2.warpAffine(n, M, (w, h), flags=cv2.INTER_LINEAR)
    return n / (n.std() + 1e-6)


def gray_scott(h, w, n_it, seed, F=0.029, k=0.057, clamp=None, inside=None):
    """Réaction-diffusion de Gray-Scott en régime « labyrinthe » : des sillons continus et sinueux, de largeur
    constante, comme les circonvolutions. clamp : masque où les sillons sont imposés (grands sillons anatomiques)."""
    r = np.random.default_rng(seed)
    U = np.ones((h, w), f32)
    V = np.zeros((h, w), f32)
    m = r.random((h, w)) < 0.08
    V[m] = r.uniform(0.2, 0.5, m.sum())
    U[m] = 0.5
    ker = np.array([[0.05, 0.2, 0.05], [0.2, -1, 0.2], [0.05, 0.2, 0.05]], f32) * f32(4.0)
    cm = None if clamp is None else clamp > 0.5
    for _ in range(n_it):
        Lu = cv2.filter2D(U, -1, ker, borderType=cv2.BORDER_REFLECT)
        Lv = cv2.filter2D(V, -1, ker, borderType=cv2.BORDER_REFLECT)
        uvv = U * V * V
        U += f32(0.16) * Lu - uvv + f32(F) * (1 - U)
        V += f32(0.08) * Lv + uvv - f32(F + k) * V
        if cm is not None:
            V[cm] = 0.34
            U[cm] = 0.25
    return V


def gyri(n, R):
    """Sillons = lignes de passage à zéro du bruit ; circonvolutions = profil circulaire de rayon R."""
    sg = n > 0
    zc = np.zeros(n.shape, bool)
    zc[:, 1:] |= sg[:, 1:] != sg[:, :-1]
    zc[1:, :] |= sg[1:, :] != sg[:-1, :]
    d = cv2.distanceTransform((~zc).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE).astype(f32)
    u = np.clip(d / R, 0, 1)
    return np.sqrt(u * (2 - u)).astype(f32)


def dome(mask, R):
    """Hauteur d'un volume arrondi : profil circulaire de rayon R depuis le bord du masque."""
    b = (mask > 0.5).astype(np.uint8)
    d = cv2.distanceTransform(b, cv2.DIST_L2, cv2.DIST_MASK_PRECISE).astype(f32)
    d = np.minimum(d, R)
    d = cv2.GaussianBlur(d, (0, 0), 0.12 * R) * b      # lisse l'arête de l'axe médian
    return np.sqrt(np.maximum(2 * R * d - d * d, 0)).astype(f32)


def shade(Hh, mask, base, dark, g, groove, light=(-0.50, -0.70, 0.48), spec=0.22, rim_col=None, rim=0.0, rimw=None):
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
    ao = (0.12 + 0.88 * g) ** 1.4 * (1 - 0.6 * groove)
    col = dark + (base - dark) * (ao[..., None] ** 0.8)
    out = col * (0.18 + 0.82 * dif)[..., None] + (sp * spec * ao)[..., None]
    if rim_col is not None and rim > 0:
        rw = 1.0 if rimw is None else rimw
        out += ((1 - nz) ** 2.0 * rim * rw)[..., None] * rim_col
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


def lateral_brain(cx, cy, Lpx, seed=8, base=None, dark=None, rim_col=None):
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
    rw = np.random.default_rng(seed + 3)
    major = []
    for nm, p in MAJOR.items():                         # grands sillons légèrement ondulés
        q = cr_open(tr(p), 10)
        nrm = np.gradient(q, axis=0)[:, ::-1] * [1, -1]
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
        wv = np.cumsum(rw.normal(0, 1, len(q)))
        wv = np.convolve(wv - wv.mean(), np.ones(9) / 9, "same")
        wv = wv / (np.abs(wv).max() + 1e-9) * 0.006 * Lpx
        major.append(q + nrm * wv[:, None])
    guide = [major[i] for i, nm in enumerate(MAJOR) if nm in ("sylvien", "central", "temp_sup", "intrapar")]
    sc = 2.5                                            # 1 pixel de simulation = sc pixels d'écran
    gh, gw = int(hgt / sc) + 1, int(wid / sc) + 1
    clamp = poly_lines((gh, gw), [p / sc for p in guide], 1, ss=3)
    V = gray_scott(gh, gw, 9000, seed, clamp=clamp)
    V = cv2.resize(V, (wid, hgt), interpolation=cv2.INTER_CUBIC)
    lam = 15 * sc                                       # période des bandes à l'écran
    rq = np.random.default_rng(seed + 7)
    wx = cv2.GaussianBlur(rq.standard_normal(sh).astype(f32), (0, 0), 1.3 * lam)
    wy = cv2.GaussianBlur(rq.standard_normal(sh).astype(f32), (0, 0), 1.3 * lam)
    wx *= 0.45 * lam / (wx.std() + 1e-6)
    wy *= 0.45 * lam / (wy.std() + 1e-6)
    gx_, gy_ = np.meshgrid(np.arange(wid, dtype=f32), np.arange(hgt, dtype=f32))
    V = cv2.remap(V, gx_ + wx, gy_ + wy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    V = np.clip(V / (np.percentile(V, 99.5) + 1e-6), 0, 1)
    g = (1 - V ** 3.0).astype(f32)                     # sillons étroits au cœur des bandes, circonvolutions larges
    groove = poly_lines(sh, guide, 0.0035 * Lpx)
    groove = np.clip(cv2.GaussianBlur(groove, (0, 0), 0.0035 * Lpx) * 1.3, 0, 1)
    yy, xx = np.mgrid[0:hgt, 0:wid].astype(f32)
    Hd = dome(m_cer, 0.20 * Lpx)
    Hc = Hd + g * (0.024 * Lpx) - groove * (0.010 * Lpx)
    base = C3(0.20, 0.24, 0.56) if base is None else base
    dark = C3(0.008, 0.010, 0.030) if dark is None else dark
    rim_col = C3(0.25, 0.75, 1.0) if rim_col is None else rim_col
    dedge = cv2.distanceTransform((m_cer > 0.5).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE).astype(f32)
    rimw = np.exp(-dedge / (0.025 * Lpx)).astype(f32)
    col_cer, nz = shade(cv2.GaussianBlur(Hc, (0, 0), 0.7), m_cer, base, dark, g, groove, rim_col=rim_col, rim=0.9,
                        rimw=rimw)
    # cervelet : lamelles parallèles
    c0 = tr([(0.16, 0.05)])[0]
    rr = np.sqrt((xx - c0[0]) ** 2 + ((yy - c0[1]) * 1.25) ** 2)
    wob = dog_noise(sh, 0.02 * Lpx, seed + 5) * (0.006 * Lpx)
    fol = (np.abs(np.sin((rr + wob) / (0.0105 * Lpx) * math.pi))).astype(f32)
    fol = np.sqrt(fol)
    Hcb = dome(m_cb, 0.09 * Lpx) + fol * 0.008 * Lpx
    col_cb, _ = shade(Hcb, m_cb, base * f32(0.80), dark, fol, np.zeros_like(fol), rim_col=rim_col, rim=0.5,
                      rimw=np.exp(-cv2.distanceTransform((m_cb > 0.5).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE) / (0.02 * Lpx)).astype(f32))
    Hst = dome(m_st, 0.05 * Lpx)
    col_st, _ = shade(Hst, m_st, base * f32(0.60), dark, np.ones_like(Hst), np.zeros_like(Hst), rim_col=rim_col, rim=0.5)
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


# ------------------------------------------------------------------ outils de contour
def offset_closed(P, d):
    """Décale un contour fermé de d pixels vers l'extérieur."""
    P = np.asarray(P, float)
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    tg = np.roll(P, -1, 0) - np.roll(P, 1, 0)
    nrm = np.stack([tg[:, 1], -tg[:, 0]], 1)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    if area < 0:
        nrm = -nrm
    Q = P + nrm * d
    # sens : on vérifie que le contour décalé est bien plus grand
    a2 = 0.5 * np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1])
    if abs(a2) < abs(area):
        Q = P - nrm * d
    return Q


def arc_len_resample(P, step, closed=True):
    P = np.asarray(P, float)
    Q = np.vstack([P, P[:1]]) if closed else P
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(int(s[-1] / step), 2)
    u = np.linspace(0, s[-1], n, endpoint=not closed)
    return np.stack([np.interp(u, s, Q[:, 0]), np.interp(u, s, Q[:, 1])], 1)


# ------------------------------------------------------------------ tête en coupe (profil gauche) autour du cerveau
HEAD = [(-0.572, 0.035), (-0.553, -0.120), (-0.480, -0.250), (-0.360, -0.345), (-0.200, -0.400), (-0.035, -0.420),
        (0.130, -0.408), (0.285, -0.360), (0.410, -0.275), (0.500, -0.160), (0.555, -0.035), (0.572, 0.075),
        (0.560, 0.180), (0.520, 0.320), (0.440, 0.480), (0.405, 0.660), (0.395, 1.000), (-0.200, 1.000),
        (-0.215, 0.880), (-0.300, 0.805), (-0.420, 0.810), (-0.540, 0.790), (-0.590, 0.720), (-0.575, 0.650),
        (-0.600, 0.600), (-0.585, 0.565), (-0.610, 0.530), (-0.605, 0.470), (-0.675, 0.420), (-0.620, 0.320),
        (-0.570, 0.200), (-0.585, 0.120)]
EAR = [(0.075, 0.300), (0.090, 0.215), (0.150, 0.185), (0.205, 0.225), (0.215, 0.315), (0.185, 0.400), (0.125, 0.440),
       (0.090, 0.415)]


def head_scene(cx, cy, Lpx, seed=8):
    """Tête de profil façon radiographie : contour de la peau, voûte du crâne, méninges, et le cerveau dedans."""
    Hs = Brain()
    Hs.brain = lateral_brain(cx, cy, Lpx, seed=seed)
    B = Hs.brain

    def trs(P):
        P = np.asarray(P, float)
        return np.stack([cx + P[:, 0] * Lpx, cy + P[:, 1] * Lpx], 1)

    Hs.head = cr_closed(trs(HEAD), 14)
    Hs.skull = offset_closed(B.outline, 0.040 * Lpx)
    Hs.dura = offset_closed(B.outline, 0.013 * Lpx)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(Hs.head * 16).astype(np.int32)], 255, cv2.LINE_AA, 4)
    fade = np.clip((cy + 0.95 * Lpx - np.arange(H, dtype=f32)) / (0.35 * Lpx), 0, 1)[:, None]
    Hs.fill = (m.astype(f32) / 255.0 * fade).astype(f32)
    # récepteurs de la douleur : méninges, crâne/cuir chevelu (jamais dans le tissu cérébral)
    r = np.random.default_rng(seed + 21)
    d_pts = arc_len_resample(Hs.dura, 0.042 * Lpx)
    up = d_pts[:, 1] < cy + 0.17 * Lpx
    d_pts = d_pts[up]
    s_pts = arc_len_resample(offset_closed(B.outline, 0.062 * Lpx), 0.05 * Lpx)
    s_pts = s_pts[s_pts[:, 1] < cy + 0.10 * Lpx]
    Hs.receptors = np.vstack([d_pts + r.normal(0, 1.5, d_pts.shape), s_pts + r.normal(0, 2.0, s_pts.shape)])
    Hs.rec_delay = r.uniform(0, 1, len(Hs.receptors))
    Hs.L, Hs.cx, Hs.cy = Lpx, cx, cy
    return Hs


# ------------------------------------------------------------------ cerveau vu de dessus (front en haut)
HEMI_L = [(-0.016, -0.488), (-0.100, -0.500), (-0.200, -0.470), (-0.290, -0.400), (-0.360, -0.282), (-0.400, -0.120),
          (-0.412, 0.050), (-0.402, 0.200), (-0.362, 0.330), (-0.282, 0.432), (-0.172, 0.490), (-0.062, 0.506),
          (-0.016, 0.490), (-0.010, 0.300), (-0.008, 0.000), (-0.010, -0.300)]
DGUIDE_L = [
    [(-0.030, 0.020), (-0.120, -0.010), (-0.210, -0.045), (-0.300, -0.090), (-0.385, -0.130)],      # sillon central
    [(-0.120, -0.120), (-0.130, -0.250), (-0.140, -0.360), (-0.150, -0.450)],                       # frontal supérieur
    [(-0.180, 0.090), (-0.200, 0.200), (-0.190, 0.310), (-0.160, 0.420)],                           # intrapariétal
    [(-0.040, -0.080), (-0.150, -0.110), (-0.260, -0.160), (-0.360, -0.230)],                       # précentral
]


def dorsal_brain(cx, cy, Lpx, seed=5):
    """Les deux hémisphères vus de dessus, séparés par la scissure inter-hémisphérique."""
    B = Brain()
    pad = 30
    x0, x1 = int(cx - 0.45 * Lpx) - pad, int(cx + 0.45 * Lpx) + pad
    y0, y1 = int(cy - 0.53 * Lpx) - pad, int(cy + 0.53 * Lpx) + pad
    B.box = (x0, y0, x1, y1)
    hgt, wid = y1 - y0, x1 - x0
    sh = (hgt, wid)

    def tr(P, mirror=False):
        P = np.asarray(P, float)
        sx = -1 if mirror else 1
        return np.stack([cx - x0 + sx * P[:, 0] * Lpx, cy - y0 + P[:, 1] * Lpx], 1)

    pl = cr_closed(tr(HEMI_L), 18)
    pr = cr_closed(tr(HEMI_L, True), 18)
    mL, mR = poly_fill(sh, pl), poly_fill(sh, pr)
    guides = [cr_open(tr(g), 10) for g in DGUIDE_L] + [cr_open(tr(g, True), 10) for g in DGUIDE_L]
    sc = 2.5
    gh, gw = int(hgt / sc) + 1, int(wid / sc) + 1
    clamp = poly_lines((gh, gw), [p / sc for p in guides], 1, ss=3)
    V = gray_scott(gh, gw, 9000, seed, clamp=clamp)
    V = cv2.resize(V, (wid, hgt), interpolation=cv2.INTER_CUBIC)
    lam = 15 * sc
    rq = np.random.default_rng(seed + 7)
    wx = cv2.GaussianBlur(rq.standard_normal(sh).astype(f32), (0, 0), 1.3 * lam)
    wy = cv2.GaussianBlur(rq.standard_normal(sh).astype(f32), (0, 0), 1.3 * lam)
    wx *= 0.45 * lam / (wx.std() + 1e-6)
    wy *= 0.45 * lam / (wy.std() + 1e-6)
    gx_, gy_ = np.meshgrid(np.arange(wid, dtype=f32), np.arange(hgt, dtype=f32))
    V = cv2.remap(V, gx_ + wx, gy_ + wy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    V = np.clip(V / (np.percentile(V, 99.5) + 1e-6), 0, 1)
    g = (1 - V ** 3.0).astype(f32)
    groove = np.zeros(sh, f32)
    base = C3(0.20, 0.24, 0.56)
    dark = C3(0.008, 0.010, 0.030)
    rim_col = C3(0.25, 0.75, 1.0)
    col = np.zeros((hgt, wid, 3), f32)
    for m in (mL, mR):
        Hd = dome(m, 0.17 * Lpx)
        Hc = Hd + g * (0.024 * Lpx) - groove * (0.010 * Lpx)
        dedge = cv2.distanceTransform((m > 0.5).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE).astype(f32)
        rimw = np.exp(-dedge / (0.025 * Lpx)).astype(f32)
        c, _ = shade(cv2.GaussianBlur(Hc, (0, 0), 0.7), m, base, dark, g, groove, light=(-0.35, -0.75, 0.55),
                     rim_col=rim_col, rim=0.9, rimw=rimw)
        col += c
    B.color = col
    B.mask = np.clip(mL + mR, 0, 1).astype(f32)
    B.mL, B.mR, B.g = mL, mR, g
    B.L, B.cx, B.cy, B.tr = Lpx, cx, cy, tr
    B.outline_l = pl + [x0, y0]
    B.outline_r = pr + [x0, y0]
    return B


# ------------------------------------------------------------------ galaxie spirale (Voie lactée stylisée)
def splat2(layer, x, y, e, col):
    h, w = layer.shape[:2]
    m = (x >= 0) & (x < w - 1) & (y >= 0) & (y < h - 1) & (e > 0)
    x, y, e, col = x[m], y[m], e[m], col[m]
    x0 = x.astype(np.int32)
    y0 = y.astype(np.int32)
    fx, fy = x - x0, y - y0
    i00 = y0 * w + x0
    idx = np.concatenate([i00, i00 + 1, i00 + w, i00 + w + 1])
    wts = np.concatenate([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy]) * np.tile(e, 4)
    for ch in range(3):
        acc = np.bincount(idx, weights=wts * np.tile(col[:, ch], 4), minlength=w * h)
        layer[..., ch] += acc.reshape(h, w).astype(f32)


def galaxy_texture(n=1024, seed=41, npart=520000, arms=4, pitch=15.0):
    r_ = np.random.default_rng(seed)
    R = 50000.0
    tp = math.tan(math.radians(pitch))
    xs, ys, cs, es = [], [], [], []
    na = int(npart * 0.5)
    rr = 3000 + r_.exponential(11000, na)
    rr = rr[rr < R]
    k = r_.integers(0, arms, len(rr))
    th = k * TAU / arms + np.log(rr / 4000.0) / tp + r_.normal(0, 0.22, len(rr)) * (1 + 3000 / rr)
    xs.append(rr * np.cos(th)); ys.append(rr * np.sin(th))
    hii = r_.random(len(rr)) < 0.05
    cs.append(np.where(hii[:, None], C3(1.0, 0.35, 0.60), C3(0.62, 0.76, 1.0))); es.append(np.where(hii, 2.4, 1.0))
    nd = int(npart * 0.3)
    rd = r_.exponential(10000, nd)
    rd = rd[rd < R * 1.05]
    td = r_.uniform(0, TAU, len(rd))
    xs.append(rd * np.cos(td)); ys.append(rd * np.sin(td))
    cs.append(np.broadcast_to(C3(1.0, 0.92, 0.82), (len(rd), 3))); es.append(np.full(len(rd), 0.7))
    nb = int(npart * 0.2)
    bl = r_.uniform(-1, 1, nb // 2) * 9000
    bw = r_.normal(0, 1300, nb // 2)
    ba = 0.45
    xs.append(bl * math.cos(ba) - bw * math.sin(ba)); ys.append(bl * math.sin(ba) + bw * math.cos(ba))
    cs.append(np.broadcast_to(C3(1.0, 0.78, 0.5), (nb // 2, 3))); es.append(np.full(nb // 2, 1.1))
    bb = r_.normal(0, 2600, (nb // 2, 2))
    xs.append(bb[:, 0]); ys.append(bb[:, 1])
    cs.append(np.broadcast_to(C3(1.0, 0.8, 0.55), (nb // 2, 3))); es.append(np.full(nb // 2, 1.3))
    x = np.concatenate(xs); y = np.concatenate(ys)
    c = np.concatenate(cs).astype(f32); e = np.concatenate(es)
    half = 60000.0
    L = np.zeros((n, n, 3), f32)
    splat2(L, (x / half * 0.5 + 0.5) * n, (0.5 - y / half * 0.5) * n, e, c)
    L = cv2.GaussianBlur(L, (0, 0), 1.4) + 0.6 * cv2.GaussianBlur(L, (0, 0), 7.0) + 0.25 * cv2.GaussianBlur(L, (0, 0), 30.0)
    L /= np.percentile(L.max(axis=2), 99.7)
    # étoiles brillantes nettes
    k2 = r_.random(len(x)) < 0.012
    Sx = np.zeros((n, n, 3), f32)
    splat2(Sx, (x[k2] / half * 0.5 + 0.5) * n, (0.5 - y[k2] / half * 0.5) * n, r_.uniform(0.6, 2.5, k2.sum()) ** 2, c[k2])
    L += cv2.GaussianBlur(Sx, (0, 0), 0.7) * 1.5
    # bandes de poussière le long des bras
    dr = 4000 + r_.exponential(9000, 70000)
    dr = dr[dr < 45000]
    dk = r_.integers(0, arms, len(dr))
    dth = -0.18 + dk * TAU / arms + np.log(dr / 4000.0) / tp + r_.normal(0, 0.06, len(dr))
    D = np.zeros((n, n, 3), f32)
    splat2(D, (dr * np.cos(dth) / half * 0.5 + 0.5) * n, (0.5 - dr * np.sin(dth) / half * 0.5) * n, np.ones(len(dr)),
           np.ones((len(dr), 3), f32))
    D = cv2.GaussianBlur(D[..., 0], (0, 0), 2.5)
    D /= D.max()
    L *= np.exp(-D * 1.2)[..., None]
    return L.astype(f32)
