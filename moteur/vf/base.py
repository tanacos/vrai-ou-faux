# -*- coding: utf-8 -*-
"""Socle de rendu vertical 1080 x 1920 de la série « Vrai ou faux ? » (couleurs, courbes d'animation, texte, formes,
post-traitement). Reprend à l'identique le rendu des épisodes 1 et 2 ; aucune dépendance hors numpy, OpenCV, Pillow."""
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

cv2.setNumThreads(1)
f32 = np.float32
TAU = 2.0 * math.pi

W, H, FPS = 1080, 1920, 30
CX, CY = W / 2, H / 2
XS, YS = np.meshgrid(np.arange(W, dtype=f32), np.arange(H, dtype=f32))

FD = os.environ.get("VF_FONTS", "/usr/share/fonts/opentype/inter/")
F_DBLACK = FD + "InterDisplay-Black.otf"
F_DXB = FD + "InterDisplay-ExtraBold.otf"
F_DBOLD = FD + "InterDisplay-Bold.otf"
F_DSEMI = FD + "InterDisplay-SemiBold.otf"
F_DMED = FD + "InterDisplay-Medium.otf"
F_REG = FD + "Inter-Regular.otf"
F_MEDI = FD + "Inter-Medium.otf"
F_SEMI = FD + "Inter-SemiBold.otf"
F_BOLD = FD + "Inter-Bold.otf"
RAQM = ImageFont.Layout.RAQM

# zones sûres TikTok (placement « in-feed ») : haut 240, bas 660, gauche 120, droite 120 (300 sous y = 840)
SAFE_TOP, SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT, SAFE_RIGHT_LOW = 240, H - 660, 120, W - 120, W - 300


def C3(r, g, b):
    return np.array([r, g, b], f32)


# ------------------------------------------------------------------ courbes d'animation
def sat(x):
    return 0.0 if x <= 0 else (1.0 if x >= 1 else x)


def sstep(a, b, x):
    u = sat((x - a) / (b - a))
    return u * u * (3 - 2 * u)


def ein(u, p=3.0):
    return sat(u) ** p


def eout(u, p=3.0):
    return 1.0 - (1.0 - sat(u)) ** p


def einout(u):
    u = sat(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def smoother(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * u * (u * (6 * u - 15) + 10)


def bump(t, a, b, c, d):
    """0 avant a, monte jusqu'à b, 1 jusqu'à c, redescend à 0 en d."""
    if t <= a or t >= d:
        return 0.0
    if t < b:
        return smoother((t - a) / (b - a))
    if t > c:
        return 1.0 - smoother((t - c) / (d - c))
    return 1.0


def back_out(u, s=1.70158):
    u = min(max(u, 0.0), 1.0) - 1
    return u * u * ((s + 1) * u + s) + 1


def aces(x):
    return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


_rr = np.sqrt(((XS - CX) / (W * 0.66)) ** 2 + ((YS - CY) / (H * 0.60)) ** 2)
VIGNETTE = (1.0 - 0.32 * np.clip(_rr, 0, 1.25) ** 2.3).astype(f32)

# ------------------------------------------------------------------ texte
_FC = {}
_TP = {}


def font(path, size):
    k = (path, size)
    if k not in _FC:
        _FC[k] = ImageFont.truetype(path, size, layout_engine=RAQM)
    return _FC[k]


def text_width(txt, path, size, tracking=0.0):
    F = font(path, size * 3)
    return sum(F.getlength(c) for c in txt) / 3 + tracking * max(len(txt) - 1, 0)


def text_patch(txt, path, size, tracking=0.0, ss=3, pad=8):
    """Texte -> (masque float32, largeur, ascent, hauteur de ligne) ; mis en cache."""
    key = (txt, path, size, round(tracking, 2))
    if key in _TP:
        return _TP[key]
    if len(_TP) > 2000:
        _TP.clear()
    F = font(path, size * ss)
    asc, desc = F.getmetrics()
    wpx = sum(F.getlength(c) for c in txt) / ss + tracking * max(len(txt) - 1, 0)
    w = int(math.ceil(wpx)) + 2 * pad
    h = int(math.ceil((asc + desc) / ss)) + 2 * pad
    img = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(img)
    x = pad * ss
    for c in txt:
        d.text((x, pad * ss + asc), c, font=F, fill=255, anchor="ls")
        x += F.getlength(c) + tracking * ss
    m = np.asarray(img.resize((w, h), Image.BOX), f32) / 255.0
    _TP[key] = (m, wpx, asc / ss + pad, (asc + desc) / ss)
    return _TP[key]


def wrap(txt, path, size, max_w, tracking=0.0):
    words = txt.split(" ")
    lines, cur = [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if cur and text_width(test, path, size, tracking) > max_w:
            lines.append(cur)
            cur = w_
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def blit_add(hdr, m, x, y, col, a=1.0):
    if a <= 0.003:
        return
    h, w = m.shape
    x0, y0 = int(round(x)), int(round(y))
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xb <= xa or yb <= ya:
        return
    hdr[ya:yb, xa:xb] += (m[ya - y0:yb - y0, xa - x0:xb - x0] * f32(a))[..., None] * col


def blit_over(hdr, m, x, y, col, a=1.0):
    if a <= 0.003:
        return
    h, w = m.shape
    x0, y0 = int(round(x)), int(round(y))
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xb <= xa or yb <= ya:
        return
    mm = (m[ya - y0:yb - y0, xa - x0:xb - x0] * f32(a))[..., None]
    roi = hdr[ya:yb, xa:xb]
    roi *= 1 - mm
    roi += mm * col


def shadow(hdr, m, x, y, a=1.0, blur=10.0, dy=6.0, strength=0.75):
    """Ombre portée douce sous un masque (lisibilité sur fond chargé)."""
    if a <= 0.003:
        return
    pad = int(blur * 3) + 4
    mm = np.pad(m, pad)
    sh = cv2.GaussianBlur(mm, (0, 0), blur)
    h, w = sh.shape
    x0, y0 = int(round(x)) - pad, int(round(y + dy)) - pad
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if xb <= xa or yb <= ya:
        return
    s = np.clip(sh[ya - y0:yb - y0, xa - x0:xb - x0] * f32(strength * a), 0, 0.95)
    hdr[ya:yb, xa:xb] *= (1 - s)[..., None]


def text(hdr, txt, path, size, x, y, col, a=1.0, align=0, tracking=0.0, sh=True, glow=0.0):
    """Texte à la ligne de base y ; align 0 = centré, -1 = gauche, 1 = droite. Renvoie la largeur."""
    if a <= 0.003 or not txt:
        return 0.0
    m, w, asc, lh = text_patch(txt, path, size, tracking)
    x0 = x - w / 2 - 8 if align == 0 else (x - 8 if align < 0 else x - w - 8)
    if sh:
        shadow(hdr, m, x0, y - asc, a, blur=max(4.0, size * 0.10), dy=size * 0.06, strength=0.85)
    if glow > 0:
        g = cv2.GaussianBlur(m, (0, 0), max(2.0, size * 0.12))
        blit_add(hdr, g, x0, y - asc, col * f32(glow), a)
    blit_over(hdr, m, x0, y - asc, col, a)
    return w


# ------------------------------------------------------------------ formes
def rounded_rect(x0, y0, x1, y1, r, n=10):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = []
    for cx_, cy_, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx_ + r * math.cos(a), cy_ + r * math.sin(a)))
    return np.array(pts)


def fill_polys(polys, ss=4):
    pts = [np.asarray(p, float) for p in polys if len(p) >= 3]
    if not pts:
        return None, None
    allp = np.concatenate(pts)
    x0 = int(max(np.floor(allp[:, 0].min()) - 2, 0))
    x1 = int(min(np.ceil(allp[:, 0].max()) + 3, W))
    y0 = int(max(np.floor(allp[:, 1].min()) - 2, 0))
    y1 = int(min(np.ceil(allp[:, 1].max()) + 3, H))
    if x1 <= x0 or y1 <= y0:
        return None, None
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for p in pts:
        q = np.clip(np.round((p - [x0, y0]) * (1 << ss)), -1e8, 1e8).astype(np.int32)
        cv2.fillPoly(m, [q], 255, cv2.LINE_AA, ss)
    return m.astype(f32) / 255.0, (x0, y0, x1, y1)


def fill_over(hdr, polys, col, a=1.0):
    m, b = fill_polys(polys)
    if m is None or a <= 0:
        return
    x0, y0, x1, y1 = b
    mm = (m * f32(a))[..., None]
    roi = hdr[y0:y1, x0:x1]
    roi *= 1 - mm
    roi += mm * col


def fill_add(hdr, polys, col, a=1.0):
    m, b = fill_polys(polys)
    if m is None or a <= 0:
        return
    x0, y0, x1, y1 = b
    hdr[y0:y1, x0:x1] += (m * f32(a))[..., None] * col


def line_mask(segs, thick=1, ss=4, full=False):
    pts = [np.asarray(p, float) for p in segs if len(p) >= 2]
    if not pts:
        return None, None
    allp = np.concatenate(pts)
    allp = allp[np.isfinite(allp).all(1)]
    if len(allp) == 0:
        return None, None
    if full:
        x0, y0, x1, y1 = 0, 0, W, H
    else:
        x0 = int(max(np.floor(allp[:, 0].min()) - thick - 2, 0))
        x1 = int(min(np.ceil(allp[:, 0].max()) + thick + 3, W))
        y0 = int(max(np.floor(allp[:, 1].min()) - thick - 2, 0))
        y1 = int(min(np.ceil(allp[:, 1].max()) + thick + 3, H))
    if x1 <= x0 or y1 <= y0:
        return None, None
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for p in pts:
        q = np.clip(np.round((p - [x0, y0]) * (1 << ss)), -1e8, 1e8).astype(np.int32)
        cv2.polylines(m, [q], False, 255, max(int(thick), 1), cv2.LINE_AA, ss)
    return m.astype(f32) / 255.0, (x0, y0, x1, y1)


def draw_lines(hdr, segs, col, I=1.0, thick=1):
    m, b = line_mask(segs, thick)
    if m is None or I <= 0:
        return
    x0, y0, x1, y1 = b
    hdr[y0:y1, x0:x1] += (m * f32(I))[..., None] * col


def circle_pts(cx, cy, r, n=None, a0=0.0, a1=TAU):
    n = n or int(np.clip(r * 0.7, 24, 720))
    a = np.linspace(a0, a1, n)
    return np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], 1)


def add_glow(hdr, xs, ys, I, color, core=3.0, halo=30.0, ext=None):
    if I < 1e-3:
        return
    ext = max(ext or 0, halo * 8)
    x0, x1 = max(int(xs - ext), 0), min(int(xs + ext) + 1, W)
    y0, y1 = max(int(ys - ext), 0), min(int(ys + ext) + 1, H)
    if x1 <= x0 or y1 <= y0:
        return
    dx = XS[y0:y1, x0:x1] - f32(xs)
    dy = YS[y0:y1, x0:x1] - f32(ys)
    r2 = dx * dx + dy * dy
    wn = np.clip(1 - r2 / f32(ext * ext), 0, 1) ** 2
    v = (np.exp(-r2 / f32(2 * core * core)) + 0.2 * np.exp(-np.sqrt(r2) / f32(halo))) * wn
    hdr[y0:y1, x0:x1] += (f32(I) * v)[..., None] * color


def splat(P, xs, ys, I, cols):
    """Dépose des points lumineux (interpolation bilinéaire) dans un calque H x W x 3."""
    h, w = P.shape[:2]
    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        np.add.at(P, (yi[ok], xi[ok]), (I[ok] * wt[ok])[:, None] * cols[ok])


def tile_noise(n, sigmas, seed, aspect=1):
    r = np.random.default_rng(seed)
    acc = np.zeros((n * aspect, n), f32)
    amp, tot = 1.0, 0.0
    for sg in sigmas:
        z = r.standard_normal((n * aspect, n)).astype(f32)
        pd = min(int(3 * sg) + 1, n - 1)
        z = np.pad(z, pd, mode="wrap")
        z = cv2.GaussianBlur(z, (0, 0), sg)[pd:pd + n * aspect, pd:pd + n]
        z /= z.std() + 1e-6
        acc += amp * z
        tot += amp
        amp *= 0.55
    return (acc / tot).astype(f32)


# ------------------------------------------------------------------ post-traitement
def bloom(hdr):
    b = np.minimum(np.maximum(hdr - f32(0.85), 0), f32(14.0))
    levels = []
    cur = b
    for _ in range(6):
        cur = cv2.resize(cur, (max(cur.shape[1] // 2, 1), max(cur.shape[0] // 2, 1)), interpolation=cv2.INTER_AREA)
        cur = cv2.GaussianBlur(cur, (0, 0), 1.3)
        levels.append(cur)
    wts = (1.0, 0.85, 0.65, 0.45, 0.30, 0.20)
    acc = levels[-1] * f32(wts[-1])
    for lvl, wt in zip(reversed(levels[:-1]), reversed(wts[:-1])):
        acc = cv2.resize(acc, (lvl.shape[1], lvl.shape[0]), interpolation=cv2.INTER_LINEAR) + lvl * f32(wt)
    return cv2.resize(acc, (W, H), interpolation=cv2.INTER_LINEAR) / f32(sum(wts))


def finalize(hdr, fade, seed, grain=0.006, shake=(0.0, 0.0)):
    if shake[0] or shake[1]:
        M = np.array([[1, 0, shake[0]], [0, 1, shake[1]]], np.float64)
        hdr = cv2.warpAffine(hdr, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    hdr *= VIGNETTE[..., None] * f32(fade)
    hdr += bloom(hdr) * f32(0.7)
    out = aces(hdr * f32(0.95))
    lum = out[..., 0] * 0.2126 + out[..., 1] * 0.7152 + out[..., 2] * 0.0722
    out = np.clip(out, 0, 1) ** f32(1 / 2.2)
    if grain > 0:
        g = np.random.default_rng(5000 + seed).standard_normal((H // 2, W // 2)).astype(f32)
        g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)
        out += (g * f32(grain) * (0.6 + 0.8 * (1 - lum)))[..., None]
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)
