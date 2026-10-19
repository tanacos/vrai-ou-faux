#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fabrication d'un épisode « Vrai ou faux ? » à partir de son script JSON.

  python3 fabriquer.py valider  episodes/003-espace/episode.json
  python3 fabriquer.py apercu   episodes/003-espace/episode.json SORTIE/      (planches des moments clés, ~1 min)
  python3 fabriquer.py tout     episodes/003-espace/episode.json SORTIE/      (vidéo finale + contrôles, ~25 min)
  python3 fabriquer.py son      episodes/003-espace/episode.json SORTIE/      (bande-son seule)
  python3 fabriquer.py controle episodes/003-espace/episode.json SORTIE/video.mp4

Codes de sortie : 0 = tout est conforme ; 1 = script invalide ; 2 = contrôle qualité en échec.
Le dossier de sortie reçoit : video.mp4, audio.wav, rapport.json, planche.png (et des tronçons intermédiaires)."""
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from vf import episode as E  # noqa: E402
from vf import ui as U  # noqa: E402
from vf import qc as QC  # noqa: E402
from vf import sound as S  # noqa: E402
from vf import icons as IC  # noqa: E402
from vf.base import W, H, FPS  # noqa: E402

CHUNK = 300                    # images par tronçon intermédiaire (10 s)
VIDEO_KBPS = 3300              # débit vidéo cible de l'encodage final (deux passes), comme les épisodes 1 et 2
EP = None                      # épisode partagé avec les processus de rendu (fork)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def build(path):
    spec = E.load(path)
    try:
        ep = E.Episode(spec)
    except ValueError as e:
        return None, [str(x) for x in str(e).split("\n")], []
    return ep, ep.errors, ep.warnings


def icon_names(spec):
    out = []
    for idee in spec.get("idees", []):
        sc = idee.get("scene") or {}
        for k in ("icone", "objet"):
            if sc.get(k):
                out.append(sc[k])
        out += sc.get("satellites") or []
        for side in ("gauche", "droite"):
            if (sc.get(side) or {}).get("icone"):
                out.append(sc[side]["icone"])
        for e in sc.get("elements") or []:
            if e.get("icone"):
                out.append(e["icone"])
    return out


def cmd_valider(path, audit_step=2, quiet=False):
    ep, errors, warns = build(path)
    if ep is not None:
        if not quiet:
            log(ep.summary())
        bad = U.audit(ep.ui, ep.TL.NF, audit_step)
        for (txt, why), v in sorted(bad.items(), key=lambda kv: kv[1][0]):
            if why.startswith(U.CHEVAUCHEMENT):
                errors.append(f"textes superposés à t={v[0]:.2f} s : {txt!r} ({why}) {v[1:]}")
            else:
                errors.append(f"texte hors zone sûre [{why}] à t={v[0]:.2f} s : {txt!r} {v[1:]}")
    else:
        bad = None
    for w in warns:
        log("AVERTISSEMENT :", w)
    for e in errors:
        log("ERREUR :", e)
    if not errors:
        log("script valide")
    return ep, errors, bad


def key_times(ep):
    TL = ep.TL
    ts = [1.2]
    for i, g in enumerate(TL.G):
        ts += [g["claim"] + 0.9, g["cd"] + 0.8, g["reveal"] + 0.22]
        ts += [(s + e) / 2 + 0.4 for (s, e) in TL.panels_t[i]]
    ts += [TL.P5A[0] + 1.5, TL.P5B[0] + 2.5]
    return ts


def contact_sheet(frames, labels, path, cols=6, tw=360, th=640):
    import cv2
    rows = (len(frames) + cols - 1) // cols
    sheet = np.zeros((rows * (th + 10), cols * (tw + 10), 3), np.uint8)
    for k, im in enumerate(frames):
        r, c = divmod(k, cols)
        sm = cv2.resize(im, (tw, th), interpolation=cv2.INTER_AREA)
        sheet[r * (th + 10) + 5:r * (th + 10) + 5 + th, c * (tw + 10) + 5:c * (tw + 10) + 5 + tw] = sm
        cv2.putText(sheet, labels[k], (c * (tw + 10) + 12, r * (th + 10) + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 0), 2)
    Image.fromarray(sheet).save(path)
    return path


def cmd_apercu(path, out):
    ep, errors, bad = cmd_valider(path, audit_step=3)
    if ep is None:
        return 1
    os.makedirs(out, exist_ok=True)
    ts = key_times(ep)
    frames = []
    for t in ts:
        frames.append(ep.render(t, int(round(t * FPS))))
    p = contact_sheet(frames, [f"{t:.1f}s" for t in ts], os.path.join(out, "apercu.png"))
    names = icon_names(ep.spec)
    if names:
        IC.planche(names, os.path.join(out, "pictogrammes.png"))
    log("aperçu :", p)
    return 0 if not errors else 1


def _frame(i):
    return EP.render(i / FPS, seed=i).tobytes()


def signature(ep):
    """Empreinte du script + du code du moteur (invalide les tronçons si l'un des deux change)."""
    import hashlib
    h = hashlib.sha256(json.dumps(ep.spec, sort_keys=True, ensure_ascii=False).encode())
    vfdir = os.path.join(HERE, "vf")
    for f in sorted(os.listdir(vfdir)):
        if f.endswith(".py"):
            h.update(open(os.path.join(vfdir, f), "rb").read())
    return h.hexdigest()


def render_chunks(ep, out):
    """Rendu parallèle (2 processus) en tronçons de 10 s encodés quasi sans perte ; reprise possible."""
    global EP
    EP = ep
    cdir = os.path.join(out, "troncons")
    os.makedirs(cdir, exist_ok=True)
    # les tronçons déjà rendus ne sont réutilisés que si le script et le moteur n'ont pas changé
    sig = signature(ep)
    sig_path = os.path.join(cdir, "signature.txt")
    if not os.path.exists(sig_path) or open(sig_path).read() != sig:
        for f in os.listdir(cdir):
            os.remove(os.path.join(cdir, f))
        open(sig_path, "w").write(sig)
    NF = ep.TL.NF
    n_chunks = (NF + CHUNK - 1) // CHUNK
    paths = []
    t0 = time.time()
    with mp.get_context("fork").Pool(2) as pool:
        for c in range(n_chunks):
            a, b = c * CHUNK, min((c + 1) * CHUNK, NF)
            p = os.path.join(cdir, f"t{c:02d}.mkv")
            paths.append(p)
            done = p + ".ok"
            if os.path.exists(done) and os.path.exists(p):
                continue
            ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                   "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "8",
                                   "-pix_fmt", "yuv444p", p], stdin=subprocess.PIPE)
            for buf in pool.imap(_frame, range(a, b), chunksize=4):
                ff.stdin.write(buf)
            ff.stdin.close()
            if ff.wait() != 0:
                raise RuntimeError(f"échec de l'encodage du tronçon {c}")
            open(done, "w").write(str(b - a))
            el = time.time() - t0
            log(f"tronçon {c + 1}/{n_chunks} ({b} / {NF} images, {el:.0f} s écoulées)")
    return paths


def encode_final(chunks, wav, mp4, kbps=VIDEO_KBPS):
    wd = os.path.dirname(os.path.abspath(mp4))
    lst = os.path.join(wd, "troncons.txt")
    with open(lst, "w") as f:
        for p in chunks:
            f.write(f"file '{os.path.abspath(p)}'\n")
    params = "aq-mode=3:aq-strength=0.85:deblock=-1,-1:psy-rd=1.00,0.10:keyint=60:min-keyint=6:rc-lookahead=60"
    vf = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
    common = ["-f", "concat", "-safe", "0", "-i", lst]
    plog = os.path.join(wd, "x264pass")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + common +
                   ["-vf", vf, "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-b:v", f"{kbps}k",
                    "-x264-params", params, "-pass", "1", "-passlogfile", plog, "-an", "-f", "mp4", "/dev/null"],
                   check=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + common + ["-i", wav, "-map", "0:v", "-map", "1:a",
                    "-vf", vf, "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-b:v", f"{kbps}k",
                    "-x264-params", params, "-pass", "2", "-passlogfile", plog,
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", mp4],
                   check=True)
    for f in os.listdir(wd):
        if f.startswith("x264pass"):
            os.remove(os.path.join(wd, f))
    return mp4


def remux_audio(mp4, wav):
    """Remplace la piste audio sans réencoder la vidéo (ajustement de volume)."""
    tmp = mp4 + ".tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", tmp],
                   check=True)
    os.replace(tmp, mp4)


def cmd_son(path, out, ep=None):
    if ep is None:
        ep, errors, _ = build(path)
        if ep is None or errors:
            return None
    os.makedirs(out, exist_ok=True)
    wav = os.path.join(out, "audio.wav")
    info = S.render(ep, wav, ep.spec.get("ambiance", "aucune"))
    log(f"bande-son : {info['lufs']:.2f} LUFS, crête vraie {info['true_peak']:.2f} dBTP, {info['duree']:.2f} s")
    return wav, info


def cmd_controle(path, mp4, ep=None, bad=None):
    if ep is None:
        ep, errors, bad = cmd_valider(path, quiet=True)
    checks = QC.run(mp4, ep, bad)
    ok = all(c["ok"] for c in checks)
    for c in checks:
        log(("OK   " if c["ok"] else "ÉCHEC"), f"{c['controle']} : {c['detail']}")
    return ok, checks


def cmd_tout(path, out):
    t_start = time.time()
    os.makedirs(out, exist_ok=True)
    ep, errors, bad = cmd_valider(path)
    rapport = dict(script=os.path.abspath(path), debut=time.strftime("%Y-%m-%d %H:%M:%S"))
    if ep is None or errors:
        rapport.update(statut="script invalide", erreurs=errors)
        json.dump(rapport, open(os.path.join(out, "rapport.json"), "w"), ensure_ascii=False, indent=1)
        return 1
    ts = key_times(ep)
    contact_sheet([ep.render(t, int(round(t * FPS))) for t in ts], [f"{t:.1f}s" for t in ts],
                  os.path.join(out, "planche.png"))
    log("planche des moments clés écrite")
    wav, ainfo = cmd_son(path, out, ep)
    chunks = render_chunks(ep, out)
    mp4 = os.path.join(out, "video.mp4")
    log("encodage final (deux passes)…")
    encode_final(chunks, wav, mp4)
    ok, checks = cmd_controle(path, mp4, ep, bad)
    # un seul ajustement automatique du volume si la sonie mesurée après AAC sort de la tolérance
    meas = [c for c in checks if c["controle"] in ("sonie intégrée", "crête vraie")]
    if not all(c["ok"] for c in meas):
        log("ajustement du volume après mesure…")
        from vf import loudness as LN
        m = LN.ffmpeg_measure(mp4)
        tgt = -14.5 + (-14.5 - m["lufs"] if m["lufs"] else 0)
        ceil = -3.0 - max(0.0, (m["true_peak"] or -3) + 2.0)
        S.render(ep, wav, ep.spec.get("ambiance", "aucune"), target_lufs=tgt, ceiling_db=ceil)
        remux_audio(mp4, wav)
        ok, checks = cmd_controle(path, mp4, ep, bad)
    credits = IC.credits(icon_names(ep.spec))
    rapport.update(statut="conforme" if ok else "contrôle qualité en échec", controles=checks,
                   duree_video=ep.TL.DUR, bande_son=ainfo, credits_pictogrammes=credits,
                   fin=time.strftime("%Y-%m-%d %H:%M:%S"), duree_fabrication_s=round(time.time() - t_start))
    if getattr(ep, "voix", None) is not None:
        vc = ep.spec.get("voix") or {}
        rapport["voix"] = dict(fournisseur=vc.get("fournisseur"), modele=vc.get("modele"), nom=vc.get("nom"),
                               alignement=round(ep.voix_taux, 3), licence=vc.get("licence"))
    json.dump(rapport, open(os.path.join(out, "rapport.json"), "w"), ensure_ascii=False, indent=1)
    log(f"terminé en {time.time() - t_start:.0f} s : {rapport['statut']}")
    if ok:
        shutil.rmtree(os.path.join(out, "troncons"), ignore_errors=True)
    return 0 if ok else 2


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "valider":
        _, errs, _ = cmd_valider(path)
        sys.exit(1 if errs else 0)
    elif cmd == "apercu":
        sys.exit(cmd_apercu(path, sys.argv[3]))
    elif cmd == "son":
        r = cmd_son(path, sys.argv[3])
        sys.exit(0 if r else 1)
    elif cmd == "controle":
        ok, _ = cmd_controle(path, sys.argv[3])
        sys.exit(0 if ok else 2)
    elif cmd == "tout":
        sys.exit(cmd_tout(path, sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(1)
