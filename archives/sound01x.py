#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bande-son de VRAI OU FAUX ? #1 (version longue, 68,7 s, 48 kHz stéréo), synthétisée et calée sur ep01x.py.
  python3 sound01x.py OUT.wav [GAIN] [PLAFOND_dB]"""
import sys
import wave

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, uniform_filter1d

sys.path.insert(0, "/home/claude/vf")
import ep01x as X  # noqa: E402

SR = 48000
DUR = X.DUR
N = int(round(SR * DUR))
TAU = 2 * np.pi
rng = np.random.default_rng(202)
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


# ------------------------------------------------------------------ pluie (coupée dans la scène du Soleil)
renv = np.ones(N)
a0, a1 = ix(X.CUT[1]), ix(X.CUT[2])
fo, fi = int(0.05 * SR), int(0.35 * SR)
renv[a0:a1] = 0.0
renv[a0 - fo:a0] = np.linspace(1, 0, fo)
renv[a1:a1 + fi] = np.linspace(0, 1, fi)
for ch in range(2):
    rn = filt("bandpass", (350, 6500), noise(N), 2)
    rn += 0.35 * filt("highpass", 5000, noise(N), 2)
    dry[:, ch] += rn * 0.030 * renv
drops = np.zeros(N)
for _ in range(2400):
    k = int(rng.uniform(0, N - 400))
    m = 300
    drops[k:k + m] += np.sin(TAU * rng.uniform(1800, 4500) * np.arange(m) / SR) * np.exp(-np.arange(m) / SR / 0.002) * rng.uniform(0.2, 1)
drops *= renv
put(0.0, np.stack([drops, np.roll(drops, 777)], 1), 0.020)

# ------------------------------------------------------------------ éclairs et tonnerre
BIG_T = {0.04, X.G[0]["reveal"] - 0.02, X.FL[3], X.CUT[0], X.G[1]["reveal"] - 0.02, X.CUT[2], X.G[3]["reveal"] - 0.02}
T23 = set(X.T23)
SLOWSET = {X.SLOW.t0}
for sc, lst in X.STRIKES.items():
    for j, s in enumerate(lst):
        if s.t0 in T23 or s.t0 in SLOWSET:
            continue
        pan = float(np.clip((s.p0[0] - 540) / 540, -1, 1)) * 0.5
        seed = 1000 + int(s.t0 * 100)
        if any(abs(s.t0 - b) < 1e-6 for b in BIG_T):
            put(s.t0, thunder(3.6, 1.5, 1.3, seed), 0.55, pan=pan, rev=0.25)
            put(s.t0, sub_hit(0.9, 1.5, 37, 90), 0.75)
        elif s.t0 > DUR - 0.5:                           # dernier éclair : la boucle repart dessus
            put(s.t0, thunder(1.0, 1.5, 0.6, seed), 0.50, pan=pan, rev=0.2)
            put(s.t0, sub_hit(0.7, 0.6, 36, 90), 0.6)
        elif abs(s.t0 - (X.P2A[0] + 2.55)) < 1e-6:        # coup sur l'arbre, tout proche
            put(s.t0, thunder(3.0, 1.6, 1.1, seed), 0.48, pan=pan, rev=0.22)
            put(s.t0, sub_hit(0.8, 1.2, 38, 90), 0.6)
        else:                                            # éclairs lointains : le tonnerre arrive après
            d = 0.55 + 0.25 * ((j * 7) % 3) / 2
            put(s.t0 + d, thunder(3.4, 0.25, 0.9, seed, 0.4), 0.30, pan=pan, rev=0.35)
for k, tk in enumerate(X.T23):                          # compteur 1 → 23
    put(tk, thunder(1.6, 0.8, 0.5, 10 + k, 0.8), 0.20 + 0.008 * k, pan=0.3 * np.sin(k * 1.7), rev=0.2)
    put(tk, pop(420 * 2 ** (k / 12 * 0.9), 0.08), 0.10, rev=0.15)
put(X.T23[-1] + 0.02, tick(2600, 0.12), 0.10, rev=0.3)
for k, (dt, I) in enumerate(X.SLOW.strokes):            # ralenti : quatre coups profonds
    t0 = X.SLOW.t0 + dt
    put(t0, thunder(2.0, 0.35, 1.2, 70 + k, 0.35), 0.36 * I, rev=0.35)
    put(t0, sub_hit(0.75, 1.0, 32 + 2 * k, 50), 0.7)
    put(t0, pop(300 + 80 * k, 0.12), 0.11, rev=0.3)
put(X.T_SC + 0.1, chime((81, 88, 93), 2.0), 0.05, rev=0.5)

# ------------------------------------------------------------------ transitions (flash blanc)
for i, tf in enumerate(X.FL):
    put(tf - 0.85, riser(0.85, 400, 7000, 1.6, 2.4), 0.07, rev=0.3)
    x = tl_(0.85)
    sw = np.sin(TAU * np.cumsum(110 * 4 ** ((x / x[-1]) ** 1.6)) / SR) * (x / x[-1]) ** 2.5
    put(tf - 0.85, sw, 0.025, rev=0.3)
    if i == 1:                                           # vers le Soleil : souffle grave et brillance
        put(tf, sub_hit(1.0, 1.8, 34, 70), 0.8)
        put(tf, chime((74, 81, 86), 2.6, (1.4, 1.1, 0.8)), 0.06, rev=0.6)
        x = tl_(1.6)
        put(tf, filt("lowpass", 700, noise(len(x))) * np.exp(-x / 0.35) * np.clip(x / 0.004, 0, 1), 0.35, rev=0.3)

# ------------------------------------------------------------------ scène du Soleil : grondement du plasma
d0, d1 = X.CUT[1], X.CUT[2]
x = tl_(d1 - d0 + 0.3)
u = x
env = np.clip(u / 0.4, 0, 1) * np.clip((d1 - d0 + 0.3 - u) / 0.3, 0, 1)
for ch in range(2):
    roar = filt("lowpass", 260, noise(len(x)))
    lfo = 0.65 + 0.35 * np.sin(TAU * 0.23 * x + ch * 1.3) * np.sin(TAU * 0.11 * x + 0.5)
    hiss = filt("bandpass", (500, 1600), noise(len(x)), 2) * (0.5 + 0.5 * np.sin(TAU * 0.17 * x + ch))
    drone = sum(a * np.sin(TAU * float(midi(m)) * (1 + 0.0015 * (ch - 0.5)) * x)
                for m, a in ((38, 0.5), (45, 0.35), (50, 0.25), (57, 0.12)))
    sig = (roar * 1.1 * lfo + hiss * 0.12 + drone * 0.22) * env
    dry[ix(d0):ix(d0) + len(x), ch] += sig[:min(len(x), N - ix(d0))] * 0.5
    send[ix(d0):ix(d0) + len(x), ch] += sig[:min(len(x), N - ix(d0))] * 0.15

# ------------------------------------------------------------------ question, compte à rebours, verdict
for g in X.G:
    i = g["i"]
    put(g["claim"] - 0.05, whoosh(0.45, 600, 4000, 1.0, 0.35), 0.06, pan=-0.2, rev=0.3)
    for k in range(3):                                  # 3, 2, 1
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
        put(tr + 0.01, chord_stab((50, 51, 57)), 0.10, rev=0.35)
    else:                                               # VRAI : accord majeur lumineux
        put(tr + 0.01, chord_stab((62, 66, 69, 74), 1.4, 2600, 0.5), 0.09, rev=0.45)
        put(tr + 0.02, chime((86, 90, 93), 2.4), 0.07, rev=0.5)
    put(g["body"] - 0.45, whoosh(0.42, 500, 3000, 1.0, 0.5), 0.05, pan=0.25, rev=0.25)

# ------------------------------------------------------------------ entrées de texte
for t0 in (X.P1A[0], X.P1B[0], X.P2A[0], X.P2B[0], X.P2C[0], X.P3A[0], X.P3B[0], X.P4A[0], X.P4B[0], X.P4C[0],
           X.P5A[0], X.P5B[0]):
    put(t0 - 0.06, whoosh(0.40, 800, 5000, 1.1, 0.55), 0.045, pan=0.2 * np.sin(t0), rev=0.25)
# idée 2 : HAUT · POINTU · ISOLÉ, puis repères
for k in range(3):
    tk = X.P2A[0] + 0.30 + 0.70 * k
    put(tk, pop(620 + 140 * k, 0.09), 0.10, rev=0.2)
x = tl_(0.45)
put(X.P2A[0] + 0.30, np.sin(TAU * np.cumsum(300 * 3 ** (x / x[-1])) / SR) * edec(x, 0.2, 0.01), 0.035, rev=0.3)
put(X.P2A[0] + 1.00, tick(2200, 0.1), 0.08, rev=0.3)
put(X.P2A[0] + 1.70, whoosh(0.4, 1500, 600, 1.0, 0.3), 0.05, pan=-0.5, rev=0.2)
put(X.P2A[0] + 1.70, whoosh(0.4, 1500, 600, 1.0, 0.3), 0.05, pan=0.5, rev=0.2)
x = tl_(0.32)                                           # croix rouge : bip d'erreur
buzz = sum(np.sign(np.sin(TAU * f * x)) * 0.3 for f in (180, 187)) * np.clip((0.32 - x) / 0.04, 0, 1) * np.clip(x / 0.004, 0, 1)
put(X.P2B[0] + 0.5, filt("lowpass", 2500, buzz, 2), 0.06, rev=0.15)
for dt, m in ((0.6, 84), (0.95, 88)):                   # coches vertes
    put(X.P2C[0] + dt, chime((m, m + 7), 1.2, (0.5, 0.35)), 0.07, rev=0.3)
# idée 3 : barres de température (hauteur du son proportionnelle au log de la température)
tb = X.P3A[0] + 0.20
for (lab, val, tv, col, d) in X.ROWS:
    st = 12 * np.log2(tv / 5500.0)
    x = tl_(1.2)
    gl = np.clip(x / 0.6, 0, 1)
    gl = 1 - (1 - gl) ** 3
    f = midi(45 + (12 + st) * gl)
    s = (np.sin(TAU * np.cumsum(f) / SR) + 0.3 * np.sin(2 * TAU * np.cumsum(f) / SR)) * np.clip(x / 0.01, 0, 1) * np.exp(-np.clip(x - 0.6, 0, None) / 0.18)
    put(tb + d + 0.1, s, 0.045, rev=0.35)
put(tb + 2.1, tick(1800, 0.08), 0.07, rev=0.3)
put(X.P3B[0] + 1.3, pop(800, 0.1), 0.09, rev=0.3)
put(X.P3B[0] + 1.32, chime((81, 85, 88), 1.6), 0.05, rev=0.5)
# idée 4 : étincelles sur la victime, puis extinction
t_on, t_off0, t_off1 = X.S[3] + 0.3, X.P4A[0] + 0.4, X.P4A[0] + 1.2
x = tl_(t_off1 - t_on)
tt = t_on + x
aenv = np.clip((tt - t_on) / 0.5, 0, 1) * (1 - np.clip((tt - t_off0) / (t_off1 - t_off0), 0, 1))
cr = np.zeros(len(x))
tc = 0.0
r2 = np.random.default_rng(7)
while tc < x[-1]:
    tc += r2.exponential(0.018)
    k = int(tc * SR)
    m = min(int(0.006 * SR), len(x) - k)
    if m > 0:
        cr[k:k + m] += r2.standard_normal(m) * np.exp(-np.arange(m) / SR / 0.0012) * r2.uniform(0.2, 1.0)
cr = filt("bandpass", (1500, 9000), cr, 2)
hum = sum(np.sin(TAU * 100 * h * x) / h for h in (1, 2, 3, 5)) * (0.6 + 0.4 * (r2.random(len(x)) < 0.7))
put(t_on, np.stack([cr, np.roll(cr, 301)], 1) * (aenv * 0.8)[:, None] + np.stack([hum, hum], 1) * (aenv * 0.05)[:, None], 0.30, rev=0.2)
x = tl_(0.9)                                            # le courant « s'éteint »
put(t_off0, np.tanh(2 * np.sin(TAU * np.cumsum(620 * (80 / 620) ** (x / x[-1])) / SR)) * edec(x, 0.35, 0.005), 0.05, rev=0.3)
put(X.P4B[0] + 0.5, chime((83, 87, 90), 1.6), 0.07, rev=0.4)    # icône de secours
for k, key in enumerate("112"):                          # 1-1-2 sur le clavier
    put(X.P4C[0] + 0.75 + 0.2 * k, dtmf(key), 0.07, rev=0.15)
x = tl_(0.9)
put(X.P4C[0] + 1.55, np.sin(TAU * 440 * x) * np.clip(x / 0.01, 0, 1) * np.clip((0.9 - x) / 0.02, 0, 1), 0.035, rev=0.2)
# fin
put(X.P5A[0] + 0.25, pop(520, 0.12), 0.12, rev=0.3)
put(X.P5A[0] + 0.27, chime((74, 81), 1.4), 0.05, rev=0.4)
put(X.P5B[0] + 0.5, pop(700, 0.09), 0.08, rev=0.3)
put(X.P5B[0] + 1.0, pop(900, 0.09), 0.09, rev=0.3)
put(X.P5B[0] + 1.02, chime((86, 93, 98), 2.0, (1.2, 0.9, 0.6)), 0.05, rev=0.5)

# ------------------------------------------------------------------ musique : nappes et pulsation (100 BPM)
F0, F1, F2, F3 = X.FL
Dm, Bb, Gm, A_, C_, F_ = (50, 57, 62, 65), (46, 53, 58, 62), (43, 50, 55, 58), (45, 52, 57, 61), (48, 55, 60, 64), (41, 48, 53, 57)
Dsus, D_, G_ = (50, 57, 62, 64), (50, 57, 62, 66), (43, 55, 59, 62)
CH = [(0.0, X.G[0]["reveal"], Dm), (X.G[0]["reveal"], 9.2, Bb), (9.2, 12.8, Gm), (12.8, F0, A_),
      (F0, X.G[1]["reveal"], Dm), (X.G[1]["reveal"], 23.5, Bb), (23.5, 27.2, C_), (27.2, 30.0, Gm), (30.0, F1, A_),
      (F1, X.G[2]["reveal"], Dsus), (X.G[2]["reveal"], 40.0, D_), (40.0, 43.0, G_), (43.0, F2, A_),
      (F2, X.G[3]["reveal"], Dm), (X.G[3]["reveal"], 52.4, Bb), (52.4, 56.0, Gm), (56.0, 59.0, F_), (59.0, F3, A_),
      (F3, X.P5B[0], Dm), (X.P5B[0], DUR, Bb)]
for t0, t1, notes in CH:
    put(t0, pad(notes, t1 - t0 + 0.7, 0.5, 0.8, 1300 if notes not in (D_, G_) else 1800), 0.30, rev=0.5, bus=bed)
WIN = [(g["reveal"], g["end"] - 0.55) for g in X.G] + [(X.P5A[0], DUR - 0.2)]
for (w0, w1) in WIN:
    for k, tb_ in enumerate(np.arange(w0, w1, 0.6)):
        x = tl_(0.5)
        f = float(midi(38)) + 45 * np.exp(-x / 0.03)
        kick = np.tanh(2.5 * np.sin(TAU * np.cumsum(f) / SR)) * edec(x, 0.16, 0.002)
        put(tb_, kick, 0.20, bus=bed)
        y = tl_(0.06)
        sh = filt("highpass", 7000, noise(len(y)), 2) * np.exp(-y / 0.012)
        put(tb_ + 0.3, sh, 0.035 if k % 2 else 0.028, pan=0.3, bus=bed)
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
