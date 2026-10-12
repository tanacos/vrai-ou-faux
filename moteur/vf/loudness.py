# -*- coding: utf-8 -*-
"""Mesure de sonie (UIT-R BS.1770-4 / EBU R128) et limiteur de crête vraie, sans dépendance externe."""
import json
import re
import subprocess

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, uniform_filter1d

SR = 48000


def _kweight(x):
    """Filtre de pondération K pour 48 kHz (coefficients de la norme)."""
    b1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    a1 = [1.0, -1.69065929318241, 0.73248077421585]
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, -1.99004745483398, 0.99007225036621]
    y = signal.lfilter(b1, a1, x, axis=0)
    return signal.lfilter(b2, a2, y, axis=0)


def integrated_lufs(x, sr=SR):
    """Sonie intégrée (LUFS) d'un signal (N,) ou (N, 2), blocs de 400 ms, recouvrement 75 %, double porte."""
    if x.ndim == 1:
        x = x[:, None]
    y = _kweight(x)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    n = 1 + max(0, (len(y) - blk) // hop)
    p = y ** 2
    cs = np.cumsum(np.vstack([np.zeros((1, p.shape[1])), p]), axis=0)
    idx = np.arange(n) * hop
    ms = (cs[idx + blk] - cs[idx]) / blk
    z = ms.sum(1)
    L = -0.691 + 10 * np.log10(np.maximum(z, 1e-12))
    g = L > -70
    if not g.any():
        return -70.0
    rel = -0.691 + 10 * np.log10(z[g].mean()) - 10
    g2 = g & (L > rel)
    return float(-0.691 + 10 * np.log10(z[g2].mean()))


def true_peak_db(x, os=4):
    """Crête vraie (dBTP) par suréchantillonnage x4."""
    if x.ndim == 1:
        x = x[:, None]
    up = signal.resample_poly(x, os, 1, axis=0)
    return float(20 * np.log10(np.abs(up).max() + 1e-12))


def limiter(x, ceiling_db=-3.0, look_ms=3.0, rel_ms=60.0, os=4):
    """Limiteur à anticipation : le gain est calculé sur le signal suréchantillonné (crête vraie)."""
    ceil = 10 ** (ceiling_db / 20)
    up = signal.resample_poly(x, os, 1, axis=0)
    pk = np.abs(up).max(1).reshape(-1, os).max(1)[:len(x)]
    if len(pk) < len(x):
        pk = np.pad(pk, (0, len(x) - len(pk)), mode="edge")
    look = max(int(look_ms * 1e-3 * SR), 1)
    pk = maximum_filter1d(pk, size=2 * look + 1)
    g = np.minimum(1.0, ceil / np.maximum(pk, 1e-9))
    g = uniform_filter1d(g, size=look)
    # relâchement exponentiel (le gain remonte lentement, redescend instantanément)
    rel = np.exp(-1 / (rel_ms * 1e-3 * SR))
    gl = g.tolist()
    for i in range(1, len(gl)):
        if gl[i] > gl[i - 1]:
            gl[i] = gl[i - 1] * rel + gl[i] * (1 - rel)
    g = np.minimum(np.array(gl), g)
    return x * g[:, None], float(-20 * np.log10(g.min() + 1e-12))


def master(mix, target_lufs=-14.5, ceiling_db=-3.0, iters=4):
    """Normalise la sonie intégrée sur la cible et garantit une crête vraie <= plafond (plusieurs passes)."""
    out = mix.copy()
    gain = 0.0
    gr = 0.0
    for _ in range(iters):
        L = integrated_lufs(out)
        d = target_lufs - L
        if abs(d) < 0.15 and true_peak_db(out) <= ceiling_db + 0.05:
            break
        gain += d
        out = mix * 10 ** (gain / 20)
        out, gr = limiter(out, ceiling_db)
    # dernière sécurité : rognage doux sous le plafond
    tp = true_peak_db(out)
    if tp > ceiling_db:
        out *= 10 ** ((ceiling_db - tp - 0.05) / 20)
    return out, dict(lufs=integrated_lufs(out), true_peak=true_peak_db(out), gain_db=gain, max_gr_db=gr)


def ffmpeg_measure(path):
    """Mesure indépendante par FFmpeg (filtre ebur128) d'un fichier audio ou vidéo : LUFS intégrés, crête vraie, LRA."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    s = txt[txt.rfind("Summary:"):]
    I = re.search(r"I:\s+(-?[\d.]+) LUFS", s)
    LRA = re.search(r"LRA:\s+(-?[\d.]+) LU", s)
    TP = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    return dict(lufs=float(I.group(1)) if I else None, lra=float(LRA.group(1)) if LRA else None,
                true_peak=float(TP.group(1)) if TP and TP.group(1) != "-inf" else None)


if __name__ == "__main__":
    import sys
    print(json.dumps(ffmpeg_measure(sys.argv[1]), indent=1))
