# -*- coding: utf-8 -*-
"""Bande-son synthétisée de la série (48 kHz stéréo), calée sur la chronologie de l'épisode : nappes musicales en
ré mineur, pulsation à 100 BPM pendant les explications, bruitages de l'interface (question, 3-2-1, verdict,
transitions), sons des scènes et des panneaux, ambiance de fond selon le thème. Mastering : -14,5 LUFS, crête vraie
<= -3 dBTP avant encodage AAC."""
import wave

import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d

from . import loudness as LN

SR = 48000
TAU = 2 * np.pi


class Mixer:
    def __init__(self, dur, seed=202):
        self.N = int(round(SR * dur))
        self.dur = dur
        self.rng = np.random.default_rng(seed)
        self.dry = np.zeros((self.N, 2))
        self.send = np.zeros((self.N, 2))
        self.bed = np.zeros((self.N, 2))

    def put(self, t0, sig, gain=1.0, pan=0.0, rev=0.0, bus=None):
        i0 = int(round(t0 * SR))
        if sig.ndim == 1:
            a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
            sig = np.stack([sig * np.cos(a), sig * np.sin(a)], 1) * np.sqrt(2)
        if i0 < 0:
            sig, i0 = sig[-i0:], 0
        n = min(len(sig), self.N - i0)
        if n <= 0:
            return
        (self.dry if bus is None else bus)[i0:i0 + n] += sig[:n] * gain
        self.send[i0:i0 + n] += sig[:n] * gain * rev


# ------------------------------------------------------------------ générateurs
_rng = np.random.default_rng(7)


def midi(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def tl_(d):
    return np.arange(int(round(d * SR))) / SR


def noise(n):
    return _rng.standard_normal(n)


def filt(kind, f, x, order=4):
    return signal.sosfilt(signal.butter(order, f, btype=kind, fs=SR, output="sos"), x, axis=0)


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


def glide(level, dur=1.0):
    """Son montant dont la hauteur finale suit une valeur (barres, échelles)."""
    x = tl_(dur)
    gl = 1 - (1 - np.clip(x / 0.6, 0, 1)) ** 3
    f = midi(52 + 24 * float(np.clip(level, 0, 1)) * gl)
    return ((np.sin(TAU * np.cumsum(f) / SR) + 0.3 * np.sin(2 * TAU * np.cumsum(f) / SR)) * np.clip(x / 0.01, 0, 1)
            * np.exp(-np.clip(x - 0.6, 0, None) / 0.18))


def buzz(dur=0.32):
    x = tl_(dur)
    b = sum(np.sign(np.sin(TAU * f * x)) * 0.3 for f in (180, 187))
    return filt("lowpass", 2500, b * np.clip((dur - x) / 0.04, 0, 1) * np.clip(x / 0.004, 0, 1), 2)


def thunder(dur=3.2, crack=1.0, rumble=1.0, seed=0, bright=1.0):
    r = np.random.default_rng(seed)
    x = tl_(dur)
    n = len(x)
    out = np.zeros((n, 2))
    ck = filt("highpass", 500, r.standard_normal(n)) * np.exp(-x / 0.018) * np.clip(x / 0.0008, 0, 1)
    ck = filt("lowpass", 7000 * bright, ck, 2)
    for ch in range(2):
        rb = filt("lowpass", 170, r.standard_normal(n))
        mod = uniform_filter1d(np.abs(r.standard_normal(n)), int(0.09 * SR))
        mod = mod / (mod.max() + 1e-9)
        env = (1 - np.exp(-x / 0.05)) * np.exp(-x / (dur * 0.33))
        mid = filt("bandpass", (120, 600), r.standard_normal(n), 2) * env * (0.3 + mod)
        out[:, ch] += rumble * (rb * env * (0.4 + 1.2 * mod) * 2.2 + mid * 0.9) + crack * ck * 0.9
    return out


# ------------------------------------------------------------------ ambiances de fond (très discrètes)
def ambience(M, kind):
    N, dur = M.N, M.dur
    x = np.arange(N) / SR
    r = np.random.default_rng(99)
    fade = np.clip(x / 1.5, 0, 1) * np.clip((dur - x) / 1.0, 0, 1)
    if kind == "espace":
        for ch in range(2):
            drone = sum(a * np.sin(TAU * float(midi(m)) * (1 + 0.0012 * (ch - 0.5)) * x + ch)
                        for m, a in ((38, 0.45), (45, 0.30), (50, 0.18), (57, 0.08)))
            air = filt("bandpass", (300, 1400), r.standard_normal(N), 2) * (0.5 + 0.5 * np.sin(TAU * 0.07 * x + ch))
            M.dry[:, ch] += (drone * 0.030 + air * 0.010) * fade
            M.send[:, ch] += drone * 0.010 * fade
        for k, t in enumerate(np.arange(3.0, dur - 2, 7.3)):
            M.put(t, chime((88 + (k % 3) * 2, 95), 3.0, (2.0, 1.4)), 0.020, pan=np.sin(k * 1.9) * 0.6, rev=0.8)
    elif kind == "nature":
        for ch in range(2):
            wind = filt("bandpass", (200, 1200), r.standard_normal(N), 2)
            lfo = 0.5 + 0.5 * np.sin(TAU * 0.09 * x + ch * 1.7) * np.sin(TAU * 0.031 * x)
            M.dry[:, ch] += wind * lfo * 0.020 * fade
        for t in np.arange(2.0, dur - 2, 4.7):
            for j in range(int(r.integers(2, 5))):
                y = tl_(0.09)
                f = r.uniform(2800, 4200) * (1 + 0.35 * np.sin(TAU * 18 * y))
                chirp = np.sin(TAU * np.cumsum(f) / SR) * np.sin(np.pi * y / 0.09) ** 2
                M.put(t + j * 0.13 + r.uniform(0, 0.4), chirp, 0.012, pan=r.uniform(-0.7, 0.7), rev=0.4)
    elif kind == "ocean":
        for ch in range(2):
            sw = 0.5 + 0.5 * np.sin(TAU * x / 8.5 + ch * 0.8) ** 2
            waves = filt("lowpass", 900, r.standard_normal(N), 2) * sw
            M.dry[:, ch] += waves * 0.030 * fade
        for t in np.arange(1.0, dur - 1, 1.3):
            y = tl_(0.06)
            b = np.sin(TAU * np.cumsum(600 + 2600 * y / 0.06) / SR) * np.exp(-y / 0.02)
            M.put(t + r.uniform(0, 0.8), b, 0.010, pan=r.uniform(-0.6, 0.6), rev=0.3)
    elif kind == "orage":
        renv = fade
        for ch in range(2):
            rn = filt("bandpass", (350, 6500), r.standard_normal(N), 2)
            M.dry[:, ch] += rn * 0.022 * renv
        for k, t in enumerate(np.arange(4.0, dur - 3, 9.0)):
            M.put(t, thunder(3.4, 0.25, 0.9, 40 + k, 0.4), 0.18, pan=np.sin(k * 2.1) * 0.5, rev=0.35)
    elif kind == "feu":
        cr = np.zeros(N)
        tc = 0.0
        while tc < dur - 0.1:
            tc += r.exponential(0.035)
            k = int(tc * SR)
            m = min(int(0.006 * SR), N - k)
            if m > 0:
                cr[k:k + m] += r.standard_normal(m) * np.exp(-np.arange(m) / SR / 0.0012) * r.uniform(0.1, 1.0)
        cr = filt("bandpass", (1500, 8000), cr, 2)
        for ch in range(2):
            roar = filt("lowpass", 300, r.standard_normal(N))
            M.dry[:, ch] += (np.roll(cr, ch * 311) * 0.05 + roar * 0.020) * fade
    elif kind == "labo":
        hum = sum(np.sin(TAU * 100 * h * x) / h for h in (1, 2, 3, 5))
        for ch in range(2):
            M.dry[:, ch] += hum * 0.006 * fade
        for k, t in enumerate(np.arange(2.5, dur - 2, 3.9)):
            y = tl_(0.08)
            M.put(t, np.sin(TAU * (1800 + 400 * (k % 3)) * y) * np.exp(-y / 0.03), 0.012, pan=0.5 * np.sin(k), rev=0.3)
    elif kind == "ville":
        for ch in range(2):
            rum = filt("lowpass", 220, r.standard_normal(N))
            traffic = filt("bandpass", (300, 2000), r.standard_normal(N), 2) * (0.5 + 0.5 * np.sin(TAU * 0.05 * x + ch * 2))
            M.dry[:, ch] += (rum * 0.020 + traffic * 0.010) * fade


# ------------------------------------------------------------------ composition
DM, BB, GM, A_, C_, F_ = (50, 57, 62, 65), (46, 53, 58, 62), (43, 50, 55, 58), (45, 52, 57, 61), (48, 55, 60, 64), (41, 48, 53, 57)
DSUS, D_, G_ = (50, 57, 62, 64), (50, 57, 62, 66), (43, 55, 59, 62)


def build(ep, ambiance="aucune", seed=202):
    """Mixage complet (avant mastering) pour un objet Episode."""
    TL = ep.TL
    M = Mixer(TL.DUR, seed)
    put = M.put
    G = TL.G
    # ouverture
    put(0.0, sub_hit(0.9, 1.4, 38, 90), 0.55)
    put(0.02, chime((74, 81, 86), 2.4, (1.3, 1.0, 0.8)), 0.05, rev=0.6)
    put(0.45, pop(620, 0.1), 0.08, rev=0.3)
    # question, compte à rebours, verdict
    for g in G:
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
        if ep.verdicts[i] == "FAUX":
            put(tr + 0.01, chord_stab((50, 51, 57)), 0.10, rev=0.35)
        else:
            put(tr + 0.01, chord_stab((62, 66, 69, 74), 1.4, 2600, 0.5), 0.09, rev=0.45)
            put(tr + 0.02, chime((86, 90, 93), 2.4), 0.07, rev=0.5)
        put(g["body"] - 0.45, whoosh(0.42, 500, 3000, 1.0, 0.5), 0.05, pan=0.25, rev=0.25)
    # transitions (flash blanc)
    for tf in TL.FL:
        put(tf - 0.85, riser(0.85, 400, 7000, 1.6, 2.4), 0.07, rev=0.3)
        x = tl_(0.85)
        sw = np.sin(TAU * np.cumsum(110 * 4 ** ((x / x[-1]) ** 1.6)) / SR) * (x / x[-1]) ** 2.5
        put(tf - 0.85, sw, 0.025, rev=0.3)
        put(tf, sub_hit(0.8, 1.0, 36, 80), 0.45)
        x = tl_(0.3)                                     # impact large bande, calé sur le flash blanc
        put(tf, filt("lowpass", 1400, noise(len(x))) * np.exp(-x / 0.035) * np.clip(x / 0.0015, 0, 1), 0.60)
        put(tf, filt("bandpass", (1500, 6500), noise(len(x)), 2) * np.exp(-x / 0.014) * np.clip(x / 0.001, 0, 1), 0.32,
            rev=0.2)
    # événements des panneaux et des scènes
    for (t, kind, p) in ep.events():
        if kind == "entree":
            put(t, whoosh(0.40, 800, 5000, 1.1, 0.55), 0.045, pan=0.2 * np.sin(t), rev=0.25)
        elif kind == "pop":
            put(t, pop(p.get("f", 520), 0.09), 0.09 * p.get("g", 1.0), rev=0.25)
        elif kind == "ding":
            put(t, pop(820, 0.09), 0.08, rev=0.3)
            put(t + 0.02, chime((86, 93), 1.4, (0.8, 0.6)), 0.05, rev=0.5)
        elif kind == "tic":
            put(t, tick(2200, 0.08), 0.10, rev=0.3)
        elif kind == "glisse":
            put(t, glide(p.get("niveau", 0.5), 1.2), 0.045, rev=0.35)
        elif kind == "compteur":
            d = p.get("duree", 1.6)
            n = 14
            for k in range(n):
                tk = t + d * (1 - (1 - (k + 1) / n) ** 0.5)
                put(tk, tick(1600 + 40 * k, 0.03), 0.05, rev=0.15)
        elif kind == "barre":
            put(t, whoosh(0.30, 2500, 700, 1.0, 0.3), 0.09, rev=0.2)
            put(t + 0.05, buzz(0.28), 0.05, rev=0.15)
    # conclusion
    put(TL.P5A[0] + 0.25, pop(520, 0.12), 0.12, rev=0.3)
    put(TL.P5A[0] + 0.27, chime((74, 81), 1.4), 0.05, rev=0.4)
    put(TL.P5B[0] + 0.5, pop(700, 0.09), 0.08, rev=0.3)
    put(TL.P5B[0] + 1.0, pop(900, 0.09), 0.09, rev=0.3)
    put(TL.P5B[0] + 1.02, chime((86, 93, 98), 2.0, (1.2, 0.9, 0.6)), 0.05, rev=0.5)
    # musique : nappes (accords qui changent au verdict) + pulsation à 100 BPM
    CH = []
    for i, g in enumerate(G):
        e = g["end"]
        b = g["body"]
        span = e - b
        if ep.verdicts[i] == "FAUX":
            seq = (DM, BB, GM, A_)
        else:
            seq = (DSUS, D_, G_, A_)
        t0 = 0.0 if i == 0 else G[i - 1]["end"]
        CH += [(t0, g["reveal"], seq[0]), (g["reveal"], b + 0.35 * span, seq[1]), (b + 0.35 * span, b + 0.72 * span, seq[2]),
               (b + 0.72 * span, e, seq[3])]
    CH += [(G[-1]["end"], TL.P5B[0], DM), (TL.P5B[0], TL.DUR, BB)]
    for t0, t1, notes in CH:
        if t1 - t0 > 0.05:
            put(t0, pad(notes, t1 - t0 + 0.7, 0.5, 0.8, 1300 if notes not in (D_, G_) else 1800), 0.30, rev=0.5, bus=M.bed)
    WIN = [(g["reveal"], g["end"] - 0.55) for g in G] + [(TL.P5A[0], TL.DUR - 0.2)]
    for (w0, w1) in WIN:
        for k, tb_ in enumerate(np.arange(w0, w1, 0.6)):
            x = tl_(0.5)
            f = float(midi(38)) + 45 * np.exp(-x / 0.03)
            kick = np.tanh(2.5 * np.sin(TAU * np.cumsum(f) / SR)) * edec(x, 0.16, 0.002)
            put(tb_, kick, 0.20, bus=M.bed)
            y = tl_(0.06)
            sh = filt("highpass", 7000, noise(len(y)), 2) * np.exp(-y / 0.012)
            put(tb_ + 0.3, sh, 0.035 if k % 2 else 0.028, pan=0.3, bus=M.bed)
    if ambiance and ambiance != "aucune":
        ambience(M, ambiance)
    M.dry += M.bed
    M.send += M.bed * 0.3
    return M


def make_ir(sec=2.6, seed=3):
    r = np.random.default_rng(seed)
    n = int(sec * SR)
    t_ = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for ch in range(2):
        ir[:, ch] = (0.5 * filt("highpass", 1500, r.standard_normal(n)) * np.exp(-6.9 * t_ / 0.9)
                     + filt("lowpass", 2500, r.standard_normal(n)) * np.exp(-6.9 * t_ / 2.2))
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]
    return ir / np.sqrt((ir ** 2).sum(0))


def render(ep, out_wav, ambiance="aucune", target_lufs=-14.5, ceiling_db=-3.0):
    M = build(ep, ambiance)
    ir = make_ir()
    wet = np.stack([signal.fftconvolve(M.send[:, ch], ir[:, ch])[:M.N] for ch in range(2)], 1)
    mix = M.dry + wet * 0.5
    mix = signal.sosfilt(signal.butter(2, 28, "highpass", fs=SR, output="sos"), mix, axis=0)
    # saturation douce des pointes (comme les épisodes 1 et 2), puis filtre de confort
    mix *= 1.28
    T = 0.55
    a = np.abs(mix)
    over = a > T
    mix[over] = np.sign(mix[over]) * (T + (1 - T) * np.tanh((a[over] - T) / (1 - T)))
    mix = signal.sosfilt(signal.butter(2, 15000, "lowpass", fs=SR, output="sos"), mix, axis=0)
    out, info = LN.master(mix, target_lufs, ceiling_db)
    fade = int(0.004 * SR)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    pcm = np.clip(out * 32767, -32768, 32767).astype("<i2")
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    info["duree"] = len(pcm) / SR
    return info
