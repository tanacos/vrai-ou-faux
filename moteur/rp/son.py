# -*- coding: utf-8 -*-
"""Bande-son générique des reportages : nappes selon l'« ambiance » de chaque scène, bruitages calés sur les
événements des scènes (paliers, chiffres, anneaux, trajets, impacts), voix traitée, effacement de la musique sous la
voix, mastering -14,5 LUFS (crête vraie <= -3 dBTP avant AAC). Tout est synthétisé : aucune musique sous droits.

    python3 -m rp.son DOSSIER        -> DOSSIER/sortie/audio.wav (à partir de chrono.json et sortie/voix.npy)

Ambiances : mystere, emerveillement, calme, tension, resolution, triomphe."""
import json
import os
import sys

import numpy as np
from scipy import signal

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "rp"

from vf import sound as S  # noqa: E402
from vf import voix as V  # noqa: E402
from vf import loudness as LN  # noqa: E402

from . import rendu as R  # noqa: E402

SR = S.SR
TAU = 2 * np.pi

# accords (notes MIDI) par ambiance : suites jouées au fil des titres de la scène
ACCORDS = {
    "mystere": [(50, 57, 62, 64), (46, 53, 58, 62, 65), (48, 55, 60, 62), (45, 52, 57, 60, 64)],
    "emerveillement": [(46, 53, 58, 62, 69), (41, 48, 53, 57, 64), (48, 55, 60, 64, 67), (50, 57, 62, 65, 69)],
    "calme": [(43, 50, 55, 58, 62), (46, 53, 58, 62, 65), (41, 48, 53, 57, 60)],
    "tension": [(50, 57, 62, 65), (49, 56, 61, 64), (46, 53, 58, 62), (45, 52, 57, 61, 64)],
    "resolution": [(50, 57, 62, 66, 69), (47, 54, 59, 62, 66)],
    "triomphe": [(50, 57, 62, 66, 69), (45, 52, 57, 61, 64, 69)],
}
COUPURE = {"mystere": 1100, "emerveillement": 1900, "calme": 1000, "tension": 1300, "resolution": 2200,
           "triomphe": 2400}


def pad_layer(M, t0, t1, notes, gain, cutoff=1300, att=1.2, rel=1.6, rev=0.6):
    if t1 - t0 > 0.1:
        M.put(t0, S.pad(notes, t1 - t0 + rel, att, rel, cutoff), gain, rev=rev, bus=M.bed)


def drone(dur, f0, seed=1):
    """Nappe grave qui respire (deux sinus désaccordés + souffle filtré)."""
    x = S.tl_(dur)
    r = np.random.default_rng(seed)
    out = np.zeros((len(x), 2))
    for ch in range(2):
        d = 1 + 0.002 * (ch - 0.5)
        s = np.sin(TAU * f0 * d * x) + 0.45 * np.sin(TAU * 2 * f0 * d * x + 1.3) + 0.2 * np.sin(TAU * 3 * f0 * x + ch)
        air = S.filt("bandpass", (250, 900), r.standard_normal(len(x)), 2) * 0.25
        lfo = 0.75 + 0.25 * np.sin(TAU * 0.11 * x + ch)
        out[:, ch] = (s * 0.5 + air) * lfo
    env = np.clip(x / 1.5, 0, 1) * np.clip((dur - x) / 1.5, 0, 1)
    return out * env[:, None]


def shimmer(dur, notes, seed=3):
    """Scintillement aigu (cloches très douces en arpège aléatoire) : le vide, l'espace."""
    r = np.random.default_rng(seed)
    out = np.zeros((int(dur * SR) + SR * 3, 2))
    t = 0.0
    while t < dur:
        m = notes[r.integers(0, len(notes))]
        c = S.chime((m,), 2.4, (1.6,))
        pan = r.uniform(-0.7, 0.7)
        a = (pan + 1) * np.pi / 4
        i0 = int(t * SR)
        out[i0:i0 + len(c), 0] += c * np.cos(a)
        out[i0:i0 + len(c), 1] += c * np.sin(a)
        t += r.uniform(0.35, 0.8)
    return out[:int(dur * SR)]


def battement(M, t0, t1, bpm=80, gain=0.18):
    """Pulsation grave (deux coups par battement) : la tension monte."""
    step = 60.0 / bpm
    t = t0
    while t < t1:
        x = S.tl_(0.45)
        f = float(S.midi(36)) + 40 * np.exp(-x / 0.025)
        kick = np.tanh(2.2 * np.sin(TAU * np.cumsum(f) / SR)) * S.edec(x, 0.13, 0.002)
        ramp = 0.55 + 0.45 * (t - t0) / max(t1 - t0, 1e-3)
        M.put(t, kick, gain * ramp, bus=M.bed)
        M.put(t + 0.24, kick * 0.6, gain * 0.55 * ramp, bus=M.bed)
        t += step


def transposer(notes, k):
    return tuple(n + k for n in notes)


def build(chrono, episode=None):
    R.setup(chrono, episode)
    dur = R.DUR
    M = S.Mixer(dur, seed=7 + int(R.EP.get("numero", 1)))
    tr = [0, 2, -2, 3, -3][int(R.EP.get("numero", 1)) % 5]        # tonalité qui varie d'un épisode à l'autre
    fx = np.zeros((M.N, 2))

    def sfx(t, sig, gain, pan=0.0, rev=0.25):
        M.put(max(t, 0.0), sig, gain, pan, rev, bus=fx)

    # ------------------------------------------------ musique (bus « bed », effacée sous la voix)
    M.put(0.0, drone(dur + 0.5, float(S.midi(38 + tr))), 0.09, bus=M.bed)
    for k, (bl, sc) in enumerate(R.SCENES):
        amb = sc.spec.get("ambiance", "mystere")
        acc = ACCORDS.get(amb, ACCORDS["mystere"])
        t0, t1 = max(sc.s0 - 0.2, 0.0), sc.s1 + 0.3
        changes = sorted({t0} | {x[0] for x in sc.titres if t0 < x[0] < t1 - 0.8})
        changes.append(t1)
        for j, (a0, a1) in enumerate(zip(changes[:-1], changes[1:])):
            pad_layer(M, a0, a1 + 0.25, transposer(acc[j % len(acc)], tr), 0.24, COUPURE.get(amb, 1400), 0.5, 1.0)
        if amb in ("mystere", "emerveillement"):
            M.put(t0 + 0.2, shimmer(max(t1 - t0 - 0.2, 0.5), tuple(n + tr for n in (86, 89, 93, 96, 98)),
                                    seed=11 + k), 0.03, rev=0.9, bus=M.bed)
        if amb == "tension":
            battement(M, t0 + 0.4, t1 - 0.2, 80, 0.18)
        if amb in ("resolution", "triomphe"):
            M.put(t0, drone(t1 - t0 + 1.0, float(S.midi(26 + tr)), 12), 0.14, bus=M.bed)

    # ------------------------------------------------ bruitages (bus sec, moins effacés)
    sfx(0.0, S.sub_hit(0.8, 1.4, 38, 90), 0.40, rev=0.0)
    sfx(0.02, S.chime(transposer((74, 81, 86), tr), 2.4, (1.3, 1.0, 0.8)), 0.06, rev=0.6)
    for k in range(1, len(R.SCENES)):
        b0 = R.BOUNDS[k]
        sfx(b0 - 0.45, S.whoosh(0.65, 400, 5200, 1.1, 0.65), 0.07, pan=0.2 * np.sin(b0))
    for _, sc in R.SCENES:
        for e in sc.evenements():
            t, k = e["t"], e["type"]
            if k == "impact":
                sfx(t, S.sub_hit(0.9, 1.3, 38, 100), 0.50, rev=0.0)
                sfx(t + 0.01, S.chime(transposer((86, 90, 93), tr), 2.4), 0.05, rev=0.5)
            elif k == "impact_doux":
                sfx(t, S.sub_hit(0.6, 0.9, 44, 70), 0.22, rev=0.0)
            elif k == "whoosh":
                if e.get("sens") == "entree":
                    sfx(t, S.whoosh(0.55, 3000, 300, 1.2, 0.6), 0.07)
                else:
                    sfx(t, S.whoosh(0.55, 300, 3000, 1.2, 0.6), 0.07)
            elif k == "compte":
                n = 14
                for j in range(n):
                    sfx(t + e.get("duree", 0.9) * (1 - (1 - (j + 1) / n) ** 0.5), S.tick(1500 + 50 * j, 0.03), 0.045,
                        rev=0.15)
            elif k == "pop":
                sfx(t, S.pop(820, 0.1), 0.09, rev=0.4)
                sfx(t + 0.02, S.chime(transposer((86, 93), tr), 1.4, (0.8, 0.6)), 0.04, rev=0.5)
            elif k == "pop_doux":
                sfx(t, S.pop(640, 0.09), 0.06, rev=0.3)
            elif k == "apparition":
                sfx(t, S.chime(transposer((81, 88), tr), 1.8, (1.0, 0.8)), 0.04, rev=0.7)
            elif k == "anneau":
                sfx(t, S.sub_hit(0.5, 0.9, 46, 70), 0.20, rev=0.0)
                sfx(t, S.chime(transposer((88, 93), tr), 2.0, (1.2, 0.9)), 0.04, rev=0.7)
            elif k == "ouverture":
                sfx(t - 0.3, S.riser(1.0, 300, 4000, 1.4, 1.8), 0.04)
                sfx(t + 0.7, S.chime(transposer((86, 90, 93, 98), tr), 3.0, (1.8, 1.4, 1.0, 0.8)), 0.05, rev=0.7)
            elif k == "montee":
                d = max(e.get("fin", t + 1.0) - t, 0.4)
                sfx(t, S.riser(d, 250, 5000, 1.5, 2.0), 0.06)
            elif k == "arrivee":
                sfx(t, S.sub_hit(0.8, 1.2, 40, 90), 0.40, rev=0.0)
                sfx(t + 0.01, S.chord_stab(transposer((62, 66, 69, 74), tr), 1.4, 2400, 0.5), 0.05, rev=0.5)
            elif k == "impact_final":
                sfx(t, S.sub_hit(1.0, 1.8, 34, 120), 0.55, rev=0.0)
                sfx(t + 0.02, S.chime(transposer((86, 90, 93, 98), tr), 3.0, (1.8, 1.4, 1.0, 0.8)), 0.06, rev=0.7)
    return M, fx


def render(chrono, voix_npy, out_wav, episode=None):
    M, fx = build(chrono, episode)
    ir = S.make_ir()
    wet = np.stack([signal.fftconvolve(M.send[:, c], ir[:, c])[:M.N] for c in range(2)], 1)
    lit = M.bed + wet * 0.45
    lit = signal.sosfilt(signal.butter(2, 30, "highpass", fs=SR, output="sos"), lit, axis=0)
    voix = np.load(voix_npy)
    v = np.zeros(M.N)
    i0 = int(round(R.T0 * SR))
    n = min(len(voix), M.N - i0)
    v[i0:i0 + n] = voix[:n]
    Lv = LN.integrated_lufs(np.stack([v, v], 1))
    Ll = LN.integrated_lufs(lit)
    lit *= 10 ** (((Lv - 17.0) - Ll) / 20)
    Lf = LN.integrated_lufs(fx + 1e-9)
    fx *= 10 ** (((Lv - 13.0) - Lf) / 20)
    mix, info = V.mixer(v, lit, fx, ducking_db=-8.0)
    fade = int(0.02 * SR)
    mix[:int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))[:, None]
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    V.ecrire_wav(out_wav, mix)
    info.update(lufs_voix_seule=round(Lv, 2), duree=round(M.N / SR, 3))
    return info


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    d = os.path.abspath(sys.argv[1])
    print(json.dumps(render(os.path.join(d, "chrono.json"), os.path.join(d, "sortie", "voix.npy"),
                            os.path.join(d, "sortie", "audio.wav"), os.path.join(d, "episode.json")), indent=1))
