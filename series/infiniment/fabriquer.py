#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fabrication d'un épisode narré de la série INFINIMENT (reportage, de l'infiniment petit à l'infiniment grand).

Chaque épisode est un dossier : episode.json (scènes, voix, sources, légende), narration (texte lu, un paragraphe
par bloc), voix/ (prise + mots horodatés). Les images et le son viennent du moteur générique moteur/rp (scènes
décrites dans episode.json, voir moteur/rp/FORMAT_REPORTAGE.md) ; un rendu.py ou un son.py placé dans le dossier
de l'épisode le remplace (épisode 1, fait sur mesure). La voix pilote tout : chaque animation et chaque sous-titre
se cale sur ses mots.

  python3 series/infiniment/fabriquer.py provisoire DOSSIER   chronologie estimée, SANS voix (régler les scènes)
  python3 series/infiniment/fabriquer.py valider    DOSSIER   repères, objets, durée (moteur générique)
  python3 series/infiniment/fabriquer.py voix       DOSSIER   chronologie réelle + piste voix (prise requise)
  python3 series/infiniment/fabriquer.py apercu     DOSSIER   planche des moments clés + audit des zones sûres
  python3 series/infiniment/fabriquer.py tout       DOSSIER   vidéo finale + contrôles (≈ 20 à 30 min)

Sortie : <épisode>/sortie/ (video.mp4, audio.wav, planche.png, rapport.json). Codes : 0 conforme, 1 erreur de
préparation, 2 contrôle qualité en échec."""
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(ICI))
sys.path.insert(0, os.path.join(RACINE, "moteur"))

import numpy as np  # noqa: E402

from vf import voix as V  # noqa: E402
from vf import qc as QC  # noqa: E402

CHUNK = 300
R = None                     # module de rendu de l'épisode (partagé avec les processus)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def charger_module(path, nom):
    spec = importlib.util.spec_from_file_location(nom, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def conf(ep_dir):
    return json.load(open(os.path.join(ep_dir, "episode.json"), encoding="utf-8"))


def sortie(ep_dir):
    d = os.path.join(ep_dir, "sortie")
    os.makedirs(d, exist_ok=True)
    return d


def appliquer_retraits(ep_dir, c):
    """Phrases retirées de la prise après coup (correction de fond sans régénérer la voix) : « voix.retraits » =
    [{"bloc", "phrase"}], appliqués à la prise lue d'après « voix.narration_prise ». La narration finale (« narration »)
    doit être exactement ce texte moins ces phrases. Renvoie (prise, mots) à utiliser."""
    import re
    v = c["voix"]
    prise, mots = os.path.join(ep_dir, v["prise"]), os.path.join(ep_dir, v["mots"])
    if not v.get("retraits"):
        return prise, mots
    texte = open(os.path.join(ep_dir, v["narration_prise"]), encoding="utf-8").read()
    out = sortie(ep_dir)
    for k, r in enumerate(v["retraits"]):
        pa, pm = os.path.join(out, f"prise_retrait{k}.wav"), os.path.join(out, f"prise_retrait{k}_mots.json")
        rep = V.retirer_phrase(prise, mots, texte, c["blocs"], r["bloc"], r["phrase"], pa, pm)
        log(f"retrait ({r['bloc']}) : {rep['duree']:.2f} s retirées, coupes à {rep['niveau_coupe_db'][0]:.0f} et "
            f"{rep['niveau_coupe_db'][1]:.0f} dBFS (silence < {rep['seuil_silence_db']:.0f})")
        if max(rep["niveau_coupe_db"]) > rep["seuil_silence_db"] + 6:
            raise RuntimeError(f"retrait {k} : coupe dans la parole ({rep['niveau_coupe_db']})")
        texte = re.sub(r"[ \t]*(\[[^\]]*\][ \t]*)?" + re.escape(r["phrase"]), "", texte, count=1)
        prise, mots = pa, pm
    final = open(os.path.join(ep_dir, c["narration"]), encoding="utf-8").read()
    mots_a = [V.nettoyer_mot(m) for m in V.Narration.sans_balises(texte).split()]
    mots_b = [V.nettoyer_mot(m) for m in V.Narration.sans_balises(final).split()]
    if mots_a != mots_b:
        raise RuntimeError("la narration finale ne correspond pas à la prise moins les phrases retirées")
    return prise, mots


def cmd_voix(ep_dir):
    c = conf(ep_dir)
    v = c["voix"]
    prise, mots = appliquer_retraits(ep_dir, c)
    narr = V.Narration(open(os.path.join(ep_dir, c["narration"]), encoding="utf-8").read(), ids=c["blocs"])
    M = V.Montage(narr, prise, mots, tempo=v.get("tempo", 1.0), respirations=v.get("respirations"),
                  garder_pauses=v.get("pauses", 1.0), eclaircir=v.get("eclaircir", False))
    ch = M.chrono()
    json.dump(ch, open(os.path.join(ep_dir, "chrono.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    np.save(os.path.join(sortie(ep_dir), "voix.npy"), M.voix.astype(np.float32))
    log(f"voix : prise {ch['duree_prise']:.2f} s -> montée {ch['duree']:.2f} s, {len(ch['coupes'])} silences "
        f"raccourcis, alignement {ch['taux_alignement'] * 100:.0f} %, {len(ch['sous_titres'])} sous-titres")
    if ch["taux_alignement"] < 0.9:
        log("ATTENTION : moins de 90 % des mots du script retrouvés dans la transcription (mot sauté ou mal prononcé ?)")
    return ch


def sur_mesure(ep_dir, nom):
    return os.path.exists(os.path.join(ep_dir, nom))


def module_rendu(ep_dir):
    """rendu.py de l'épisode s'il existe (épisode fait sur mesure), sinon le moteur générique moteur/rp."""
    if sur_mesure(ep_dir, "rendu.py"):
        return charger_module(os.path.join(ep_dir, "rendu.py"), "rendu_ep")
    from rp import rendu as RG
    return RG


def module_son(ep_dir):
    if sur_mesure(ep_dir, "son.py"):
        return charger_module(os.path.join(ep_dir, "son.py"), "son_ep")
    from rp import son as SG
    return SG


def signature(ep_dir):
    """Empreinte du contenu qui détermine les images : un tronçon déjà rendu reste valable tant qu'elle ne change pas
    (même après une interruption de la machine, ou si « voix » réécrit une chronologie identique)."""
    h = hashlib.sha1()
    if sur_mesure(ep_dir, "rendu.py"):
        fichiers = [os.path.join(ep_dir, "rendu.py")]
    else:
        rp_dir = os.path.join(RACINE, "moteur", "rp")
        fichiers = [os.path.join(ep_dir, "episode.json")] + sorted(
            os.path.join(rp_dir, f) for f in os.listdir(rp_dir) if f.endswith(".py"))
    for f in fichiers + [os.path.join(ep_dir, "chrono.json")]:
        h.update(open(f, "rb").read())
    return h.hexdigest()


def _frame(i):
    return R.frame(i / R.FPS, i).tobytes()


def render_chunks(ep_dir, out):
    global R
    R = module_rendu(ep_dir)
    R.setup(os.path.join(ep_dir, "chrono.json"))
    NF = R.nframes()
    cdir = os.path.join(out, "troncons")
    os.makedirs(cdir, exist_ok=True)
    sig = signature(ep_dir)
    sp = os.path.join(cdir, "signature.txt")
    if not os.path.exists(sp) or open(sp).read() != sig:
        for f in os.listdir(cdir):
            os.remove(os.path.join(cdir, f))
        open(sp, "w").write(sig)
    paths = []
    t0 = time.time()
    n_chunks = (NF + CHUNK - 1) // CHUNK
    with mp.get_context("fork").Pool(2) as pool:
        for k in range(n_chunks):
            a, b = k * CHUNK, min((k + 1) * CHUNK, NF)
            p = os.path.join(cdir, f"t{k:02d}.mkv")
            paths.append(p)
            if os.path.exists(p + ".ok") and os.path.exists(p):
                continue
            ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                                   f"{R.W}x{R.H}", "-r", str(R.FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                                   "-crf", "8", "-pix_fmt", "yuv444p", p], stdin=subprocess.PIPE)
            for buf in pool.imap(_frame, range(a, b), chunksize=4):
                ff.stdin.write(buf)
            ff.stdin.close()
            if ff.wait() != 0:
                raise RuntimeError(f"échec de l'encodage du tronçon {k}")
            open(p + ".ok", "w").write(str(b - a))
            log(f"tronçon {k + 1}/{n_chunks} ({b}/{NF} images, {time.time() - t0:.0f} s)")
    return paths, NF, R.DUR


def cmd_apercu(ep_dir, cache=False):
    """Planche des moments clés + audit des zones sûres. Avec cache=True, réutilise l'audit déjà fait sur le même
    contenu (sortie/audit.json)."""
    out = sortie(ep_dir)
    ap = os.path.join(out, "audit.json")
    sig = signature(ep_dir)
    if cache and os.path.exists(ap) and os.path.exists(os.path.join(out, "planche.png")):
        a = json.load(open(ap, encoding="utf-8"))
        if a.get("signature") == sig:
            bad = {(txt, why): t for txt, why, t in a["problemes"]}
            log("planche et audit déjà faits sur ce contenu :", "aucun problème" if not bad else f"{len(bad)} problème(s)")
            return bad
    R_ = module_rendu(ep_dir)
    R_.setup(os.path.join(ep_dir, "chrono.json"))
    if hasattr(R_, "valider"):
        v = R_.valider()
        if not v["ok"]:
            for e in v["erreurs"]:
                log("ERREUR :", e)
            raise SystemExit(1)
    p = R_.planche(os.path.join(out, "planche.png"))
    bad = R_.audit(3)
    for (txt, why), t in bad.items():
        log(f"AUDIT : {txt!r} [{why}] à t={t}")
    json.dump({"signature": sig, "problemes": [[txt, why, t] for (txt, why), t in bad.items()]},
              open(ap, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("planche :", p, "| audit :", "aucun problème" if not bad else f"{len(bad)} problème(s)")
    return bad


def cmd_tout(ep_dir):
    t_start = time.time()
    c = conf(ep_dir)
    out = sortie(ep_dir)
    rapport = dict(serie=c["serie"], numero=c["numero"], debut=time.strftime("%Y-%m-%d %H:%M:%S"))
    ch = cmd_voix(ep_dir)
    bad = cmd_apercu(ep_dir, cache=True)
    S_ = module_son(ep_dir)
    wav = os.path.join(out, "audio.wav")
    ainfo = S_.render(os.path.join(ep_dir, "chrono.json"), os.path.join(out, "voix.npy"), wav)
    log(f"bande-son : {ainfo['lufs']:.2f} LUFS, crête vraie {ainfo['true_peak']:.2f} dBTP, limiteur {ainfo['max_gr_db']:.1f} dB")
    chunks, NF, DUR = render_chunks(ep_dir, out)
    mp4 = os.path.join(out, "video.mp4")
    log("encodage final (deux passes)…")
    sys.path.insert(0, os.path.join(RACINE, "moteur"))
    import fabriquer as FAB                      # encodeur de la série (même réglage que les épisodes publiés)
    FAB.encode_final(chunks, wav, mp4)
    voix = np.load(os.path.join(out, "voix.npy")).astype(np.float64)
    checks = QC.run_narre(mp4, DUR, NF, bad, voix=voix, t0=c["voix"].get("avance_image_s", 0.3))
    ok = all(x["ok"] for x in checks)
    for x in checks:
        log(("OK   " if x["ok"] else "ÉCHEC"), f"{x['controle']} : {x['detail']}")
    rapport.update(statut="conforme" if ok else "contrôle qualité en échec", controles=checks, duree_video=DUR,
                   bande_son=ainfo, voix=dict(duree_prise=ch["duree_prise"], duree_montee=ch["duree"],
                                              alignement=ch["taux_alignement"], tempo=c["voix"].get("tempo", 1.0)),
                   fin=time.strftime("%Y-%m-%d %H:%M:%S"), duree_fabrication_s=round(time.time() - t_start))
    json.dump(rapport, open(os.path.join(out, "rapport.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"terminé en {time.time() - t_start:.0f} s : {rapport['statut']}")
    if ok:
        shutil.rmtree(os.path.join(out, "troncons"), ignore_errors=True)
    return 0 if ok else 2


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd, ep = sys.argv[1], os.path.abspath(sys.argv[2])
    if cmd == "provisoire":
        from rp import provisoire as PV
        PV.main(ep)
    elif cmd == "valider" and sur_mesure(ep, "rendu.py"):
        # épisode fait sur mesure (ép. 1) : ses scènes sont dans son rendu.py, pas dans episode.json ; on vérifie
        # ce qui reste vérifiable ici (chronologie réelle, durée, alignement de la voix)
        ch = json.load(open(os.path.join(ep, "chrono.json"), encoding="utf-8"))
        err = []
        if ch.get("provisoire"):
            err.append("chronologie provisoire : lancer « fabriquer.py voix » d'abord")
        if not 61 <= float(ch.get("duree", 0)) <= 96:
            err.append(f"durée {ch.get('duree')} s hors de 61 à 96 s")
        if float(ch.get("taux_alignement", 0)) < 0.9:
            err.append(f"alignement de la voix {ch.get('taux_alignement')} < 0,90")
        r = dict(ok=not err, erreurs=err, avertissements=["épisode sur mesure : scènes contrôlées par l'aperçu et "
                                                          "l'audit des zones sûres, pas par ce validateur"],
                 duree=ch.get("duree"), scenes=len(conf(ep).get("blocs", [])))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(0 if r["ok"] else 2)
    elif cmd == "valider":
        from rp import rendu as RG
        RG.setup(os.path.join(ep, "chrono.json"), os.path.join(ep, "episode.json"))
        r = RG.valider()
        if json.load(open(os.path.join(ep, "chrono.json"), encoding="utf-8")).get("provisoire"):
            r["avertissements"].append("chronologie provisoire (sans voix) : durée et repères estimés")
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(0 if r["ok"] else 2)
    elif cmd == "voix":
        cmd_voix(ep)
    elif cmd == "apercu":
        sys.exit(1 if cmd_apercu(ep) else 0)
    elif cmd == "tout":
        sys.exit(cmd_tout(ep))
    else:
        print(__doc__)
        sys.exit(1)
