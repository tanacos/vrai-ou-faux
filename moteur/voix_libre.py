#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voix libre « Estelle » : narration lue par un modèle Kyutai (poids CC BY 4.0, usage commercial avec attribution
« Voix : Kyutai TTS (CC BY 4.0) »), chaque paragraphe vérifié par une transcription indépendante (faster-whisper) et
refait s'il manque ou s'il s'ajoute un passage.

    python3 moteur/voix_libre.py diagnostic
        -> {"ok": true} si le modèle peut tourner ici (paquets installés, Hugging Face joignable), sinon ce qui manque.
           Code de sortie 0 (prêt) ou 3 (pas prêt : l'épisode se fait sans voix).
    python3 moteur/voix_libre.py generer <dossier de l'épisode> [--declarer]
        -> voix/prise.mp3 et voix/prise_mots.json (mots horodatés au format attendu par moteur/vf/voix.py).
           --declarer écrit aussi le champ « voix » dans episode.json. Code 0 : tous les paragraphes vérifiés ;
           2 : au moins un paragraphe non vérifié (ne pas utiliser la prise).
    (ancienne forme, toujours acceptée : python3 moteur/voix_libre.py <dossier>)

Texte lu :
  - série narrée (INFINIMENT) : le fichier « narration » de episode.json, un paragraphe par bloc ;
  - épisode « Vrai ou faux ? » (pas de champ « narration ») : les blocs de vf.voix.narration_quiz (ouverture,
    affirmations, verdicts, panneaux, score, annonce), exactement comme pour ElevenLabs.
  Nombres, unités et sigles sont écrits en lettres pour la voix seulement (vf/nombres.py) : l'écran garde les chiffres.

Moteurs (episode.json → "voix_libre" → "moteur") :
  "kyutai-1.6b" (défaut) : Kyutai TTS 1.6B en/fr, voix « estelle » (kyutai/tts-voices,
      unmute-prod-website/developpeuse-3.wav, cédée en CC0). Sur processeur : environ 10 fois plus lent que le temps
      réel sur 4 cœurs (≈ 15 à 20 min pour un épisode), environ 20 fois sur 2 cœurs.
      pip install "moshi==0.2.11" sphn faster-whisper --extra-index-url https://download.pytorch.org/whl/cpu
  "pocket" : Kyutai Pocket TTS (100 M de paramètres), rapide mais plus robotique. pip install pocket-tts

Constaté lors des essais (19-20/10/2026) : sans vérification, une prise sur trois ajoutait une syllabe parasite au
début, et des morceaux trop longs faisaient sauter une phrase entière : la vérification fait partie de la chaîne."""
import difflib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import numpy as np  # noqa: E402

from vf.nombres import parlable  # noqa: E402

VOIX_16B = "unmute-prod-website/developpeuse-3.wav"
DECLARATION = {
    "fournisseur": "Kyutai",
    "modele": "kyutai/tts-1.6b-en_fr",
    "nom": "Estelle",
    "voix_16b": VOIX_16B,
    "tempo": 1.0,
    "eclaircir": True,
    "prise": "voix/prise.mp3",
    "mots": "voix/prise_mots.json",
    "horodatage": "faster-whisper medium (transcription indépendante)",
    "licence": "poids CC BY 4.0 : mention « Voix : Kyutai TTS (CC BY 4.0) » dans la légende ; voix Estelle cédée en CC0",
}
MENTION = "Voix de synthèse : Kyutai TTS (CC BY 4.0)"


def texte_parle(bloc):
    """Texte envoyé au modèle : mêmes mots que l'écran, balises retirées, nombres et sigles écrits comme ils se
    disent, points de suspension remplacés par une virgule (coupure trop longue sinon)."""
    s = bloc.replace(" ", " ").replace("\xa0", " ")
    s = re.sub(r"\[[^\]]*\]\s*", "", s)
    s = re.sub(r"\s*…\s*", ", ", s)
    s = s.replace("«", "").replace("»", "")
    return parlable(re.sub(r"\s+", " ", s)).strip(" ,")


def norm(w):
    w = w.replace("’", "'").lower()
    w = unicodedata.normalize("NFD", w)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w%]+", "", w)


def mots(texte):
    return [norm(w) for w in texte.replace("'", " ").replace("’", " ").replace("-", " ").split() if norm(w)]


def verifier(transcrire, audio16, attendu):
    """Transcription indépendante d'un paragraphe. Échec si un passage de 3 mots ou plus manque, si 3 mots ou plus
    s'ajoutent (hors nombres transcrits en chiffres), ou si quelque chose est ajouté avant le premier mot."""
    entendu = transcrire(audio16)
    e, h = mots(attendu), mots(entendu)
    ops = difflib.SequenceMatcher(None, e, h, autojunk=False).get_opcodes()
    trous, ajouts = [], []
    for tag, i1, i2, j1, j2 in ops:
        chiffres = any(ch.isdigit() for w in h[j1:j2] for ch in w)
        if tag in ("delete", "replace") and i2 - i1 >= 3:
            if tag == "replace" and chiffres:
                continue                                    # « quatre-vingt-dix-neuf… » transcrit « 99,9 % »
            if tag == "replace" and (j2 - j1) > (i2 - i1) - 2:
                continue                                    # mots déformés mais présents
            trous.append(" ".join(e[i1:i2]))
        if tag in ("insert", "replace") and (j2 - j1) - (i2 - i1) >= 3 and not chiffres:
            ajouts.append(" ".join(h[j1:j2]))
    ajout_debut = bool(ops) and ops[0][0] == "insert"
    court = len(e) <= 3 and len(h) > len(e) + 2               # « Faux ! » suivi d'une phrase inventée
    ok = not trous and not ajouts and not ajout_debut and not court
    return ok, {"entendu": entendu, "trous": trous, "ajouts": ajouts, "ajout_debut": ajout_debut}


def blocs_a_lire(ep_dir, c):
    """[(identifiant, texte du script, texte lu)] dans l'ordre de la vidéo."""
    if c.get("narration"):
        texte = open(os.path.join(ep_dir, c["narration"]), encoding="utf-8").read()
        paras = [b for b in re.split(r"\n\s*\n", texte.strip()) if b.strip()]
        ids = c.get("blocs") or [f"b{i}" for i in range(len(paras))]
        if len(ids) != len(paras):
            raise SystemExit(f"{len(paras)} paragraphes de narration pour {len(ids)} blocs déclarés")
        return [(k, p, texte_parle(p)) for k, p in zip(ids, paras)]
    from vf import voix as VX                   # épisode « Vrai ou faux ? »
    return [(k, t, texte_parle(t)) for k, t in VX.narration_quiz(c)]


# ------------------------------------------------------------------ diagnostic de l'environnement
def diagnostic(afficher=True):
    manque = []
    for mod, paquet in (("moshi", "moshi==0.2.11"), ("sphn", "sphn"), ("faster_whisper", "faster-whisper"),
                        ("torch", "torch (index CPU)"), ("scipy", "scipy")):
        try:
            __import__(mod)
        except Exception:  # noqa: BLE001
            manque.append(paquet)
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        manque.append("ffmpeg")
    reseau = None
    try:
        import urllib.request
        with urllib.request.urlopen("https://huggingface.co/api/models/kyutai/tts-1.6b-en_fr", timeout=20) as r:
            reseau = r.status == 200
    except Exception as e:  # noqa: BLE001
        reseau = False
        manque.append(f"accès à huggingface.co ({type(e).__name__})")
    out = dict(ok=not manque, manque=manque, huggingface=reseau, coeurs=os.cpu_count())
    try:
        out["memoire_gio"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (ValueError, OSError):
        pass
    if afficher:
        print(json.dumps(out, ensure_ascii=False))
    return out


# ------------------------------------------------------------------ génération
def generer(ep_dir, declarer=False):
    import resource

    import scipy.io.wavfile
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly

    path_ep = os.path.join(ep_dir, "episode.json")
    c = json.load(open(path_ep, encoding="utf-8"))
    r = dict(moteur="kyutai-1.6b", voix="estelle", langue="french_24l", temperature=0.4, max_tokens=80, tentatives=4,
             silence_entre_blocs=0.5, temperature_16b=0.6, voix_16b=VOIX_16B, asr="medium")
    r.update(c.get("voix_libre") or {})
    blocs = blocs_a_lire(ep_dir, c)
    t0 = time.time()
    try:
        import torch
        torch.set_num_threads(os.cpu_count() or 4)
    except ImportError:
        torch = None
    asr = WhisperModel(r["asr"], device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    if r["moteur"] == "kyutai-1.6b":
        from moshi.models.loaders import CheckpointInfo
        from moshi.models.tts import DEFAULT_DSM_TTS_REPO, TTSModel as DSM

        dsm = DSM.from_checkpoint_info(CheckpointInfo.from_hf_repo(DEFAULT_DSM_TTS_REPO), n_q=32,
                                       temp=r["temperature_16b"], device="cpu")
        cond = dsm.make_condition_attributes([dsm.get_voice_path(r["voix_16b"])], cfg_coef=2.0)
        sr = dsm.mimi.sample_rate
        dtype = str(next(dsm.lm.parameters()).dtype)

        def produire(texte):
            res = dsm.generate([dsm.prepare_script([texte], padding_between=1)], [cond])
            with dsm.mimi.streaming(1), torch.no_grad():
                return np.concatenate([np.clip(dsm.mimi.decode(f[:, 1:, :]).cpu().numpy()[0, 0], -1, 1)
                                       for f in res.frames[dsm.delay_steps:]]).astype(np.float32)
    else:
        from pocket_tts import TTSModel
        tts = TTSModel.load_model(language=r["langue"], temp=r["temperature"])
        etat = tts.get_state_for_audio_prompt(r["voix"])
        sr = tts.sample_rate
        dtype = "pocket"

        def produire(texte):
            return tts.generate_audio(etat, texte, max_tokens=r["max_tokens"]).numpy().astype(np.float32)
    print(f"modèle {r['moteur']} chargé en {time.time() - t0:.0f} s ({dtype}, {os.cpu_count()} cœurs)", flush=True)

    def transcrire(a16):
        segs, _ = asr.transcribe(a16, language="fr", beam_size=5, vad_filter=False)
        return " ".join(s.text for s in segs).strip()

    parts, rapport, bornes, deja = [], [], [], {}
    t_cur = 0.0
    for k, (bid, _ecran, lu) in enumerate(blocs):
        t1 = time.time()
        if lu in deja:                                     # même phrase (« Vrai ! ») : même prise vérifiée
            ok, det, a, n_essais = deja[lu]
        else:
            essais = []
            for _ in range(r["tentatives"]):
                a = produire(lu)
                ok, det = verifier(transcrire, resample_poly(a, 2, 3).astype(np.float32), lu)
                essais.append((ok, det, a))
                if ok:
                    break
            ok, det, a = next((x for x in essais if x[0]), essais[-1])
            n_essais = len(essais)
            deja[lu] = (ok, det, a, n_essais)
        rapport.append(dict(bloc=bid, texte_lu=lu, essais=n_essais, verifie=ok, trous=det["trous"],
                            ajouts=det.get("ajouts", []), ajout_debut=det["ajout_debut"], entendu=det["entendu"]))
        d = len(a) / sr
        bornes.append(dict(bloc=bid, debut=round(t_cur, 3), fin=round(t_cur + d, 3)))
        print(f"bloc {k + 1}/{len(blocs)} {bid} : {'vérifié' if ok else 'NON VÉRIFIÉ'} en {n_essais} essai(s), "
              f"{d:.1f} s d'audio, {time.time() - t1:.0f} s", flush=True)
        sil = np.zeros(int(r["silence_entre_blocs"] * sr), np.float32)
        parts += [a, sil]
        t_cur += d + len(sil) / sr
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
    tout_ok = all(x["verifie"] for x in rapport)
    json.dump({"words": ws, "modele": f"faster-whisper {r['asr']}", "voix": r, "blocs": bornes,
               "verification": rapport, "tout_verifie": tout_ok},
              open(os.path.join(ep_dir, "voix", "prise_mots.json"), "w", encoding="utf-8"), ensure_ascii=False)
    if declarer and tout_ok:
        v = dict(DECLARATION)
        if r["moteur"] != "kyutai-1.6b":
            v.update(modele="kyutai/pocket-tts", voix_16b=None)
        ancienne = c.get("voix") or {}
        for cle in ("tempo", "respirations", "pauses", "avance_image_s", "retraits", "narration_prise"):
            if cle in ancienne:
                v[cle] = ancienne[cle]
        c["voix"] = v
        json.dump(c, open(path_ep, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 20
    print(json.dumps(dict(duree_s=round(len(y) / sr, 1), calcul_s=round(time.time() - t0), memoire_max_gio=round(rss, 1),
                          tout_verifie=tout_ok, non_verifies=[x["bloc"] for x in rapport if not x["verifie"]],
                          declare=bool(declarer and tout_ok)), ensure_ascii=False), flush=True)
    return 0 if tout_ok else 2


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    if a[0] == "diagnostic":
        sys.exit(0 if diagnostic()["ok"] else 3)
    if a[0] == "generer":
        a = a[1:]
    if not a or not os.path.isdir(a[0]):
        print(__doc__)
        sys.exit(1)
    sys.exit(generer(a[0], declarer="--declarer" in a))
