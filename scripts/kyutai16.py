"""Échantillons Kyutai TTS 1.6B (en_fr, poids CC BY 4.0) sur processeur : une demande JSON -> MP3 par travail.
Voix : embeddings précalculés du dépôt kyutai/tts-voices (chemin relatif, ex. unmute-prod-website/developpeuse-3.wav)."""
import json
import os
import subprocess
import sys
import time
import traceback

import numpy as np
import sphn
import torch
from moshi.models.loaders import CheckpointInfo
from moshi.models.tts import DEFAULT_DSM_TTS_REPO, TTSModel

torch.set_num_threads(os.cpu_count() or 4)
dem = json.load(open(sys.argv[1], encoding="utf-8"))
out = sys.argv[2]
t0 = time.time()
tts = TTSModel.from_checkpoint_info(CheckpointInfo.from_hf_repo(DEFAULT_DSM_TTS_REPO), n_q=32,
                                    temp=dem.get("temperature", 0.6), device="cpu")
print(f"Kyutai TTS 1.6B chargé en {time.time() - t0:.1f} s ({os.cpu_count()} cœurs)", flush=True)
for job in dem["jobs"]:
    try:
        t1 = time.time()
        entries = tts.prepare_script([job["texte"]], padding_between=1)
        voice = tts.get_voice_path(job["voix"])
        cond = tts.make_condition_attributes([voice], cfg_coef=job.get("cfg", 2.0))
        res = tts.generate([entries], [cond])
        with tts.mimi.streaming(1), torch.no_grad():
            pcm = np.concatenate([np.clip(tts.mimi.decode(f[:, 1:, :]).cpu().numpy()[0, 0], -1, 1)
                                  for f in res.frames[tts.delay_steps:]], axis=-1)
        wav = os.path.join(out, job["nom"] + ".wav")
        sphn.write_wav(wav, pcm, tts.mimi.sample_rate)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "160k",
                        os.path.join(out, job["nom"] + ".mp3")], check=True)
        os.remove(wav)
        json.dump({"voix": job["voix"], "moteur": "kyutai tts-1.6b-en_fr", "blocs": [{"texte": job["texte"]}]},
                  open(os.path.join(out, job["nom"] + "_blocs.json"), "w", encoding="utf-8"), ensure_ascii=False)
        d = len(pcm) / tts.mimi.sample_rate
        print(f"{job['nom']} : {d:.1f} s d'audio en {time.time() - t1:.1f} s de calcul ({job['voix']})", flush=True)
    except Exception:  # noqa: BLE001
        print(f"ÉCHEC {job['nom']} :", flush=True)
        traceback.print_exc()
