# -*- coding: utf-8 -*-
"""Nombres, unités et sigles écrits comme ils se disent, pour une voix de synthèse (texte lu seulement : l'écran et les
sous-titres gardent les chiffres).

    >>> parlable("Moins de 5 % rêvent en noir et blanc.")
    'Moins de cinq pour cent rêvent en noir et blanc.'
    >>> parlable("Un trajet de 384 400 km, soit 1,3 seconde-lumière.")
    'Un trajet de trois cent quatre-vingt-quatre mille quatre cents kilomètres, soit un virgule trois seconde-lumière.'
"""
import re

_U = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
      "quatorze", "quinze", "seize"]
_D = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_cent(n):
    if n <= 16:
        return _U[n]
    if n < 20:
        return "dix-" + _U[n - 10]
    d, u = divmod(n, 10)
    if d in (7, 9):                          # soixante-dix…, quatre-vingt-dix…
        base = "soixante" if d == 7 else "quatre-vingt"
        reste = 10 + u
        if d == 7 and u == 1:
            return "soixante et onze"
        return base + "-" + _moins_de_cent(reste)
    if d == 8:
        return "quatre-vingts" if u == 0 else "quatre-vingt-" + _U[u]
    if u == 0:
        return _D[d]
    if u == 1:
        return _D[d] + " et un"
    return _D[d] + "-" + _U[u]


def _moins_de_mille(n, final=True):
    c, r = divmod(n, 100)
    parts = []
    if c:
        if c == 1:
            parts.append("cent")
        else:
            parts.append(_U[c] + (" cents" if r == 0 and final else " cent"))
    if r or not c:
        mot = _moins_de_cent(r)
        if not final and mot.endswith("quatre-vingts"):
            mot = mot[:-1]
        parts.append(mot)
    return " ".join(parts)


def entier(n):
    """Entier positif ou nul en toutes lettres (jusqu'aux milliers de milliards)."""
    n = int(n)
    if n < 0:
        return "moins " + entier(-n)
    if n < 1000:
        return _moins_de_mille(n)
    out = []
    for valeur, nom in ((10 ** 12, "billion"), (10 ** 9, "milliard"), (10 ** 6, "million")):
        q, n = divmod(n, valeur)
        if q:
            out.append(f"{_moins_de_mille(q)} {nom}{'s' if q > 1 else ''}")
    q, n = divmod(n, 1000)
    if q:
        out.append("mille" if q == 1 else _moins_de_mille(q, final=False) + " mille")
    if n:
        out.append(_moins_de_mille(n))
    return " ".join(out)


def decimal(s):
    """« 99,9 » -> « quatre-vingt-dix-neuf virgule neuf » ; « 0,05 » -> « zéro virgule zéro cinq »."""
    s = s.replace(" ", "").replace(" ", "").replace("\xa0", "")
    if "," not in s:
        return entier(int(s))
    a, b = s.split(",", 1)
    zeros = len(b) - len(b.lstrip("0"))
    queue = ("zéro " * zeros) + (entier(int(b)) if b.strip("0") else "")
    return f"{entier(int(a or 0))} virgule {queue.strip()}".strip()


UNITES = {"%": "pour cent", "°C": "degrés", "°": "degrés", "km/h": "kilomètres-heure", "km/s": "kilomètres par seconde",
          "km²": "kilomètres carrés", "m²": "mètres carrés", "km": "kilomètres", "cm": "centimètres",
          "mm": "millimètres", "µm": "micromètres", "nm": "nanomètres", "m": "mètres", "kg": "kilos", "g": "grammes",
          "t": "tonnes", "h": "heures", "min": "minutes", "s": "secondes", "ms": "millisecondes", "ans": "ans",
          "Md": "milliards", "M": "millions"}
_UNITE_RX = "|".join(re.escape(u) for u in sorted(UNITES, key=len, reverse=True))
# nombre (milliers séparés par une espace fine, insécable ou normale), décimales éventuelles, unité facultative
_NOMBRE = re.compile(r"(?<![\w,])(\d{1,3}(?:[  \xa0]\d{3})+|\d+)(?:,(\d+))?(?:[  \xa0]?(" + _UNITE_RX +
                     r")(?![\w²]))?")
_PUISSANCE = re.compile(r"10([⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)(?:[ \u202f\xa0]?(" + _UNITE_RX + r")(?![\w²]))?")
_ORDINAUX = {"1er": "premier", "1re": "première", "1ère": "première", "2e": "deuxième", "3e": "troisième",
             "4e": "quatrième", "5e": "cinquième", "10e": "dixième", "20e": "vingtième", "21e": "vingt et unième"}
_SUP = str.maketrans("⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "-0123456789")
# sigles lus comme des mots (les autres sont épelés)
SIGLES_MOTS = {"NASA": "Nasa", "ESA": "Esa", "ONU": "Onu", "OTAN": "Otan", "UNESCO": "Unesco", "CERN": "Cern",
               "INSERM": "Inserm", "CNES": "Cnes", "SIDA": "sida", "COVID": "Covid", "UNICEF": "Unicef", "LASER": "laser", "RADAR": "radar"}
_SIGLE = re.compile(r"\b([A-ZÉÈ]{2,6})\b")


_SINGULIER = {"mètres": "mètre", "kilomètres": "kilomètre", "centimètres": "centimètre", "millimètres": "millimètre",
              "micromètres": "micromètre", "nanomètres": "nanomètre", "carrés": "carré", "kilos": "kilo", "grammes": "gramme", "tonnes": "tonne",
              "heures": "heure", "minutes": "minute", "secondes": "seconde", "millisecondes": "milliseconde",
              "degrés": "degré", "millions": "million", "milliards": "milliard", "ans": "an"}
_FEMININ = {"heures", "minutes", "secondes", "millisecondes", "tonnes"}


def _nombre(m):
    ent, dec, unite = m.group(1), m.group(2), m.group(3)
    n = int(re.sub(r"[  \xa0]", "", ent))
    mots = decimal(f"{n},{dec}") if dec else entier(n)
    if unite:
        u = UNITES[unite]
        if n == 1 and not dec:
            if u.split()[0].split("-")[0] in _FEMININ:
                mots = "une"
            u = " ".join(_SINGULIER.get(w, w) for w in u.replace("-", " - ").split()).replace(" - ", "-")
        mots += " " + u
    return mots


def parlable(texte, epeler_sigles=True):
    """Texte prêt à être lu : nombres et unités en lettres, sigles épelés (« ADN » -> « A-D-N »), puissances de dix
    (« 10²⁶ » -> « dix puissance vingt-six »). Les mots ordinaires ne changent pas."""
    s = texte.replace(" ", " ").replace("\xa0", " ")
    for k, v in _ORDINAUX.items():
        s = re.sub(r"(?<!\w)" + re.escape(k) + r"(?!\w)", v, s)
    def puissance(m):
        e = int(m.group(1).translate(_SUP))
        mots = "dix puissance " + ("moins " if e < 0 else "") + entier(abs(e))
        return mots + (" " + UNITES[m.group(2)] if m.group(2) else "")
    s = _PUISSANCE.sub(puissance, s)
    s = _NOMBRE.sub(_nombre, s)
    if epeler_sigles:
        def sigle(m):
            w = m.group(1)
            if w in SIGLES_MOTS:
                return SIGLES_MOTS[w]
            if w in ("VRAI", "FAUX", "OK"):
                return w.capitalize() if w != "OK" else "OK"
            return "-".join(w)
        s = _SIGLE.sub(sigle, s)
    return re.sub(r"\s+", " ", s).strip()


if __name__ == "__main__":
    import doctest
    import sys
    doctest.testmod()
    for a in sys.argv[1:]:
        print(parlable(a))
