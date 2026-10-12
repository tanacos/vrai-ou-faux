# -*- coding: utf-8 -*-
"""Contrôles qualité automatiques d'une vidéo finale. Chaque contrôle renvoie (nom, ok, détail) ; tout échec bloque la
publication."""
import json
import subprocess

import numpy as np

from . import loudness as LN

FPS = 30


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def faststart(path):
    """Vrai si l'atome moov précède mdat (lecture immédiate en streaming)."""
    with open(path, "rb") as f:
        head = f.read(1 << 20)
    i_moov, i_mdat = head.find(b"moov"), head.find(b"mdat")
    return i_moov != -1 and (i_mdat == -1 or i_moov < i_mdat)


def decode_small(path, w=54, h=96):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)


def decode_audio(path):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, "<i2").astype(np.float64) / 32768


def sync_offsets(v, a, flashes):
    """Écart son/image à chaque flash de transition : montée de luminosité la plus forte (image) contre début du
    transitoire le plus fort de la bande 1,5-6,5 kHz (son : l'impact large bande calé sur le flash)."""
    from scipy import signal
    lum = v.mean((1, 2))
    tv = np.arange(len(lum)) / FPS
    dl = np.diff(lum)
    band = signal.sosfilt(signal.butter(4, (1500, 6500), "bandpass", fs=48000, output="sos"), a)
    hop = 48                                             # 1 ms
    env = np.sqrt(np.convolve(band ** 2, np.ones(240) / 240, "same")[::hop])
    te = np.arange(len(env)) * hop / 48000
    out = []
    for t0 in flashes:
        sel = (tv[1:] > t0 - 0.25) & (tv[1:] < t0 + 0.25)
        if not sel.any():
            continue
        k = np.argmax(np.where(sel, dl, -1e9)) + 1
        ti = tv[k]
        w = (te > t0 - 0.15) & (te < t0 + 0.15)
        if not w.any():
            continue
        e = env[w]
        i_pk = int(np.argmax(e))
        above = np.nonzero(e[:i_pk + 1] >= 0.5 * e[i_pk])[0]
        ta = te[w][above[0] if len(above) else i_pk]
        out.append((t0, ti, ta, 1000 * (ta - ti)))
    return out


def run(path, ep, audit_bad=None, size_max_mb=200.0):
    checks = []

    def add(name, ok, detail):
        checks.append(dict(controle=name, ok=bool(ok), detail=detail))

    info = ffprobe(path)
    vs = [s for s in info["streams"] if s["codec_type"] == "video"]
    as_ = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not vs or not as_:
        add("flux", False, "piste vidéo ou audio absente")
        return checks
    v0, a0 = vs[0], as_[0]
    fr = v0.get("r_frame_rate", "0/1").split("/")
    fps = float(fr[0]) / float(fr[1])
    add("format vidéo", v0["codec_name"] == "h264" and v0.get("profile") == "High" and v0["width"] == 1080
        and v0["height"] == 1920 and v0.get("pix_fmt") == "yuv420p" and abs(fps - 30) < 0.01,
        f"{v0['codec_name']} {v0.get('profile')} {v0['width']}x{v0['height']} {v0.get('pix_fmt')} {fps:.2f} i/s")
    add("format audio", a0["codec_name"] == "aac" and int(a0["sample_rate"]) == 48000 and int(a0["channels"]) == 2,
        f"{a0['codec_name']} {a0['sample_rate']} Hz {a0['channels']} canaux")
    dur = float(info["format"]["duration"])
    add("durée", abs(dur - ep.TL.DUR) < 0.15 and dur > 61.0, f"{dur:.2f} s (prévu {ep.TL.DUR:.2f} s, minimum 61 s)")
    mb = float(info["format"]["size"]) / 2 ** 20
    add("poids", mb < size_max_mb, f"{mb:.1f} Mio")
    add("lecture immédiate (faststart)", faststart(path), "atome moov en tête de fichier")
    m = LN.ffmpeg_measure(path)
    add("sonie intégrée", m["lufs"] is not None and -15.5 <= m["lufs"] <= -13.5, f"{m['lufs']} LUFS (cible -14,5 ± 1)")
    add("crête vraie", m["true_peak"] is not None and m["true_peak"] <= -1.0, f"{m['true_peak']} dBTP (maximum -1)")
    v = decode_small(path)
    n_expected = ep.TL.NF
    add("nombre d'images", abs(len(v) - n_expected) <= 1, f"{len(v)} images (prévu {n_expected})")
    lum = v.mean((1, 2))
    black = np.nonzero(lum < 3.0)[0]
    add("pas d'image noire", len(black) == 0, f"{len(black)} image(s) noire(s)" + (f", ex. t={black[0] / FPS:.2f} s" if len(black) else ""))
    d = np.abs(np.diff(v, axis=0)).mean((1, 2))
    still = d < 0.02
    run_, best = 0, 0
    for s in still:
        run_ = run_ + 1 if s else 0
        best = max(best, run_)
    add("pas d'image figée", best < 3 * FPS, f"plus longue séquence immobile : {best / FPS:.2f} s")
    a = decode_audio(path)
    sil = np.sqrt(np.convolve(a ** 2, np.ones(4800) / 4800, "valid")[::4800])
    long_sil = int(np.max(np.convolve((sil < 10 ** (-60 / 20)).astype(int), np.ones(20), "valid"))) if len(sil) > 20 else 0
    add("pas de silence", long_sil < 20, "aucun trou de 2 s sous -60 dBFS" if long_sil < 20 else "silence de 2 s détecté")
    offs = sync_offsets(v, a, ep.TL.FL)
    worst = max([abs(o[3]) for o in offs] + [0])
    add("synchro son/image", worst <= 60, "écarts aux transitions : " + ", ".join(f"{o[3]:+.0f} ms" for o in offs))
    if audit_bad is not None:
        add("zones sûres TikTok", len(audit_bad) == 0,
            "aucun texte hors zone" if not audit_bad else "; ".join(f"{k[0]!r} [{k[1]}] t={v_[0]:.2f}" for k, v_ in list(audit_bad.items())[:5]))
    return checks
