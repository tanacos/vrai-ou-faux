# -*- coding: utf-8 -*-
"""Bibliothèque de scènes de fond (« mondes ») pour la série. Chaque idée reçue reçoit une scène paramétrée depuis le
script JSON de l'épisode ; la scène dessine le monde en HDR (avant bloom et tonemapping) et ses étiquettes dans la
couche d'interface (auditées pour les zones sûres).

Types : pictogramme, globe, horizon, grille, echelle, frise, duel.
Fonds : nuit, espace, aurore, chaud, ocean, labo, nature."""
import math

import cv2
import numpy as np

from . import icons as IC
from . import ui as U
from .base import (C3, W, H, FPS, f32, TAU, XS, YS, sat, sstep, eout, smoother, splat, tile_noise, add_glow,
                   line_mask, circle_pts, F_DBOLD, F_DBLACK, F_MEDI, F_SEMI, text_width, wrap)
from .ui import T, PILL, PARA, ain, CYAN, CORAL, GREEN, WHITE, LIGHT, INK, DARK

CENTER = (540.0, 1060.0)


# ------------------------------------------------------------------ outils de composition
def add_patch(hdr, m, cx, cy, colv, I=1.0, scale=1.0, ang=0.0):
    """Ajoute (mode additif) le masque m centré en (cx, cy), avec échelle et rotation, teinte colv, intensité I."""
    if I <= 1e-4:
        return
    h, w = m.shape[:2]
    if abs(scale - 1.0) < 1e-3 and abs(ang) < 1e-3:
        x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
        xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
        if xb <= xa or yb <= ya:
            return
        sub = m[ya - y0:yb - y0, xa - x0:xb - x0]
    else:
        s = scale
        R = int(math.ceil(max(w, h) * s * 0.75)) + 2
        xa, ya, xb, yb = max(int(cx) - R, 0), max(int(cy) - R, 0), min(int(cx) + R, W), min(int(cy) + R, H)
        if xb <= xa or yb <= ya:
            return
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, s)
        M[0, 2] += cx - w / 2 - xa
        M[1, 2] += cy - h / 2 - ya
        sub = cv2.warpAffine(m, M, (xb - xa, yb - ya), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    if sub.ndim == 2:
        hdr[ya:yb, xa:xb] += (sub * f32(I))[..., None] * colv
    else:
        hdr[ya:yb, xa:xb] += sub * f32(I) * colv


def over_patch(hdr, m, cx, cy, colv, a=1.0, scale=1.0, ang=0.0):
    """Recouvre (mode normal) avec le masque m : sert à masquer ce qui est derrière un objet opaque."""
    if a <= 1e-4:
        return
    h, w = m.shape[:2]
    s = scale
    R = int(math.ceil(max(w, h) * s * 0.75)) + 2
    xa, ya, xb, yb = max(int(cx) - R, 0), max(int(cy) - R, 0), min(int(cx) + R, W), min(int(cy) + R, H)
    if xb <= xa or yb <= ya:
        return
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, s)
    M[0, 2] += cx - w / 2 - xa
    M[1, 2] += cy - h / 2 - ya
    sub = cv2.warpAffine(m, M, (xb - xa, yb - ya), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    mm = (sub * f32(a))[..., None]
    roi = hdr[ya:yb, xa:xb]
    roi *= 1 - mm
    roi += mm * colv


def lines_add(hdr, segs, colv, I, th=2, blur=0.0):
    m, b = line_mask(segs, th)
    if m is None or I <= 0:
        return
    x0, y0, x1, y1 = b
    hdr[y0:y1, x0:x1] += (m * f32(I))[..., None] * colv
    if blur > 0:
        pad = int(blur * 3)
        mm = np.pad(m, pad)
        g = cv2.GaussianBlur(mm, (0, 0), blur)
        xa, ya = max(x0 - pad, 0), max(y0 - pad, 0)
        xb, yb = min(x1 + pad, W), min(y1 + pad, H)
        hdr[ya:yb, xa:xb] += (g[ya - (y0 - pad):yb - (y0 - pad), xa - (x0 - pad):xb - (x0 - pad)] * f32(I * 0.9))[..., None] * colv


def ring(hdr, cx, cy, r, colv, I, th=2, blur=0.0, a0=0.0, a1=TAU, dash=None, rot=0.0):
    if dash:
        n = int(dash)
        segs = []
        for k in range(n):
            u0 = a0 + rot + (a1 - a0) * k / n
            u1 = u0 + (a1 - a0) / n * 0.55
            segs.append(circle_pts(cx, cy, r, 16, u0, u1))
        lines_add(hdr, segs, colv, I, th, blur)
    else:
        lines_add(hdr, [circle_pts(cx, cy, r, None, a0 + rot, a1 + rot)], colv, I, th, blur)


class Icon:
    """Pictogramme préparé : masque, contour et halo, à une taille donnée."""

    def __init__(self, name, size):
        self.name = name
        self.size = int(size)
        pad = int(size * 0.18)
        m = IC.mask(name, size)
        self.m = np.pad(m, pad)
        k = max(3, int(size * 0.016)) | 1
        er = cv2.erode(self.m, np.ones((k, k), np.uint8))
        self.rim = np.clip(self.m - er, 0, 1)
        self.glow = cv2.GaussianBlur(self.m, (0, 0), size * 0.045)
        self.glow2 = cv2.GaussianBlur(self.m, (0, 0), size * 0.12)
        hh = self.m.shape[0]
        gy = np.linspace(1.0, 0.0, hh, dtype=f32)[:, None]
        self.fill = self.m * (0.35 + 0.65 * gy)
        self.h = hh


def draw_icon(hdr, ic, cx, cy, colv, I=1.0, scale=1.0, ang=0.0, shimmer=None, fill=0.22, rim=1.7, glow=0.55):
    """Pictogramme « holographique » : remplissage dégradé, contour lumineux, halo, reflet balayant."""
    if I <= 1e-3:
        return
    add_patch(hdr, ic.glow2, cx, cy, colv, 0.22 * glow * I, scale, ang)
    add_patch(hdr, ic.glow, cx, cy, colv, 0.45 * glow * I, scale, ang)
    over_patch(hdr, ic.m, cx, cy, C3(0.010, 0.014, 0.030), 0.85 * min(I, 1.0), scale, ang)
    add_patch(hdr, ic.fill, cx, cy, colv, fill * I, scale, ang)
    add_patch(hdr, ic.rim, cx, cy, colv, rim * I, scale, ang)
    if shimmer is not None:
        hh = ic.h
        yb = (shimmer % 1.0) * hh * 1.6 - hh * 0.3
        band = np.exp(-((np.arange(hh, dtype=f32) - yb) / (hh * 0.05)) ** 2)[:, None] * ic.m
        add_patch(hdr, band, cx, cy, C3(0.8, 0.95, 1.0), 0.55 * I, scale, ang)


# ------------------------------------------------------------------ fonds
def _gradient(top, bot):
    yy = (np.arange(H, dtype=f32) / H)[:, None, None]
    return ((top * (1 - yy) + bot * yy) * np.ones((1, W, 1), f32)).astype(f32)


def _radial(cx, cy, r, colv):
    d2 = (XS - f32(cx)) ** 2 + (YS - f32(cy)) ** 2
    return (np.exp(-d2 / f32(2 * r * r))[..., None] * colv).astype(f32)


def _particles(n, seed, size=(2160, 1080), blur=2.2, inten=0.25, colv=C3(0.45, 0.70, 1.0)):
    r = np.random.default_rng(seed)
    P = np.zeros((size[0], size[1], 3), f32)
    splat(P, r.uniform(0, size[1], n), r.uniform(0, size[0], n), (r.uniform(0.3, 1.0, n) ** 2 * 6.0).astype(f32),
          np.broadcast_to(colv, (n, 3)).astype(f32))
    return (cv2.GaussianBlur(P, (0, 0), blur) * f32(inten)).astype(f32)


def _stars(n, seed):
    r = np.random.default_rng(seed)
    P = np.zeros((H, W, 3), f32)
    cols = np.where((r.random(n) < 0.3)[:, None], C3(1.0, 0.85, 0.7), C3(0.75, 0.82, 1.0)).astype(f32)
    splat(P, r.uniform(0, W, n), r.uniform(0, H, n), (r.uniform(0.2, 1.0, n) ** 3 * 4.0).astype(f32), cols)
    return cv2.GaussianBlur(P, (0, 0), 0.7).astype(f32)


def drift(layer, t, vx, vy):
    h, w = layer.shape[:2]
    M = np.array([[1, 0, -(t * vx) % w], [0, 1, -(t * vy) % h]], np.float64)
    return cv2.warpAffine(layer, M, (w, h), borderMode=cv2.BORDER_WRAP)[:H, :W]


_CACHE = {}


def cached(key, fn):
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


class Fond:
    KINDS = ("nuit", "espace", "aurore", "chaud", "ocean", "labo", "nature")

    def __init__(self, kind, accent, center=CENTER):
        self.kind = kind if kind in self.KINDS else "nuit"
        self.acc = accent
        cx, cy = center
        k = self.kind
        glow_col = accent * f32(0.12) if k not in ("chaud",) else C3(0.11, 0.045, 0.015)
        if k == "nuit":
            self.base = _gradient(C3(0.004, 0.005, 0.014), C3(0.010, 0.012, 0.030)) + _radial(cx, cy, 420, glow_col)
        elif k == "espace":
            self.base = _gradient(C3(0.002, 0.003, 0.008), C3(0.004, 0.005, 0.012)) + _radial(cx, cy, 460, glow_col * 0.6)
            neb = tile_noise(270, (40, 14, 5), 31, aspect=2)
            neb = cv2.resize(np.clip(neb, 0, None) ** 1.6, (W, H), interpolation=cv2.INTER_CUBIC)
            neb2 = cv2.resize(np.clip(tile_noise(270, (60, 20), 47, aspect=2), 0, None) ** 2, (W, H),
                              interpolation=cv2.INTER_CUBIC)
            self.base += neb[..., None] * C3(0.020, 0.010, 0.045) + neb2[..., None] * C3(0.004, 0.020, 0.040)
            self.base += cached("stars1", lambda: _stars(1600, 9)) * f32(0.9)
            self.tw = cached("stars2", lambda: _stars(500, 19))
        elif k == "aurore":
            self.base = _gradient(C3(0.003, 0.006, 0.012), C3(0.006, 0.014, 0.022)) + _radial(cx, cy, 420, glow_col * 0.7)
            self.base += cached("stars1", lambda: _stars(1600, 9)) * f32(0.45)
            r = np.random.default_rng(21)
            n = 4096
            z = cv2.GaussianBlur(r.standard_normal((1, n)).astype(f32), (0, 0), 2.5)[0]
            z2 = cv2.GaussianBlur(r.standard_normal((1, n)).astype(f32), (0, 0), 9.0)[0]
            self.streak = np.clip(0.55 + 0.9 * z / z.std() * 0.35 + 0.6 * z2 / z2.std() * 0.35, 0, None).astype(f32)
            self.Yh = (np.arange(H // 2, dtype=f32)[:, None] * np.ones((1, W // 2), f32))
            self.xh = np.arange(W // 2, dtype=f32)
        elif k == "chaud":
            self.base = _gradient(C3(0.012, 0.005, 0.004), C3(0.030, 0.010, 0.004)) + _radial(cx, cy + 120, 520, glow_col)
            r = np.random.default_rng(3)
            self.emb = (r.uniform(0, W, 170), r.uniform(0, H, 170), r.uniform(25, 70, 170), r.uniform(0, TAU, 170),
                        r.uniform(0.3, 1.0, 170))
        elif k == "ocean":
            self.base = _gradient(C3(0.004, 0.020, 0.040), C3(0.001, 0.006, 0.016)) + _radial(cx, cy, 460, glow_col * 0.7)
            ang = np.radians(12)
            u = (XS * math.cos(ang) + YS * math.sin(ang)) / 70.0
            rays = (0.5 + 0.5 * np.sin(u) * np.sin(u * 0.37 + 1.0)) ** 6
            fall = np.clip(1 - YS / 1500.0, 0, 1) ** 2
            self.rays = (rays * fall).astype(f32)
            r = np.random.default_rng(4)
            self.bub = (r.uniform(0, W, 90), r.uniform(0, H, 90), r.uniform(40, 120, 90), r.uniform(1.5, 4.5, 90))
        elif k == "labo":
            self.base = _gradient(C3(0.003, 0.010, 0.012), C3(0.006, 0.016, 0.020)) + _radial(cx, cy, 420, glow_col)
            m = np.zeros((H, W), np.uint8)
            s = 46.0
            for row in range(-1, int(H / (s * 1.5)) + 2):
                for c in range(-1, int(W / (s * math.sqrt(3))) + 2):
                    x0 = c * s * math.sqrt(3) + (row % 2) * s * math.sqrt(3) / 2
                    y0 = row * s * 1.5
                    pts = np.array([(x0 + s * math.cos(math.radians(60 * k_ + 30)),
                                     y0 + s * math.sin(math.radians(60 * k_ + 30))) for k_ in range(6)])
                    cv2.polylines(m, [np.round(pts * 16).astype(np.int32)], True, 255, 1, cv2.LINE_AA, 4)
            hexm = m.astype(f32) / 255.0
            fade = np.exp(-(((XS - cx) / 520) ** 2 + ((YS - cy) / 640) ** 2))
            self.base += (hexm * fade * 0.05)[..., None] * accent
        elif k == "nature":
            self.base = _gradient(C3(0.004, 0.010, 0.006), C3(0.008, 0.018, 0.010)) + _radial(cx, cy, 440, C3(0.020, 0.060, 0.030))
            r = np.random.default_rng(6)
            self.ff = (r.uniform(140, 940, 26), r.uniform(700, 1500, 26), r.uniform(0, TAU, 26), r.uniform(0.3, 0.9, 26))
        self.dust_far = cached("dust_far", lambda: _particles(700, 5, blur=1.2, inten=0.18))
        self.dust_near = cached("dust_near", lambda: _particles(260, 4, blur=3.0, inten=0.30))

    def render(self, t):
        k = self.kind
        hdr = self.base.copy()
        if k in ("nuit", "labo"):
            hdr += drift(self.dust_far, t, 6, -9)
            hdr += drift(self.dust_near, t, -10, -16)
        elif k == "espace":
            hdr += self.tw * f32(0.55 + 0.45 * math.sin(t * 1.7))
            hdr += drift(self.dust_far, t, 3, -4) * f32(0.4)
        elif k == "aurore":
            xh = self.xh
            yb = (640 + 34 * np.sin(xh * 0.012 + t * 0.22) + 20 * np.sin(xh * 0.031 - t * 0.37)
                  + 12 * np.sin(xh * 0.071 + t * 0.6)).astype(f32)
            off = int(t * 9) % 2048
            st = self.streak[off:off + W // 2] * (0.75 + 0.25 * np.sin(xh * 0.05 + t * 1.3))
            d = yb[None, :] - self.Yh
            I = np.where(d > 0, np.exp(-np.clip(d, 0, None) / 150.0), np.exp(np.clip(d, None, 0) / 7.0)) * st[None, :]
            u = np.clip(d / 260.0, 0, 1)
            A = np.stack([I * (0.10 + 0.40 * u), I * (0.85 - 0.60 * u), I * (0.45 + 0.20 * u)], -1).astype(f32)
            hdr += cv2.resize(A, (W, H), interpolation=cv2.INTER_LINEAR) * f32(0.20)
            hdr += drift(self.dust_far, t, 4, -6) * f32(0.6)
        elif k == "chaud":
            x, y, v, ph, I = self.emb
            yy = (y - v * t) % H
            xx = x + 18 * np.sin(t * 1.3 + ph)
            P = np.zeros((H // 2, W // 2, 3), f32)
            splat(P, xx / 2, yy / 2, (I * 2.2).astype(f32), np.broadcast_to(C3(1.0, 0.45, 0.12), (len(x), 3)).astype(f32))
            P = cv2.GaussianBlur(P, (0, 0), 1.2)
            hdr += cv2.resize(P, (W, H), interpolation=cv2.INTER_LINEAR)
            hdr += drift(self.dust_far, t, 4, -14) * f32(0.35) * C3(1.0, 0.6, 0.4)
        elif k == "ocean":
            hdr += (self.rays * f32(0.05 + 0.02 * math.sin(t * 0.8)))[..., None] * C3(0.30, 0.65, 0.85)
            x, y, v, rad = self.bub
            yy = (y - v * t) % H
            xx = x + 10 * np.sin(t * 2.0 + y)
            P = np.zeros((H // 2, W // 2, 3), f32)
            splat(P, xx / 2, yy / 2, (rad * 0.5).astype(f32), np.broadcast_to(C3(0.5, 0.8, 1.0), (len(x), 3)).astype(f32))
            hdr += cv2.resize(cv2.GaussianBlur(P, (0, 0), 1.0), (W, H)) * f32(0.6)
        elif k == "nature":
            hdr += drift(self.dust_far, t, 3, -5) * C3(0.8, 1.0, 0.6) * f32(0.6)
            x, y, ph, I = self.ff
            for k_ in range(len(x)):
                fl = 0.5 + 0.5 * math.sin(t * 2.3 + ph[k_] * 3)
                add_glow(hdr, float(x[k_] + 30 * math.sin(t * 0.4 + ph[k_])), float(y[k_] + 20 * math.sin(t * 0.6 + ph[k_])),
                         0.8 * I[k_] * fl, C3(0.75, 1.0, 0.45), core=2.0, halo=6.0, ext=40)
        if k == "labo":
            yb = (t * 140) % (H + 400) - 200
            band = np.exp(-((np.arange(H, dtype=f32) - yb) / 40.0) ** 2)
            hdr += (band * 0.02)[:, None, None] * self.acc
        return hdr


# ------------------------------------------------------------------ scènes
class Scene:
    kind = "base"

    def __init__(self, spec, ctx):
        self.s = spec
        self.ctx = ctx
        self.g = ctx["g"]
        self.verdict = ctx["verdict"]
        self.acc = U.col(spec.get("couleur"), CYAN)
        self.vcol = U.VCOL[self.verdict]
        self.center = CENTER
        self.fond = Fond(spec.get("fond", ctx.get("fond", "nuit")), self.acc, self.center)
        self.errors = []
        self.events = []
        self.setup()

    def setup(self):
        pass

    # phase helpers
    def reveal_pulse(self, t):
        u = t - self.g["reveal"]
        return math.exp(-u / 0.35) if 0 <= u < 3 else 0.0

    def tint(self, t, neutral):
        """Couleur de l'objet principal : accent, virant vers la couleur du verdict au moment de la révélation."""
        if neutral:
            return self.acc
        u = t - self.g["reveal"]
        if u < 0:
            return self.acc
        k = math.exp(-max(u - 0.25, 0) / 1.2) * min(u / 0.12, 1.0)
        return self.acc * f32(1 - k) + self.vcol * f32(k)

    def shockwave(self, hdr, t, cx, cy, r0=120, r1=620):
        u = t - self.g["reveal"]
        if 0 <= u < 0.9:
            r = r0 + (r1 - r0) * eout(u / 0.9, 2)
            ring(hdr, cx, cy, r, self.vcol, 1.4 * (1 - u / 0.9) ** 1.5, th=4, blur=6)

    def label_alpha(self, t, neutral):
        if neutral:
            return 0.0
        a = ain(t, self.g["body"] + 0.2) * (1 - sstep(self.g["end"] - 0.3, self.g["end"] - 0.05, t))
        return a * (1 - self.ctx["visual_busy"](t))

    def world(self, t, neutral=False):
        return self.fond.render(t)

    def ui(self, img, t, cam, neutral=False):
        pass


class Pictogramme(Scene):
    """{"type": "pictogramme", "icone": "globe", "satellites": ["moon"], "marque": "barre|coche|aucune",
    "taille": 430, "couleur": "cyan", "fond": "nuit"}"""
    kind = "pictogramme"

    def setup(self):
        s = self.s
        name = s.get("icone", "question")
        if not IC.exists(name):
            self.errors.append(f"pictogramme inconnu : {name!r}")
            name = "question"
        self.size = int(np.clip(s.get("taille", 430), 260, 520))
        self.ic = Icon(name, self.size)
        self.sats = []
        for k, n in enumerate((s.get("satellites") or [])[:4]):
            if not IC.exists(n):
                self.errors.append(f"pictogramme inconnu : {n!r}")
                continue
            self.sats.append((Icon(n, int(self.size * 0.24)), k))
        self.marque = s.get("marque", "aucune")
        r = np.random.default_rng(11)
        n = 220
        self.pa = r.uniform(0, TAU, n)
        self.pr = r.normal(1.0, 0.06, n)
        self.pI = r.uniform(0.2, 1.0, n) ** 2
        if self.marque in ("barre", "coche") and not self.ctx.get("neutral_only"):
            self.events.append((self.g["reveal"] + 0.18, "barre" if self.marque == "barre" else "ding", {}))

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        cx, cy = self.center
        S = self.size
        col = self.tint(t, neutral)
        bob = 10 * math.sin(t * 1.1)
        ang = 2.0 * math.sin(t * 0.7)
        # anneaux « tête haute » derrière l'objet
        ring(hdr, cx, cy, S * 0.66, self.acc, 0.10, th=2, dash=48, rot=t * 0.15)
        ring(hdr, cx, cy, S * 0.80, self.acc, 0.07, th=2, dash=90, rot=-t * 0.08)
        ring(hdr, cx, cy, S * 0.92, self.acc, 0.05, th=1)
        # poussière en orbite (ellipse inclinée)
        a = self.pa + t * 0.25
        ex, ey = S * 0.78 * self.pr, S * 0.26 * self.pr
        rot = math.radians(-14)
        px = cx + ex * np.cos(a) * math.cos(rot) - ey * np.sin(a) * math.sin(rot)
        py = cy + ex * np.cos(a) * math.sin(rot) + ey * np.sin(a) * math.cos(rot)
        front = np.sin(a) > 0
        P = np.zeros((H // 2, W // 2, 3), f32)
        cols = np.broadcast_to(self.acc, (len(a), 3)).astype(f32)
        splat(P, px[~front] / 2, py[~front] / 2, (self.pI[~front] * 1.2).astype(f32), cols[~front])
        hdr += cv2.resize(cv2.GaussianBlur(P, (0, 0), 0.8), (W, H)) * f32(0.8)
        # satellites derrière
        sat_pos = []
        for ic, k in self.sats:
            ph = t * 0.45 + k * TAU / max(len(self.sats), 1)
            sx = cx + S * 0.82 * math.cos(ph)
            sy = cy + bob * 0.5 + S * 0.30 * math.sin(ph) - S * 0.10 * math.cos(ph)
            depth = math.sin(ph)
            sat_pos.append((ic, sx, sy, depth))
            if depth < 0:
                draw_icon(hdr, ic, sx, sy, self.acc, 0.55 + 0.25 * depth, 0.9 + 0.1 * depth)
        # objet principal
        shim = (t - self.g["claim"]) / 2.6
        draw_icon(hdr, self.ic, cx, cy + bob, col, 1.0 + 0.6 * self.reveal_pulse(t) * (not neutral), 1.0, ang,
                  shimmer=shim)
        # poussière devant
        P[:] = 0
        splat(P, px[front] / 2, py[front] / 2, (self.pI[front] * 1.6).astype(f32), cols[front])
        hdr += cv2.resize(cv2.GaussianBlur(P, (0, 0), 0.8), (W, H)) * f32(0.9)
        for ic, sx, sy, depth in sat_pos:
            if depth >= 0:
                draw_icon(hdr, ic, sx, sy, self.acc, 0.75 + 0.25 * depth, 0.9 + 0.12 * depth)
        if not neutral:
            self.shockwave(hdr, t, cx, cy + bob, S * 0.35, S * 1.25)
            self._marque(hdr, t, cx, cy + bob)
        return hdr

    def _marque(self, hdr, t, cx, cy):
        u = t - self.g["reveal"] - 0.18
        if u < 0 or t >= self.g["end"]:
            return
        S = self.size
        fade = 1 - sstep(self.g["end"] - 0.35, self.g["end"] - 0.05, t)
        if self.marque == "barre":
            L = S * 0.62
            p0 = np.array([cx - L * 0.72, cy - L * 0.72])
            p1 = np.array([cx + L * 0.72, cy + L * 0.72])
            k = eout(min(u / 0.22, 1.0), 2)
            pe = p0 + (p1 - p0) * k
            m, b = line_mask([np.array([p0, pe])], int(S * 0.085) + 14)
            if m is not None:
                x0, y0, x1, y1 = b
                hdr[y0:y1, x0:x1] *= (1 - m * 0.92 * fade)[..., None]
            lines_add(hdr, [np.array([p0, pe])], CORAL, 1.6 * fade, th=int(S * 0.085), blur=10)
            ring(hdr, cx, cy, L * 1.04, CORAL, 1.3 * fade * k, th=int(S * 0.05), blur=10)
        elif self.marque == "coche":
            k = eout(min(u / 0.3, 1.0), 2)
            bx, by = cx + S * 0.36, cy - S * 0.34
            R = S * 0.15 * (0.6 + 0.4 * k)
            P = np.zeros((int(R * 2 + 8), int(R * 2 + 8)), np.uint8)
            cv2.circle(P, (P.shape[1] // 2, P.shape[0] // 2), int(R), 255, -1, cv2.LINE_AA)
            add_patch(hdr, P.astype(f32) / 255.0, bx, by, GREEN, 1.4 * fade * k)
            pts = np.array([(bx - R * 0.45, by + R * 0.02), (bx - R * 0.12, by + R * 0.34), (bx + R * 0.48, by - R * 0.32)])
            m, b = line_mask([pts], max(int(R * 0.22), 2))
            if m is not None:
                x0, y0, x1, y1 = b
                hdr[y0:y1, x0:x1] = hdr[y0:y1, x0:x1] * (1 - m[..., None] * fade) + (m * fade)[..., None] * C3(0.01, 0.05, 0.02)


class Globe(Scene):
    """{"type": "globe", "marqueurs": [{"lat": 40.4, "lon": 116.6, "libelle": "Pékin"}],
    "orbite": {"altitude_km": 400, "inclinaison": 51.6, "libelle": "ISS · 400 km"}, "visee": true,
    "rayon": 300, "couleur": "cyan", "fond": "espace"}
    Globe « de données » : sphère de points, méridiens et parallèles discrets, atmosphère, repères, orbite."""
    kind = "globe"

    def setup(self):
        s = self.s
        self.center = (540.0, 1105.0)
        self.fond = Fond(s.get("fond", self.ctx.get("fond", "espace")), self.acc, self.center)
        self.R = float(np.clip(s.get("rayon", 300), 200, 340))
        self.marks = []
        for mk in (s.get("marqueurs") or [])[:3]:
            try:
                self.marks.append((float(mk["lat"]), float(mk["lon"]), U.fr(mk.get("libelle", ""))))
            except (KeyError, TypeError, ValueError):
                self.errors.append(f"marqueur invalide : {mk!r}")
        self.orb = s.get("orbite")
        self.visee = bool(s.get("visee", False)) and self.orb is not None and bool(self.marks)
        self.lat0 = math.radians(float(s.get("inclinaison_vue", 20)))
        self.lon_c = self.marks[0][1] if self.marks else 10.0
        self.lat_c = self.marks[0][0] if self.marks else 0.0
        self.speed = float(s.get("rotation", 1.6))
        cx, cy = self.center
        R = self.R
        d = np.sqrt((XS - cx) ** 2 + (YS - cy) ** 2) / R
        self.disk = np.clip((1 - d) * R / 1.5, 0, 1).astype(f32)
        shade = np.clip(1 - d, 0, 1) ** 0.6
        self.body = ((self.disk * (0.006 + 0.018 * shade))[..., None] * C3(0.25, 0.55, 1.0)).astype(f32)
        atmo = np.exp(-((d - 1.0) / 0.016) ** 2) * 0.60 + np.exp(-np.clip(d - 1.0, 0, None) / 0.06) * (d > 1) * 0.32
        inner = np.clip((d - 0.72) / 0.28, 0, 1) ** 3 * self.disk * 0.12
        self.atmo = (atmo + inner).astype(f32)
        # sphère de points (spirale de Fibonacci)
        n = 1700
        k = np.arange(n) + 0.5
        y = 1 - 2 * k / n
        r = np.sqrt(1 - y * y)
        ph = k * math.pi * (3 - math.sqrt(5))
        self.pts = np.stack([r * np.sin(ph), y, r * np.cos(ph)], 1).astype(f32)
        if self.orb:
            alt = float(self.orb.get("altitude_km", 400))
            self.r_orb = R * max(1 + alt / 6371.0, 1.075)
            self.incl = math.radians(float(self.orb.get("inclinaison", 51.6)))
            self.events.append((self.g["body"] + 0.4, "glisse", {"niveau": 0.5}))

    # rotation de la vue : le premier repère passe lentement devant la caméra
    def rot(self, t):
        return math.radians(self.lon_c + 26 - self.speed * (t - self.g["claim"]))

    def _view(self, P, t):
        """Vecteurs 3D (repère Terre) -> (x, y, z) écran, z > 0 : face visible."""
        a = -self.rot(t)
        ca, sa = math.cos(a), math.sin(a)
        x = P[..., 0] * ca + P[..., 2] * sa
        z = -P[..., 0] * sa + P[..., 2] * ca
        y = P[..., 1]
        c, s = math.cos(self.lat0), math.sin(self.lat0)
        y2 = y * c - z * s
        z2 = y * s + z * c
        cx, cy = self.center
        return cx + self.R * x, cy - self.R * y2, z2

    def proj(self, lat, lon, t):
        la, lo = math.radians(lat), math.radians(lon)
        P = np.array([math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo)])
        x, y, z = self._view(P, t)
        return float(x), float(y), float(z)

    def grat(self, t):
        front, back = [], []

        def poly(lats, lons):
            la, lo = np.radians(lats), np.radians(lons)
            P = np.stack([np.cos(la) * np.sin(lo), np.sin(la), np.cos(la) * np.cos(lo)], 1)
            x, y, z = self._view(P, t)
            Q = np.stack([x, y], 1)
            vis = z > 0
            k = 0
            while k < len(Q):
                v = vis[k]
                j = k
                while j < len(Q) and vis[j] == v:
                    j += 1
                seg = Q[max(k - 1, 0):j]
                if len(seg) >= 2:
                    (front if v else back).append(seg)
                k = j

        for lon in range(-180, 180, 30):
            poly(np.linspace(-90, 90, 61), np.full(61, lon, float))
        for lat in (-60, -30, 0, 30, 60):
            poly(np.full(121, lat, float), np.linspace(-180, 180, 121))
        return front, back

    def orbit(self, t):
        """Orbite circulaire inclinée autour de l'axe de la Terre ; renvoie points écran, profondeur, phase satellite."""
        a = np.linspace(0, TAU, 361)
        ci, si = math.cos(self.incl), math.sin(self.incl)
        rr = self.r_orb / self.R
        P = np.stack([rr * np.cos(a), rr * np.sin(a) * si, rr * np.sin(a) * ci], 1)
        ph0 = (t - self.g["claim"]) * 0.30 + 1.0
        # l'orbite tourne avec la Terre fixe : on applique seulement l'inclinaison de la vue
        c, s = math.cos(self.lat0), math.sin(self.lat0)
        cx, cy = self.center
        x = cx + self.R * P[:, 0]
        y2 = P[:, 1] * c - P[:, 2] * s
        z2 = P[:, 1] * s + P[:, 2] * c
        Q = np.stack([x, cy - self.R * y2], 1)
        sp = np.array([rr * math.cos(ph0), rr * math.sin(ph0) * si, rr * math.sin(ph0) * ci])
        sx = cx + self.R * sp[0]
        sy = cy - self.R * (sp[1] * c - sp[2] * s)
        sz = sp[1] * s + sp[2] * c
        return Q, z2, a, (sx, sy, sz, ph0 % TAU)

    def sat_visible(self, sx, sy, sz):
        cx, cy = self.center
        return sz > 0 or math.hypot(sx - cx, sy - cy) > self.R * 1.01

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        cx, cy = self.center
        col = self.tint(t, neutral)
        hdr *= (1 - self.disk * 0.9)[..., None]
        hdr += self.body
        # points de la sphère
        x, y, z = self._view(self.pts, t)
        Ih = np.where(z > 0, 0.25 + 0.75 * z, 0.10).astype(f32)
        P = np.zeros((H // 2, W // 2, 3), f32)
        splat(P, x / 2, y / 2, Ih * 1.1, np.broadcast_to(col, (len(x), 3)).astype(f32))
        hdr += cv2.resize(cv2.GaussianBlur(P, (0, 0), 0.6), (W, H), interpolation=cv2.INTER_LINEAR)
        front, back = self.grat(t)
        lines_add(hdr, back, self.acc, 0.05, th=1)
        lines_add(hdr, front, col, 0.20, th=2, blur=2)
        hdr += self.atmo[..., None] * col * f32(0.9)
        if self.orb is not None:
            Q, z2, a, (sx, sy, sz, ph) = self.orbit(t)
            d_c = np.hypot(Q[:, 0] - cx, Q[:, 1] - cy)
            vis = (z2 > 0) | (d_c > self.R * 1.01)
            for v, I in ((False, 0.06), (True, 0.30)):
                segs, k = [], 0
                while k < len(Q):
                    j = k
                    while j < len(Q) and vis[j] == vis[k]:
                        j += 1
                    if vis[k] == v and j - k >= 2:
                        segs.append(Q[k:j])
                    k = j
                lines_add(hdr, segs, WHITE, I, th=2, blur=3 if v else 0)
            # traînée lumineuse derrière le satellite
            tr = (ph - a) % TAU
            on = (tr < 0.9) & vis
            if on.any():
                idx = np.nonzero(on)[0]
                for i0 in idx:
                    if i0 + 1 < len(Q) and on[i0 + 1]:
                        lines_add(hdr, [Q[i0:i0 + 2]], C3(1.0, 0.95, 0.85), 1.2 * (1 - tr[i0] / 0.9) ** 2, th=3)
            if self.sat_visible(sx, sy, sz):
                add_glow(hdr, sx, sy, 3.2, C3(1.0, 0.95, 0.85), core=4, halo=10, ext=90)
        for lat, lon, lab in self.marks:
            x, y, z = self.proj(lat, lon, t)
            if z > 0.05:
                k = min(z * 3, 1)
                mc = CORAL if not neutral else self.acc
                add_glow(hdr, x, y, 2.8 * k, mc, core=5, halo=12, ext=100)
                for off in (0.0, 0.5):
                    ph = (((t - self.g["claim"]) / 1.8) + off) % 1.0
                    ring(hdr, x, y, 10 + 60 * ph, mc, 1.0 * (1 - ph) ** 1.5 * k, th=3)
                nx, ny = (x - cx) / self.R, (y - cy) / self.R
                L = 70 * k
                lines_add(hdr, [np.array([(x, y), (x + nx * L, y + ny * L - 40 * k)])], mc, 0.7 * k, th=3, blur=4)
        if self.visee and not neutral and t >= self.g["body"]:
            Q, z2, a, (sx, sy, sz, ph) = self.orbit(t)
            x, y, z = self.proj(self.marks[0][0], self.marks[0][1], t)
            if z > 0.05 and self.sat_visible(sx, sy, sz):
                n = max(int(math.hypot(x - sx, y - sy) / 16), 2)
                segs = [np.array([(sx + (x - sx) * k / n, sy + (y - sy) * k / n),
                                  (sx + (x - sx) * (k + 0.5) / n, sy + (y - sy) * (k + 0.5) / n)]) for k in range(n)]
                lines_add(hdr, segs, WHITE, 0.55 * ain(t, self.g["body"] + 0.4), th=2)
        if not neutral:
            self.shockwave(hdr, t, cx, cy, self.R * 0.9, self.R * 1.75)
        return hdr

    def ui(self, img, t, cam, neutral=False):
        a = self.label_alpha(t, neutral)
        if a <= 0:
            return
        cx, cy = self.center
        for lat, lon, lab in self.marks[:1]:
            if not lab:
                continue
            x, y, z = self.proj(lat, lon, t)
            if z > 0.1:
                qx, qy = cam((x, y))
                qy = min(max(qy + 78, 900), 1190)
                w = U.pill_w(lab, 30, 16, 1.0, F_DBOLD)
                PILL(img, lab, U.safe_cx(qx, w, qy + 14), qy, C3(0.05, 0.06, 0.09), CORAL, a * min(z * 3, 1), size=30,
                     pad=16, tracking=1.0, path=F_DBOLD)
        if self.orb is not None and self.orb.get("libelle"):
            lab = U.fr(self.orb["libelle"])
            PILL(img, lab, 540, 1236, C3(0.05, 0.06, 0.09), WHITE, a, size=30, pad=16, tracking=1.0, path=F_DBOLD)


class Horizon(Scene):
    """Bord de la Terre vu d'orbite. {"type": "horizon", "objet": "md:satellite-alt", "libelle": "400 km",
    "couleur": "cyan"}"""
    kind = "horizon"

    def setup(self):
        s = self.s
        self.fond = Fond("espace", self.acc, self.center)
        self.Rb = 1500.0
        self.apex = float(s.get("horizon_y", 1140))
        cy_e = self.apex + self.Rb
        self.ce = (540.0, cy_e)
        d = np.sqrt((XS - 540.0) ** 2 + (YS - cy_e) ** 2)
        self.inside = np.clip((self.Rb - d) / 1.5, 0, 1).astype(f32)
        nx = (XS - 540.0) / self.Rb
        ny = (YS - cy_e) / self.Rb
        nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
        self.u = (np.arctan2(nx, nz) / math.pi * 1400).astype(f32)
        self.v = (np.arcsin(np.clip(ny, -1, 1)) / math.pi * 1400).astype(f32)
        cl = tile_noise(512, (5, 2.2, 0.9), 77)
        cl = cv2.resize(cl, (1024, 512), interpolation=cv2.INTER_CUBIC)
        cl = np.clip((cl - 0.05) * 1.1, 0, 1) ** 1.6
        self.clouds = cl.astype(f32)
        self.cfade = (np.exp(-np.clip(YS - self.apex, 0, None) / 520.0)).astype(f32)
        edge = np.clip((self.Rb - d) / 260.0, 0, 1)
        self.limb = (np.exp(-((d - self.Rb) / 7.0) ** 2) * 1.3 +
                     np.exp(-np.clip(d - self.Rb, 0, None) / 45.0) * (d > self.Rb) * 0.40).astype(f32)
        sunx = 200.0
        self.sun = sunx
        light = np.clip(0.35 + 0.95 * (-(XS - 540.0) / 900.0), 0.04, 1.3)
        self.light = (light * (0.55 + 0.45 * edge)).astype(f32)
        self.ocean = ((self.inside * (0.006 + 0.020 * edge) * self.light)[..., None] * C3(0.10, 0.35, 0.85)).astype(f32)
        sy = cy_e - math.sqrt(self.Rb ** 2 - (sunx - 540) ** 2)
        g = np.exp(-(((XS - sunx) / 160.0) ** 2 + ((YS - sy - 60) / 70.0) ** 2)) * self.inside
        self.glint = (g * 0.35).astype(f32)
        self.sun_y = sy
        warm = np.exp(-((XS - sunx) / 260.0) ** 2) * np.exp(-((d - self.Rb) / 18.0) ** 2)
        self.warm = (warm * 0.9).astype(f32)
        self.obj = None
        name = s.get("objet")
        if name:
            if IC.exists(name):
                self.obj = Icon(name, 200)
            else:
                self.errors.append(f"pictogramme inconnu : {name!r}")

    def obj_pos(self, t):
        u = (t - self.g["claim"]) / max(self.g["end"] - self.g["claim"], 1)
        return 330 + 420 * u, 905 + 12 * math.sin(t * 0.9)

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        hdr *= (1 - self.inside)[..., None]
        hdr += self.ocean
        sh = (t * 7.0) % 1024
        mx = (self.u + sh) % 1024
        my = (self.v + 700) % 512
        cl = cv2.remap(self.clouds, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_WRAP)
        hdr += (cl * self.inside * self.light * self.cfade * 0.20)[..., None] * C3(0.85, 0.92, 1.0)
        hdr += self.glint[..., None] * C3(1.0, 0.9, 0.75)
        col = self.tint(t, neutral)
        hdr += self.limb[..., None] * (C3(0.30, 0.60, 1.0) * f32(0.75) + col * f32(0.25))
        hdr += self.warm[..., None] * C3(1.0, 0.55, 0.25)
        add_glow(hdr, self.sun, self.sun_y - 3, 7.0, C3(1.0, 0.88, 0.70), core=6, halo=40, ext=420)
        lines_add(hdr, [np.array([(self.sun - 300, self.sun_y - 3), (self.sun + 300, self.sun_y - 3)])],
                  C3(1.0, 0.85, 0.7), 0.30, th=2, blur=6)
        if self.obj is not None:
            ox, oy = self.obj_pos(t)
            draw_icon(hdr, self.obj, ox, oy, col, 1.0, 1.0, -10)
            if not neutral and t >= self.g["body"]:
                yb = self.apex + (ox - 540) ** 2 / (2 * self.Rb)
                al = ain(t, self.g["body"] + 0.3)
                segs = []
                y = oy + 100
                while y < yb - 8:
                    segs.append(np.array([(ox, y), (ox, min(y + 12, yb - 8))]))
                    y += 22
                lines_add(hdr, segs, WHITE, 0.6 * al, th=2)
        if not neutral:
            self.shockwave(hdr, t, 540, 960, 100, 700)
        return hdr

    def ui(self, img, t, cam, neutral=False):
        a = self.label_alpha(t, neutral)
        lab = self.s.get("libelle")
        if a <= 0 or not lab or self.obj is None:
            return
        ox, oy = self.obj_pos(t)
        yb = self.apex + (ox - 540) ** 2 / (2 * self.Rb)
        qx, qy = cam((ox, (oy + 100 + yb) / 2))
        lab = U.fr(lab)
        w = U.pill_w(lab, 30, 16, 1.0, F_DBOLD)
        qy = min(qy, 1180)
        cxl = qx + 30 + w / 2 if qx + 30 + w <= 770 else qx - 30 - w / 2
        PILL(img, lab, U.safe_cx(cxl, w, qy + 14), qy, C3(0.05, 0.06, 0.09), WHITE, a, size=30,
             pad=16, tracking=1.0, path=F_DBOLD)


class Grille(Scene):
    """{"type": "grille", "icone": "person", "total": 100, "surlignes": 10, "colonnes": 10,
    "couleur": "cyan", "couleur_surligne": "corail", "libelle": "1 sur 10"}"""
    kind = "grille"

    def setup(self):
        s = self.s
        name = s.get("icone", "person")
        if not IC.exists(name):
            self.errors.append(f"pictogramme inconnu : {name!r}")
            name = "circle"
        self.n = int(np.clip(s.get("total", 100), 4, 200))
        self.k = int(np.clip(s.get("surlignes", 10), 0, self.n))
        cols = int(s.get("colonnes", 10 if self.n >= 50 else int(math.ceil(math.sqrt(self.n)))))
        rows = int(math.ceil(self.n / cols))
        x0, x1, y0, y1 = 170.0, 910.0, 860.0, 1205.0
        cell = min((x1 - x0) / cols, (y1 - y0) / rows)
        self.icsz = int(cell * 0.82)
        self.ic = Icon(name, self.icsz)
        gx0 = 540 - cell * cols / 2 + cell / 2
        gy0 = (y0 + y1) / 2 - cell * rows / 2 + cell / 2
        self.pos = [(gx0 + cell * (i % cols), gy0 + cell * (i // cols)) for i in range(self.n)]
        rr = np.random.default_rng(5)
        order = list(range(self.n))
        if s.get("ordre") == "hasard":
            rr.shuffle(order)
        self.hl = set(order[:self.k])
        self.hl_order = order[:self.k]
        self.hcol = U.col(s.get("couleur_surligne"), CORAL)
        self.t_hl = self.g["body"] + 0.3
        self.d_hl = min(1.6, 0.12 * self.k + 0.2)
        if self.k <= 24:
            for j in range(self.k):
                self.events.append((self.t_hl + self.d_hl * j / max(self.k, 1), "pop", {"f": 500 + 18 * j, "g": 0.6}))
        else:
            self.events.append((self.t_hl, "glisse", {"niveau": 0.8}))

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        app = 1.0 if neutral else ain(t, self.g["claim"] - 0.2, 0.8)
        for i, (x, y) in enumerate(self.pos):
            on = 0.0
            if not neutral and i in self.hl:
                j = self.hl_order.index(i)
                on = sstep(0, 0.15, t - (self.t_hl + self.d_hl * j / max(self.k, 1)))
                on *= 1 - sstep(self.g["end"] - 0.35, self.g["end"] - 0.05, t)
            c = self.acc * f32(1 - on) + self.hcol * f32(on)
            draw_icon(hdr, self.ic, x, y + 3 * math.sin(t * 1.3 + i * 0.37), c, (0.45 + 0.75 * on) * app, 1.0 + 0.08 * on,
                      fill=0.18, rim=1.2, glow=0.35)
        return hdr

    def ui(self, img, t, cam, neutral=False):
        a = self.label_alpha(t, neutral)
        lab = self.s.get("libelle")
        if a > 0 and lab:
            PILL(img, U.fr(lab), 540, 1240, C3(0.05, 0.06, 0.09), self.hcol, a, size=32, pad=18, tracking=1.0,
                 path=F_DBOLD)


class Echelle(Scene):
    """Comparaison de tailles : {"type": "echelle", "elements": [{"icone", "valeur", "libelle", "affichage"}, ...]}."""
    kind = "echelle"

    def setup(self):
        s = self.s
        els = (s.get("elements") or [])[:3]
        if len(els) < 2:
            self.errors.append("echelle : 2 ou 3 éléments attendus")
        vmax = max([float(e.get("valeur", 1)) for e in els] + [1e-9])
        n = max(len(els), 1)
        self.base_y = 1185.0
        self.hmax = 290.0
        xs = {1: [540], 2: [340, 690], 3: [260, 480, 700]}[min(n, 3)]
        self.els = []
        for e, x in zip(els, xs):
            name = e.get("icone", "circle")
            if not IC.exists(name):
                self.errors.append(f"pictogramme inconnu : {name!r}")
                name = "circle"
            v = float(e.get("valeur", 1))
            h = max(self.hmax * v / vmax, 26.0)
            isz = int(max(h, self.hmax * 0.62))
            ic = Icon(name, isz)
            self.els.append(dict(x=x, h=h, ic=ic, isz=isz, lab=U.fr(e.get("libelle", "")),
                                 aff=U.fr(str(e.get("affichage", ""))), small=(self.hmax * v / vmax) < 26.0))
        self.t_grow = self.g["body"] + 0.2
        for k in range(len(self.els)):
            self.events.append((self.t_grow + 0.5 * k, "glisse", {"niveau": self.els[k]["h"] / self.hmax}))

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        lines_add(hdr, [np.array([(150, self.base_y), (930, self.base_y)])], self.acc, 0.35, th=2, blur=3)
        h_eq = self.hmax * 0.62          # avant l'explication : tous à la même taille (on ne dévoile rien)
        for k, e in enumerate(self.els):
            u = 1.0 if neutral else eout(sat((t - self.t_grow - 0.5 * k) / 0.7), 3)
            hh = h_eq + (e["h"] - h_eq) * u
            sc = max(hh / e["isz"], 0.05)
            draw_icon(hdr, e["ic"], e["x"], self.base_y - hh / 2 - 4, self.acc, 1.0, sc)
            if neutral or t >= self.g["body"]:
                xd = e["x"] + max(e["h"] * 0.42, 30) + 26
                top = self.base_y - hh
                segs = [np.array([(xd, self.base_y), (xd, top)]), np.array([(xd - 10, top), (xd + 10, top)]),
                        np.array([(xd - 10, self.base_y), (xd + 10, self.base_y)])]
                nt = 6
                for j in range(1, nt):
                    yj = self.base_y - hh * j / nt
                    segs.append(np.array([(xd - 5, yj), (xd + 5, yj)]))
                lines_add(hdr, segs, WHITE, 0.45, th=2, blur=2)
        return hdr

    def ui(self, img, t, cam, neutral=False):
        if neutral:
            return
        a_l = ain(t, self.g["claim"] + 0.3) * (1 - sstep(self.g["end"] - 0.3, self.g["end"] - 0.05, t))
        a_l *= 1 - self.ctx["visual_busy"](t)
        for k, e in enumerate(self.els):
            if e["lab"]:
                qx, qy = cam((e["x"], self.base_y + 52))
                qx = U.safe_cx(qx, text_width(e["lab"], F_SEMI, 30), 1240)
                T(img, e["lab"], F_SEMI, 30, qx, min(qy, 1238), LIGHT, a_l)
            gr = eout(sat((t - self.t_grow - 0.5 * k) / 0.6), 3)
            if e["aff"] and t >= self.g["body"]:
                qx, qy = cam((e["x"], self.base_y - e["h"] - 30))
                qx = U.safe_cx(qx, text_width(e["aff"], F_DBOLD, 40), 1000)
                T(img, e["aff"], F_DBOLD, 40, qx, max(qy, 880), WHITE, a_l * gr)


class Frise(Scene):
    """{"type": "frise", "reperes": [{"annee": "1969", "libelle": "Apollo 11"}, ...] (2 à 4)}"""
    kind = "frise"

    def setup(self):
        s = self.s
        rp = (s.get("reperes") or [])[:4]
        if len(rp) < 2:
            self.errors.append("frise : 2 à 4 repères attendus")
        n = max(len(rp), 1)
        self.y = 1060.0
        self.x0, self.x1 = 250.0, 690.0
        self.rp = []
        for k, r in enumerate(rp):
            x = self.x0 + (self.x1 - self.x0) * (k / max(n - 1, 1))
            lab = U.fr(r.get("libelle", ""))
            ln = wrap(lab, F_MEDI, 30, 220)
            if len(ln) > 2:
                self.errors.append(f"libellé de repère trop long : {lab!r}")
            an = U.fr(str(r.get("annee", "")))
            wl = max([text_width(an, F_DBOLD, 44)] + [text_width(x_, F_MEDI, 30) for x_ in ln[:2]])
            self.rp.append((x, an, ln[:2], wl))
        self.t0 = self.g["body"] + 0.2
        for k in range(len(self.rp)):
            self.events.append((self.t0 + 0.55 * k, "tic", {}))

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        prog = 1.0 if neutral else sat((t - self.t0) / (0.55 * max(len(self.rp) - 1, 1) + 0.01))
        lines_add(hdr, [np.array([(self.x0 - 90, self.y), (self.x1 + 90, self.y)])], self.acc, 0.25, th=3)
        xe = self.x0 + (self.x1 - self.x0) * prog
        if prog > 0:
            lines_add(hdr, [np.array([(self.x0, self.y), (xe, self.y)])], self.acc, 1.2, th=4, blur=6)
        for k, (x, an, ln, lx) in enumerate(self.rp):
            on = 1.0 if neutral else sstep(0, 0.2, t - (self.t0 + 0.55 * k))
            add_glow(hdr, x, self.y, 1.0 + 2.0 * on, self.acc if k < len(self.rp) - 1 else self.vcol, core=6, halo=14,
                     ext=110)
        return hdr

    def ui(self, img, t, cam, neutral=False):
        if neutral:
            return
        a = (1 - sstep(self.g["end"] - 0.3, self.g["end"] - 0.05, t)) * (1 - self.ctx["visual_busy"](t))
        for k, (x, an, ln, lx) in enumerate(self.rp):
            on = ain(t, self.t0 + 0.55 * k)
            if t < self.g["body"]:
                on = 0
            qx, qy = cam((x, self.y))
            qx = U.safe_cx(qx, lx, 1200)
            T(img, an, F_DBOLD, 44, qx, qy - 40, WHITE, a * on)
            PARA(img, ln, F_MEDI, 30, qx, qy + 62, LIGHT, a * on, 0, 1.12)


class Duel(Scene):
    """{"type": "duel", "gauche": {"icone", "libelle"}, "droite": {"icone", "libelle"}, "signe": "vs|=|≠|>|<",
    "signe_apres": "=", "gagnant": "gauche|droite|aucun"}"""
    kind = "duel"

    def setup(self):
        s = self.s
        self.sides = []
        for k, x in (("gauche", 320.0), ("droite", 760.0)):
            d = s.get(k) or {}
            name = d.get("icone", "question")
            if not IC.exists(name):
                self.errors.append(f"pictogramme inconnu : {name!r}")
                name = "question"
            lab = U.fr(d.get("libelle", ""))
            ln = wrap(lab, F_DBOLD, 34, 250) if lab else []
            if len(ln) > 2:
                self.errors.append(f"libellé trop long pour un duel : {lab!r}")
            wmax = max([text_width(x_, F_DBOLD, 34) for x_ in ln] + [0])
            self.sides.append(dict(x=x, ic=Icon(name, 280), lab=lab, ln=ln[:2], lx=U.safe_cx(x, wmax, 1250), key=k))
        self.sign = s.get("signe", "vs")
        self.sign2 = s.get("signe_apres", self.sign)
        self.win = s.get("gagnant", "aucun")
        self.cy = 1060.0
        if self.sign2 != self.sign:
            self.events.append((self.g["reveal"] + 0.05, "pop", {"f": 640}))

    def world(self, t, neutral=False):
        hdr = self.fond.render(t)
        cy = self.cy
        lines_add(hdr, [np.array([(150, cy), (930, cy)])], self.acc, 0.10, th=2, blur=4)
        for k, sd in enumerate(self.sides):
            c = self.acc
            I = 1.0
            if not neutral and t >= self.g["reveal"] and self.win in ("gauche", "droite"):
                on = sstep(self.g["reveal"], self.g["reveal"] + 0.3, t) * (1 - sstep(self.g["end"] - 0.3, self.g["end"], t))
                if sd["key"] == self.win:
                    c = self.acc * f32(1 - on) + self.vcol * f32(on)
                    I = 1.0 + 0.35 * on
                else:
                    I = 1.0 - 0.55 * on
            ring(hdr, sd["x"], cy, 190, self.acc, 0.10, th=2, dash=40, rot=(t * 0.2) * (1 if k else -1))
            ring(hdr, sd["x"], cy, 215, self.acc, 0.05, th=1)
            draw_icon(hdr, sd["ic"], sd["x"], cy + 8 * math.sin(t * 1.2 + k * 2), c, I, shimmer=(t - k * 0.7) / 3.0)
        if not neutral:
            self.shockwave(hdr, t, 540, cy, 120, 650)
        return hdr

    def ui(self, img, t, cam, neutral=False):
        if neutral:
            return
        a = ain(t, self.g["claim"] + 0.2) * (1 - sstep(self.g["end"] - 0.3, self.g["end"] - 0.05, t))
        a *= 1 - self.ctx["visual_busy"](t)
        hide_cd = 1 - (sstep(self.g["cd"] - 0.2, self.g["cd"], t) * (1 - sstep(self.g["reveal"] + 0.6, self.g["reveal"] + 0.9, t)))
        for sd in self.sides:
            if sd["ln"]:
                y0 = 1218 if len(sd["ln"]) == 1 else 1190
                PARA(img, sd["ln"], F_DBOLD, 34, sd["lx"], y0, WHITE, a * hide_cd, 0, 1.08)
        sg = self.sign if t < self.g["reveal"] else self.sign2
        sg = {"vs": "VS", "=": "=", "≠": "≠", ">": ">", "<": "<"}.get(sg, sg)
        qx, qy = cam((540, self.cy + 28))
        T(img, sg, F_DBLACK, 92 if sg != "VS" else 60, qx, qy, WHITE if sg == "VS" else CYAN, a * hide_cd)


SCENES = {"pictogramme": Pictogramme, "globe": Globe, "horizon": Horizon, "grille": Grille, "echelle": Echelle,
          "frise": Frise, "duel": Duel}


def make_scene(spec, ctx):
    k = (spec or {}).get("type", "pictogramme")
    if k not in SCENES:
        sc = Pictogramme({"icone": "question"}, ctx)
        sc.errors.append(f"type de scène inconnu : {k!r} (attendus : {', '.join(SCENES)})")
        return sc
    return SCENES[k](spec or {}, ctx)
