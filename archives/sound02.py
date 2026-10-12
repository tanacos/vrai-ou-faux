#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bande-son de VRAI OU FAUX ? #2 (cerveau, 70 s, 48 kHz stéréo), synthétisée et calée sur ep02.py.
  python3 sound01x.py OUT.wav [GAIN] [PLAFOND_dB]"""
import sys
import wave

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, uniform_filter1d

sys.path.insert(0, "/home/claude/vf")
import ep02 as X  # noqa: E402

SR = 48000
DUR = X.DUR
N = int(round(SR * DUR))
TAU = 2 * np.pi
rng = np.random.default_rng(303)
dry = np.zeros((N, 2))
send = np.zeros((N, 2))
bed = np.zeros((N, 2))


def midi(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def ix(t):
    return int(round(t * SR))


def tl_(d):
    return np.arange(int(round(d * SR))) / SR


def noise(n):
    return rng.standard_normal(n)


def filt(kind, f, x, order=4):
    return signal.sosfilt(signal.butter(order, f, btype=kind, fs=SR, output="sos"), x, axis=0)


def put(t0, sig, gain=1.0, pan=0.0, rev=0.0, bus=None):
    i0 = ix(t0)
    if sig.ndim == 1:
        a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
        sig = np.stack([sig * np.cos(a), sig * np.sin(a)], 1) * np.sqrt(2)
    if i0 < 0:
        sig, i0 = sig[-i0:], 0
    n = min(len(sig), N - i0)
    if n <= 0:
        return
    (dry if bus is None else bus)[i0:i0 + n] += sig[:n] * gain
    send[i0:i0 + n] += sig[:n] * gain * rev


def edec(x, tau, att=0.002):
    return np.exp(-x / tau) * np.clip(x / att, 0, 1)


def saw(f, nh=24, cutoff=None):
    f = np.asarray(f, float)
    ph = TAU * np.cumsum(f) / SR
    out = np.zeros_like(f)
    for k in range(1, nh + 1):
        a = (k * f < 0.45 * SR) / k
        if cutoff is not None:
            a = a / np.sqrt(1 + (k * f / cutoff) ** 4)
        out += a * np.sin(k * ph)
    return out


def svf_bp(x, fc, Q=1.0):
    fc = np.broadcast_to(np.asarray(fc, float), x.shape)
    g = np.tan(np.pi * np.clip(fc, 10, 0.45 * SR) / SR)
    k = 1.0 / Q
    a1 = 1 / (1 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    a1, a2, a3, xs = a1.tolist(), a2.tolist(), a3.tolist(), x.tolist()
    ic1 = ic2 = 0.0
    out = [0.0] * len(xs)
    for i, xi in enumerate(xs):
        v3 = xi - ic2
        v1 = a1[i] * ic1 + a2[i] * v3
        v2 = ic2 + a2[i] * ic1 + a3[i] * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        out[i] = v1
    return np.array(out)


def pad(notes, dur, att=0.8, rel=1.0, cutoff=1400, voices=4, det=0.007):
    x = tl_(dur)
    env = (np.clip(x / att, 0, 1) * np.clip((dur - x) / rel, 0, 1)) ** 1.5
    out = np.zeros((len(x), 2))
    for m in notes:
        f = float(midi(m))
        for v in range(voices):
            d = 1 + det * (v - (voices - 1) / 2) / max(voices - 1, 1) * 2
            s_ = saw(np.full(len(x), f * d), nh=18, cutoff=cutoff)
            out[:, v % 2] += s_
            out[:, 1 - v % 2] += 0.35 * s_
    return out * env[:, None] / (len(notes) * voices)


def thunder(dur=3.2, crack=1.0, rumble=1.0, seed=0, bright=1.0):
    r = np.random.default_rng(seed)
    x = tl_(dur)
    n = len(x)
    out = np.zeros((n, 2))
    cr = np.zeros(n)
    tc = 0.0
    while tc < 0.06:                                    # déchirement initial (traceur)
        tc += r.exponential(0.0025)
        k = int(tc * SR)
        m = min(int(0.004 * SR), n - k)
        if m > 0:
            cr[k:k + m] += r.standard_normal(m) * np.exp(-np.arange(m) / SR / 0.0008) * r.uniform(0.3, 1.0)
    cr = filt("bandpass", (900, 9000 * bright), cr, 2)
    ck = filt("highpass", 500, r.standard_normal(n)) * np.exp(-x / 0.018) * np.clip(x / 0.0008, 0, 1)
    ck = filt("lowpass", 7000 * bright, ck, 2)
    for ch in range(2):                                 # grondement
        rb = filt("lowpass", 170, r.standard_normal(n))
        mod = uniform_filter1d(np.abs(r.standard_normal(n)), int(0.09 * SR))
        mod = mod / (mod.max() + 1e-9)
        env = (1 - np.exp(-x / 0.05)) * np.exp(-x / (dur * 0.33))
        boom = filt("lowpass", 90, r.standard_normal(n)) * np.exp(-x / 0.35) * np.clip(x / 0.01, 0, 1)
        mid = filt("bandpass", (120, 600), r.standard_normal(n), 2) * env * (0.3 + mod)   # audible sur téléphone
        out[:, ch] += rumble * (rb * env * (0.4 + 1.2 * mod) * 2.2 + boom * 2.6 + mid * 0.9)
        out[:, ch] += crack * (ck * 0.9 + cr * 0.6)
    return out


def tick(f=1900, dur=0.05):
    x = tl_(dur)
    return (np.sin(TAU * f * x) * 0.8 + filt("bandpass", (f * 0.6, f * 1.6), noise(len(x)), 2) * 0.5) * np.exp(-x / 0.012)


def pop(f0=500, dur=0.09):
    x = tl_(dur)
    f = f0 * (1 + 1.2 * (1 - np.exp(-x / 0.02)))
    return np.sin(TAU * np.cumsum(f) / SR) * np.exp(-x / 0.035) * np.clip(x / 0.002, 0, 1)


def whoosh(dur, f0, f1, Q=1.2, pk=0.5):
    x = tl_(dur)
    u = x / dur
    env = np.where(u < pk, (u / pk) ** 2, ((1 - u) / (1 - pk)) ** 1.5)
    return svf_bp(noise(len(x)), f0 * (f1 / f0) ** u, Q) * env


def sub_hit(level=1.0, dur=1.2, f0=42, sweep=80):
    x = tl_(dur)
    s = np.tanh(2.0 * np.sin(TAU * np.cumsum(f0 + sweep * np.exp(-x / 0.06)) / SR)) / np.tanh(2.0)
    s += 0.35 * np.tanh(3.0 * np.sin(TAU * np.cumsum(2 * f0 + 2 * sweep * np.exp(-x / 0.05)) / SR)) * np.exp(-x / 0.12)
    return s * edec(x, 0.35, 0.002) * level


def chime(notes, dur=2.0, decay=(1.0, 0.8, 0.6)):
    x = tl_(dur)
    out = np.zeros(len(x))
    for m, d in zip(notes, decay):
        f = float(midi(m))
        out += np.sin(TAU * f * x) * np.exp(-x / d) + 0.25 * np.sin(TAU * 2.76 * f * x) * np.exp(-x / (d * 0.3))
    return out * np.clip(x / 0.002, 0, 1) / len(notes)


def chord_stab(notes, dur=0.9, cutoff=1600, tau=0.30):
    x = tl_(dur)
    return sum(saw(np.full(len(x), float(midi(m))), nh=16, cutoff=cutoff) for m in notes) * edec(x, tau, 0.004)


def riser(dur, f0=300, f1=6000, Q=1.8, p=2.2):
    x = tl_(dur)
    u = x / x[-1]
    r_ = svf_bp(noise(len(x)), f0 * (f1 / f0) ** (u ** 1.3), Q) * u ** p
    return np.stack([r_, np.roll(r_, 220)], 1)


def dtmf(key, dur=0.12):
    lo = {"1": 697, "2": 697}[key]
    hi = {"1": 1209, "2": 1336}[key]
    x = tl_(dur)
    env = np.clip(x / 0.004, 0, 1) * np.clip((dur - x) / 0.006, 0, 1)
    return (np.sin(TAU * lo * x) + np.sin(TAU * hi * x)) * 0.5 * env



# ------------------------------------------------------------------ nouveaux sons de l'épisode « cerveau »
PENTA = [57, 60, 62, 64, 67, 69, 72, 74, 76, 79, 81, 84, 86, 88]     # la mineur pentatonique


def ping(m, dur=0.35, tau=0.12, bright=0.25):
    x = tl_(dur)
    f = float(midi(m))
    s = np.sin(TAU * f * x) + bright * np.sin(TAU * 2 * f * x) * np.exp(-x / (tau * 0.4))
    return s * edec(x, tau, 0.002)


def pluck(m, dur=0.30, tau=0.11, cutoff=2400):
    x = tl_(dur)
    f = np.full(len(x), float(midi(m)))
    return saw(f, nh=14, cutoff=cutoff) * edec(x, tau, 0.003) * 0.6


def thump(f0=55, dur=0.35, tau=0.10):
    x = tl_(dur)
    f = f0 + 40 * np.exp(-x / 0.02)
    s = np.sin(TAU * np.cumsum(f) / SR) + 0.3 * np.sin(2 * TAU * np.cumsum(f) / SR)
    s = filt("lowpass", 400, s, 2)
    return s * edec(x, tau, 0.004)


def zap(dur=0.18, f0=2400, f1=600):
    x = tl_(dur)
    u = x / dur
    f = f0 * (f1 / f0) ** u
    s = np.sign(np.sin(TAU * np.cumsum(f) / SR)) * 0.4 + filt("bandpass", (1500, 7000), noise(len(x)), 2) * 0.6
    return filt("lowpass", 9000, s, 2) * np.exp(-x / 0.05) * np.clip(x / 0.002, 0, 1)


def mri(dur, rate=6.5, f=820):
    """Cliquetis rythmé façon IRM, par rafales."""
    x = tl_(dur)
    gate = (np.sin(TAU * rate * x) > 0.55).astype(float)
    gate = uniform_filter1d(gate, int(0.004 * SR))
    burst = (np.sin(TAU * x / 1.82) > -0.2).astype(float)
    burst = uniform_filter1d(burst, int(0.03 * SR))
    tone = np.sign(np.sin(TAU * f * x)) * 0.5 + 0.5 * np.sin(TAU * 2 * f * x)
    return filt("bandpass", (400, 3500), tone, 2) * gate * burst


# ------------------------------------------------------------------ ambiances par scène
def scene_env(k, t_fade_in=0.08, t_fade_out=0.06):
    """Enveloppe (0..1) de la scène k sur toute la durée."""
    b = [0.0] + X.CUT + [DUR + 1.0]
    t = np.arange(N) / SR
    t0, t1 = b[k], b[k + 1]
    return np.clip((t - t0) / t_fade_in + (k == 0), 0, 1) * np.clip((t1 - t) / t_fade_out, 0, 1)


E_B = scene_env(0) + scene_env(4)
E_H = scene_env(1)
E_D = scene_env(2)
E_G = scene_env(3)
for ch in range(2):                                     # souffle « neuronal » (aigu, doux)
    air = filt("bandpass", (2500, 9000), noise(N), 2)
    lfo = 0.6 + 0.4 * np.sin(TAU * 0.13 * np.arange(N) / SR + ch * 1.7)
    dry[:, ch] += air * lfo * 0.010 * (E_B + E_D + 0.6 * E_H)
    hum = filt("lowpass", 180, noise(N))                # corps (scène de la tête)
    dry[:, ch] += hum * 0.10 * E_H
    space = filt("bandpass", (60, 240), noise(N), 2)    # espace (scène de la galaxie)
    shimmer = filt("bandpass", (5000, 12000), noise(N), 2) * (0.5 + 0.5 * np.sin(TAU * 0.21 * np.arange(N) / SR + ch))
    dry[:, ch] += (space * 0.16 + shimmer * 0.008) * E_G
t_ax = np.arange(N) / SR
drone = sum(a * np.sin(TAU * float(midi(m)) * t_ax) for m, a in ((33, 0.5), (40, 0.32), (45, 0.22), (52, 0.10)))
put(0.0, np.stack([drone, drone], 1) * (E_G * 0.10)[:, None], 1.0, rev=0.2)

# crépitement neuronal : densité proportionnelle à l'activité du cortex (scène de profil)
rp = np.random.default_rng(5)
tt = 0.0
while tt < DUR:
    sc = X.TL.scene_index(tt)
    if sc in (0, 4):
        _, frac = X.activity(tt)
        rate = 1.5 + 14.0 * frac
    elif sc == 2:
        rate = 6.0
    elif sc == 1:
        rate = 1.5
    else:
        rate = 0.0
    if rate > 0:
        tt += rp.exponential(1.0 / rate)
        if tt >= DUR:
            break
        put(tt, ping(int(rp.choice(PENTA[5:])), 0.22, rp.uniform(0.04, 0.09), 0.15), rp.uniform(0.010, 0.022),
            pan=rp.uniform(-0.8, 0.8), rev=0.45)
    else:
        tt += 0.05

# ------------------------------------------------------------------ transitions et boucle
for i, tf in enumerate(X.FL):
    put(tf - 0.85, riser(0.85, 400, 7000, 1.6, 2.4), 0.08, rev=0.3)
    x = tl_(0.85)
    sw = np.sin(TAU * np.cumsum(110 * 4 ** ((x / x[-1]) ** 1.6)) / SR) * (x / x[-1]) ** 2.5
    put(tf - 0.85, sw, 0.03, rev=0.3)
    put(tf, sub_hit(0.9, 1.4, 38, 70), 0.75)
    put(tf, chime((76, 81, 88), 2.2, (1.2, 0.9, 0.6)), 0.05, rev=0.6)
    x = tl_(0.9)
    put(tf, filt("lowpass", 900, noise(len(x))) * np.exp(-x / 0.12) * np.clip(x / 0.003, 0, 1), 0.30, rev=0.3)
    if i == 3:                                          # vers la galaxie : grand souffle spatial
        put(tf, whoosh(2.2, 2000, 200, 0.9, 0.15), 0.07, rev=0.5)
put(DUR - 0.95, riser(0.95, 300, 8000, 1.5, 2.6), 0.08, rev=0.3)       # éclair de bouclage
put(DUR - 0.12, zap(0.12), 0.05, rev=0.2)
put(0.0, sub_hit(0.8, 1.2, 40, 80), 0.55)                              # la boucle repart sur un impact
put(0.0, chime((69, 76, 81), 2.0), 0.04, rev=0.6)

# ------------------------------------------------------------------ question, compte à rebours, verdict (identité de la série)
for g in X.G:
    i = g["i"]
    put(g["claim"] - 0.05, whoosh(0.45, 600, 4000, 1.0, 0.35), 0.06, pan=-0.2, rev=0.3)
    for k in range(3):
        put(g["cd"] + 0.65 * k, tick(1500 + 300 * k, 0.07), 0.22, rev=0.2)
    put(g["cd"], riser(g["reveal"] - g["cd"], 300, 6000), 0.07, rev=0.3)
    x = tl_(g["reveal"] - g["cd"])
    u = x / x[-1]
    put(g["cd"], np.sin(TAU * np.cumsum(220 * 2 ** u) / SR) * u ** 2, 0.025, rev=0.3)
    tr = g["reveal"]
    put(tr, sub_hit(1.0, 1.2, 40, 100), 0.85)
    x = tl_(0.25)
    put(tr, filt("lowpass", 900, noise(len(x))) * np.exp(-x / 0.03), 0.9)
    put(tr, filt("bandpass", (900, 3500), noise(len(x)), 2) * np.exp(-x / 0.02), 0.45)
    if X.VERDICT[i] == "FAUX":
        put(tr + 0.01, chord_stab((57, 58, 64)), 0.10, rev=0.35)
    else:
        put(tr + 0.01, chord_stab((60, 64, 67, 72), 1.4, 2600, 0.5), 0.09, rev=0.45)
        put(tr + 0.02, chime((84, 88, 91), 2.4), 0.07, rev=0.5)
    put(g["body"] - 0.45, whoosh(0.42, 500, 3000, 1.0, 0.5), 0.05, pan=0.25, rev=0.25)

for t0 in (X.P1A[0], X.P1B[0], X.P1C[0], X.P2A[0], X.P2B[0], X.P2C[0], X.P3A[0], X.P3B[0], X.P3C[0], X.P4A[0],
           X.P4B[0], X.P4C[0], X.P5A[0], X.P5B[0]):
    put(t0 - 0.06, whoosh(0.40, 800, 5000, 1.1, 0.55), 0.042, pan=0.2 * np.sin(t0), rev=0.25)

# ------------------------------------------------------------------ idée n° 1 : la cascade d'activation (une note par région)
for j, k in enumerate(X.REST):
    tk = X.T_CASCADE0 + (X.T_CASCADE1 - X.T_CASCADE0) * j / max(len(X.REST) - 1, 1)
    m = PENTA[min(int(j / len(X.REST) * len(PENTA)), len(PENTA) - 1)]
    put(tk, pluck(m, 0.35, 0.10), 0.045, pan=float(np.clip((X.BL.seeds[k][0] - 425) / 330, -1, 1)) * 0.6, rev=0.35)
put(X.T_CASCADE1 + 0.3, chime((81, 88, 93), 2.2, (1.2, 0.9, 0.6)), 0.07, rev=0.5)
put(X.P1B[0] + 0.25, pop(480, 0.11), 0.12, pan=-0.4, rev=0.25)
put(X.P1B[0] + 0.85, pop(760, 0.11), 0.12, pan=0.4, rev=0.25)
put(X.P1B[0] + 0.86, thump(70, 0.4, 0.12), 0.35)

# ------------------------------------------------------------------ idée n° 2 : balayage, récepteurs, sonde, mal de tête
xs_ = lambda u: 200 + 680 * (u * u * u * (u * (6 * u - 15) + 10))
x = tl_(1.9)
u = x / x[-1]
scan = svf_bp(noise(len(x)), 500 * 6 ** u, 3.0) * np.sin(np.pi * u) ** 0.5
scan += 0.3 * np.sin(TAU * np.cumsum(300 + 500 * u) / SR) * np.sin(np.pi * u)
put(X.P2A[0] + 0.5, np.stack([scan * (1 - 0.6 * u), scan * (0.4 + 0.6 * u)], 1), 0.05, rev=0.3)
uu = np.linspace(0, 1, 2000)
xx = xs_(uu)
rec_times = []
for (rx, ry) in X.HS.receptors:
    k = int(np.searchsorted(xx, rx))
    if 0 < k < len(uu):
        rec_times.append((X.P2A[0] + 0.5 + 1.9 * uu[k], rx))
rec_times.sort()
last = -1.0
for tr_, rx in rec_times:
    if tr_ - last < 0.035:
        continue
    last = tr_
    put(tr_, ping(int(rp.choice([86, 88, 91, 93])), 0.18, 0.05, 0.4), 0.020, pan=float(np.clip((rx - 540) / 340, -1, 1)),
        rev=0.3)
x = tl_(0.8)                                            # la sonde descend
whirr = np.sin(TAU * np.cumsum(180 + 90 * np.sin(TAU * 13 * x)) / SR) * np.sin(np.pi * x / x[-1])
put(X.P2B[0] + 0.2, filt("bandpass", (150, 2500), whirr, 2), 0.03, pan=0.3, rev=0.2)
tz = X.P2B[0] + 1.0
while tz < X.P2B[1] - 0.3:                              # stimulation à chaque onde
    put(tz, zap(0.16, 2600, 900), 0.035, pan=-0.1, rev=0.3)
    tz += 0.8
put(X.P2B[0] + 1.4, pop(980, 0.08), 0.09, pan=-0.6, rev=0.25)        # bulle « … »
put(X.P2B[0] + 1.48, pop(1240, 0.07), 0.07, pan=-0.6, rev=0.25)
p_on = X.P2C[0] + 0.2
kk = 0
while True:                                             # battements du mal de tête (pics de la pulsation lumineuse)
    tb = (0.25 + kk / 2) / 1.15
    kk += 1
    if tb < p_on:
        continue
    if tb > X.FL[1] - 0.4:
        break
    put(tb, thump(52, 0.35, 0.09), 0.55, rev=0.1)

# ------------------------------------------------------------------ idée n° 3 : gauche / droite, IRM
g2 = X.G[2]
put(g2["claim"] + 0.4, pop(560, 0.10), 0.09, pan=-0.6, rev=0.25)
put(g2["claim"] + 0.5, pop(700, 0.10), 0.09, pan=0.6, rev=0.25)
put(X.P3A[0] + 0.05, mri(X.P3A[1] - X.P3A[0] - 0.2), 0.030, rev=0.25)
tc = X.P3A[0] + 0.3
nprev = 0
while tc < X.P3A[0] + 1.9:                              # compteur 0 → 1 011
    n = int(round(1011 * (1 - (1 - min((tc - X.P3A[0] - 0.3) / 1.6, 1)) ** 2)))
    if n != nprev:
        put(tc, tick(2400 + 600 * n / 1011, 0.03), 0.035, rev=0.15)
        nprev = n
    tc += 0.045
put(X.P3A[0] + 1.95, chime((79, 86), 1.4), 0.05, rev=0.4)
put(X.P3B[0] + 0.4, pop(620, 0.10), 0.10, rev=0.3)
put(X.P3B[0] + 0.42, chord_stab((57, 64, 69), 1.0, 2000, 0.35), 0.035, rev=0.4)
put(X.P3C[0] + 0.5, ping(81, 0.6, 0.25, 0.3), 0.07, pan=-0.6, rev=0.4)
put(X.P3C[0] + 0.62, ping(88, 0.6, 0.25, 0.3), 0.07, pan=0.6, rev=0.4)

# ------------------------------------------------------------------ idée n° 4 : barres, comptage, champ de galaxies
tb0 = X.P4A[0] + 0.20
for (lab, val, tv, col, d) in X.ROWS4:
    st = 12 * np.log2(tv / 86.0)
    x = tl_(1.2)
    gl = np.clip(x / 0.6, 0, 1)
    gl = 1 - (1 - gl) ** 3
    f = midi(45 + (12 + st) * gl)
    s_ = (np.sin(TAU * np.cumsum(f) / SR) + 0.3 * np.sin(2 * TAU * np.cumsum(f) / SR)) * np.clip(x / 0.01, 0, 1) * \
        np.exp(-np.clip(x - 0.6, 0, None) / 0.18)
    put(tb0 + d + 0.1, s_, 0.045, rev=0.35)
put(tb0 + 2.1, tick(1800, 0.08), 0.07, rev=0.3)
put(X.P4B[0] + 0.7, thump(46, 0.5, 0.15), 0.4)                          # « jamais démontré »
put(X.P4B[0] + 0.72, chord_stab((52, 53), 0.6, 1200, 0.2), 0.05, rev=0.3)
put(X.P4B[0] + 1.3, pop(700, 0.09), 0.08, rev=0.3)
put(X.P4C[0] - 0.1, riser(0.9, 300, 5000, 1.4, 2.0), 0.06, rev=0.4)
for k_, ((gx, gy, d, size, ang, sq)) in enumerate(X.GRID):            # chaque galaxie qui apparaît scintille
    gs = 0.10 + 0.55 * min(d, 1.4) / 1.4
    grid_t0, grid_t1 = X.P4C[0] + 0.2, X.P4C[0] + 1.6
    # grid = sstep(grid_t0, grid_t1, t) ; apparition quand grid ≈ gs + 0.1
    target = gs + 0.1
    lo, hi = grid_t0, grid_t1
    for _ in range(30):
        mid_ = (lo + hi) / 2
        v = X.sstep(grid_t0, grid_t1, mid_)
        lo, hi = (mid_, hi) if v < target else (lo, mid_)
    if k_ % 3 == 0:
        put(lo, ping(int(rp.choice(PENTA[7:])), 0.25, 0.06, 0.3), 0.012, pan=float(np.clip((gx - 540) / 400, -1, 1)),
            rev=0.5)
put(X.P4C[0] + 1.6, chord_stab((57, 64, 69, 72, 76), 2.0, 3000, 0.8), 0.06, rev=0.6)
put(X.P4C[0] + 1.62, chime((88, 93, 96), 2.6, (1.4, 1.0, 0.7)), 0.06, rev=0.6)

# ------------------------------------------------------------------ fin
put(X.P5A[0] + 0.25, pop(520, 0.12), 0.12, rev=0.3)
put(X.P5A[0] + 0.27, chime((76, 81), 1.4), 0.05, rev=0.4)
put(X.P5B[0] + 0.5, pop(700, 0.09), 0.08, rev=0.3)
put(X.P5B[0] + 1.0, pop(900, 0.09), 0.09, rev=0.3)
put(X.P5B[0] + 1.02, chime((88, 93, 98), 2.0, (1.2, 0.9, 0.6)), 0.05, rev=0.5)

# ------------------------------------------------------------------ musique : nappes, pulsation (100 BPM), arpège
F0, F1, F2, F3 = X.FL
Am, Fm7, C_, G_, E_, Dm, F_ = (45, 52, 57, 60), (41, 48, 52, 57), (48, 55, 60, 64), (43, 50, 55, 59), (44, 52, 56, 59), \
    (50, 53, 57, 62), (41, 48, 53, 57)
R = [g["reveal"] for g in X.G]
CH = [(0.0, R[0], Am), (R[0], 9.6, F_), (9.6, 13.0, C_), (13.0, F0, G_),
      (F0, R[1], Am), (R[1], 24.0, C_), (24.0, 28.6, F_), (28.6, F1, E_),
      (F1, R[2], Am), (R[2], 39.5, F_), (39.5, 43.1, Dm), (43.1, F2, G_),
      (F2, R[3], Am), (R[3], X.P4B[0], Fm7), (X.P4B[0], X.P4C[0], C_), (X.P4C[0], F3, E_),
      (F3, X.P5B[0], Am), (X.P5B[0], DUR, F_)]
for t0, t1, notes in CH:
    put(t0, pad(notes, t1 - t0 + 0.7, 0.5, 0.8, 1500), 0.32, rev=0.5, bus=bed)
WIN = [(g["reveal"], g["end"] - 0.55) for g in X.G] + [(X.P5A[0], DUR - 0.3)]


def chord_at(t):
    for t0, t1, notes in CH:
        if t0 <= t < t1:
            return notes
    return Am


for (w0, w1) in WIN:
    for k, tb_ in enumerate(np.arange(w0, w1, 0.6)):
        x = tl_(0.5)
        f = float(midi(33)) + 45 * np.exp(-x / 0.03)
        kick = np.tanh(2.5 * np.sin(TAU * np.cumsum(f) / SR)) * edec(x, 0.16, 0.002)
        put(tb_, kick, 0.13, bus=bed)
        y = tl_(0.06)
        sh = filt("highpass", 7000, noise(len(y)), 2) * np.exp(-y / 0.012)
        put(tb_ + 0.3, sh, 0.030 if k % 2 else 0.024, pan=0.3, bus=bed)
    for k, ta in enumerate(np.arange(w0, w1, 0.3)):     # arpège en croches sur les notes de l'accord
        notes = chord_at(ta)
        m = notes[[1, 2, 3, 2][k % 4]] + 12
        put(ta, pluck(m, 0.28, 0.09, 2000), 0.036, pan=0.35 * np.sin(k * 0.9), rev=0.35, bus=bed)
dry += bed
send += bed * 0.3


# ------------------------------------------------------------------ réverbération, mastering
def make_ir(sec=2.6):
    n = int(sec * SR)
    t_ = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for ch in range(2):
        ir[:, ch] = 0.5 * filt("highpass", 1500, noise(n)) * np.exp(-6.9 * t_ / 0.9) + filt("lowpass", 2500, noise(n)) * np.exp(-6.9 * t_ / 2.2)
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]
    return ir / np.sqrt((ir ** 2).sum(0))


ir = make_ir()
wet = np.stack([signal.fftconvolve(send[:, ch], ir[:, ch])[:N] for ch in range(2)], 1)
mix = dry + wet * 0.5
mix = signal.sosfilt(signal.butter(2, 28, "highpass", fs=SR, output="sos"), mix, axis=0)
mix *= float(sys.argv[2]) if len(sys.argv) > 2 else 1.28
T = 0.55
a = np.abs(mix)
over = a > T
mix[over] = np.sign(mix[over]) * (T + (1 - T) * np.tanh((a[over] - T) / (1 - T)))
mix = signal.sosfilt(signal.butter(2, 15000, "lowpass", fs=SR, output="sos"), mix, axis=0)
ceiling = 10 ** ((float(sys.argv[3]) if len(sys.argv) > 3 else -3.8) / 20)
look = int(0.003 * SR)
pk = maximum_filter1d(np.abs(mix).max(1), size=2 * look + 1)
g = uniform_filter1d(np.minimum(1.0, ceiling / np.maximum(pk, 1e-9)), size=look)
rel = np.exp(-1 / (0.05 * SR))
gl = g.tolist()
for i in range(1, len(gl)):
    if gl[i] > gl[i - 1]:
        gl[i] = gl[i - 1] * rel + gl[i] * (1 - rel)
g = np.array(gl)
mix *= g[:, None]
fade = int(0.004 * SR)                                   # pas de clic aux bords de la boucle
mix[:fade] *= np.linspace(0, 1, fade)[:, None]
mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
print(f"peak={20*np.log10(np.abs(mix).max()):.2f} dBFS  max GR={-20*np.log10(g.min()):.1f} dB")
pcm = np.clip(mix * 32767, -32768, 32767).astype("<i2")
with wave.open(sys.argv[1], "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes(pcm.tobytes())
print("wrote", sys.argv[1], pcm.shape[0] / SR, "s")
