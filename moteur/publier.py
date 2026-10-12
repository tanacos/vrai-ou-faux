#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mise en ligne d'une vidéo terminée et tenue du journal.

  python3 moteur/publier.py heberger episodes/004-sommeil SORTIE/video.mp4
      -> crée (ou complète) la release GitHub « ep-004 » du dépôt public et y dépose la vidéo ;
         affiche l'URL publique à donner à Metricool, après avoir vérifié qu'elle répond.
  python3 moteur/publier.py creneau [JSON_DES_POSTS_METRICOOL]
      -> prochain créneau libre (mercredi ou samedi, au moins 48 h plus tard), au format ISO, d'après config.json
         et la liste des publications déjà programmées (fichier JSON de getScheduledPosts, facultatif).
  python3 moteur/publier.py journal episodes/004-sommeil --cle valeur [--cle valeur…]
      -> ajoute ou met à jour l'entrée de l'épisode dans journal.json.
  python3 moteur/publier.py legende episodes/004-sommeil [RAPPORT.json]
      -> légende finale (légende du script + crédits obligatoires des pictogrammes).
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
TZ = ZoneInfo(CONFIG.get("fuseau", "Europe/Paris"))
JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}


def sh(*cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r


def episode_info(ep_dir):
    spec = json.load(open(os.path.join(ep_dir, "episode.json"), encoding="utf-8"))
    return spec, int(spec["numero"]), spec.get("slug", "episode")


def url_ok(url, tries=6):
    """Vérifie qu'une URL publique répond (redirections suivies) ; renvoie (ok, code, taille)."""
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "vrai-ou-faux"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return True, r.status, int(r.headers.get("Content-Length") or 0)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (k + 1))
    return False, str(last), 0


def heberger(ep_dir, mp4):
    spec, num, slug = episode_info(ep_dir)
    repo = CONFIG["depot"]
    tag = f"ep-{num:03d}"
    name = f"vrai_ou_faux_{num:02d}_{slug}.mp4"
    tmp = os.path.join(os.path.dirname(os.path.abspath(mp4)), name)
    if os.path.abspath(tmp) != os.path.abspath(mp4):
        import shutil
        shutil.copyfile(mp4, tmp)
    notes = [f"Épisode {num} — {' '.join(spec['titre'])}", ""]
    for i, idee in enumerate(spec["idees"]):
        notes.append(f"{i + 1}. {idee['affirmation']} → {idee['verdict']}")
        for s in idee.get("sources", []):
            notes.append(f"   - {s.get('editeur')} : {s.get('url')}")
    notes_txt = "\n".join(notes)
    have = sh("gh", "release", "view", tag, "--repo", repo, check=False)
    if have.returncode != 0:
        sh("gh", "release", "create", tag, tmp, "--repo", repo, "--title", f"Épisode {num} — {slug}",
           "--notes", notes_txt)
    else:
        sh("gh", "release", "upload", tag, tmp, "--repo", repo, "--clobber")
    url = f"https://github.com/{repo}/releases/download/{tag}/{name}"
    ok, code, size = url_ok(url)
    print(json.dumps(dict(url=url, accessible=ok, code=code, taille=size, release=tag), ensure_ascii=False))
    return url if ok else None


def creneau(posts_json=None, now=None):
    """Premier créneau libre parmi les jours de publication, au moins delai_veto_h heures plus tard."""
    now = now or dt.datetime.now(TZ)
    jours = [JOURS[j] for j in CONFIG["jours_publication"]]
    delai = dt.timedelta(hours=CONFIG.get("delai_veto_h", 48))
    h0 = CONFIG.get("heure_defaut", "18:00")
    pris = set()
    if posts_json:
        data = json.load(open(posts_json, encoding="utf-8"))
        for p in data.get("data", data if isinstance(data, list) else []):
            d = (p.get("publicationDate") or {}).get("dateTime", "")[:10]
            if d:
                pris.add(d)
    for e in json.load(open(os.path.join(ROOT, "journal.json"), encoding="utf-8")).get("episodes", []):
        if e.get("publication"):
            pris.add(e["publication"][:10])
    d = now.date()
    for _ in range(60):
        hh, mm = map(int, h0.split(":"))
        cand = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
        if d.weekday() in jours and cand - now >= delai and d.isoformat() not in pris:
            return cand.isoformat()
        d += dt.timedelta(days=1)
    raise RuntimeError("aucun créneau libre dans les 60 prochains jours")


def journal(ep_dir, kv):
    path = os.path.join(ROOT, "journal.json")
    J = json.load(open(path, encoding="utf-8"))
    spec, num, slug = episode_info(ep_dir)
    eps = J.setdefault("episodes", [])
    e = next((x for x in eps if x.get("numero") == num), None)
    if e is None:
        e = dict(numero=num, slug=slug)
        eps.append(e)
    e.update(dict(titre=" ".join(spec["titre"]), theme=spec.get("theme", slug),
                  idees=[dict(affirmation=i["affirmation"], verdict=i["verdict"],
                              sources=[s.get("url") for s in i.get("sources", [])]) for i in spec["idees"]],
                  prochain=spec["prochain"]["affirmation"]))
    e.update(kv)
    eps.sort(key=lambda x: x["numero"])
    J["dernier_numero"] = max(x["numero"] for x in eps)
    J["prochaine_affirmation"] = eps[-1].get("prochain")
    json.dump(J, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(e, ensure_ascii=False, indent=1))


def legende(ep_dir, rapport=None):
    spec, num, slug = episode_info(ep_dir)
    txt = spec["publication"]["legende"].strip()
    credits = []
    if rapport and os.path.exists(rapport):
        credits = json.load(open(rapport, encoding="utf-8")).get("credits_pictogrammes", [])
    for c in credits:
        if c not in txt:
            txt += "\n" + c
    print(txt)
    return txt


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    c = sys.argv[1]
    if c == "heberger":
        sys.exit(0 if heberger(sys.argv[2], sys.argv[3]) else 2)
    elif c == "creneau":
        print(creneau(sys.argv[2] if len(sys.argv) > 2 else None))
    elif c == "journal":
        args = sys.argv[3:]
        kv = {}
        for k, v in zip(args[0::2], args[1::2]):
            kv[k.lstrip("-")] = v
        journal(sys.argv[2], kv)
    elif c == "legende":
        legende(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        print(__doc__)
        sys.exit(1)
