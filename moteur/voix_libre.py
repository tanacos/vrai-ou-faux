#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voix libre : narration lue par un modèle Kyutai (poids CC BY 4.0, usage commercial avec attribution « Kyutai »),
chaque paragraphe vérifié par une transcription indépendante (faster-whisper) et refait s'il manque un passage.

Deux moteurs (episode.json → "voix_libre" → "moteur") :
  "kyutai-1.6b" (conseillé) : Kyutai TTS 1.6B en/fr, nettement moins robotique, voix « estelle »
      (unmute-prod-website/developpeuse-3.wav, CC0) ; environ 11 fois plus lent que le temps réel sur 4 cœurs
      (≈ 18 min pour un épisode de 90 s). pip install "moshi==0.2.11" sphn
  "pocket" : Kyutai Pocket TTS, 100 M de paramètres, plus rapide que le temps réel mais plus robotique.

Dépendances (absentes de l'environnement par défaut, voir moteur/VOIX.md) :
    pip install pocket-tts faster-whisper scipy --extra-index-url https://download.pytorch.org/whl/cpu
et l'accès réseau à Hugging Face (téléchargement des poids). ffmpeg doit être installé.

    python3 moteur/voix_libre.py series/infiniment/ep01_estelle
        lit episode.json (« narration » et « voix_libre ») -> écrit voix/prise.mp3 et voix/prise_mots.json
        (mots horodatés au format attendu par moteur/vf/voix.py), puis affiche le compte rendu.

Réglages (episode.json → "voix_libre") : voix ("estelle" par défaut : enregistrement Kyutai cédé en CC0),
langue ("french_24l"), temperature (0.4), max_tokens (80 : au-delà, le modèle saute parfois une phrase entière),
tentatives (4), silence_entre_blocs (0.5).

Ce qui a été constaté lors des essais (19/10/2026) : sans vérification, une prise sur trois ajoutait une syllabe
parasite au tout début, et avec des morceaux de 120 jetons les trois prises ont sauté la même phrase. La
vérification par transcription n'est donc pas une option : elle fait partie de la chaîne."""
import difflib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

import numpy as np

REMPLACEMENTS_PAROLE = [
    (re.compile(r"\[[^\]]*\]\s*"), ""),                     # balises ElevenLabs : sans effet ici
    (re.compile(r"\s*…\s*"), ", "),                         # points de suspension : coupure trop longue
    (re.compile(r"\bADN\b"), "A-D-N"),
    (re.compile(r"\bNASA\b"), "Nasa"),
]
NOMBRES_PARLES = {"99,9 %": "quatre-vingt-dix-neuf virgule neuf pour cent"}


def texte_parle(bloc):
    """Texte envoyé au modèle : mêmes mots que l'écran, nombres et sigles écrits comme ils se disent."""
    s = bloc.replace(" ", " ").replace("\xa0", " ")
    for k, v in NOMBRES_PARLES.items():
        s = s.replace(k, v)
    for rx, rep in REMPLACEMENTS_PAROLE:
        s = rx.sub(rep, s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def norm(w):
    w = w.replace("’", "'").lower()
    w = unicodedata.normalize("NFD", w)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w%]+", "", w)


def mots(texte):
    return [norm(w) for w in texte.replace("'", " ").replace("’", " ").replace("-", " ").split() if norm(w)]


def verifier(transcrire, audio16, attendu):
    """Transcription indépendante d'un paragraphe. Échec si un passage de 3 mots ou plus manque (hors chiffres
    écrits en lettres) ou si quelque chose est ajouté avant le premier mot."""
    entendu = transcrire(audio16)
    e, h = mots(attendu), mots(entendu)
    ops = difflib.SequenceMatcher(None, e, h, autojunk=False).get_opcodes()
    trous = []
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("delete", "replace") and i2 - i1 >= 3:
            if tag == "replace" and any(ch.isdigit() for w in h[j1:j2] for ch in w):
                continue                                    # « quatre-vingt-dix-neuf… » transcrit « 99,9 % »
            if tag == "replace" and (j2 - j1) > (i2 - i1) - 2:
                continue                                    # mots déformés mais présents
            trous.append(" ".join(e[i1:i2]))
    ajout = bool(ops) and ops[0][0] == "insert"
    return (not trous and not ajout), {"entendu": entendu, "trous": trous, "ajout_debut": ajout}


def main(ep_dir):
    import scipy.io.wavfile
    from faster_whisper import WhisperModel
    try:
        from pocket_tts import TTSModel
    except ImportError:          # moteur kyutai-1.6b seul
        TTSModel = None
    from scipy.signal import resample_poly

    c = json.load(open(os.path.join(ep_dir, "episode.json"), encoding="utf-8"))
    r = dict(voix="estelle", langue="french_24l", temperature=0.4, max_tokens=80, tentatives=4,
             silence_entre_blocs=0.5)
    r.update(c.get("voix_libre") or {})
    texte = open(os.path.join(ep_dir, c["narration"]), encoding="utf-8").read()
    blocs = [texte_parle(b) for b in re.split(r"\n\s*\n", texte.strip()) if b.strip()]
    t0 = time.time()
    asr = WhisperModel("medium", device="cpu", compute_type="int8")
    if r.get("moteur", "kyutai-1.6b") == "kyutai-1.6b":
        import torch
        from moshi.models.loaders import CheckpointInfo
        from moshi.models.tts import DEFAULT_DSM_TTS_REPO, TTSModel as DSM

        dsm = DSM.from_checkpoint_info(CheckpointInfo.from_hf_repo(DEFAULT_DSM_TTS_REPO), n_q=32,
                                       temp=r.get("temperature_16b", 0.6), device="cpu")
        cond = dsm.make_condition_attributes([dsm.get_voice_path(r.get("voix_16b",
                                              "unmute-prod-website/developpeuse-3.wav"))], cfg_coef=2.0)
        sr = dsm.mimi.sample_rate

        def generer(texte):
            res = dsm.generate([dsm.prepare_script([texte], padding_between=1)], [cond])
            with dsm.mimi.streaming(1), torch.no_grad():
                return np.concatenate([np.clip(dsm.mimi.decode(f[:, 1:, :]).cpu().numpy()[0, 0], -1, 1)
                                       for f in res.frames[dsm.delay_steps:]]).astype(np.float32)
    else:
        tts = TTSModel.load_model(language=r["langue"], temp=r["temperature"])
        etat = tts.get_state_for_audio_prompt(r["voix"])
        sr = tts.sample_rate

        def generer(texte):
            return tts.generate_audio(etat, texte, max_tokens=r["max_tokens"]).numpy().astype(np.float32)

    def transcrire(a16):
        segs, _ = asr.transcribe(a16, language="fr", beam_size=5, vad_filter=False)
        return " ".join(s.text for s in segs).strip()

    parts, rapport = [], []
    for k, b in enumerate(blocs):
        essais = []
        for n in range(r["tentatives"]):
            a = generer(b)
            ok, det = verifier(transcrire, resample_poly(a, 2, 3).astype(np.float32), b)
            essais.append((ok, det, a))
            if ok:
                break
        ok, det, a = next((x for x in essais if x[0]), essais[-1])
        rapport.append(dict(bloc=k, essais=len(essais), verifie=ok, trous=det["trous"], ajout_debut=det["ajout_debut"]))
        print(f"bloc {k} : {'vérifié' if ok else 'NON VÉRIFIÉ'} en {len(essais)} essai(s)", flush=True)
        parts += [a, np.zeros(int(r["silence_entre_blocs"] * sr), np.float32)]
    y = np.concatenate(parts)
    y = y / max(1e-6, float(np.abs(y).max())) * 0.89
    os.makedirs(os.path.join(ep_dir, "voix"), exist_ok=True)
    wav = os.path.join(ep_dir, "voix", "prise.wav")
    scipy.io.wavfile.write(wav, sr, (y * 32767).astype(np.int16))
    mp3 = os.path.join(ep_dir, "voix", "prise.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "160k", mp3], check=True)
    os.remove(wav)
    # horodatage mot à mot de la prise complète (transcription indépendante, sans le script en invite)
    segs, _ = asr.transcribe(resample_poly(y, 2, 3).astype(np.float32), language="fr", beam_size=5,
                             word_timestamps=True, vad_filter=False)
    ws = [{"text": w.word.strip(), "type": "word", "start": round(w.start, 3), "end": round(w.end, 3)}
          for s in segs for w in (s.words or [])]
    json.dump({"words": ws, "modele": "faster-whisper medium", "voix": r, "verification": rapport},
              open(os.path.join(ep_dir, "voix", "prise_mots.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps(dict(duree_s=round(len(y) / sr, 1), calcul_s=round(time.time() - t0), blocs=rapport),
                     ensure_ascii=False))
    return 0 if all(x["verifie"] for x in rapport) else 2


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
