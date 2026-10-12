#!/usr/bin/env python3
"""Contrôle de synchro son/image sur le fichier encodé : pics de luminosité vs attaques sonores."""
import subprocess
import sys

import numpy as np
from scipy import signal

sys.path.insert(0, "/home/claude/vf")
import ep01x as X  # noqa: E402

f = sys.argv[1]
w, h = 54, 96
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                     capture_output=True, check=True).stdout
v = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(float)
lum = v.mean((1, 2))
tv = np.arange(len(lum)) / 30.0
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                     capture_output=True, check=True).stdout
a = np.frombuffer(pcm, "<i2").astype(float) / 32768
print(f"images décodées : {len(lum)}  ({len(lum) / 30:.3f} s)   audio : {len(a) / 48000:.3f} s")
hp = signal.sosfilt(signal.butter(4, 60, "highpass", fs=48000, output="sos"), a)
hop = 240                                              # 5 ms
e = np.sqrt(np.convolve(hp ** 2, np.ones(hop) / hop, "same")[::hop])
te = np.arange(len(e)) * hop / 48000
de = np.maximum(np.diff(np.log(e + 1e-5)), 0)          # flux d'attaque
events = [("flash", t) for t in X.FL] + [("verdict", g["reveal"]) for g in X.G]
print(f"{'événement':10s} {'prévu':>7s} {'image':>7s} {'son':>7s}  écart son-image")
for name, t0 in events:
    sel = (tv > t0 - 0.25) & (tv < t0 + 0.25)
    dl = np.diff(lum)
    k = np.argmax(np.where(sel[1:], dl, -1e9)) + 1      # plus forte montée de luminosité
    ti = tv[k]
    sa = (te[1:] > t0 - 0.25) & (te[1:] < t0 + 0.25)
    ka = np.argmax(np.where(sa, de, -1e9))
    ta = te[1:][ka]
    print(f"{name:10s} {t0:7.3f} {ti:7.3f} {ta:7.3f}  {1000 * (ta - ti):+6.0f} ms")
