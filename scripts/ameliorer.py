"""Essai de restauration « studio » d'une voix de synthèse (extrait de 25 s) avec plusieurs outils libres.
Chaque outil est tenté indépendamment ; les résultats vont dans sorties/ (MP3 48 kHz)."""
import os
import subprocess
import sys
import time
import traceback

src, out = sys.argv[1], sys.argv[2]
wav16 = "/tmp/extrait16.wav"
wav24 = "/tmp/extrait24.wav"
wav44 = "/tmp/extrait44.wav"
for sr, w in ((16000, wav16), (24000, wav24), (44100, wav44)):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", "25", "-i", src, "-ac", "1", "-ar", str(sr), w], check=True)


def mp3(w, nom):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", w, "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "192k",
                    os.path.join(out, nom + ".mp3")], check=True)


mp3(wav24, "resto_0_original")


def essai(nom, f):
    t0 = time.time()
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + f["pip"] +
                       ["--extra-index-url", "https://download.pytorch.org/whl/cpu"], check=True)
        w = f["run"]()
        mp3(w, nom)
        print(f"{nom} : ok en {time.time() - t0:.0f} s", flush=True)
    except Exception:  # noqa: BLE001
        print(f"ÉCHEC {nom} :", flush=True)
        traceback.print_exc()


def voicefixer():
    from voicefixer import VoiceFixer
    VoiceFixer().restore(input=wav44, output="/tmp/vf.wav", cuda=False, mode=0)
    return "/tmp/vf.wav"


def clearvoice():
    from clearvoice import ClearVoice
    cv = ClearVoice(task="speech_super_resolution", model_names=["MossFormer2_SR_48K"])
    o = cv(input_path=wav16, online_write=False)
    cv.write(o, output_path="/tmp/cv.wav")
    return "/tmp/cv.wav"


def resemble():
    import torch
    import torchaudio
    from resemble_enhance.enhancer.inference import enhance
    dwav, sr = torchaudio.load(wav44)
    wav, nsr = enhance(dwav.mean(dim=0), sr, "cpu", nfe=32, solver="midpoint", lambd=0.5, tau=0.5)
    torchaudio.save("/tmp/re.wav", wav.unsqueeze(0), nsr)
    return "/tmp/re.wav"


essai("resto_1_voicefixer", {"pip": ["voicefixer"], "run": voicefixer})
essai("resto_2_clearvoice_sr48k", {"pip": ["clearvoice"], "run": clearvoice})
essai("resto_3_resemble_enhance", {"pip": ["resemble-enhance"], "run": resemble})
