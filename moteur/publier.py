#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mise en ligne d'une vidéo terminée et tenue du journal, pour les deux séries : « Vrai ou faux ? » (journal.json,
#vraioufaux) et le mini-reportage INFINIMENT (journal_reportages.json, #infiniment). La série d'un épisode se lit
dans son episode.json ; pour « etat » et « creneau », --serie infiniment choisit le reportage.

  python3 moteur/publier.py heberger episodes/004-sommeil SORTIE/video.mp4
      -> dépose la vidéo dans la branche « videos » du dépôt public et affiche son lien direct
         (raw.githubusercontent.com) à donner à Metricool ; vérifie sa présence via l'API GitHub.
  python3 moteur/publier.py creneau [JSON_DES_POSTS_METRICOOL]
      -> prochain créneau libre (mercredi ou samedi, au moins 48 h plus tard), au format ISO, d'après config.json
         et la liste des publications déjà programmées (fichier JSON de getScheduledPosts, facultatif).
  python3 moteur/publier.py journal episodes/004-sommeil --cle valeur [--cle valeur…]
      -> ajoute ou met à jour l'entrée de l'épisode dans journal.json.
  python3 moteur/publier.py legende episodes/004-sommeil [RAPPORT.json]
      -> légende finale (légende du script + crédits obligatoires des pictogrammes).
  python3 moteur/publier.py etat [--serie infiniment] [JSON_DES_POSTS_METRICOOL]
      -> point de départ de la routine : pause ?, file pleine ?, épisode à reprendre (statut « fabriqué » ou
         « hébergé » après un run interrompu) ou nouveau numéro, publications Metricool absentes du journal.
         Chaque série ne compte que ses propres publications (mot-dièse #vraioufaux ou #infiniment).
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
_REP = CONFIG.get("reportage", {})
SERIES = {
    "vraioufaux": dict(journal="journal.json", hashtag="#vraioufaux", prefixe="vrai_ou_faux", pauses=("PAUSE",),
                       jours=CONFIG["jours_publication"], heure=CONFIG.get("heure_defaut", "18:00"),
                       file_max=CONFIG.get("file_max", 3)),
    "infiniment": dict(journal=_REP.get("journal", "journal_reportages.json"), hashtag=_REP.get("hashtag", "#infiniment"),
                       prefixe="infiniment", pauses=("PAUSE", "PAUSE_REPORTAGE"),
                       jours=_REP.get("jours_publication", ["lundi"]), heure=_REP.get("heure_defaut", "18:00"),
                       file_max=_REP.get("file_max", 2)),
}


def serie_de(spec):
    return "infiniment" if str(spec.get("serie", "")).upper() == "INFINIMENT" else "vraioufaux"


def lire_journal(serie):
    p = os.path.join(ROOT, SERIES[serie]["journal"])
    if not os.path.exists(p):
        return {"episodes": []}
    return json.load(open(p, encoding="utf-8"))


def nom_video(spec):
    sr = serie_de(spec)
    return f"{SERIES[sr]['prefixe']}_{int(spec['numero']):02d}_{spec.get('slug', 'episode')}.mp4"


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


VIDEOS_DIR = "/tmp/vrai-ou-faux-videos"


def heberger(ep_dir, mp4):
    """Dépose la vidéo dans la branche « videos » du dépôt public (les releases GitHub sont refusées aux sessions
    Claude) et renvoie son lien direct raw.githubusercontent.com, que Metricool télécharge puis recopie chez lui.
    Les vidéos des épisodes déjà publiés sont retirées de la branche (Metricool en garde sa propre copie)."""
    import shutil
    spec, num, slug = episode_info(ep_dir)
    repo = CONFIG["depot"]
    name = nom_video(spec)
    if not os.path.isdir(os.path.join(VIDEOS_DIR, ".git")):
        shutil.rmtree(VIDEOS_DIR, ignore_errors=True)
        r = sh("git", "clone", "--depth", "1", "--branch", "videos", "--single-branch",
               f"https://github.com/{repo}", VIDEOS_DIR, check=False)
        if r.returncode != 0:
            if "not found" not in (r.stderr + r.stdout).lower():
                raise RuntimeError(f"clonage de la branche videos impossible :\n{r.stderr}")
            # branche supprimée par Nathan (entretien, voir README) : on la recrée, vide d'historique
            shutil.rmtree(VIDEOS_DIR, ignore_errors=True)
            os.makedirs(VIDEOS_DIR)
            sh("git", "-C", VIDEOS_DIR, "init", "-q", "-b", "videos")
            sh("git", "-C", VIDEOS_DIR, "remote", "add", "origin", f"https://github.com/{repo}")
            with open(os.path.join(VIDEOS_DIR, "LISEZMOI.md"), "w", encoding="utf-8") as f:
                f.write("Vidéos en transit vers Metricool (qui en garde sa propre copie). Branche jetable.\n")
    else:
        sh("git", "-C", VIDEOS_DIR, "pull", "--ff-only")
    # ménage : retirer les vidéos d'épisodes (des deux séries) dont la date de publication est passée
    now = dt.datetime.now(TZ)
    for sr in SERIES:
        for e in lire_journal(sr).get("episodes", []):
            f = f"{SERIES[sr]['prefixe']}_{int(e['numero']):02d}_{e.get('slug', '')}.mp4"
            pub = e.get("publication")
            if pub and os.path.exists(os.path.join(VIDEOS_DIR, f)) and f != name:
                if dt.datetime.fromisoformat(pub) < now:
                    sh("git", "-C", VIDEOS_DIR, "rm", "-q", f)
    for f in os.listdir(VIDEOS_DIR):
        if f.startswith("essai") and f.endswith(".mp4"):
            sh("git", "-C", VIDEOS_DIR, "rm", "-q", f)
    shutil.copyfile(mp4, os.path.join(VIDEOS_DIR, name))
    sh("git", "-C", VIDEOS_DIR, "add", "-A")
    st = sh("git", "-C", VIDEOS_DIR, "status", "--porcelain").stdout.strip()
    if st:
        sh("git", "-C", VIDEOS_DIR, "commit", "-q", "-m", f"Vidéo de l'épisode {num} ({slug})")
        sh("git", "-C", VIDEOS_DIR, "push", "-q", "origin", "videos")
    # vérification côté GitHub : le fichier existe bien dans la branche, avec la bonne taille
    meta = json.loads(sh("gh", "api", f"repos/{repo}/contents/{name}?ref=videos").stdout)
    size_local = os.path.getsize(mp4)
    ok = int(meta.get("size", -1)) == size_local
    # lien figé sur le commit : immuable, donc jamais servi depuis un cache périmé
    sha = sh("git", "-C", VIDEOS_DIR, "rev-parse", "HEAD").stdout.strip()
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{name}"
    out = dict(url=url, present_sur_github=ok, taille=size_local)
    # l'historique de la branche garde chaque vidéo (les sessions Claude ne peuvent pas le réécrire) : on surveille
    try:
        kio = int(sh("gh", "api", f"repos/{repo}", "--jq", ".size").stdout.strip())
        out["taille_depot_mio"] = round(kio / 1024)
        if kio > TAILLE_ALERTE_KIO:
            out["alerte"] = (f"Le dépôt pèse {kio / 1024 / 1024:.1f} Gio. Entretien conseillé : sur GitHub, onglet "
                             "« Branches », supprimer la branche « videos » (la routine la recrée toute seule au "
                             "prochain épisode ; Metricool garde ses copies).")
    except Exception:  # noqa: BLE001 — la mesure de taille est un confort, jamais bloquante
        pass
    print(json.dumps(out, ensure_ascii=False))
    return url if ok else None


TAILLE_ALERTE_KIO = 2 * 1024 * 1024        # 2 Gio : GitHub recommande de rester sous 5 Gio par dépôt


def etat(posts_json=None, serie="vraioufaux"):
    """Point de départ de la routine : pause, file d'attente, épisode à reprendre ou nouvel épisode, publications
    Metricool absentes du journal (run précédent interrompu après la programmation). Seules les publications de la
    série (son mot-dièse) comptent."""
    cfg = SERIES[serie]
    J = lire_journal(serie)
    eps = sorted(J.get("episodes", []), key=lambda e: e["numero"])
    out = dict(serie=serie, pause=any(os.path.exists(os.path.join(ROOT, f)) for f in cfg["pauses"]))
    reprises = ("fabriqué", "hébergé") + (("en attente de voix", "voix faite") if serie == "infiniment" else ())
    en_cours = [e for e in eps if e.get("statut") in reprises]
    if en_cours:
        e = en_cours[0]
        dossier = e.get("dossier") or f"episodes/{int(e['numero']):03d}-{e.get('slug', '')}"
        out.update(action="reprendre", numero=e["numero"], statut=e["statut"], dossier=dossier, video=e.get("video"))
    elif serie == "infiniment":
        out.update(action="nouveau", numero=int(J.get("dernier_numero", 0)) + 1,
                   sujet_impose=J.get("prochain_sujet"))
    else:
        out.update(action="nouveau", numero=int(J.get("dernier_numero", 0)) + 1,
                   idee_1_imposee=J.get("prochaine_affirmation"))
    if posts_json:
        data = json.load(open(posts_json, encoding="utf-8"))
        posts = data.get("data", data) if isinstance(data, dict) else data
        tk = [p for p in posts if any((pr or {}).get("network") == "tiktok" for pr in p.get("providers") or [])]
        mien = [p for p in tk if cfg["hashtag"] in (p.get("text") or "")]
        a_venir = [p for p in mien if not p.get("draft")]
        out["file_attente"] = len(a_venir)
        out["file_max"] = cfg["file_max"]
        out["file_pleine"] = len(a_venir) >= out["file_max"]
        dates = {str(e.get("publication", ""))[:16] for e in eps}
        orph = []
        for p in mien:
            d = (p.get("publicationDate") or {}).get("dateTime", "")[:16]
            if d not in dates:
                orph.append(dict(id=p.get("id"), uuid=p.get("uuid"), date=d, brouillon=bool(p.get("draft")),
                                 debut=(p.get("text") or "")[:90]))
        out["orphelins"] = orph
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def creneau(posts_json=None, now=None, serie="vraioufaux"):
    """Premier créneau libre parmi les jours de publication de la série, au moins delai_veto_h heures plus tard ;
    un jour qui a déjà une publication (n'importe quelle série) est pris."""
    cfg = SERIES[serie]
    now = now or dt.datetime.now(TZ)
    jours = [JOURS[j] for j in cfg["jours"]]
    delai = dt.timedelta(hours=CONFIG.get("delai_veto_h", 48))
    h0 = cfg["heure"]
    pris = set()
    if posts_json:
        data = json.load(open(posts_json, encoding="utf-8"))
        for p in data.get("data", data if isinstance(data, list) else []):
            d = (p.get("publicationDate") or {}).get("dateTime", "")[:10]
            if d:
                pris.add(d)
    for sr in SERIES:
        for e in lire_journal(sr).get("episodes", []):
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
    spec, num, slug = episode_info(ep_dir)
    serie = serie_de(spec)
    path = os.path.join(ROOT, SERIES[serie]["journal"])
    J = lire_journal(serie)
    eps = J.setdefault("episodes", [])
    e = next((x for x in eps if x.get("numero") == num), None)
    if e is None:
        e = dict(numero=num, slug=slug)
        eps.append(e)
    if serie == "infiniment":
        e.update(dict(titre=spec.get("titre", slug), dossier=os.path.relpath(os.path.abspath(ep_dir), ROOT),
                      sources=[x.get("url") for x in spec.get("sources", [])], prochain=spec.get("prochain")))
    else:
        e.update(dict(titre=" ".join(spec["titre"]), theme=spec.get("theme", slug),
                      idees=[dict(affirmation=i["affirmation"], verdict=i["verdict"],
                                  sources=[x.get("url") for x in i.get("sources", [])]) for i in spec["idees"]],
                      prochain=spec["prochain"]["affirmation"]))
    if kv.get("publication"):
        # « 2026-10-21T18:00:00 » (heure de Paris, telle que Metricool la donne) -> avec le bon décalage été/hiver
        d = dt.datetime.fromisoformat(kv["publication"])
        kv["publication"] = (d if d.tzinfo else d.replace(tzinfo=TZ)).isoformat()
    e.update(kv)
    eps.sort(key=lambda x: x["numero"])
    J["dernier_numero"] = max(x["numero"] for x in eps)
    if serie == "infiniment":
        J["prochain_sujet"] = eps[-1].get("prochain")
    else:
        J["prochaine_affirmation"] = eps[-1].get("prochain")
    json.dump(J, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(e, ensure_ascii=False, indent=1))


def legende(ep_dir, rapport=None):
    spec, num, slug = episode_info(ep_dir)
    txt = spec["publication"]["legende"].strip()
    credits = []
    if rapport and os.path.exists(rapport):
        credits = json.load(open(rapport, encoding="utf-8")).get("credits_pictogrammes", [])
    if serie_de(spec) == "infiniment":                 # pictogrammes utilisés dans les scènes du reportage
        noms = []

        def chercher(x):
            if isinstance(x, dict):
                if x.get("type") == "icone" and x.get("nom"):
                    noms.append(x["nom"])
                for v in x.values():
                    chercher(v)
            elif isinstance(x, list):
                for v in x:
                    chercher(v)
        chercher(spec.get("scenes", {}))
        if noms:
            sys.path.insert(0, os.path.join(ROOT, "moteur"))
            from vf import icons as IC
            credits += IC.credits(noms)
    v = spec.get("voix") or {}
    if str(v.get("fournisseur", "")).lower().startswith("kyutai"):
        credits.append("Voix de synthèse : Kyutai TTS (CC BY 4.0)")        # attribution exigée par la licence
    for c in credits:
        if c in txt or (c.startswith("Voix de synthèse") and "Kyutai TTS (CC BY 4.0)" in txt):
            continue
        lignes = txt.split("\n")
        k_hash = max((k for k, l_ in enumerate(lignes) if l_.lstrip().startswith("#")), default=None)
        if c.startswith("Voix de synthèse") and k_hash is not None:
            lignes.insert(k_hash, c)                              # avant la ligne des mots-dièse
            txt = "\n".join(lignes)
        else:
            txt += "\n" + c
    print(txt)
    return txt


if __name__ == "__main__":
    args = sys.argv[1:]
    serie = "vraioufaux"
    if "--serie" in args:
        k = args.index("--serie")
        serie = args[k + 1]
        del args[k:k + 2]
        if serie not in SERIES:
            print(f"série inconnue : {serie} (vraioufaux, infiniment)")
            sys.exit(1)
    if not args:
        print(__doc__)
        sys.exit(1)
    c = args[0]
    if c == "heberger":
        sys.exit(0 if heberger(args[1], args[2]) else 2)
    elif c == "creneau":
        print(creneau(args[1] if len(args) > 1 else None, serie=serie))
    elif c == "journal":
        rest = args[2:]
        kv = {}
        for k, v in zip(rest[0::2], rest[1::2]):
            kv[k.lstrip("-")] = v
        journal(args[1], kv)
    elif c == "legende":
        legende(args[1], args[2] if len(args) > 2 else None)
    elif c == "etat":
        etat(args[1] if len(args) > 1 else None, serie=serie)
    else:
        print(__doc__)
        sys.exit(1)
