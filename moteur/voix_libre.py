#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voix libre « Estelle » : narration lue par un modèle Kyutai (poids CC BY 4.0, usage commercial avec attribution
« Voix : Kyutai TTS (CC BY 4.0) »), chaque paragraphe vérifié par une transcription indépendante (faster-whisper) et
refait s'il manque ou s'il s'ajoute un passage.

    python3 moteur/voix_libre.py diagnostic
        -> {"ok": true} si le modèle peut tourner ici (paquets installés, Hugging Face joignable), sinon ce qui manque.
           Code de sortie 0 (prêt) ou 3 (pas prêt : l'épisode se fait sans voix).
    python3 moteur/voix_libre.py installer
        -> installe les paquets (PyPI, index CPU de PyTorch) et ffmpeg, puis refait le diagnostic (codes 0 / 3).
    python3 moteur/voix_libre.py horodater <dossier de l'épisode>
        -> refait les mots horodatés d'une prise existante, bloc par bloc, sans régénérer la voix.
    python3 moteur/voix_libre.py generer <dossier de l'épisode> [--declarer] [--refaire bloc1,bloc2]
        -> voix/prise.mp3 et voix/prise_mots.json (mots horodatés au format attendu par moteur/vf/voix.py).
           --declarer écrit aussi le champ « voix » dans episode.json. Code 0 : tous les paragraphes vérifiés ;
           2 : au moins un paragraphe non vérifié (ne pas utiliser la prise).
           --refaire : ne régénère que ces blocs (phrase corrigée) et reprend les autres de la prise existante,
           à condition que leur texte n'ait pas changé (≈ 3 min par bloc au lieu de toute la prise).
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
    s'ajoutent (hors nombres transcrits en chiffres), ou si quelque chose est ajouté avant le premier mot.
    La même transcription fournit les mots horodatés du paragraphe (« mots », en secondes depuis son début)."""
    entendu, mots_h = transcrire(audio16)
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
    # bloc très court : chaque mot doit être entendu tel quel, et la parole ne doit pas s'étirer (20/10/2026 : un
    # « Faux ! » sorti en « Fouuuuu… » de 1,1 s était passé, faute de mot manquant à compter)
    deforme, etire = [], None
    if len(e) <= 3:
        chiffres_h = any(ch.isdigit() for w in h for ch in w)
        deforme = [w for w in e if w not in h and not (chiffres_h and w in NOMBRES_LETTRES)]
    if len(e) <= 6:
        # mot du verdict entendu tel quel (21/10/2026 : « faux » sortait souvent entendu « fou ») ; parole pas étirée
        # (≤ 0,3 s par syllabe + 0,35 s : un « C'est faux ! » de 1,1 s ou un « Eh non, c'est faux ! » de 1,9 s)
        deforme += [w for w in ("faux", "vrai") if w in e and w not in h and w not in deforme]
        p = duree_parole(audio16)
        if p > 0.3 * syllabes(attendu) + 0.35:
            etire = round(p, 2)
    ok = not trous and not ajouts and not ajout_debut and not court and not deforme and etire is None
    return ok, {"entendu": entendu, "trous": trous + deforme, "ajouts": ajouts, "ajout_debut": ajout_debut,
                "parole_etiree_s": etire, "mots": mots_h}


NOMBRES_LETTRES = {"un", "une", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix"}


def syllabes(texte):
    """Nombre approximatif de syllabes (groupes de voyelles, e muet final non compté) : « Eh non, c'est faux ! » → 4."""
    n = 0
    for w in mots(texte):
        g = re.findall(r"[aeiouy]+", w)
        k = len(g)
        if k > 1 and w.endswith("e") and g[-1] == "e":
            k -= 1                                          # « tasse », « vide » : e muet
        n += k                                              # « c' », « l' » : 0
    return n


def duree_parole(a, sr=16000):
    """Durée (s) des trames de parole d'un court extrait : fenêtres de 30 ms au-dessus de max(-50 dBFS, crête - 30 dB)."""
    hop, win = int(sr * 0.01), int(sr * 0.03)
    if len(a) < win:
        return 0.0
    p = np.convolve(np.asarray(a, np.float64) ** 2, np.ones(win) / win, "same")[::hop]
    db = 10 * np.log10(p + 1e-12)
    return float((db > max(-50.0, db.max() - 30.0)).sum() * 0.01)


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
    import urllib.parse
    import urllib.request
    reseau = None
    # 16 premiers octets d'un vrai fichier du modèle (la voix Estelle) : huggingface.co répond par une redirection vers
    # son réseau de diffusion (us.aws.cdn.hf.co le 21/10/2026), qui doit être autorisé lui aussi
    url = "https://huggingface.co/kyutai/tts-voices/resolve/main/" + urllib.parse.quote(VOIX_16B + ".1e68beda@240.safetensors")
    hote = "huggingface.co"
    try:
        with urllib.request.urlopen("https://huggingface.co/api/models/kyutai/tts-1.6b-en_fr", timeout=20) as r:
            reseau = r.status == 200

        class _Note(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                nonlocal hote
                hote = urllib.parse.urlparse(newurl).hostname or hote
                return super().redirect_request(req, fp, code, msg, hdrs, newurl)
        op = urllib.request.build_opener(_Note)
        with op.open(urllib.request.Request(url, headers={"Range": "bytes=0-15"}), timeout=30) as r:
            reseau = reseau and len(r.read()) > 0
    except Exception as e:  # noqa: BLE001
        reseau = False
        manque.append(f"téléchargement depuis {hote} refusé ({type(e).__name__}) : à autoriser sur claude.ai → "
                      "Paramètres → Capacités → accès réseau sortant (voir moteur/VOIX.md)")
    out = dict(ok=not manque, manque=manque, huggingface=reseau, coeurs=os.cpu_count())
    try:
        out["memoire_gio"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (ValueError, OSError):
        pass
    if afficher:
        print(json.dumps(out, ensure_ascii=False))
    return out


# ------------------------------------------------------------------ génération
def niveau_parole(a, sr):
    """Niveau efficace de la parole d'un bloc (trames à moins de 30 dB du maximum), pour égaliser les blocs."""
    hop = max(int(sr * 0.02), 1)
    n = len(a) // hop
    if n == 0:
        return 1e-3
    rms = np.sqrt((a[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1) + 1e-12)
    act = rms[rms > rms.max() * 10 ** (-30 / 20)]
    return float(np.sqrt((act ** 2).mean())) if len(act) else float(rms.mean())


def lire_prise(path, sr):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.float32).copy()


def memoire_gio():
    """Mémoire résidente actuelle du processus (Gio)."""
    try:
        for ligne in open("/proc/self/status"):
            if ligne.startswith("VmRSS:"):
                return int(ligne.split()[1]) / 2 ** 20
    except OSError:
        pass
    return 0.0


def assurer_memoire(cible_gio=14.0):
    """Le modèle de voix et la transcription montent à ≈ 7,5 Gio (mesuré sur GitHub Actions) : sur une machine de
    8 Go, le noyau tuerait la génération. On ajoute un fichier d'échange sur disque (plus lent qu'en mémoire, mais
    seulement pour les pics) quand mémoire + échange < cible. Sans droits root ou sans place : on continue sans."""
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        ram = page * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
        swap = 0.0
        for ligne in open("/proc/meminfo"):
            if ligne.startswith("SwapTotal:"):
                swap = int(ligne.split()[1]) / 2 ** 20
        manque = cible_gio - ram - swap
        if manque <= 0.5:
            return dict(memoire_gio=round(ram, 1), echange_gio=round(swap, 1), ajoute_gio=0)
        taille = int(np.ceil(manque))
        libre = os.statvfs("/").f_bavail * os.statvfs("/").f_frsize / 2 ** 30
        if libre < taille + 8:                             # garder la place des poids (≈ 6 Go) et de la vidéo
            return dict(memoire_gio=round(ram, 1), echange_gio=round(swap, 1), ajoute_gio=0, raison="disque")
        f = "/var/tmp/voix_libre.swap"
        if not os.path.exists(f):
            subprocess.run(["fallocate", "-l", f"{taille}G", f], check=True, capture_output=True)
            os.chmod(f, 0o600)
            subprocess.run(["mkswap", f], check=True, capture_output=True)
        subprocess.run(["swapon", f], check=True, capture_output=True)
        return dict(memoire_gio=round(ram, 1), echange_gio=round(swap + taille, 1), ajoute_gio=taille)
    except Exception as e:  # noqa: BLE001 — confort, jamais bloquant
        return dict(erreur=f"{type(e).__name__}: {e}"[:200])


def generer(ep_dir, declarer=False, refaire=None):
    import resource

    import scipy.io.wavfile
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly

    print("mémoire :", json.dumps(assurer_memoire(), ensure_ascii=False), flush=True)

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
    import gc
    gc.collect()
    # la transcription se charge APRÈS le modèle de voix : le pic de mémoire du chargement ne s'additionne pas
    asr = WhisperModel(r["asr"], device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    print(f"modèle {r['moteur']} chargé en {time.time() - t0:.0f} s ({dtype}, {os.cpu_count()} cœurs, "
          f"mémoire {memoire_gio():.1f} Gio)", flush=True)

    def transcrire(a16):
        """Texte entendu + mots horodatés (secondes depuis le début du paragraphe)."""
        segs, _ = asr.transcribe(a16, language="fr", beam_size=5, vad_filter=False, word_timestamps=True)
        segs = list(segs)
        ws = [{"text": w.word.strip(), "type": "word", "start": round(w.start, 3), "end": round(w.end, 3)}
              for s in segs for w in (s.words or []) if w.word.strip()]
        return " ".join(s.text for s in segs).strip(), ws

    anciens = {}                                           # --refaire : blocs repris de la prise existante
    if refaire is not None:
        mj = json.load(open(os.path.join(ep_dir, "voix", "prise_mots.json"), encoding="utf-8"))
        vieux = lire_prise(os.path.join(ep_dir, "voix", "prise.mp3"), sr)
        verif = {v["bloc"]: v for v in mj.get("verification", [])}
        for b in mj.get("blocs", []):
            v = verif.get(b["bloc"], {})
            # mots horodatés de ce bloc dans l'ancienne prise, ramenés au début du bloc (même audio, mêmes instants)
            mots_b = [dict(w, start=round(float(w["start"]) - b["debut"], 3), end=round(float(w["end"]) - b["debut"], 3))
                      for w in mj.get("words", []) if b["debut"] - 0.05 <= float(w["start"]) < b["fin"] + 0.05]
            anciens[b["bloc"]] = (v.get("texte_lu"), v, vieux[int(b["debut"] * sr):int(b["fin"] * sr)], mots_b)
        for bid, _ecran, lu in blocs:
            if bid not in refaire and (bid not in anciens or anciens[bid][0] != lu):
                raise SystemExit(f"bloc {bid} : texte changé ou absent de la prise existante, à mettre dans --refaire")

    parts, rapport, bornes, deja, mots_prise = [], [], [], {}, []
    t_cur = 0.0
    for k, (bid, _ecran, lu) in enumerate(blocs):
        t1 = time.time()
        if refaire is not None and bid not in refaire:     # repris tel quel (déjà vérifié)
            _, v, a, mots_b = anciens[bid]
            ok, n_essais = bool(v.get("verifie")), 0
            det = dict(trous=v.get("trous", []), ajouts=v.get("ajouts", []), ajout_debut=v.get("ajout_debut", False),
                       entendu=v.get("entendu", ""), mots=mots_b)
        elif lu in deja:                                   # même phrase (« Vrai ! ») : même prise vérifiée
            ok, det, a, n_essais = deja[lu]
        else:
            essais = []
            # bloc très court (« C'est faux ! ») : 2 fois plus d'essais, chacun ne coûte que 20 à 30 s (21/10/2026 :
            # 2 rejets sur 3 pour « C'est faux ! », la vérification stricte des blocs courts fait son travail)
            n_max = r["tentatives"] * (2 if len(mots(lu)) <= 3 else 1)
            for _ in range(n_max):
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
        a = (a * (0.1 / max(niveau_parole(a, sr), 1e-4))).astype(np.float32)    # blocs au même niveau
        d = len(a) / sr
        bornes.append(dict(bloc=bid, debut=round(t_cur, 3), fin=round(t_cur + d, 3)))
        # mots horodatés du bloc, placés sur la prise : chaque bloc garde SA transcription (une transcription de la
        # prise entière peut sauter ou décaler un passage : constaté le 20/10/2026 sur INFINIMENT 2)
        mots_b = [dict(w, start=round(t_cur + float(w["start"]), 3), end=round(t_cur + min(float(w["end"]), d), 3))
                  for w in det.get("mots") or [] if float(w["start"]) < d]
        if not mots_b and lu.strip():
            print(f"  (bloc {bid} : aucun mot horodaté, ses mots seront répartis sur sa parole au montage)", flush=True)
        mots_prise += mots_b
        print(f"bloc {k + 1}/{len(blocs)} {bid} : {'vérifié' if ok else 'NON VÉRIFIÉ'} en {n_essais} essai(s)"
              f"{' (repris)' if refaire is not None and bid not in refaire else ''}, {d:.1f} s d'audio, "
              f"{time.time() - t1:.0f} s", flush=True)
        sil = np.zeros(int(r["silence_entre_blocs"] * sr), np.float32)
        parts += [a, sil]
        t_cur += d + len(sil) / sr
    y = np.concatenate(parts)
    y = y * min(1.0, 0.89 / max(1e-6, float(np.abs(y).max())))
    os.makedirs(os.path.join(ep_dir, "voix"), exist_ok=True)
    wav = os.path.join(ep_dir, "voix", "prise.wav")
    scipy.io.wavfile.write(wav, sr, (y * 32767).astype(np.int16))
    mp3 = os.path.join(ep_dir, "voix", "prise.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "160k", mp3], check=True)
    os.remove(wav)
    # horodatage mot à mot : la transcription indépendante de chaque bloc (faite pour la vérification), placée
    # sur la prise ; un bloc repris de l'ancienne prise garde ses mots d'origine
    ws = mots_prise
    tout_ok = all(x["verifie"] for x in rapport)
    json.dump({"words": ws, "modele": f"faster-whisper {r['asr']} (par bloc)", "voix": r, "blocs": bornes,
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


def blocs_changes(ep_dir):
    """--refaire auto : blocs dont le texte lu a changé depuis la prise existante (ou absents de celle-ci, ou non
    vérifiés). None s'il n'y a pas de prise utilisable : tout est à générer."""
    chemin = os.path.join(ep_dir, "voix", "prise_mots.json")
    if not (os.path.exists(chemin) and os.path.exists(os.path.join(ep_dir, "voix", "prise.mp3"))):
        return None
    mj = json.load(open(chemin, encoding="utf-8"))
    if not mj.get("blocs") or not mj.get("verification"):
        return None
    verif = {v["bloc"]: v for v in mj["verification"]}
    c = json.load(open(os.path.join(ep_dir, "episode.json"), encoding="utf-8"))
    return {bid for bid, _e, lu in blocs_a_lire(ep_dir, c)
            if bid not in verif or verif[bid].get("texte_lu") != lu or not verif[bid].get("verifie")}


def horodater(ep_dir):
    """Refait les mots horodatés d'une prise existante bloc par bloc (bornes de prise_mots.json → « blocs »), sans
    régénérer la voix : pour une prise dont la transcription d'ensemble a sauté ou décalé un passage."""
    from faster_whisper import WhisperModel
    chemin = os.path.join(ep_dir, "voix", "prise_mots.json")
    mj = json.load(open(chemin, encoding="utf-8"))
    if not mj.get("blocs"):
        raise SystemExit("prise sans bornes de blocs (« blocs ») : rien à refaire bloc par bloc")
    x = lire_prise(os.path.join(ep_dir, "voix", "prise.mp3"), 16000)
    asr = WhisperModel((mj.get("voix") or {}).get("asr", "medium"), device="cpu", compute_type="int8",
                       cpu_threads=os.cpu_count() or 4)
    ws = []
    for b in mj["blocs"]:
        d = b["fin"] - b["debut"]
        segs, _ = asr.transcribe(x[int(b["debut"] * 16000):int(b["fin"] * 16000)], language="fr", beam_size=5,
                                 vad_filter=False, word_timestamps=True)
        n0 = len(ws)
        for s in segs:
            for w in s.words or []:
                if w.word.strip() and w.start < d:
                    ws.append(dict(text=w.word.strip(), type="word", start=round(b["debut"] + w.start, 3),
                                   end=round(b["debut"] + min(w.end, d), 3)))
        print(f"bloc {b['bloc']} : {len(ws) - n0} mots", flush=True)
    mj.update(words=ws, modele=f"faster-whisper {(mj.get('voix') or {}).get('asr', 'medium')} (par bloc)")
    json.dump(mj, open(chemin, "w", encoding="utf-8"), ensure_ascii=False)
    return 0


def env_reseau():
    """Environnement des téléchargements : PyPI passe par le proxy de la session (la liste « no_proxy » des sessions
    Claude envoie pypi.org en direct, où le nom ne se résout pas : constaté le 21/10/2026), et Hugging Face sert les
    fichiers en HTTPS simple (son protocole Xet passe par d'autres serveurs, *.xethub.hf.co)."""
    env = dict(os.environ)
    for k in ("no_proxy", "NO_PROXY"):
        if k in env:
            env[k] = ",".join(h for h in env[k].split(",") if h.strip() not in ("pypi.org", "files.pythonhosted.org"))
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    return env


VENV = "/opt/voix-kyutai"            # environnement Python à part : moshi impose numpy < 2.3, le moteur vidéo en a un récent


def py_venv():
    return os.path.join(VENV, "bin", "python")


def installer():
    """Installe la voix dans un environnement Python séparé (VENV) et ffmpeg si besoin, puis refait le diagnostic.

    Constaté le 21/10/2026 (Python 3.13 des sessions) : moshi 0.2.11 exige sentencepiece == 0.2.0, sans paquet
    compilé pour Python 3.13 (sa compilation échoue) ; on installe donc moshi sans ses dépendances, puis ses
    dépendances une à une avec sentencepiece ≥ 0.2.1. PyTorch vient de l'index CPU (≈ 200 Mo ; download.pytorch.org
    renvoie vers download-r2.pytorch.org), sinon de PyPI (version CUDA, ≈ 3 Go de plus, même résultat sur processeur).
    Code 0 : prêt ; 3 : pas prêt (accès réseau refusé par l'environnement, voir moteur/VOIX.md)."""
    t0 = time.time()
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        subprocess.run("apt-get update -qq && apt-get install -y -qq ffmpeg", shell=True, capture_output=True)
    env = env_reseau()
    if not os.path.exists(py_venv()):
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True, capture_output=True)
    pip = [py_venv(), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--retries", "2", "--timeout", "60"]
    torch_req = "torch>=2.2,<2.8"
    etapes = [("torch (index CPU)", pip + [torch_req, "--index-url", "https://download.pytorch.org/whl/cpu"]),
              ("torch (PyPI)", pip + [torch_req]),
              ("dépendances", pip + ["numpy>=1.26,<2.3", "safetensors>=0.4.0,<0.6", "huggingface-hub>=0.24,<0.34",
                                     "einops>=0.7,<0.9", "sphn>=0.1.4,<0.2", "aiohttp>=3.10.5,<3.12",
                                     "sentencepiece>=0.2.1", "faster-whisper", "scipy"]),
              ("moshi", pip + ["--no-deps", "moshi==0.2.11"])]
    torch_ok = False
    for nom, cmd in etapes:
        if nom == "torch (PyPI)" and torch_ok:
            continue
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400, env=env)
        if nom.startswith("torch"):
            torch_ok = torch_ok or r.returncode == 0
        print(json.dumps(dict(etape=nom, ok=r.returncode == 0, secondes=round(time.time() - t0),
                              detail=None if r.returncode == 0 else (r.stderr or r.stdout)[-300:]),
                         ensure_ascii=False), flush=True)
    r = subprocess.run([py_venv(), os.path.abspath(__file__), "diagnostic"], env=env)
    return r.returncode


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    if a[0] == "installer":
        sys.exit(installer())
    dans_venv = os.path.realpath(sys.prefix) == os.path.realpath(VENV)
    if a[0] in ("diagnostic", "generer", "horodater") and os.path.exists(py_venv()) and not dans_venv:
        # relance dans l'environnement de la voix, avec les réglages réseau (env_reseau) et moins de mémoire
        # « réservée » par les fils de calcul (glibc)
        env = env_reseau()
        env["MALLOC_ARENA_MAX"] = "2"
        os.execve(py_venv(), [py_venv(), os.path.abspath(__file__)] + a, env)
    if a[0] == "diagnostic":
        sys.exit(0 if diagnostic()["ok"] else 3)
    if a[0] == "horodater":
        sys.exit(horodater(a[1]))
    if a[0] == "generer":
        a = a[1:]
    if not a or not os.path.isdir(a[0]):
        print(__doc__)
        sys.exit(1)
    ref = None
    if "--refaire" in a:
        val = a[a.index("--refaire") + 1]
        ref = blocs_changes(a[0]) if val == "auto" else set(val.split(","))
        if ref is not None:
            print(f"blocs à refaire : {', '.join(sorted(ref)) or 'aucun (prise reprise telle quelle)'}", flush=True)
    sys.exit(generer(a[0], declarer="--declarer" in a, refaire=ref))
