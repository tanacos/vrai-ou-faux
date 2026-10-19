#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Relais des médias ElevenLabs vers la session Claude.

Les sessions Claude n'ont pas accès au réseau d'ElevenLabs ni à son stockage (storage.googleapis.com) : un fichier
généré (voix, musique, bruitage, image) ne peut donc pas être téléchargé directement. Le relais passe par GitHub, seul
service joignable des deux côtés : la session dépose une demande (l'URL du fichier) dans la branche jetable « relais »
du dépôt public ; un runner GitHub Actions (moteur/relais/relais-medias.yml) télécharge le fichier et le dépose dans la
même branche ; la session le récupère par git. Compter 10 à 40 s par lot.

  python3 moteur/relais.py recuperer DOSSIER nom1.mp3=URL1 [nom2.mp3=URL2 …] [--attente 300]
      -> DOSSIER/nom1.mp3 … ; affiche un JSON {nom: {fichier, octets, sha256}} ; code 0 si tout est arrivé.
  python3 moteur/relais.py etat
      -> état de la branche relais (fichiers, taille, workflow à jour ?).
  python3 moteur/relais.py menage [--garder-jours 10]
      -> retire de la branche les médias plus anciens que N jours (l'historique git les garde ; la branche peut être
         supprimée sur GitHub à tout moment : elle est recréée au besoin).

Attention : le dépôt est public, donc les médias relayés le sont aussi (comme les vidéos de la branche « videos »).
"""
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
REPO = CONFIG["depot"]
BRANCHE = "relais"
WORKFLOW_SRC = os.path.join(ROOT, "moteur", "relais", "relais-medias.yml")
WORKFLOW_DST = ".github/workflows/relais-medias.yml"
LOCAL = os.environ.get("VF_RELAIS_DIR", "/tmp/vrai-ou-faux-relais")


def sh(*cmd, check=True, cwd=None, binary=False):
    r = subprocess.run(cmd, capture_output=True, cwd=cwd, text=not binary)
    if check and r.returncode != 0:
        err = r.stderr if not binary else r.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"{' '.join(cmd)}\n{err}")
    return r


def git(*args, check=True, binary=False):
    return sh("git", "-C", LOCAL, *args, check=check, binary=binary)


def _ident():
    return ["-c", "user.name=Claude (routine vrai-ou-faux)", "-c", "user.email=noreply@anthropic.com"]


def preparer():
    """Copie locale à jour de la branche relais (créée si elle n'existe pas), workflow synchronisé avec main."""
    if os.path.isdir(os.path.join(LOCAL, ".git")):
        r = git("fetch", "-q", "--depth", "1", "origin", BRANCHE, check=False)
        if r.returncode == 0:
            git("reset", "-q", "--hard", f"origin/{BRANCHE}")
        else:
            shutil.rmtree(LOCAL, ignore_errors=True)
    if not os.path.isdir(os.path.join(LOCAL, ".git")):
        shutil.rmtree(LOCAL, ignore_errors=True)
        r = sh("git", "clone", "-q", "--depth", "1", "--branch", BRANCHE, "--single-branch",
               f"https://github.com/{REPO}", LOCAL, check=False)
        if r.returncode != 0:
            if "not found" not in (r.stderr + r.stdout).lower():
                raise RuntimeError(f"clonage de la branche {BRANCHE} impossible :\n{r.stderr}")
            shutil.rmtree(LOCAL, ignore_errors=True)
            os.makedirs(LOCAL)
            sh("git", "-C", LOCAL, "init", "-q", "-b", BRANCHE)
            sh("git", "-C", LOCAL, "remote", "add", "origin", f"https://github.com/{REPO}")
            with open(os.path.join(LOCAL, "LISEZMOI.md"), "w", encoding="utf-8") as f:
                f.write("Branche jetable : relais des médias ElevenLabs vers les sessions Claude "
                        "(voir moteur/relais.py sur main). Elle peut être supprimée à tout moment.\n")
    # le workflow de la branche suit toujours le modèle de main
    dst = os.path.join(LOCAL, WORKFLOW_DST)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    src = open(WORKFLOW_SRC, encoding="utf-8").read()
    if not os.path.exists(dst) or open(dst, encoding="utf-8").read() != src:
        open(dst, "w", encoding="utf-8").write(src)
    os.makedirs(os.path.join(LOCAL, "demandes"), exist_ok=True)


def pousser(message):
    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        return False
    sh("git", "-C", LOCAL, *_ident(), "commit", "-q", "-m", message)
    for _ in range(5):
        r = git("push", "-q", "origin", f"HEAD:{BRANCHE}", check=False)
        if r.returncode == 0:
            return True
        git("pull", "-q", "--rebase", "origin", BRANCHE, check=False)
        time.sleep(2)
    raise RuntimeError(f"push refusé sur la branche {BRANCHE} :\n{r.stderr}")


def _slug(nom):
    base = os.path.basename(nom)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:80]


def recuperer(dossier, demandes, attente=300):
    """demandes = [(nom_local, url)] ; renvoie {nom_local: {fichier, octets, sha256}} (ou {erreur})."""
    os.makedirs(dossier, exist_ok=True)
    preparer()
    jeton = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + hashlib.sha1(
        json.dumps(demandes).encode()).hexdigest()[:6]
    attendus = {}
    for nom, url in demandes:
        distant = f"{jeton}__{_slug(nom)}"
        with open(os.path.join(LOCAL, "demandes", distant + ".json"), "w", encoding="utf-8") as f:
            json.dump({"url": url, "nom": distant}, f, ensure_ascii=False)
        attendus[nom] = distant
    pousser(f"relais : {len(demandes)} demande(s) {jeton}")
    t0 = time.time()
    res = {}
    while time.time() - t0 < attente and len(res) < len(attendus):
        time.sleep(4)
        if git("fetch", "-q", "--depth", "1", "origin", BRANCHE, check=False).returncode != 0:
            continue
        ls = git("ls-tree", "-r", "--name-only", f"origin/{BRANCHE}", "medias").stdout.split()
        for nom, distant in attendus.items():
            if nom in res:
                continue
            if f"medias/{distant}.erreur" in ls:
                msg = git("show", f"origin/{BRANCHE}:medias/{distant}.erreur").stdout.strip()
                res[nom] = {"erreur": msg}
            elif f"medias/{distant}" in ls:
                data = git("show", f"origin/{BRANCHE}:medias/{distant}", binary=True).stdout
                out = os.path.join(dossier, nom)
                with open(out, "wb") as f:
                    f.write(data)
                res[nom] = {"fichier": os.path.abspath(out), "octets": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()}
    for nom in attendus:
        res.setdefault(nom, {"erreur": f"délai dépassé ({attente} s) : le runner GitHub n'a rien déposé"})
    git("reset", "-q", "--hard", f"origin/{BRANCHE}", check=False)
    res["_duree_s"] = round(time.time() - t0, 1)
    return res


def menage(garder_jours=10):
    preparer()
    limite = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=garder_jours)).strftime("%Y%m%d%H%M%S")
    n = 0
    mdir = os.path.join(LOCAL, "medias")
    for f in sorted(os.listdir(mdir)) if os.path.isdir(mdir) else []:
        m = re.match(r"(\d{14})_", f)
        if f.startswith("test_") or (m and m.group(1) < limite):
            git("rm", "-q", os.path.join("medias", f))
            n += 1
    pousser(f"relais : ménage ({n} fichier(s) de plus de {garder_jours} j)")
    return n


def etat():
    preparer()
    mdir = os.path.join(LOCAL, "medias")
    fichiers = sorted(os.listdir(mdir)) if os.path.isdir(mdir) else []
    taille = sum(os.path.getsize(os.path.join(mdir, f)) for f in fichiers)
    wf = os.path.join(LOCAL, WORKFLOW_DST)
    return dict(branche=BRANCHE, fichiers=len(fichiers), taille_mio=round(taille / 2 ** 20, 2),
                workflow_a_jour=os.path.exists(wf) and open(wf).read() == open(WORKFLOW_SRC).read())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    c = sys.argv[1]
    if c == "recuperer":
        args = sys.argv[3:]
        att = 300
        if "--attente" in args:
            k = args.index("--attente")
            att = int(args[k + 1])
            del args[k:k + 2]
        dem = []
        for a in args:
            nom, url = a.split("=", 1)
            dem.append((nom, url))
        out = recuperer(sys.argv[2], dem, att)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        sys.exit(0 if all("fichier" in v for k, v in out.items() if not k.startswith("_")) else 2)
    elif c == "menage":
        j = int(sys.argv[sys.argv.index("--garder-jours") + 1]) if "--garder-jours" in sys.argv else 10
        print(json.dumps({"retires": menage(j)}, ensure_ascii=False))
    elif c == "etat":
        print(json.dumps(etat(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        sys.exit(1)
