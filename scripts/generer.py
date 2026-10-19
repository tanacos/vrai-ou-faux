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
            a = m.generate_audio(st, bloc, **kw).numpy().astype(np.float32)
            chrono.append({"bloc": k, "debut": round(t, 3), "fin": round(t + len(a) / sr, 3), "texte": bloc})
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
