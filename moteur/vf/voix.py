# -*- coding: utf-8 -*-
"""Couche voix : la narration ElevenLabs devient une piste montée, alignée au mot près, prête au mixage.

Chaîne (voir moteur/VOIX.md pour les appels ElevenLabs faits par la session) :
  1. texte de narration (balises d'interprétation eleven_v4 entre crochets, blocs séparés par une ligne vide) ;
  2. prise audio générée par ElevenLabs, rapatriée par moteur/relais.py ;
  3. mots horodatés (transcription ElevenLabs Scribe) ;
  4. ici : alignement script <-> mots, resserrage des silences trop longs (rythme TikTok), traitement de la voix
     (passe-haut, égalisation, compression douce), repères pour l'animation, sous-titres mot à mot, piste 48 kHz ;
  5. mixage : la musique et les bruitages s'effacent sous la voix (ducking), puis mastering à -14,5 LUFS.

Aucune dépendance hors numpy / scipy / ffmpeg."""
import difflib
import json
import re
import subprocess
import unicodedata

import numpy as np
from scipy import signal

from . import loudness as LN

SR = 48000
TAG = re.compile(r"\[[^\]]*\]")
PONCT_FIN = "…?!.:;,"


# ------------------------------------------------------------------ texte
def nettoyer_mot(m):
    """Forme normalisée d'un mot pour l'alignement (minuscules, sans ponctuation ni accents)."""
    m = m.replace("’", "'").lower()
    m = unicodedata.normalize("NFD", m)
    m = "".join(c for c in m if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w%']+", "", m)


class Narration:
    """Texte de narration découpé en blocs (paragraphes) puis en mots affichables.

    Chaque mot : {"texte": mot tel qu'écrit (ponctuation comprise), "bloc": i, "pause_avant": durée demandée par une
    balise [pause]/[short pause]/[long pause] placée juste avant, ou 0}."""

    PAUSES = {"short pause": 0.42, "pause": 0.62, "long pause": 0.95}

    def __init__(self, texte, ids=None):
        blocs = [b.strip() for b in re.split(r"\n\s*\n", texte.strip()) if b.strip()]
        self.ids = ids or [f"b{i}" for i in range(len(blocs))]
        if len(self.ids) != len(blocs):
            raise ValueError(f"{len(blocs)} blocs de narration pour {len(self.ids)} identifiants")
        self.blocs = blocs
        self.mots = []
        for i, b in enumerate(blocs):
            pause = 0.0
            for tok in re.split(r"(\[[^\]]*\])|\s+", b):
                if not tok:
                    continue
                m = TAG.fullmatch(tok)
                if m:
                    pause = max(pause, self.PAUSES.get(tok[1:-1].strip().lower(), 0.0))
                    continue
                if tok in ("?", "!", ":", ";", "%", "»") and self.mots and self.mots[-1]["bloc"] == i:
                    self.mots[-1]["texte"] += " " + tok if tok != "%" else " %"
                    continue
                self.mots.append(dict(texte=tok, bloc=i, pause_avant=pause))
                pause = 0.0
        for k, w in enumerate(self.mots):
            w["idx"] = k
            w["norm"] = nettoyer_mot(w["texte"])

    @staticmethod
    def sans_balises(texte):
        return re.sub(r"\s+", " ", TAG.sub(" ", texte)).strip()

    def texte_parle(self):
        return "\n\n".join(self.sans_balises(b) for b in self.blocs)


def charger_mots_scribe(path):
    """Mots horodatés de Scribe, balises d'interprétation retirées (Scribe les renvoie parfois comme des mots)."""
    d = json.load(open(path, encoding="utf-8"))
    ws = d["words"] if isinstance(d, dict) else d
    out, dans_balise = [], False
    for w in ws:
        t = (w.get("text") or "").strip()
        if w.get("type", "word") != "word" or not t:
            continue
        if t.startswith("["):
            dans_balise = not t.endswith("]")
            continue
        if dans_balise:
            dans_balise = not t.endswith("]")
            continue
        if t in ("?", "!", ":", ";", "%", "…") and out:
            out[-1]["text"] += t
            out[-1]["end"] = max(out[-1]["end"], float(w["end"]))
            continue
        out.append(dict(text=t, start=float(w["start"]), end=float(w["end"])))
    return out


def aligner(narr, mots_scribe):
    """Associe chaque mot du script à un mot horodaté (alignement de séquences sur les formes normalisées) ; les mots
    sans correspondance sont interpolés. Renvoie (liste de (début, fin) par mot du script, taux de correspondance)."""
    a = [w["norm"] for w in narr.mots]
    b = [nettoyer_mot(w["text"]) for w in mots_scribe]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times = [None] * len(a)
    ok = 0
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            w = mots_scribe[blk.b + k]
            times[blk.a + k] = (w["start"], w["end"])
            ok += 1
    # interpolation des trous (mots non reconnus) entre voisins connus
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        raise ValueError("aucun mot du script n'a été retrouvé dans la transcription")
    for i in range(len(times)):
        if times[i] is not None:
            continue
        prv = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        t0 = times[prv][1] if prv is not None else max(times[nxt][0] - 0.3, 0.0)
        t1 = times[nxt][0] if nxt is not None else times[prv][1] + 0.3
        n_gap = (nxt if nxt is not None else len(times)) - (prv if prv is not None else -1) - 1
        k_in = i - (prv if prv is not None else -1) - 1
        d = (t1 - t0) / max(n_gap, 1)
        times[i] = (t0 + k_in * d, t0 + (k_in + 1) * d)
    return times, ok / max(len(a), 1)


# ------------------------------------------------------------------ audio
def lire_audio(path, sr=SR):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, "<i2").astype(np.float64) / 32768.0


def atempo(x, tempo, sr=SR):
    """Accélération sans changement de hauteur (filtre atempo de FFmpeg, WSOLA)."""
    pcm = np.clip(x * 32767, -32768, 32767).astype("<i2").tobytes()
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
                        "-af", f"atempo={tempo:.4f}", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-"],
                       input=pcm, capture_output=True, check=True)
    return np.frombuffer(r.stdout, "<i2").astype(np.float64) / 32768.0


def enveloppe_db(x, sr=SR, hop_s=0.01, win_s=0.03):
    hop, win = int(sr * hop_s), int(sr * win_s)
    p = np.convolve(x ** 2, np.ones(win) / win, "same")[::hop]
    return 10 * np.log10(p + 1e-12)


def seuil_silence(env_db):
    """Seuil de silence adapté au niveau de la prise : 32 dB sous le niveau des syllabes fortes, entre -52 et -36 dBFS."""
    haut = np.percentile(env_db, 95)
    return float(np.clip(haut - 32.0, -52.0, -36.0))


def pause_cible(mot, fin_de_bloc, pause_avant_suivant):
    """Pause maximale conservée après un mot (secondes), selon la ponctuation : rythme de narration TikTok."""
    t = mot.rstrip(" »\"'")
    if pause_avant_suivant:
        return max(pause_avant_suivant, 0.30)
    if fin_de_bloc:
        return 0.50
    if t.endswith("…"):
        return 0.42
    if t.endswith("?"):
        return 0.40
    if t.endswith((".", "!")):
        return 0.34
    if t.endswith((":", ";")):
        return 0.26
    if t.endswith(","):
        return 0.18
    return 0.12


class Montage:
    """Prise resserrée : silences trop longs raccourcis, voix traitée, mots replacés sur la nouvelle chronologie."""

    def __init__(self, narr, prise_mp3, mots_json, debut=0.12, fin=0.35, garder_pauses=1.0, tempo=1.0,
                 respirations=None):
        """tempo > 1 accélère légèrement la voix sans changer sa hauteur (ffmpeg atempo, 1,03 à 1,08 conseillé).
        respirations = {id de bloc: secondes} : silence minimal APRÈS ce bloc (laisser « atterrir » une révélation,
        le temps d'une image forte et de la musique), obtenu en insérant du silence."""
        self.narr = narr
        self.tempo = float(tempo)
        x = lire_audio(prise_mp3)
        mots_s = charger_mots_scribe(mots_json)
        times, self.taux = aligner(narr, mots_s)
        env = enveloppe_db(x)
        thr = seuil_silence(env)
        sil = env < thr
        hop = 0.01
        N = len(x)
        # coupes : pour chaque intervalle entre deux mots, on mesure le vrai silence dans la forme d'onde
        cuts = []                                    # (début, fin) des tranches retirées, en secondes de la prise
        W = narr.mots
        garde = {}                                   # pause conservée après le mot i
        for i in range(len(W) - 1):
            a0 = times[i][0] + 0.6 * (times[i][1] - times[i][0])
            a1 = times[i + 1][0] + 0.03
            i0, i1 = int(a0 / hop), int(a1 / hop)
            if i1 - i0 < 8:
                continue
            seg = sil[i0:i1]
            # plus longue suite de trames silencieuses dans l'intervalle
            best, cur, bstart = 0, 0, 0
            for k, s in enumerate(seg):
                cur = cur + 1 if s else 0
                if cur > best:
                    best, bstart = cur, k - cur + 1
            L = best * hop
            fin_bloc = W[i + 1]["bloc"] != W[i]["bloc"]
            P = pause_cible(W[i]["texte"], fin_bloc, W[i + 1]["pause_avant"]) * garder_pauses
            garde[i] = min(L, P + 0.05)
            if L > P + 0.05:
                s0 = (i0 + bstart) * hop
                excess = L - P
                c0 = s0 + (L - excess) / 2           # on garde la moitié de la pause de chaque côté
                cuts.append((c0, c0 + excess))
        # silence de tête et de queue
        first = times[0][0]
        lead = max(first - 0.05 - debut, 0.0)
        if lead > 0.01:
            cuts.insert(0, (0.0, lead))
        last_end = times[-1][1]
        # fin réelle de la voix : dernière trame non silencieuse
        nz = np.nonzero(~sil)[0]
        voice_end = (nz[-1] + 1) * hop if len(nz) else last_end
        tail0 = min(max(last_end, voice_end) + fin, N / SR)
        if tail0 < N / SR - 0.01:
            cuts.append((tail0, N / SR))
        self.cuts = cuts
        # assemblage avec fondus de 8 ms aux coupes
        keep, t = [], 0.0
        for c0, c1 in cuts:
            if c0 > t:
                keep.append((t, c0))
            t = max(t, c1)
        if t < N / SR:
            keep.append((t, N / SR))
        # respirations : silence ajouté juste avant le premier mot du bloc suivant
        inserts = []
        for bid, sec in (respirations or {}).items():
            if bid not in narr.ids:
                raise ValueError(f"respiration : bloc inconnu {bid!r}")
            bi = narr.ids.index(bid)
            j = next((k for k, w in enumerate(W) if w["bloc"] == bi + 1), None)
            if j is None:
                continue
            d = sec - garde.get(j - 1, 0.0)
            if d > 0.02:
                inserts.append((times[j][0] - 0.04, d))
        inserts.sort()
        fade = int(0.008 * SR)
        parts = []
        self.map_pts = []                            # (temps prise, temps monté)
        tm = 0.0
        pieces = []
        for k0, k1 in keep:                          # découpe des segments gardés aux points d'insertion
            cur = k0
            for ti, d in inserts:
                if cur < ti < k1:
                    pieces.append((cur, ti, 0.0))
                    pieces.append((ti, ti, d))
                    cur = ti
            pieces.append((cur, k1, 0.0))
        for k0, k1, d in pieces:
            if d > 0:
                self.map_pts.append((k0 + 5e-7, tm))
                tm += d
                self.map_pts.append((k0 + 1e-6, tm))
                parts.append(np.zeros(int(round(d * SR))))
                continue
            a, b = int(round(k0 * SR)), int(round(k1 * SR))
            seg = x[a:b].copy()
            if len(seg) > 2 * fade:
                seg[:fade] *= np.linspace(0, 1, fade)
                seg[-fade:] *= np.linspace(1, 0, fade)
            self.map_pts.append((k0 + (2e-6 if self.map_pts and self.map_pts[-1][0] >= k0 else 0.0), tm))
            tm += len(seg) / SR
            self.map_pts.append((k1, tm))
            parts.append(seg)
        self.respirations = [(round(ti, 3), round(d, 3)) for ti, d in inserts]
        self.brut = np.concatenate(parts) if parts else x
        if abs(self.tempo - 1.0) > 1e-3:
            self.brut = atempo(self.brut, self.tempo)
        self.duree = len(self.brut) / SR
        self.duree_prise = N / SR
        self.mots = []
        for w, (s, e) in zip(W, times):
            self.mots.append(dict(texte=w["texte"], bloc=w["bloc"], idx=w["idx"], s=self.vers_monte(s),
                                  e=self.vers_monte(e)))
        # bornes des mots : jamais au-delà du début du mot suivant
        for i in range(len(self.mots) - 1):
            self.mots[i]["e"] = min(self.mots[i]["e"], self.mots[i + 1]["s"])
        self.voix = traiter(self.brut)

    def vers_monte(self, t):
        pts = self.map_pts
        if not pts:
            return t / self.tempo
        src = np.array([p[0] for p in pts])
        dst = np.array([p[1] for p in pts])
        return float(np.interp(t, src, dst)) / self.tempo

    # -------------------------------------------------------------- repères et sous-titres
    def blocs(self):
        """{id du bloc: (début, fin)} sur la chronologie montée."""
        out = {}
        for w in self.mots:
            k = self.narr.ids[w["bloc"]]
            s, e = out.get(k, (w["s"], w["e"]))
            out[k] = (min(s, w["s"]), max(e, w["e"]))
        return out

    def reperes(self):
        """Index « bloc:mot » -> liste des instants de début (mot normalisé, sans accents ni ponctuation)."""
        c = {}
        for w in self.mots:
            key = self.narr.ids[w["bloc"]] + ":" + nettoyer_mot(w["texte"]).replace("'", "")
            c.setdefault(key, []).append(round(w["s"], 3))
        return c

    def sous_titres(self, max_mots=3, max_car=17):
        return sous_titres(self.mots, max_mots, max_car)

    def chrono(self):
        return dict(duree=round(self.duree, 3), duree_prise=round(self.duree_prise, 3), taux_alignement=round(self.taux, 3),
                    respirations=self.respirations, tempo=self.tempo,
                    coupes=[(round(a, 3), round(b, 3)) for a, b in self.cuts], blocs=self.blocs(), reperes=self.reperes(),
                    sous_titres=self.sous_titres(), mots=[dict(t=w["texte"], b=self.narr.ids[w["bloc"]],
                                                               s=round(w["s"], 3), e=round(w["e"], 3)) for w in self.mots])


def affichage(mot):
    """Mot tel qu'affiché dans les sous-titres : majuscules, sans ponctuation finale (sauf ? et %)."""
    s = mot.replace("…", "").strip()
    s = re.sub(r"[.,;:!»«\"]+$", "", s)
    s = s.replace(" :", "").strip()
    return s.upper()


MOTS_FAIBLES = {"le", "la", "les", "l", "de", "du", "des", "d", "un", "une", "et", "a", "à", "au", "aux", "que", "qui",
                "ce", "cet", "cette", "ces", "ta", "ton", "tes", "son", "sa", "ses", "mon", "ma", "mes", "dans", "en",
                "sur", "pour", "par", "ne", "se", "or", "si", "on", "tu", "il", "elle", "leur", "plus", "c'est", "n'as",
                "aussi", "bien", "très", "parce", "même", "tout", "toute"}
NOMBRES = {"un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "vingt",
           "trente", "quarante", "cinquante", "soixante", "cent", "cents", "mille", "million", "millions", "milliard",
           "milliards"}


def sous_titres(mots, max_mots=3, max_car=17):
    """Groupes de 1 à 3 mots, coupés aux ponctuations, sans finir sur un mot-outil (« de », « la »…), qui passe alors
    au groupe suivant ; chaque groupe reste affiché jusqu'au suivant (0,45 s de plus au maximum)."""
    groupes, cur = [], []

    def vider():
        if cur:
            groupes.append(cur[:])
            cur.clear()

    def faible(w):
        return affichage(w["texte"]).lower() in MOTS_FAIBLES

    def nombre(w):
        return affichage(w["texte"]).lower() in NOMBRES

    def fin_phrase(w):
        return w["texte"].rstrip(" »").endswith(tuple(PONCT_FIN))

    def longueur(ws):
        return sum(len(affichage(x["texte"])) + 1 for x in ws)

    for w in mots:
        disp = affichage(w["texte"])
        if not disp:
            continue
        lon = longueur(cur)
        meme_bloc = bool(cur) and w["bloc"] == cur[-1]["bloc"]
        trop = cur and (len(cur) >= max_mots or lon + len(disp) > max_car or not meme_bloc)
        # un 4e mot court qui termine la phrase reste avec les autres (« DONT TU ES FAIT »)
        if trop and meme_bloc and len(cur) == max_mots and fin_phrase(w) and lon + len(disp) <= max_car:
            trop = False
        if trop:
            report = []
            # on ne finit pas un groupe sur un mot-outil, ni au milieu d'un nombre (« CENT | MILLE »)
            while (len(cur) > 1 and meme_bloc and (faible(cur[-1]) or (nombre(cur[-1]) and nombre(w)))
                   and (len(cur) > 2 or any(not faible(x) for x in cur[:-1]))):
                report.insert(0, cur.pop())
            vider()
            cur.extend(report)
            if cur and (len(cur) >= max_mots + 1 or longueur(cur) + len(disp) > max_car + 3):
                vider()
        cur.append(w)
        if fin_phrase(w):
            vider()
    vider()
    out = []
    for i, g in enumerate(groupes):
        s, e = g[0]["s"], g[-1]["e"]
        nxt = groupes[i + 1][0]["s"] if i + 1 < len(groupes) else e + 0.6
        out.append(dict(debut=round(s, 3), fin=round(min(nxt, e + 0.45), 3),
                        mots=[dict(t=affichage(x["texte"]), s=round(x["s"], 3), e=round(x["e"], 3)) for x in g]))
    return out


# ------------------------------------------------------------------ traitement de la voix
def _biquad(kind, f0, q=0.707, gain_db=0.0, sr=SR):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    if kind == "peak":
        b = [1 + al * A, -2 * c, 1 - al * A]
        a = [1 + al / A, -2 * c, 1 - al / A]
    elif kind == "highshelf":
        sq = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * c + sq), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - sq)]
        a = [(A + 1) - (A - 1) * c + sq, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sq]
    elif kind == "lowshelf":
        sq = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * c + sq), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - sq)]
        a = [(A + 1) + (A - 1) * c + sq, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - sq]
    else:
        raise ValueError(kind)
    return np.array(b) / a[0], np.array(a) / a[0]


def compresseur(x, seuil_db=-26.0, ratio=2.2, att=0.008, rel=0.120, genou=6.0):
    """Compression douce (détection RMS courte), sans gain de compensation (le mixage règle le niveau)."""
    env = np.sqrt(signal.lfilter([1 - np.exp(-1 / (0.005 * SR))], [1, -np.exp(-1 / (0.005 * SR))], x ** 2) + 1e-12)
    lv = 20 * np.log10(env)
    over = lv - seuil_db
    gr = np.where(over <= -genou / 2, 0.0,
                  np.where(over >= genou / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + genou / 2) ** 2 / (2 * genou)))
    # lissage attaque / relâchement du gain (en dB)
    a_att, a_rel = np.exp(-1 / (att * SR)), np.exp(-1 / (rel * SR))
    g = np.empty_like(gr)
    prev = 0.0
    grl = gr.tolist()
    for i, v in enumerate(grl):
        k = a_att if v > prev else a_rel
        prev = k * prev + (1 - k) * v
        g[i] = prev
    return x * 10 ** (-g / 20)


def _lufs_mono(y):
    return LN.integrated_lufs(np.stack([y, y], 1))


def traiter(x, cible_lufs=-16.5, plafond_db=-1.5):
    """Voix « radio documentaire » : passe-haut 75 Hz, chaleur légère, présence, air doux, compression 3:1 sur un
    niveau de référence, puis limiteur de crête vraie : la voix arrive au mixage avec un écart crête/sonie maîtrisé
    (sinon le limiteur final écraserait les consonnes)."""
    y = signal.sosfilt(signal.butter(2, 75, "highpass", fs=SR, output="sos"), x)
    for kind, f, q, g in (("lowshelf", 180, 0.7, 1.0), ("peak", 320, 1.0, -1.5), ("peak", 3200, 0.9, 1.8),
                          ("highshelf", 9500, 0.7, -1.0)):
        b, a = _biquad(kind, f, q, g)
        y = signal.lfilter(b, a, y)
    y *= 10 ** ((-20.0 - _lufs_mono(y)) / 20)
    y = compresseur(y, seuil_db=-26.0, ratio=3.5, att=0.004, rel=0.14)
    y *= 10 ** ((cible_lufs - _lufs_mono(y)) / 20)
    y, _ = LN.limiter(y[:, None], plafond_db, look_ms=2.0, rel_ms=80.0)
    return y[:, 0]


# ------------------------------------------------------------------ mixage
def activite(voix, sr=SR, seuil_db=-42.0, att=0.06, rel=0.38):
    """Courbe 0..1 de présence de la voix (pour effacer la musique dessous), lissée attaque / relâchement."""
    env = enveloppe_db(voix, sr, hop_s=0.005, win_s=0.03)
    on = (env > seuil_db).astype(float)
    hop = 0.005
    a_att, a_rel = np.exp(-hop / att), np.exp(-hop / rel)
    out = np.empty_like(on)
    p = 0.0
    for i, v in enumerate(on.tolist()):
        k = a_att if v > p else a_rel
        p = k * p + (1 - k) * v
        out[i] = p
    t_env = np.arange(len(out)) * hop
    return np.interp(np.arange(len(voix)) / sr, t_env, out)


def mixer(voix, lit, sfx=None, ducking_db=-9.0, voix_gain_db=0.0, cible=-14.5, plafond=-3.0):
    """voix (N,) mono ; lit (N,2) musique+ambiance ; sfx (N,2) bruitages (moins effacés). Renvoie (mix, infos)."""
    n = max(len(voix), len(lit), len(sfx) if sfx is not None else 0)

    def pad(a, ch):
        if a is None:
            return np.zeros((n, ch))
        if a.ndim == 1:
            a = a[:, None]
        return np.pad(a, ((0, n - len(a)), (0, 0)))

    v = pad(voix, 1)[:, 0] * 10 ** (voix_gain_db / 20)
    act = activite(v)
    g_lit = 10 ** (ducking_db * act / 20)
    g_sfx = 10 ** (0.45 * ducking_db * act / 20)
    mix = np.stack([v, v], 1) + pad(lit, 2) * g_lit[:, None] + pad(sfx, 2) * g_sfx[:, None]
    out, info = LN.master(mix, cible, plafond)
    info["ducking_db"] = ducking_db
    return out, info


def ecrire_wav(path, stereo):
    import wave
    pcm = np.clip(stereo * 32767, -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ format quiz « Vrai ou faux ? » : voix par blocs
NUMEROS = ("Un", "Deux", "Trois", "Quatre")
UNITES_PARLEES = {"h": "heures", "%": "pour cent", "mm": "millimètres", "cm": "centimètres", "m": "mètres",
                  "km": "kilomètres", "j": "jours", "ans": "ans", "kg": "kilos", "t": "tonnes", "°C": "degrés"}


def _sans_guillemets(s):
    return s.replace("«", "").replace("»", "").replace(" ", " ").replace("\xa0", " ").strip()


def _nombre_parle(p):
    v = p.get("valeur", "")
    dec = int(p.get("decimales", 0))
    s = f"{float(v):.{dec}f}".replace(".", ",") if isinstance(v, (int, float)) else str(v)
    suf = (p.get("suffixe") or "").strip()
    suf = UNITES_PARLEES.get(suf, suf)
    return " ".join(x for x in ((p.get("prefixe") or "").strip(), s, suf) if x)


def voix_panneau_defaut(p):
    """Texte lu par défaut pour un panneau (le script peut toujours le remplacer par sa clé « voix »)."""
    k = p.get("type", "texte")
    titre = _sans_guillemets(p.get("titre") or "")
    if k == "texte":
        t = _sans_guillemets(p.get("texte") or "")
        return (titre + " " + t).strip() if titre.endswith("?") else t
    if k == "chiffre":
        return f"{titre} {_nombre_parle(p)}.".strip()
    if k == "citation":
        return _sans_guillemets(p.get("texte") or "")
    if k in ("duo", "barres"):
        return titre
    return ""


def narration_quiz(spec):
    """Blocs (identifiant, texte lu) d'un épisode « Vrai ou faux ? » : ouverture, puis pour chaque idée l'affirmation,
    le verdict et ses panneaux, enfin le score et l'annonce du prochain épisode. Chaque texte peut être fixé dans le
    script : « voix_intro », idée.« voix_affirmation » / « voix_verdict », panneau.« voix » (chaîne vide = muet),
    « voix_score », « voix_prochain »."""
    theme = spec.get("theme", "")
    blocs = [("intro", spec.get("voix_intro") or f"Vrai ou faux ? Quatre idées reçues sur {theme}. "
                                                 "Compte tes bonnes réponses !")]
    for i, idee in enumerate(spec["idees"]):
        n = i + 1
        blocs.append((f"i{n}_affirmation", idee.get("voix_affirmation")
                      or f"{NUMEROS[i]}. {_sans_guillemets(idee['affirmation'])}"))
        blocs.append((f"i{n}_verdict", idee.get("voix_verdict")
                      or ("Vrai !" if idee["verdict"].upper() == "VRAI" else "Faux !")))
        for k, p in enumerate(idee.get("panneaux", [])):
            t = p.get("voix")
            if t is None:
                t = voix_panneau_defaut(p)
            if t:
                blocs.append((f"i{n}_p{k + 1}", t))
    blocs.append(("score", spec.get("voix_score") or "Alors, ton score ? Dis-le en commentaire !"))
    nxt = _sans_guillemets((spec.get("prochain") or {}).get("affirmation", ""))
    nxt = nxt[:1].lower() + nxt[1:] if nxt[:2] != nxt[:2].upper() else nxt
    blocs.append(("prochain", spec.get("voix_prochain") or f"Prochain épisode : {nxt} Vrai ou faux ?"))
    return blocs


def _milieu_silence(env, thr, a, b, hop=0.01):
    """Instant au milieu du plus long silence entre a et b (secondes) ; à défaut, le point le plus calme."""
    i0, i1 = max(int(a / hop), 0), min(int(b / hop) + 1, len(env))
    if i1 <= i0:
        return (a + b) / 2
    seg = env[i0:i1]
    best, cur, bstart = 0, 0, 0
    for k, s in enumerate(seg < thr):
        cur = cur + 1 if s else 0
        if cur > best:
            best, bstart = cur, k - cur + 1
    j = i0 + (bstart + best // 2 if best else int(np.argmin(seg)))
    return j * hop


def retirer_phrase(prise, mots_json, texte, ids, bloc, phrase, sortie_audio, sortie_mots):
    """Retire une phrase d'une prise sans régénérer la voix (correction de fond après coup) : la prise et ses mots
    horodatés sont réécrits sans elle, coupés au milieu des silences qui l'encadrent. La narration doit être réécrite
    sans cette phrase de son côté. Renvoie un compte rendu (tranche retirée, niveaux aux points de coupe)."""
    narr = Narration(texte, ids)
    ws = json.load(open(mots_json, encoding="utf-8"))
    liste = ws["words"] if isinstance(ws, dict) else ws
    times, taux = aligner(narr, charger_mots_scribe(mots_json))
    bi = narr.ids.index(bloc)
    cible = [nettoyer_mot(t) for t in Narration.sans_balises(phrase).split() if nettoyer_mot(t)]
    norms = [w["norm"] for w in narr.mots]
    i0 = next((k for k in range(len(norms) - len(cible) + 1)
               if narr.mots[k]["bloc"] == bi and norms[k:k + len(cible)] == cible), None)
    if i0 is None:
        raise ValueError(f"phrase introuvable dans le bloc {bloc!r} : {phrase!r}")
    i1 = i0 + len(cible) - 1
    x = lire_audio(prise)
    env = enveloppe_db(x)
    thr = seuil_silence(env)
    a = _milieu_silence(env, thr, times[i0 - 1][1], times[i0][0]) if i0 > 0 else max(times[i0][0] - 0.05, 0.0)
    b = (_milieu_silence(env, thr, times[i1][1], times[i1 + 1][0]) if i1 + 1 < len(times)
         else min(times[i1][1] + 0.3, len(x) / SR))
    ia, ib = int(round(a * SR)), int(round(b * SR))
    f = int(0.010 * SR)
    tete, queue = x[:ia].copy(), x[ib:].copy()
    if len(tete) > f and len(queue) > f:
        tete[-f:] *= np.linspace(1, 0, f)
        queue[:f] *= np.linspace(0, 1, f)
    y = np.concatenate([tete, queue])
    pcm = np.clip(y * 32767, -32768, 32767).astype("<i2")
    import wave
    with wave.open(sortie_audio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    d = b - a
    garde = []
    for w in liste:
        s = float(w.get("start", 0.0))
        if a <= s < b:
            continue
        w2 = dict(w)
        if s >= b:
            w2["start"] = round(s - d, 3)
            w2["end"] = round(float(w["end"]) - d, 3)
        garde.append(w2)
    json.dump({"words": garde}, open(sortie_mots, "w", encoding="utf-8"), ensure_ascii=False)
    niv = lambda t: round(float(env[min(int(t / 0.01), len(env) - 1)]), 1)  # noqa: E731
    return dict(bloc=bloc, phrase=phrase, debut=round(a, 3), fin=round(b, 3), duree=round(d, 3),
                niveau_coupe_db=(niv(a), niv(b)), seuil_silence_db=round(thr, 1), alignement=round(taux, 3))


def mots_a_ecouter(prise_mp3, mots_json, marge_db=10.0):
    """Mots dont l'intervalle horodaté ne contient presque pas de voix (mot avalé, sauté ou mal placé ?).

    Limite : la « transcription » renvoyée par ElevenLabs pour une prise générée reprend le texte demandé (balises
    comprises) : c'est un alignement forcé, pas une vraie reconnaissance. Le taux d'alignement ne prouve donc pas que
    chaque mot a été prononcé ; ce relevé acoustique signale seulement les cas suspects, l'écoute reste le juge."""
    x = lire_audio(prise_mp3)
    env = enveloppe_db(x)
    thr = seuil_silence(env)
    out = []
    for w in charger_mots_scribe(mots_json):
        if len(nettoyer_mot(w["text"])) < 2:
            continue
        i0 = int(w["start"] / 0.01)
        i1 = max(int((w["end"] + 0.06) / 0.01), i0 + 1)       # +60 ms : occlusion d'une consonne (« qui », « pas »)
        mx = float(env[i0:i1 + 1].max()) if i0 < len(env) else -120.0
        if mx < thr + marge_db:
            out.append(dict(mot=w["text"], debut=round(w["start"], 2), niveau_db=round(mx, 1)))
    return out


def texte_narration(blocs):
    """Texte complet envoyé à ElevenLabs (un bloc par paragraphe) et nombre de caractères (≈ crédits)."""
    t = "\n\n".join(b for _, b in blocs)
    return t, len(t)


class Clips:
    """Découpe une prise montée en un extrait par bloc, pour placer chaque phrase où le montage la veut.

    Chaque extrait garde un peu de silence de part et d'autre (coupe au milieu du silence entre deux blocs) ;
    « attaque » = instant du premier mot dans l'extrait, « parole » = durée du premier au dernier mot."""

    def __init__(self, M):
        self.M = M
        ids = M.narr.ids
        b = M.blocs()
        order = [k for k in ids if k in b]
        # point de coupe choisi dans la forme d'onde : milieu du plus long silence entre la fin (horodatée) d'un bloc
        # et le début du suivant, fenêtre élargie de part et d'autre (les horodatages peuvent rogner une fin de mot)
        hop = 0.01
        env = enveloppe_db(M.voix)
        thr = seuil_silence(env)
        cuts = [0.0]
        self.niveaux_coupe = {}                      # niveau de la voix (dBFS) à chaque coupe, pour le contrôle
        for k0, k1 in zip(order, order[1:]):
            lo, hi = b[k0][1] - 0.06, b[k1][0] + 0.04
            if hi - lo < 0.03:
                lo, hi = (b[k0][1] + b[k1][0]) / 2 - 0.05, (b[k0][1] + b[k1][0]) / 2 + 0.05
            i0, i1 = max(int(lo / hop), 0), min(int(hi / hop) + 1, len(env))
            seg = env[i0:i1]
            sil = seg < thr
            best, cur, bstart = 0, 0, 0
            for k, s in enumerate(sil):
                cur = cur + 1 if s else 0
                if cur > best:
                    best, bstart = cur, k - cur + 1
            j = i0 + (bstart + best // 2 if best else int(np.argmin(seg)))
            c = j * hop
            cuts.append(c)
            self.niveaux_coupe[f"{k0}|{k1}"] = round(float(env[min(j, len(env) - 1)]), 1)
        self.seuil_silence = round(thr, 1)
        cuts.append(M.duree)
        fade = int(0.010 * SR)
        self.clips = {}
        for k, c0, c1 in zip(order, cuts[:-1], cuts[1:]):
            a, z = int(round(c0 * SR)), int(round(c1 * SR))
            x = M.voix[a:z].copy()
            if len(x) > 2 * fade:
                x[:fade] *= np.linspace(0, 1, fade)
                x[-fade:] *= np.linspace(1, 0, fade)
            self.clips[k] = dict(audio=x, attaque=b[k][0] - c0, parole=b[k][1] - b[k][0])

    def durees(self):
        return {k: c["parole"] for k, c in self.clips.items()}

    def coupes_douteuses(self, marge_db=10.0):
        """Coupes tombées dans de la parole (niveau nettement au-dessus du silence) : une fin ou un début de phrase
        risque d'être rogné."""
        return {k: v for k, v in self.niveaux_coupe.items() if v > self.seuil_silence + marge_db}

    def piste(self, placements, n):
        """Piste voix mono de n échantillons : placements = [(instant du premier mot, id du bloc)]."""
        out = np.zeros(n)
        for t, k in placements:
            c = self.clips.get(k)
            if c is None:
                continue
            i0 = int(round((t - c["attaque"]) * SR))
            x = c["audio"]
            if i0 < 0:
                x, i0 = x[-i0:], 0
            m = min(len(x), n - i0)
            if m > 0:
                out[i0:i0 + m] += x[:m]
        return out


# ------------------------------------------------------------------ ligne de commande (format quiz)
def _main(argv):
    """python3 -m vf.voix texte    ../episodes/NNN-slug/episode.json   -> texte à faire lire + nombre de caractères
       python3 -m vf.voix verifier ../episodes/NNN-slug/episode.json   -> contrôle de la prise avant fabrication"""
    import os
    import sys
    if len(argv) < 2 or argv[0] not in ("texte", "verifier"):
        print(_main.__doc__)
        return 1
    path = argv[1]
    spec = json.load(open(path, encoding="utf-8"))
    blocs = narration_quiz(spec)
    if argv[0] == "texte":
        t, n = texte_narration(blocs)
        print(t)
        print(f"\n--- {len(blocs)} blocs, {n} caractères (≈ {n} crédits ElevenLabs par prise)", file=sys.stderr)
        return 0
    vc = spec.get("voix") or {}
    base = os.path.dirname(os.path.abspath(path))
    prise, mots = os.path.join(base, vc.get("prise", "")), os.path.join(base, vc.get("mots", ""))
    if not (os.path.isfile(prise) and os.path.isfile(mots)):
        print(json.dumps({"ok": False, "erreur": "prise ou mots introuvables (champ « voix » du script)"},
                         ensure_ascii=False))
        return 2
    narr = Narration("\n\n".join(t for _, t in blocs), ids=[k for k, _ in blocs])
    M = Montage(narr, prise, mots, tempo=float(vc.get("tempo", 1.0)))
    C = Clips(M)
    rep = dict(alignement=round(M.taux, 3), duree_prise=round(M.duree_prise, 2), duree_montee=round(M.duree, 2),
               coupes_douteuses=C.coupes_douteuses(), mots_a_ecouter=mots_a_ecouter(prise, mots))
    rep["ok"] = M.taux >= 0.9 and not rep["coupes_douteuses"]
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
