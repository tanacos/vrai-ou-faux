# -*- coding: utf-8 -*-
"""INFINIMENT — ép. 1 : bande-son (musique d'ambiance, bruitages calés sur les mots, voix ElevenLabs), mixage avec
effacement de la musique sous la voix, mastering -14,5 LUFS (crête vraie <= -3 dBTP avant AAC).

  python3 son.py chrono.json voix.npy sortie.wav
"""
import json
import os
import sys

import numpy as np
from scipy import signal

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(ICI)))
sys.path.insert(0, os.path.join(RACINE, "moteur"))

from vf import sound as S  # noqa: E402
from vf import voix as V  # noqa: E402
from vf import loudness as LN  # noqa: E402

SR = S.SR
TAU = 2 * np.pi
T0 = 0.30                                   # même avance que l'image (rendu.py)


def charger(chrono):
    ch = json.load(open(chrono, encoding="utf-8"))

    def cue(key, n=0, default=None):
        v = ch["reperes"].get(key)
        if v and len(v) > n:
            return v[n] + T0
        if default is None:
            raise KeyError(key)
        return default

    def bloc(name):
        s, e = ch["blocs"][name]
        return s + T0, e + T0
    return ch, cue, bloc


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


def heartbeat(M, t0, t1, bpm=84, gain=0.20):
    """Pulsation grave (deux coups par battement) pour la tension de l'expérience."""
    step = 60.0 / bpm
    t = t0
    k = 0
    while t < t1:
        x = S.tl_(0.45)
        f = float(S.midi(36)) + 40 * np.exp(-x / 0.025)
        kick = np.tanh(2.2 * np.sin(TAU * np.cumsum(f) / SR)) * S.edec(x, 0.13, 0.002)
        ramp = 0.55 + 0.45 * (t - t0) / max(t1 - t0, 1e-3)
        M.put(t, kick, gain * ramp, bus=M.bed)
        M.put(t + 0.24, kick * 0.6, gain * 0.55 * ramp, bus=M.bed)
        t += step
        k += 1


def build(chrono):
    ch, cue, bloc = charger(chrono)
    dur = ch["duree"] + T0 + 0.25
    M = S.Mixer(dur, seed=7)
    put = M.put
    B = {k: bloc(k) for k in ch["blocs"]}
    D, BB, G, A, C, F = (50, 57, 62, 65, 69), (46, 53, 58, 62, 65), (43, 50, 55, 58, 62), (45, 52, 57, 61, 64), \
        (48, 55, 60, 64, 67), (41, 48, 53, 57, 60)
    DMAJ = (50, 57, 62, 66, 69)

    # ------------------------------------------------ musique (bus « bed », effacé sous la voix)
    hs, he = 0.0, B["descente"][0]
    pad_layer(M, hs, cue("hook:sucre") - 0.3, (50, 57, 62, 64), 0.22, 1100, 0.6)
    pad_layer(M, cue("hook:sucre") - 0.3, he + 0.4, (46, 53, 58, 62, 65), 0.26, 1500, 0.4)
    put(0.0, drone(B["atome"][0] + 1.0, float(S.midi(38))), 0.10, bus=M.bed)
    # descente : accords qui descendent, filtre qui se referme
    ds, de = B["descente"]
    marks = [ds, cue("descente:peau"), cue("descente:cellules"), cue("descente:adn"), cue("descente:atomes"), de + 0.3]
    for (a0, a1), notes, cut in zip(zip(marks[:-1], marks[1:]), (G, F, (44, 51, 56, 60), (43, 50, 55, 58), D),
                                    (1700, 1450, 1250, 1050, 900)):
        pad_layer(M, a0 - 0.15, a1 + 0.2, notes, 0.24, cut, 0.35, 0.9)
    # atome : le vide (drone grave + scintillements)
    as_, ae = B["atome"]
    put(as_, drone(ae - as_ + 9.0, float(S.midi(38)), 4), 0.12, bus=M.bed)
    put(as_ + 0.3, shimmer(ae - as_ + 8.0, (86, 89, 93, 96, 98)), 0.035, rev=0.9, bus=M.bed)
    pad_layer(M, cue("atome:noyau") - 0.2, ae + 0.5, (45, 52, 57, 60, 64), 0.16, 1000, 1.2)
    # stade et masse
    ss, se = B["stade"]
    pad_layer(M, ss - 0.2, se + 0.3, (45, 52, 57, 60, 64), 0.20, 1300, 0.8)
    ms, me = B["masse"]
    pad_layer(M, ms - 0.2, me + 0.4, F, 0.24, 1600, 0.5)
    # expérience : tension (pulsation qui monte), puis résolution majeure sur « sucre »
    es, ee = B["experience"]
    t_sucre2 = cue("experience:sucre", 1)
    seq = [(es - 0.2, cue("experience:dense"), D), (cue("experience:dense"), cue("experience:nasa"), BB),
           (cue("experience:nasa"), cue("experience:lhumanite"), G), (cue("experience:lhumanite"), cue("experience:tiendrait"), A),
           (cue("experience:tiendrait"), t_sucre2, (45, 52, 57, 61, 64, 69)), (t_sucre2, ee + 1.0, DMAJ)]
    for a0, a1, notes in seq:
        pad_layer(M, a0, a1 + 0.25, notes, 0.25 if notes != DMAJ else 0.30, 1500 if notes != DMAJ else 2200, 0.4, 1.0)
    heartbeat(M, cue("experience:prend"), cue("experience:tiendrait"), 84, 0.22)
    # étoile : drone énorme + scintillement
    ts, te = B["etoile"]
    put(ts - 0.2, drone(te - ts + 1.5, float(S.midi(33)), 9), 0.20, bus=M.bed)
    put(ts, shimmer(te - ts, (81, 86, 88, 93)), 0.04, rev=0.9, bus=M.bed)
    pad_layer(M, ts - 0.2, te + 0.3, (45, 52, 57, 64, 69), 0.20, 1800, 0.5)
    # chaise : intime, puis accord final
    cs, ce = B["chaise"]
    t_au = cue("chaise:au", 0, cue("chaise:toucher"))       # sans la chute finale : l'accord arrive sur « Toucher »
    pad_layer(M, cs - 0.2, t_au, (43, 50, 55, 58, 62), 0.20, 1100, 0.8)
    pad_layer(M, t_au - 0.1, ce + 0.6, (46, 53, 58, 62, 65, 69), 0.24, 1700, 1.0, 1.4)
    for k, tt in enumerate(np.arange(cs + 0.3, t_au - 0.3, 0.86)):
        put(tt, S.chime(((74, 77, 81, 79)[k % 4],), 1.6, (0.9,)), 0.030, pan=0.3 * np.sin(k), rev=0.7, bus=M.bed)
    # fin : montée vers l'infiniment grand
    os_, oe = B["outro"]
    pad_layer(M, os_ - 0.2, dur, DMAJ, 0.26, 2400, 0.5, 0.8)
    put(os_, drone(dur - os_, float(S.midi(26)), 12), 0.16, bus=M.bed)

    # ------------------------------------------------ bruitages (bus sec, moins effacés)
    fx = np.zeros((M.N, 2))

    def sfx(t, sig, gain, pan=0.0, rev=0.25):
        M.put(t, sig, gain, pan, rev, bus=fx_bus)

    fx_bus = fx
    # ouverture : impact + scintillement sur la 1re image
    sfx(0.0, S.sub_hit(0.8, 1.4, 38, 90), 0.40, rev=0.0)
    sfx(0.02, S.chime((74, 81, 86), 2.4, (1.3, 1.0, 0.8)), 0.06, rev=0.6)
    # essaim et compteur
    sfx(cue("hook:lhumanite") - 0.1, S.whoosh(0.9, 300, 4000, 1.0, 0.4), 0.06, pan=-0.2)
    t_huit = cue("hook:huit")
    for k in range(18):
        tk = t_huit - 0.3 + 1.3 * (1 - (1 - (k + 1) / 18) ** 0.5)
        sfx(tk, S.tick(1500 + 40 * k, 0.03), 0.045, rev=0.15)
    # narration v6 : « tiendrait » (v5 : « pourrait tenir »)
    t_tenir = cue("hook:tiendrait", 0, cue("hook:pourrait", 0, cue("hook:sucre") - 1.2))
    sfx(t_tenir - 0.1, S.riser(cue("hook:sucre") - t_tenir + 0.1, 300, 5000), 0.05)
    sfx(cue("hook:sucre"), S.sub_hit(1.0, 1.3, 40, 100), 0.55, rev=0.0)
    sfx(cue("hook:sucre") + 0.01, S.chime((86, 90, 93), 2.4), 0.05, rev=0.5)
    # transitions entre blocs : souffle
    for name in ("descente", "atome", "stade", "masse", "experience", "etoile", "chaise", "outro"):
        b0 = B[name][0]
        sfx(b0 - 0.55, S.whoosh(0.65, 400, 5200, 1.1, 0.65), 0.07, pan=0.2 * np.sin(b0))
    # descente : quatre plongées
    for key in ("descente:peau", "descente:cellules", "descente:adn", "descente:atomes"):
        t = cue(key)
        sfx(t - 0.35, S.whoosh(0.5, 3000, 300, 1.2, 0.6), 0.07)
        sfx(t, S.sub_hit(0.6, 0.9, 44, 70), 0.22, rev=0.0)
    # atome
    sfx(cue("atome:vide"), S.chime((93, 98), 2.6, (1.8, 1.4)), 0.05, rev=0.9)
    sfx(cue("atome:noyau"), S.pop(820, 0.1), 0.10, rev=0.4)
    sfx(cue("atome:cent"), S.sub_hit(0.7, 1.0, 40, 80), 0.30, rev=0.0)
    # stade
    sfx(cue("stade:stade") - 0.1, S.whoosh(0.6, 500, 3500, 1.0, 0.5), 0.06)
    x = S.tl_(0.5)
    buzz = np.sin(TAU * 610 * x + 3 * np.sin(TAU * 31 * x)) * np.clip(x / 0.05, 0, 1) * np.clip((0.5 - x) / 0.15, 0, 1)
    sfx(cue("stade:moustique"), S.filt("bandpass", (400, 3000), buzz, 2), 0.035, pan=0.3)
    sfx(cue("stade:rien"), S.chime((98,), 2.0, (1.5,)), 0.04, rev=0.9)
    # masse : compteur 99,9 %
    t99 = cue("masse:999%")
    for k in range(14):
        sfx(t99 - 0.2 + 1.0 * (1 - (1 - (k + 1) / 14) ** 0.5), S.tick(1600 + 50 * k, 0.03), 0.05, rev=0.15)
    sfx(t99 + 0.85, S.pop(900, 0.1), 0.10, rev=0.4)
    sfx(t99 + 0.87, S.chime((86, 93), 1.4, (0.8, 0.6)), 0.05, rev=0.5)
    # expérience
    sfx(cue("experience:retire") - 0.1, S.whoosh(1.2, 4000, 400, 1.0, 0.3), 0.07)
    sfx(cue("experience:tasse"), S.riser(cue("experience:dense") - cue("experience:tasse"), 200, 3000, 1.5, 1.6), 0.05)
    sfx(cue("experience:dense"), S.sub_hit(1.0, 1.3, 36, 90), 0.50, rev=0.0)
    sfx(cue("experience:nasa"), S.pop(640, 0.1), 0.09, rev=0.3)
    sfx(cue("experience:milliard"), S.sub_hit(0.7, 1.0, 42, 80), 0.28, rev=0.0)
    sfx(cue("experience:lhumanite"), S.pop(520, 0.1), 0.09, rev=0.3)
    sfx(cue("experience:tiendrait"), S.riser(t_sucre2 - cue("experience:tiendrait"), 300, 7000, 1.6, 2.2), 0.08)
    sfx(t_sucre2, S.sub_hit(1.0, 1.4, 38, 110), 0.62, rev=0.0)
    sfx(t_sucre2 + 0.01, S.chord_stab((62, 66, 69, 74), 1.6, 2600, 0.55), 0.06, rev=0.5)
    sfx(t_sucre2 + 0.02, S.chime((86, 90, 93), 2.6), 0.07, rev=0.5)
    # étoile
    sfx(cue("etoile:etoile"), S.sub_hit(1.0, 1.6, 33, 120), 0.55, rev=0.0)
    sfx(cue("etoile:etoile"), S.thunder(2.6, 0.0, 0.6, 5, 0.3), 0.10, rev=0.3)
    sfx(cue("etoile:kilometres"), S.pop(700, 0.1), 0.08, rev=0.3)
    # chaise
    sfx(cue("chaise:repoussent"), S.whoosh(0.5, 4000, 900, 1.3, 0.2), 0.06, pan=-0.3)
    sfx(cue("chaise:quantique"), S.chime((88, 95), 1.4, (0.7, 0.5)), 0.05, rev=0.6)
    sfx(cue("chaise:toucher"), S.pop(480, 0.12), 0.08, rev=0.3)
    t_touche = cue("chaise:touche", 0, ce)                   # sans la chute finale : impact à la fin de « répulsion »
    sfx(t_au - 0.2, S.riser(t_touche - t_au + 0.6, 200, 2500, 1.4, 1.8), 0.04)
    sfx(t_touche + 0.15, S.sub_hit(0.9, 1.6, 36, 90), 0.45, rev=0.0)
    sfx(t_touche + 0.16, S.chime((74, 81, 86), 2.8, (1.6, 1.2, 0.9)), 0.06, rev=0.7)
    # fin : vitesse lumière
    sfx(os_ - 0.1, S.riser(cue("outro:bord") - os_ + 0.2, 200, 8000, 1.4, 2.0), 0.09)
    sfx(cue("outro:bord") + 0.1, S.sub_hit(1.0, 1.8, 34, 120), 0.55, rev=0.0)
    sfx(cue("outro:bord") + 0.12, S.chime((86, 90, 93, 98), 3.0, (1.8, 1.4, 1.0, 0.8)), 0.06, rev=0.7)
    return M, fx, ch


def render(chrono, voix_npy, out_wav):
    M, fx, ch = build(chrono)
    ir = S.make_ir()
    wet = np.stack([signal.fftconvolve(M.send[:, c], ir[:, c])[:M.N] for c in range(2)], 1)
    lit = M.bed + wet * 0.45
    lit = signal.sosfilt(signal.butter(2, 30, "highpass", fs=SR, output="sos"), lit, axis=0)
    # niveau du lit musical : 18 dB sous la voix avant effacement
    voix = np.load(voix_npy)
    v = np.zeros(M.N)
    i0 = int(round(T0 * SR))
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
    print(json.dumps(render(sys.argv[1], sys.argv[2], sys.argv[3]), indent=1))
