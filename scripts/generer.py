"""Échantillons Pocket TTS (Kyutai) : une demande JSON -> MP3 + chronologie des blocs.

Options par travail : temperature (0,3 par défaut), max_tokens (taille des morceaux de texte, 50 par défaut),
suite (true : tout le texte en un seul appel, l'état du modèle continue d'un morceau au suivant au lieu de repartir
de la voix seule -> intonation qui enchaîne), frames_after_eos (silence de fin de morceau)."""
import json
import os
import subprocess
import sys
import time
import traceback

import numpy as np
import scipy.io.wavfile

from pocket_tts import TTSModel

dem = json.load(open(sys.argv[1], encoding="utf-8"))
out = sys.argv[2]
os.makedirs(out, exist_ok=True)
MODELES = {}
WHISPER = []


def norm(w):
    import re
    import unicodedata
    w = w.replace("’", "'").lower()
    w = unicodedata.normalize("NFD", w)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w%]+", "", w)


def verifier(audio, sr, attendu):
    """Transcription indépendante d'un bloc ; renvoie (ok, détail) : aucun trou de 3 mots ou plus, et rien
    d'ajouté avant le premier mot."""
    import difflib
    from scipy.signal import resample_poly
    if not WHISPER:
        from faster_whisper import WhisperModel
        WHISPER.append(WhisperModel("medium", device="cpu", compute_type="int8"))
    a16 = resample_poly(audio, 2, 3).astype(np.float32) if sr == 24000 else audio
    segs, _ = WHISPER[0].transcribe(a16, language="fr", beam_size=5, vad_filter=False)
    texte = " ".join(x.text for x in segs).strip()
    e = [norm(w) for w in attendu.replace("-", " ").split() if norm(w)]
    h = [norm(w) for w in texte.replace("'", " ").replace("-", " ").split() if norm(w)]
    e2 = [x for w in e for x in w.split("'")]
    sm = difflib.SequenceMatcher(None, [w.replace("'", "") for w in e], [w.replace("'", "") for w in h], autojunk=False)
    trous = [(i1, i2) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ("delete", "replace") and i2 - i1 >= 3
             and (tag == "delete" or (j2 - j1) <= (i2 - i1) - 2)]
    ajout_debut = bool(sm.get_opcodes()) and sm.get_opcodes()[0][0] in ("insert", "replace") and sm.get_opcodes()[0][1] == 0
    ok = not trous and not ajout_debut
    return ok, {"entendu": texte, "trous": [" ".join(e[i:j]) for i, j in trous], "ajout_debut": ajout_debut}


def modele(temp):
    if temp not in MODELES:
        t0 = time.time()
        MODELES[temp] = TTSModel.load_model(language=dem.get("langue", "french_24l"), temp=temp)
        print(f"modèle {dem.get('langue')} (température {temp}) chargé en {time.time() - t0:.1f} s", flush=True)
    return MODELES[temp]


def faire(job):
    t1 = time.time()
    m = modele(job.get("temperature", 0.3))
    sr = m.sample_rate
    kw = dict(max_tokens=job.get("max_tokens", 50))
    if job.get("frames_after_eos") is not None:
        kw["frames_after_eos"] = job["frames_after_eos"]
    parts, chrono, t = [], [], 0.0
    if job.get("suite"):
        st = m.get_state_for_audio_prompt(job["voix"])
        a = m.generate_audio(st, " ".join(job["blocs"]), copy_state=False, **kw).numpy().astype(np.float32)
        parts.append(a)
        t = len(a) / sr
        chrono.append({"bloc": "tout", "debut": 0.0, "fin": round(t, 3), "texte": " ".join(job["blocs"])})
    else:
        st = m.get_state_for_audio_prompt(job["voix"])
        for k, bloc in enumerate(job["blocs"]):
            essais = []
            for n in range(job.get("tentatives", 1)):
                a = m.generate_audio(st, bloc, **kw).numpy().astype(np.float32)
                if not job.get("verifier"):
                    essais.append((True, {}, a))
                    break
                ok, det = verifier(a, sr, bloc)
                essais.append((ok, det, a))
                print(f"  bloc {k} essai {n + 1} : {'ok' if ok else 'à refaire'} {det.get('trous') or ''}"
                      f"{' (ajout au début)' if det.get('ajout_debut') else ''}", flush=True)
                if ok:
                    break
            ok, det, a = next((x for x in essais if x[0]), essais[-1])
            chrono.append({"bloc": k, "debut": round(t, 3), "fin": round(t + len(a) / sr, 3), "texte": bloc,
                           "verifie": ok, "essais": len(essais), "entendu": det.get("entendu")})
            parts.append(a)
            t += len(a) / sr
            sil = np.zeros(int(job.get("silence_entre_blocs", 0.6) * sr), np.float32)
            parts.append(sil)
            t += len(sil) / sr
    y = np.concatenate(parts)
    y = y / max(1e-6, float(np.abs(y).max())) * 0.89
    duree_calcul = time.time() - t1
    wav = os.path.join(out, job["nom"] + ".wav")
    scipy.io.wavfile.write(wav, sr, (y * 32767).astype(np.int16))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "160k",
                    os.path.join(out, job["nom"] + ".mp3")], check=True)
    os.remove(wav)
    json.dump({"voix": job["voix"], "options": {k: v for k, v in job.items() if k not in ("blocs", "nom")},
               "sr": sr, "blocs": chrono},
              open(os.path.join(out, job["nom"] + "_blocs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{job['nom']} : {t:.1f} s d'audio en {duree_calcul:.1f} s de calcul", flush=True)


for job in dem["jobs"]:
    try:
        faire(job)
    except Exception:  # noqa: BLE001 — un essai en échec ne bloque pas les autres
        print(f"ÉCHEC {job['nom']} :", flush=True)
        traceback.print_exc()
