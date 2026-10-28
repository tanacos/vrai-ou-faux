# -*- coding: utf-8 -*-
"""Pictogrammes vectoriels embarqués, 14 118 au total (extraits du paquet react-icons 5.7.0) :
  pi: Phosphor (MIT)            md: Material Design (Apache 2.0)   io: Ionicons 5 (MIT)
  ri: Remix Icon (Apache 2.0)   bs: Bootstrap Icons (MIT)          gi: Game Icons (CC BY 3.0 -> crédit obligatoire,
                                                                       affiché à l'écran par le quiz)
Noms acceptés : « globe », « pi:globe », « globe-hemisphere-west », « md:castle », « gi:shark-fin », « io:telescope »,
« ri:planet », « PiRocketLaunchFill »… Sans préfixe : Phosphor plein, puis Material, Remix, Ionicons, Bootstrap, Game Icons.
« :duotone » ou « :bold » en suffixe pour les autres graisses Phosphor.
  python3 -m vf.icons chercher lune requin    -> liste les noms qui contiennent « moon », « shark »
  python3 -m vf.icons planche globe moon …    -> image PNG de contrôle des pictogrammes
"""
import gzip
import json
import math
import os
import re
import sys

import cv2
import numpy as np

f32 = np.float32
_DATA = None
_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "pictogrammes.json.gz")
CREDITS = {"Gi": "Pictogrammes : game-icons.net (CC BY 3.0)"}

# quelques équivalences français -> anglais pour la recherche
FR_EN = {"lune": "moon", "soleil": "sun", "étoile": "star", "etoile": "star", "terre": "globe", "planète": "planet",
         "planete": "planet", "fusée": "rocket", "fusee": "rocket", "cerveau": "brain", "coeur": "heart", "cœur": "heart",
         "eau": "drop", "feu": "fire", "arbre": "tree", "feuille": "leaf", "chat": "cat", "chien": "dog", "oiseau": "bird",
         "poisson": "fish", "œil": "eye", "oeil": "eye", "oreille": "ear", "dent": "tooth", "os": "bone", "crâne": "skull",
         "horloge": "clock", "sablier": "hourglass", "calendrier": "calendar", "carte": "map", "boussole": "compass",
         "maison": "house", "voiture": "car", "avion": "airplane", "bateau": "boat", "train": "train", "vélo": "bicycle",
         "argent": "money", "livre": "book", "musique": "music", "éclair": "lightning", "eclair": "lightning",
         "nuage": "cloud", "pluie": "rain", "neige": "snowflake", "vent": "wind", "montagne": "mountains",
         "vague": "wave", "virus": "virus", "microbe": "bacteria", "pilule": "pill", "médicament": "pill",
         "thermomètre": "thermometer", "ampoule": "lightbulb", "aimant": "magnet", "atome": "atom", "adn": "dna",
         "satellite": "satellite", "téléscope": "binoculars", "personne": "person", "bébé": "baby", "foule": "users",
         "mur": "wall", "château": "castle", "chateau": "castle", "temple": "temple", "pyramide": "pyramid",
         "question": "question", "attention": "warning", "interdit": "prohibit", "requin": "shark", "baleine": "whale",
         "astronaute": "astronaut", "télescope": "telescope", "telescope": "telescope", "muraille": "wall",
         "météore": "meteor", "comète": "comet", "volcan": "volcano", "dinosaure": "dinosaur", "abeille": "bee",
         "fourmi": "ant", "araignée": "spider", "serpent": "snake", "cheval": "horse", "vache": "cow",
         "pyramide_": "pyramid", "statue": "statue", "tour": "tower", "pont": "bridge", "usine": "factory",
         "soldat": "soldier", "épée": "sword", "couronne": "crown", "roi": "king", "dent_": "tooth"}


def data():
    global _DATA
    if _DATA is None:
        with gzip.open(_PATH, "rt", encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def _camel(s):
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[-_\s]+", s.strip()) if p)


_PREF = {"pi": "Pi", "md": "Md", "io": "Io", "ri": "Ri", "bs": "Bs", "gi": "Gi"}


def _cands(lib, c, weight):
    return {"Pi": [f"Pi{c}{weight}", f"Pi{c}Fill"], "Md": [f"Md{c}"], "Ri": [f"Ri{c}Fill"], "Io": [f"Io{c}"],
            "Bs": [f"Bs{c}Fill", f"BsFill{c}Fill"], "Gi": [f"Gi{c}"]}[lib]


def resolve(name):
    """Nom libre -> clé exacte du catalogue (ou None)."""
    D = data()
    if not isinstance(name, str) or not name.strip():
        return None
    if name in D:
        return name
    n = name.strip()
    lib, weight = None, "Fill"
    parts = n.split(":")
    if parts[0].lower() in _PREF:
        lib = _PREF[parts[0].lower()]
        parts = parts[1:]
    n = parts[0] if parts else ""
    if len(parts) > 1:
        weight = {"duotone": "Duotone", "bold": "Bold", "fill": "Fill"}.get(parts[1].lower(), "Fill")
    c = _camel(n)
    order = [lib] if lib else ["Pi", "Md", "Ri", "Io", "Bs", "Gi"]
    for L in order:
        for k in _cands(L, c, weight):
            if k in D:
                return k
    return None


def search(word, limit=80):
    w = FR_EN.get(word.lower(), word.lower()).replace("-", "").replace(" ", "")
    keys = [k for k in data() if w in k.lower()
            and (k.endswith("Fill") or k.startswith(("Md", "Gi", "Io")))]
    rank = {"Pi": 0, "Md": 1, "Ri": 2, "Io": 3, "Bs": 4, "Gi": 5}
    keys.sort(key=lambda k: (rank.get(k[:2], 9), k))
    return keys[:limit]


def credits(names):
    """Crédits obligatoires pour une liste de pictogrammes (licences avec attribution)."""
    out = []
    for n in names:
        k = resolve(n)
        if k and k[:2] in CREDITS and CREDITS[k[:2]] not in out:
            out.append(CREDITS[k[:2]])
    return out


# ------------------------------------------------------------------ chemins SVG -> polylignes
_TOK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _arc(p0, rx, ry, phi, fa, fs, p1, tol):
    """Arc elliptique SVG (paramétrage par extrémités) -> points (sans le premier)."""
    x1, y1 = p0
    x2, y2 = p1
    if rx == 0 or ry == 0:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(num / den, 0)) if den > 0 else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(2, int(math.ceil(abs(dt) * max(rx, ry) / max(tol * 6, 1e-6))))
    n = min(n, 400)
    pts = []
    for k in range(1, n + 1):
        t = t1 + dt * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    return pts


def _bez(pts, tol):
    p = np.asarray(pts, float)
    L = sum(np.hypot(*(p[i + 1] - p[i])) for i in range(len(p) - 1))
    n = int(min(max(math.ceil(L / max(tol * 4, 1e-6)), 2), 200))
    t = np.linspace(0, 1, n + 1)[1:, None]
    if len(p) == 3:
        q = (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * p[1] + t ** 2 * p[2]
    else:
        q = (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]
    return [tuple(v) for v in q]


def path_polys(d, tol=0.05):
    """Chaîne « d » d'un chemin SVG -> liste de polylignes fermées (coordonnées du viewBox)."""
    toks = _TOK.findall(d)
    i = 0
    polys, cur = [], []
    x = y = 0.0
    sx = sy = 0.0
    cmd = None
    last_c = None      # dernier point de contrôle (pour S/T)
    last_cmd = None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def flag():
        # les drapeaux d'arc peuvent être collés : « 0,0,1 » ou « 011 »
        nonlocal i
        t = toks[i]
        if len(t) > 1 and t[0] in "01" and not t.startswith(("0.", "1.")):
            toks[i] = t[1:]
            return int(t[0])
        i += 1
        return int(float(t))

    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    polys.append(cur)
                cur = []
                x, y = sx, sy
                last_c, last_cmd = None, "Z"
                continue
        elif cmd is None:
            i += 1
            continue
        rel = cmd.islower()
        C = cmd.upper()
        if C == "M":
            nx, ny = num(), num()
            if rel:
                nx, ny = x + nx, y + ny
            if cur:
                polys.append(cur)
            cur = [(nx, ny)]
            x, y = sx, sy = nx, ny
            cmd = "l" if rel else "L"
            last_c = None
        elif C == "L":
            nx, ny = num(), num()
            if rel:
                nx, ny = x + nx, y + ny
            cur.append((nx, ny))
            x, y = nx, ny
            last_c = None
        elif C == "H":
            nx = num()
            x = x + nx if rel else nx
            cur.append((x, y))
            last_c = None
        elif C == "V":
            ny = num()
            y = y + ny if rel else ny
            cur.append((x, y))
            last_c = None
        elif C == "C":
            c1 = (num(), num())
            c2 = (num(), num())
            p = (num(), num())
            if rel:
                c1, c2, p = (x + c1[0], y + c1[1]), (x + c2[0], y + c2[1]), (x + p[0], y + p[1])
            cur += _bez([(x, y), c1, c2, p], tol)
            last_c = c2
            x, y = p
        elif C == "S":
            c2 = (num(), num())
            p = (num(), num())
            if rel:
                c2, p = (x + c2[0], y + c2[1]), (x + p[0], y + p[1])
            c1 = (2 * x - last_c[0], 2 * y - last_c[1]) if (last_c is not None and last_cmd in "CS") else (x, y)
            cur += _bez([(x, y), c1, c2, p], tol)
            last_c = c2
            x, y = p
        elif C == "Q":
            c1 = (num(), num())
            p = (num(), num())
            if rel:
                c1, p = (x + c1[0], y + c1[1]), (x + p[0], y + p[1])
            cur += _bez([(x, y), c1, p], tol)
            last_c = c1
            x, y = p
        elif C == "T":
            p = (num(), num())
            if rel:
                p = (x + p[0], y + p[1])
            c1 = (2 * x - last_c[0], 2 * y - last_c[1]) if (last_c is not None and last_cmd in "QT") else (x, y)
            cur += _bez([(x, y), c1, p], tol)
            last_c = c1
            x, y = p
        elif C == "A":
            rx, ry, phi = num(), num(), num()
            fa, fs = flag(), flag()
            p = (num(), num())
            if rel:
                p = (x + p[0], y + p[1])
            cur += _arc((x, y), rx, ry, phi, fa, fs, p, tol)
            last_c = None
            x, y = p
        else:
            i += 1
        last_cmd = C
        if not cur:
            cur = [(x, y)]
    if cur and len(cur) > 1:
        polys.append(cur)
    return [np.asarray(p, float) for p in polys if len(p) >= 3]


def _elem_polys(e, tol):
    t = e["t"]
    if t == "path":
        return path_polys(e["d"], tol)
    if t in ("circle", "ellipse"):
        cx, cy = float(e.get("cx", 0)), float(e.get("cy", 0))
        rx = float(e.get("r", e.get("rx", 0)))
        ry = float(e.get("r", e.get("ry", rx)))
        n = max(24, int(2 * math.pi * max(rx, ry) / max(tol * 4, 1e-6)))
        a = np.linspace(0, 2 * math.pi, min(n, 720), endpoint=False)
        return [np.stack([cx + rx * np.cos(a), cy + ry * np.sin(a)], 1)]
    if t == "rect":
        x0, y0 = float(e.get("x", 0)), float(e.get("y", 0))
        w, h = float(e["width"]), float(e["height"])
        return [np.array([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)])]
    if t == "polygon":
        v = [float(s) for s in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", e["points"])]
        return [np.array(v).reshape(-1, 2)]
    return []


def _signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


_MC = {}


def mask(name, size, layer=None):
    """Masque float32 (size x size) du pictogramme, règle de remplissage non nulle ; layer=« plein »/« clair » pour
    les duotones (renvoie la couche opaque ou la couche translucide)."""
    key = (name, int(size), layer)
    if key in _MC:
        return _MC[key]
    k = resolve(name)
    if k is None:
        raise KeyError(f"pictogramme inconnu : {name!r}")
    ic = data()[k]
    vx, vy, vw, vh = ic["vb"]
    s = size / max(vw, vh)
    ox = (size - vw * s) / 2 - vx * s
    oy = (size - vh * s) / 2 - vy * s
    SH = 4
    acc = np.zeros((int(size), int(size)), f32)
    for e in ic["el"]:
        op = float(e.get("op", 1.0))
        if layer == "plein" and op < 0.999:
            continue
        if layer == "clair" and op >= 0.999:
            continue
        polys = _elem_polys(e, tol=0.25 / s)
        wind = np.zeros_like(acc)
        for p in polys:
            q = np.clip(np.round((p * s + [ox, oy]) * (1 << SH)), -1e8, 1e8).astype(np.int32)
            m = np.zeros(acc.shape, np.uint8)
            cv2.fillPoly(m, [q], 255, cv2.LINE_AA, SH)
            sgn = 1.0 if _signed_area(p) >= 0 else -1.0
            if e.get("eo"):
                wind += m.astype(f32) / 255.0
            else:
                wind += sgn * m.astype(f32) / 255.0
        if e.get("eo"):
            cov = 1 - np.abs(1 - np.mod(wind, 2.0))
        else:
            cov = np.clip(np.abs(wind), 0, 1)
        acc = np.maximum(acc, cov * (1.0 if layer == "clair" else op)) if layer != "clair" else np.maximum(acc, cov)
    if len(_MC) > 400:
        _MC.clear()
    _MC[key] = acc
    return acc


def exists(name):
    return resolve(name) is not None


def planche(names, path, S=200, cols=6):
    """Image de contrôle : pictogrammes et leurs noms (pour vérifier visuellement un choix)."""
    from PIL import Image, ImageDraw, ImageFont
    rows = (len(names) + cols - 1) // cols
    img = Image.new("L", (cols * S, rows * (S + 40)), 0)
    d = ImageDraw.Draw(img)
    try:
        F = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Medium.otf", 18)
    except OSError:
        F = ImageFont.load_default()
    for k, n in enumerate(names):
        r, c = divmod(k, cols)
        key = resolve(n)
        if key is None:
            d.text((c * S + 10, r * (S + 40) + S // 2), f"INCONNU : {n}", fill=255, font=F)
            continue
        m = (mask(key, S - 40) * 255).astype(np.uint8)
        img.paste(Image.fromarray(m), (c * S + 20, r * (S + 40) + 10))
        d.text((c * S + 10, r * (S + 40) + S - 18), key, fill=200, font=F)
    img.save(path)
    return path


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "chercher":
        for w in sys.argv[2:]:
            res = search(w)
            print(f"{w} ({FR_EN.get(w.lower(), w)}) : {len(res)} résultat(s)")
            print("  " + ", ".join(res))
    elif len(sys.argv) >= 3 and sys.argv[1] == "existe":
        for w in sys.argv[2:]:
            print(w, "->", resolve(w))
    elif len(sys.argv) >= 4 and sys.argv[1] == "planche":
        print(planche(sys.argv[3:], sys.argv[2]))
    else:
        print(__doc__)
