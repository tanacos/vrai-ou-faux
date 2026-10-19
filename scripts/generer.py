"""Échantillons Pocket TTS (Kyutai) : une demande JSON -> fichiers WAV/MP3 + chronologie des blocs."""
import json
import os
import subprocess
import sys
import time

import numpy as np
import scipy.io.wavfile

from pocket_tts import TTSModel

dem = json.load(open(sys.argv[1], encoding="utf-8"))
out = sys.argv[2]
os.makedirs(out, exist_ok=True)
t0 = time.time()
model = TTSModel.load_model(language=dem.get("langue", "french_24l"))
sr = model.sample_rate
print(f"modèle {dem.get('langue')} chargé en {time.time() - t0:.1f} s, {sr} Hz", flush=True)

# inventaire des voix disponibles (pour choisir les suivantes en connaissant leur licence)
try:
    from huggingface_hub import list_repo_files
    fichiers = list_repo_files("kyutai/tts-voices")
    inv = [f for f in fichiers if f.startswith(("unmute-prod-website/", "cml-tts/fr/", "voice-donations/"))]
    open(os.path.join(out, "voix_disponibles.txt"), "w").write("\n".join(inv) + "\n")
except Exception as e:  # noqa: BLE001
    print("inventaire impossible :", e)

for job in dem["jobs"]:
    t1 = time.time()
    st = model.get_state_for_audio_prompt(job["voix"])
    parts, chrono, t = [], [], 0.0
    for k, bloc in enumerate(job["blocs"]):
        a = model.generate_audio(st, bloc).numpy().astype(np.float32)
        chrono.append({"bloc": k, "debut": round(t, 3), "fin": round(t + len(a) / sr, 3), "texte": bloc})
        parts.append(a)
        t += len(a) / sr
        sil = np.zeros(int(job.get("silence_entre_blocs", 0.6) * sr), np.float32)
        parts.append(sil)
        t += len(sil) / sr
    y = np.concatenate(parts)
    y = y / max(1e-6, float(np.abs(y).max())) * 0.89
    wav = os.path.join(out, job["nom"] + ".wav")
    scipy.io.wavfile.write(wav, sr, (y * 32767).astype(np.int16))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "160k",
                    os.path.join(out, job["nom"] + ".mp3")], check=True)
    os.remove(wav)
    json.dump({"voix": job["voix"], "langue": dem.get("langue"), "sr": sr, "blocs": chrono},
              open(os.path.join(out, job["nom"] + "_blocs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{job['nom']} : {t:.1f} s d'audio en {time.time() - t1:.1f} s (voix {job['voix']})", flush=True)
