"""Transcription indépendante (faster-whisper, sans le script en invite) : texte + mots horodatés, au format
attendu par moteur/vf/voix.py (clé « words »). Traite chaque audio de sorties/ qui n'a pas encore ses mots."""
import glob
import json
import os
import sys
import time

from faster_whisper import WhisperModel

d = sys.argv[1]
todo = [a for a in sorted(glob.glob(os.path.join(d, "*.mp3")) + glob.glob(os.path.join(d, "*.wav")))
        if not os.path.exists(a.rsplit(".", 1)[0] + "_mots.json")]
if not todo:
    sys.exit(0)
t0 = time.time()
m = WhisperModel("medium", device="cpu", compute_type="int8")
print(f"whisper medium chargé en {time.time() - t0:.1f} s", flush=True)
for a in todo:
    t1 = time.time()
    segs, info = m.transcribe(a, language="fr", word_timestamps=True, beam_size=5, vad_filter=False)
    words, text = [], []
    for s in segs:
        text.append(s.text)
        for w in (s.words or []):
            words.append({"text": w.word.strip(), "type": "word", "start": round(w.start, 3), "end": round(w.end, 3),
                          "probabilite": round(w.probability, 3)})
    json.dump({"text": "".join(text).strip(), "words": words, "modele": "faster-whisper medium (int8, CPU)"},
              open(a.rsplit(".", 1)[0] + "_mots.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{os.path.basename(a)} : {len(words)} mots transcrits en {time.time() - t1:.1f} s", flush=True)
