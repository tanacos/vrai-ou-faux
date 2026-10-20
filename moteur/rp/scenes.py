# -*- coding: utf-8 -*-
"""Types de scènes des reportages. Une scène = un bloc de narration ; ses éléments apparaissent sur des mots de la
narration (« quand »). Voir FORMAT_REPORTAGE.md pour la description complète.

Mise en page (1080 x 1920) : titre 470-650 (un chiffre affiché remplace le titre), information 690, objet centré
en (540, 905) dans 720-1090,
sous-titres 1150-1255. Sous y = 840, un texte ne dépasse jamais x = 780 (boutons TikTok) : les étiquettes basses
sont recentrées automatiquement."""
import math

import numpy as np

from . import objets as O
from .base import (CX, R_VIS, Y_TITRE, Y_INFO, WHITE, AMBER, CYAN, LIGHT, F_DBLACK, F_DBOLD, F_SEMI, text_width,
                   couleur, clamp, sstep, eout, einout, lerp, txt, titre, ligne_mixte, new_frame, compose_glow,
                   crisp_lines, crisp_dot, cercle_pointille, gcircle, gline, add_pts, format_nombre, rng)

CY_OBJ = 905                  # centre des objets
Y_CHIFFRE, Y_UNITE, Y_SOURCE = 568, 686, 732     # le chiffre prend la place du titre
XMAX_BAS = 772                # bord droit des textes sous y = 840


def x_bas(x, w):
    """Centre x d'un texte bas (y > 840) de largeur w, ramené à gauche des boutons TikTok."""
    return min(x, XMAX_BAS - w / 2)


class Scene:
    type = "?"

    def __init__(self, ctx, bloc, spec):
        self.ctx, self.bloc, self.spec = ctx, bloc, spec
        self.erreurs = []

    # -------------------------------------------------------------- temps
    def q(self, quand, defaut=None):
        """Instant (temps vidéo) d'un repère « quand » de ce bloc ; défaut : début du bloc. Dans la première scène,
        ce qui commence avec le premier mot est visible dès la première image (miniature TikTok)."""
        if quand is None:
            v = self.t_debut if defaut is None else defaut
        else:
            v = self.ctx.quand(self.bloc, quand)
            if v is None:
                self.erreurs.append(f"bloc {self.bloc} : repère introuvable {quand!r}")
                v = self.t_debut if defaut is None else defaut
        if self.s0 <= 0.0 and v <= self.t_debut + 0.01:
            return -1.0
        return v

    def preparer(self):
        self.t_debut, self.t_fin = self.ctx.bloc(self.bloc)            # premiers et derniers mots
        self.s0, self.s1 = getattr(self, "bornes", None) or self.ctx.scene(self.bloc)   # bornes d'affichage
        if self.spec.get("a_partir_de") is not None:                   # plan suivant dans le même bloc
            self.t_debut = max(self.t_debut, self.s0 + 0.25)
        sp = self.spec
        # titres successifs
        self.titres = []
        if sp.get("titres"):
            for tt in sp["titres"]:
                self.titres.append([self.q(tt.get("quand")), tt["lignes"]])
        elif sp.get("titre"):
            self.titres.append([self.q(sp.get("titre_quand")), sp["titre"]])
        if sp.get("couverture"):                                       # miniature : visible dès la 1re image
            self.titres.insert(0, [-1.0, sp["couverture"]])
        self.titres.sort(key=lambda x: x[0])
        self.infos = sorted([[self.q(i.get("quand")), i["texte"], i.get("couleur", "ambre")]
                             for i in sp.get("infos", [])], key=lambda x: x[0])
        self.chiffres = sorted([dict(c, t=self.q(c.get("quand"))) for c in sp.get("chiffres", [])],
                               key=lambda c: c["t"])
        if sp.get("chiffre"):
            c = sp["chiffre"]
            self.chiffres.append(dict(c, t=self.q(c.get("quand"))))
        ex = sp.get("expo")
        if isinstance(ex, list):
            self.expos = [(self.q(k), float(v)) for k, v in ex]
        elif ex is not None:
            self.expos = [(self.s0, float(ex))]
        else:
            self.expos = []
        self.impacts = [self.q(k) for k in sp.get("impacts", [])]

    # -------------------------------------------------------------- éléments communs
    @staticmethod
    def _sequence(items, t, idx_t=0):
        """Élément affiché à l'instant t dans une suite qui se remplace, avec son opacité (sortie avant l'entrée du
        suivant : jamais deux textes superposés)."""
        out = []
        for k, it in enumerate(items):
            t0 = it[idx_t] if isinstance(it, list) else it["t"]
            t1 = (items[k + 1][idx_t] if isinstance(items[k + 1], list) else items[k + 1]["t"]) if k + 1 < len(items) else 1e9
            a = sstep(t0 - 0.05, t0 + 0.22, t) * (1 - sstep(t1 - 0.30, t1 - 0.08, t))
            if a > 0.003:
                out.append((it, a))
        return out

    def dessiner_titres(self, cv, t, y0=Y_TITRE, size=86):
        k = 1 - self.zone_chiffres(t)
        for (t0, lignes), a in self._sequence(self.titres, t):
            titre(cv, lignes, a * k, y0=y0, size=size)

    def dessiner_infos(self, cv, t, y=Y_INFO, size=50):
        k = 1 - self.zone_chiffres(t)
        for (t0, texte, col), a in self._sequence(self.infos, t):
            ligne_mixte(cv, texte, 540, y, _ajuste(texte, F_DBOLD, size, 860), F_DBOLD, couleur(col, "ambre"), WHITE,
                        a * k, 3.0)

    def chiffre_visible(self, t):
        return max([a for _, a in self._sequence(self.chiffres, t)] + [0.0])

    def zone_chiffres(self, t):
        """1 tant que des chiffres occupent la zone du titre (du premier chiffre à la fin de la scène, ou au repère
        « jusqua » du dernier chiffre) : les titres et les infos s'effacent AVANT l'entrée du premier chiffre."""
        if not self.chiffres:
            return 0.0
        t0 = self.chiffres[0]["t"]
        fin = self.chiffres[-1].get("jusqua")
        t1 = self.q(fin) if fin else 1e9
        return sstep(t0 - 0.30, t0 - 0.08, t) * (1 - sstep(t1 - 0.05, t1 + 0.20, t))

    def dessiner_chiffres(self, cv, t):
        for c, a in self._sequence(self.chiffres, t):
            dur = float(c.get("duree", 0.9))
            prog = (t - c["t"] + 0.25) / dur
            v0 = float(c.get("de", 0.0))
            if c.get("affichage"):                 # texte libre, ex. « ≈ 2,5 × 10²⁵ » (pas de compteur)
                s = c["affichage"]
            else:
                v = lerp(v0, float(c["valeur"]), eout(prog)) if c.get("compter", True) else float(c["valeur"])
                s = (c.get("prefixe", "") + format_nombre(v, int(c.get("decimales", 0))) + c.get("suffixe", "")).strip()
            sz = _ajuste(s, F_DBLACK, int(c.get("taille", 150)), 860)
            txt(cv, s, 540, Y_CHIFFRE, sz, F_DBLACK, couleur(c.get("couleur"), "blanc"), a)
            u = c.get("unite")
            if u:
                ligne_mixte(cv, u, 540, Y_UNITE, _ajuste(u, F_DBOLD, 40, 860, 5.0), F_DBOLD, CYAN, AMBER, a, 5.0)
            src = c.get("source")
            if src:                       # la source n'apparaît qu'une fois le compte arrivé au vrai chiffre
                w = text_width(src, F_SEMI, 26, 3.0)
                txt(cv, src, x_bas(540, w), Y_SOURCE, 26, F_SEMI, LIGHT, 0.85 * a * sstep(1.0, 1.2, prog), 0, 3.0)

    def expo(self, t):
        if not self.expos:
            return None
        v = self.expos[0][1]
        for k in range(1, len(self.expos)):
            tk, ek = self.expos[k]
            v = lerp(v, ek, einout((t - tk + 0.35) / 0.9))
        return v

    def regle(self, t):
        return 1.0 if self.expos else 0.0

    def sous_titres(self, t):
        return 1.0

    def fond(self, t):
        return new_frame(t)

    def moments(self):
        ts = [self.t_debut + 0.5] + [x[0] + 0.6 for x in self.titres if x[0] > 0] + [x[0] + 0.6 for x in self.infos]
        ts += [c["t"] + 0.9 for c in self.chiffres]
        ts.append(self.t_fin - 0.15)
        return ts

    def evenements(self):
        ev = [dict(t=x, type="impact") for x in self.impacts]
        for c in self.chiffres:
            if c.get("compter", True) and not c.get("affichage"):
                ev.append(dict(t=c["t"] - 0.25, type="compte", duree=float(c.get("duree", 0.9))))
            ev.append(dict(t=c["t"] + float(c.get("duree", 0.9)) - 0.25, type="pop"))
        for i in self.infos:
            ev.append(dict(t=i[0], type="pop_doux"))
        return ev

    def rendre(self, t):
        raise NotImplementedError


def _ajuste(s, font, size, max_w, track=0.0):
    s = s.replace("*", "")
    while size > 24 and text_width(s, font, size, track) > max_w:
        size -= 2
    return size


# ==================================================================== héros : objet, titre, chiffres, infos
class Heros(Scene):
    """Un objet (ou plusieurs) au centre, des titres, des infos et des chiffres qui se succèdent.
    spec : objet / objets [{objet, quand, dx, dy, taille}], titre / titres, infos, chiffre / chiffres, zoom_lent."""
    type = "heros"

    def preparer(self):
        super().preparer()
        sp = self.spec
        self.objs = []
        if sp.get("objet"):
            self.objs.append(dict(objet=sp["objet"], t=self.q(sp.get("objet_quand"), self.s0), dx=0, dy=0, taille=1.0,
                                  t_fin=self.q(sp["objet_jusqua"]) if sp.get("objet_jusqua") else None,
                                  echelle=sp.get("echelle")))
        for o in sp.get("objets", []):
            self.objs.append(dict(objet=o["objet"], t=self.q(o.get("quand"), self.s0), dx=o.get("dx", 0),
                                  dy=o.get("dy", 0), taille=o.get("taille", 1.0),
                                  t_fin=self.q(o["jusqua"]) if o.get("jusqua") else None, echelle=o.get("echelle")))

    def rendre(self, t):
        cv, gl = self.fond(t)
        dim = 1 - 0.45 * self.chiffre_visible(t)
        prog = clamp((t - self.s0) / max(self.s1 - self.s0, 1))
        lent = 1 + float(self.spec.get("zoom_lent", 0.06)) * prog
        for o in self.objs:
            e = eout((t - o["t"] + 0.1) / 0.7)
            a = sstep(o["t"] - 0.15, o["t"] + 0.3, t)
            if o["t_fin"] is not None:
                a *= 1 - sstep(o["t_fin"] - 0.2, o["t_fin"] + 0.2, t)
            if a <= 0.005:
                continue
            ech = o.get("echelle")
            croiss = lerp(float(ech[0]), float(ech[1]), einout(prog)) if ech else 1.0
            R = R_VIS * o["taille"] * (0.82 + 0.18 * e) * lent * croiss
            O.dessiner(cv, gl, o["objet"], CX + o["dx"], CY_OBJ + o["dy"], R, a * dim, t)
        for ti in self.impacts:
            k = clamp((t - ti) / 0.8)
            if 0 < k < 1:
                gcircle(gl, (CX, CY_OBJ), 120 + 420 * eout(k), AMBER * 0.7 * (1 - k), 3)
        compose_glow(cv, gl)
        self.dessiner_titres(cv, t)
        self.dessiner_infos(cv, t)
        self.dessiner_chiffres(cv, t)
        return cv

    def evenements(self):
        ev = super().evenements()
        for o in self.objs:
            if o["t"] > self.t_debut + 0.2:
                ev.append(dict(t=o["t"], type="apparition"))
        return ev


# ==================================================================== voyage d'échelle
class Zoom(Scene):
    """Voyage d'échelle par paliers : chaque palier (un mot de la narration) remplace l'objet, le titre, l'info et la
    puissance de dix. sens = « sortie » (vers le plus grand) ou « entree » (vers le plus petit)."""
    type = "zoom"
    D = 0.9

    def preparer(self):
        super().preparer()
        self.sens = self.spec.get("sens", "sortie")
        self.paliers = [dict(p, t=self.q(p.get("quand"))) for p in self.spec["paliers"]]
        self.paliers.sort(key=lambda p: p["t"])
        tit = list(self.titres)
        for p in self.paliers:
            if p.get("titre"):
                tit.append([p["t"], p["titre"]])
            if p.get("info"):
                self.infos.append([p["t"] + 0.15, p["info"], p.get("couleur_info", "ambre")])
        self.titres = sorted(tit, key=lambda x: x[0])
        self.infos.sort(key=lambda x: x[0])
        if not self.expos:
            e0 = self.spec.get("expo_depart", self.paliers[0].get("expo"))
            self.expos = [(self.s0, float(e0))] + [(p["t"], float(p["expo"])) for p in self.paliers if "expo" in p]
        self.obj0 = self.spec.get("objet")                              # objet avant le 1er palier (facultatif)

    def _etat(self, t):
        """(index du palier courant, avancement de la transition 0..1)."""
        k = -1
        for i, p in enumerate(self.paliers):
            if t >= p["t"] - self.D * 0.6:
                k = i
        if k < 0:
            return -1, 1.0
        u = clamp((t - (self.paliers[k]["t"] - self.D * 0.6)) / self.D)
        return k, u

    def fond(self, t):
        k, u = self._etat(t)
        flux = math.sin(math.pi * u) if k >= 0 and u < 1 else 0.0
        return new_frame(t, flux=flux, flux_sens=-1.0 if self.sens == "sortie" else 1.0)

    def rendre(self, t):
        cv, gl = self.fond(t)
        k, u = self._etat(t)
        e = einout(u)
        sortie = self.sens == "sortie"
        prev = self.paliers[k - 1]["objet"] if k >= 1 else self.obj0
        if k >= 0 and u < 1 and prev:
            sc = lerp(1.0, 0.10 if sortie else 3.2, e)
            O.dessiner(cv, gl, prev, CX, CY_OBJ, R_VIS * 0.9 * sc, (1 - e) ** 1.3, t)
        cur = self.paliers[k]["objet"] if k >= 0 else self.obj0
        if cur:
            sc = lerp(2.4 if sortie else 0.25, 1.0, eout(u)) if k >= 0 else 1.0
            a = sstep(0.15, 0.6, u) if k >= 0 else sstep(self.s0, self.s0 + 0.4, t)
            O.dessiner(cv, gl, cur, CX, CY_OBJ, R_VIS * 0.9 * sc, a, t)
        compose_glow(cv, gl)
        self.dessiner_titres(cv, t)
        self.dessiner_infos(cv, t)
        self.dessiner_chiffres(cv, t)
        return cv

    def moments(self):
        return super().moments() + [p["t"] + 0.7 for p in self.paliers]

    def evenements(self):
        ev = super().evenements()
        for p in self.paliers:
            ev.append(dict(t=p["t"] - 0.45, type="whoosh", sens=self.sens))
            ev.append(dict(t=p["t"], type="impact_doux"))
        return ev


# ==================================================================== anneaux à l'échelle
class Anneaux(Scene):
    """Cercles concentriques à l'échelle autour d'un centre (toi) : rayons comparés, étiquettes courtes.
    spec : centre {objet, texte}, anneaux [{quand, rayon, texte, couleur, style}], remplissage (objet),
    au_dela {quand} (le cercle extérieur devient pointillé, l'espace continue au-delà)."""
    type = "anneaux"
    RMAX = 190

    def preparer(self):
        super().preparer()
        sp = self.spec
        self.ann = [dict(a, t=self.q(a.get("quand"))) for a in sp.get("anneaux", [])]
        rmax = max([float(a["rayon"]) for a in self.ann] + [1e-9])
        for a in self.ann:
            a["r"] = self.RMAX * float(a["rayon"]) / rmax
        self.centre = sp.get("centre") or {}
        self.t_centre = self.q(self.centre.get("quand"))
        self.rempl = sp.get("remplissage")
        self.t_rempl = self.q(sp.get("remplissage_quand")) if self.rempl else None
        ad = sp.get("au_dela")
        self.t_au_dela = self.q(ad.get("quand")) if ad else None

    def rendre(self, t):
        cv, gl = self.fond(t)
        dim = 1 - 0.6 * self.chiffre_visible(t)
        ext = max(self.ann, key=lambda a: a["r"]) if self.ann else None
        if self.t_au_dela is not None:
            b = sstep(self.t_au_dela - 0.2, self.t_au_dela + 1.2, t)
            if b > 0:
                n = 1600
                r2 = np.random.default_rng(77)
                ang = r2.uniform(0, 2 * np.pi, n)
                rad = self.RMAX * (1.06 + r2.uniform(0, 1.6, n) ** 0.8) * (1 + 0.05 * b)
                add_pts(gl, CX + np.cos(ang) * rad, CY_OBJ + np.sin(ang) * rad, 0.55 * b * dim * r2.uniform(0.4, 1.0, n),
                        np.array([0.75, 0.82, 1.0], np.float32))
                for k in range(6):                 # quelques galaxies au-delà (côtés et bas, jamais sur le titre)
                    th = math.radians(-15 + k * 42)
                    rr = self.RMAX * (1.32 + 0.10 * (k % 3))
                    O.dessiner(cv, gl, {"type": "galaxie", "inclinaison": 0.3 + 0.08 * k, "angle": k * 0.7,
                                        "eclat": 0.35}, CX + math.cos(th) * rr, CY_OBJ + math.sin(th) * rr,
                               20 + 4 * (k % 3), b * dim, t + k)
        if self.rempl and ext is not None:
            a = sstep(self.t_rempl - 0.1, self.t_rempl + 0.6, t)
            spec = dict(self.rempl, bord=False)
            O.dessiner(cv, gl, spec, CX, CY_OBJ, ext["r"] * 0.98 * (0.9 + 0.1 * eout((t - self.t_rempl) / 1.2)),
                       a * dim, t)
        for an in self.ann:
            g = eout((t - an["t"] + 0.1) / 0.75)
            if g <= 0.002:
                continue
            r = an["r"] * g
            c = couleur(an.get("couleur"), "cyan")
            pointille = an.get("style") == "pointille" or (an is ext and self.t_au_dela is not None and
                                                          t > self.t_au_dela)
            if pointille:
                cercle_pointille(cv, CX, CY_OBJ, r, c, 0.9 * dim, 3, phase=t * 0.4)
            else:
                crisp_lines(cv, [np.stack([CX + r * np.cos(np.linspace(0, 2 * np.pi, 160)),
                                           CY_OBJ + r * np.sin(np.linspace(0, 2 * np.pi, 160))], 1)], c, 0.9 * dim, 3,
                            True)
            gcircle(gl, (CX, CY_OBJ), r, c * 0.35 * dim, 4)
            fl = clamp((t - an["t"]) / 0.6)
            if 0 < fl < 1:
                gcircle(gl, (CX, CY_OBJ), r, c * 1.2 * (1 - fl), 8)
        if self.centre:
            ob = self.centre.get("objet", {"type": "point"})
            O.dessiner(cv, gl, ob, CX, CY_OBJ, ob.get("rayon", 14), sstep(self.t_centre - 0.1, self.t_centre + 0.3, t)
                       * dim, t)
        compose_glow(cv, gl)
        for an in self.ann:
            if an.get("texte"):
                a = sstep(an["t"] + 0.3, an["t"] + 0.6, t) * dim
                col = couleur(an.get("couleur"), "cyan")
                if an["r"] < 115:                  # petit anneau : étiquette juste dessous (« NOUS » au centre)
                    sz = 30
                    w = text_width(an["texte"], F_DBOLD, sz, 3.0)
                    txt(cv, an["texte"], x_bas(540, w), CY_OBJ + max(an["r"], 50) + 42, sz, F_DBOLD, col, a, 0, 3.0)
                else:
                    y = CY_OBJ - an["r"] - 26
                    sz = 34
                    w = text_width(an["texte"], F_DBOLD, sz, 3.0)
                    x = x_bas(540, w) if y + 0.6 * sz > 840 else 540
                    txt(cv, an["texte"], x, y, sz, F_DBOLD, col, a, 0, 3.0)
        if self.centre.get("texte"):
            a = sstep(self.t_centre + 0.2, self.t_centre + 0.5, t) * dim
            txt(cv, self.centre["texte"], 540, CY_OBJ + 36, 26, F_DBOLD, AMBER, a, 0, 4.0)
        self.dessiner_titres(cv, t)
        self.dessiner_infos(cv, t)
        self.dessiner_chiffres(cv, t)
        return cv

    def moments(self):
        return super().moments() + [a["t"] + 0.8 for a in self.ann] + \
            ([self.t_au_dela + 1.0] if self.t_au_dela is not None else [])

    def evenements(self):
        ev = super().evenements()
        for a in self.ann:
            ev.append(dict(t=a["t"], type="anneau"))
        if self.t_au_dela is not None:
            ev.append(dict(t=self.t_au_dela, type="ouverture"))
        return ev


# ==================================================================== trajet (avec ou sans étirement de l'espace)
class Trajet(Scene):
    """Un mobile va du départ (gauche) à l'arrivée (droite, fixe). Avec « etirement » S > 1, le support s'étire
    pendant le trajet (image de l'expansion : la fourmi sur l'élastique) ; le chemin parcouru et la distance finale
    sont dessinés à l'échelle du modèle (rapport S·ln S / (S − 1)).
    spec : depart {objet, texte}, arrivee {objet, texte}, mobile {type…}, debut, fin, etirement, support
    (« elastique » | « vide »), mesures {quand, parcouru, aujourdhui}, compteur {de, a, decimales, unite}."""
    type = "trajet"
    XA, XB = 150.0, 910.0

    def preparer(self):
        super().preparer()
        sp = self.spec
        self.S = max(float(sp.get("etirement", 1.0)), 1.0)
        self.td = self.q(sp.get("debut"))
        self.ta = self.q(sp.get("fin"), self.t_fin)
        if self.ta <= self.td + 0.5:
            self.erreurs.append(f"bloc {self.bloc} : trajet trop court ({self.ta - self.td:.2f} s)")
            self.ta = self.td + 1.0
        self.L0 = (self.XB - self.XA) / self.S
        m = sp.get("mesures")
        self.t_mes = self.q(m.get("quand")) if m else None
        c = sp.get("compteur")
        self.compteur = c

    def _u(self, t):
        return clamp((t - self.td) / (self.ta - self.td))

    def _a(self, u):
        return 1 + (self.S - 1) * u

    def _chi(self, u):
        if self.S <= 1.0001:
            return u
        return math.log(1 + (self.S - 1) * u) / math.log(self.S)

    def _x(self, chi, u):
        return self.XB - (1 - chi) * self.L0 * self._a(u)

    def rendre(self, t):
        cv, gl = self.fond(t)
        sp = self.spec
        u = self._u(t)
        y = CY_OBJ
        a_in = sstep(self.s0 + 0.1, self.s0 + 0.5, t)
        xA = self._x(0.0, u)
        # support : élastique (deux traits + graduations comobiles) ou vide
        if sp.get("support", "elastique") == "elastique":
            tension = 0.55 + 0.45 * u
            cs = couleur(sp.get("couleur_support"), "corail")
            crisp_lines(cv, [[(xA, y - 7), (self.XB, y - 7)], [(xA, y + 7), (self.XB, y + 7)]], cs * tension,
                        0.9 * a_in, 4)
            gline(gl, (xA, y), (self.XB, y), cs, 10, 0.25 * a_in * tension)
            ticks = []
            for k in range(1, 12):
                xk = self._x(k / 12, u)
                ticks.append([(xk, y - 16), (xk, y + 16)])
            crisp_lines(cv, ticks, LIGHT, 0.6 * a_in, 3)
        else:
            crisp_lines(cv, [[(xA, y), (self.XB, y)]], LIGHT, 0.25 * a_in, 2)
        dep, arr = sp.get("depart") or {}, sp.get("arrivee") or {}
        if dep.get("objet"):
            O.dessiner(cv, gl, dep["objet"], xA, y, dep.get("rayon", 22), a_in, t)
        if arr.get("objet"):
            O.dessiner(cv, gl, arr["objet"], self.XB, y, arr.get("rayon", 22), a_in, t)
        # mobile
        mob = sp.get("mobile") or {"type": "lumiere"}
        xm = self._x(self._chi(u), u)
        am = a_in * (1 - sstep(self.ta + 0.2, self.ta + 0.6, t) * (1 if mob.get("disparait") else 0))
        if mob.get("type") == "lumiere" and 0 < u < 1:
            for j in range(1, 10):
                uj = max(u - j * 0.012, 0)
                gline(gl, (self._x(self._chi(uj), uj), y), (xm, y), np.array([1, 1, 0.9], np.float32), 2,
                      0.08 * am)
        rm = mob.get("rayon", 56 if mob.get("type") == "fourmi" else 22)
        yo = y - (rm * 0.40 if mob.get("type") == "fourmi" else 0)
        O.dessiner(cv, gl, dict(mob, vitesse_pattes=1.0 if 0 < u < 1 else 0.0), xm, yo, rm, am,
                   t if 0 < u < 1 else self.td)
        compose_glow(cv, gl)
        # étiquettes du départ et de l'arrivée
        for (o, x), yy in (((dep, xA), y - 60), ((arr, self.XB), y + 64)):
            if o.get("texte"):
                w = text_width(o["texte"], F_DBOLD, 32, 3.0)
                xx = clamp(x, 120 + w / 2, XMAX_BAS - w / 2)
                txt(cv, o["texte"], xx, yy, 32, F_DBOLD, LIGHT, 0.85 * a_in * (1 - self._a_mesures(t)), 0, 3.0)
        # mesures après l'arrivée : distance aujourd'hui (au-dessus) et chemin parcouru (au-dessous)
        am2 = self._a_mesures(t)
        m = sp.get("mesures")
        if m and am2 > 0.003:
            xa_f = self._x(0.0, 1.0)
            parcouru = self.L0 * (self.S - 1) / math.log(self.S) if self.S > 1.0001 else self.XB - self.XA
            self._accolade(cv, xa_f, self.XB, y - 50, -1, AMBER, am2)
            self._accolade(cv, self.XB - parcouru, self.XB, y + 50, 1, CYAN, am2)
            for texte, x0, x1, yy, col in ((m.get("aujourdhui", ""), xa_f, self.XB, y - 96, AMBER),
                                           (m.get("parcouru", ""), self.XB - parcouru, self.XB, y + 98, CYAN)):
                if texte:
                    w = text_width(texte, F_DBOLD, 36, 3.0)
                    txt(cv, texte, clamp((x0 + x1) / 2, 120 + w / 2, XMAX_BAS - w / 2), yy, 36, F_DBOLD, col, am2, 0,
                        3.0)
        if self.compteur and 0 < t - self.td + 0.3:
            c = self.compteur
            v = lerp(float(c.get("de", 0)), float(c["a"]), self._u(t))
            s = format_nombre(v, int(c.get("decimales", 0))) + " " + c.get("unite", "")
            ac = sstep(self.td - 0.3, self.td, t) * (1 - sstep(self.t_fin + 0.2, self.t_fin + 0.5, t))
            txt(cv, s.strip(), 540, Y_INFO + 10, 64, F_DBLACK, AMBER, ac)
        self.dessiner_titres(cv, t)
        if not self.compteur:
            self.dessiner_infos(cv, t)
        return cv

    def _a_mesures(self, t):
        if self.t_mes is None:
            return 0.0
        return sstep(self.t_mes - 0.1, self.t_mes + 0.35, t)

    @staticmethod
    def _accolade(cv, x0, x1, y, sens, col, a):
        h = 16 * sens
        crisp_lines(cv, [[(x0, y + h), (x0, y), (x1, y), (x1, y + h)]], col, a, 4)

    def moments(self):
        ts = super().moments() + [self.td + 0.2, (self.td + self.ta) / 2, self.ta + 0.3]
        if self.t_mes is not None:
            ts.append(self.t_mes + 0.8)
        return ts

    def evenements(self):
        ev = super().evenements()
        ev.append(dict(t=self.td, type="montee", fin=self.ta))
        ev.append(dict(t=self.ta, type="arrivee"))
        if self.t_mes is not None:
            ev.append(dict(t=self.t_mes, type="pop"))
        return ev


# ==================================================================== fin : prochain épisode
WARP_N = 1400
_wr = np.random.default_rng(9)
WX = _wr.uniform(-1, 1, WARP_N).astype(np.float32)
WY = _wr.uniform(-1, 1, WARP_N).astype(np.float32)
WZ = _wr.uniform(0.05, 1.0, WARP_N).astype(np.float32)


class Fin(Scene):
    """« PROCHAIN ÉPISODE », le titre annoncé (sur un mot de la narration), « Sources en description ↓ »."""
    type = "fin"

    def preparer(self):
        super().preparer()
        sp = self.spec
        self.t_prochain = self.q(sp.get("quand"), self.t_debut + 1.0)
        self.t_sources = self.q(sp.get("sources_quand"), self.t_fin - 1.2)
        self.sens = -1.0 if sp.get("sens") == "entree" else 1.0

    def sous_titres(self, t):
        return 0.0

    def rendre(self, t):
        cv, gl = new_frame(t, stars=0.3)
        u = t - self.s0
        speed = 0.08 + 0.55 * sstep(0, 3.0, u)
        z = (WZ - (u * speed) % 1.0) % 1.0 + 0.02
        z_prev = z + 0.035 * speed / 0.6
        x, y = CX + WX / z * 140, CY_OBJ + WY / z * 140
        xp, yp = CX + WX / z_prev * 140, CY_OBJ + WY / z_prev * 140
        b = np.clip(0.9 - z, 0, 1)
        for i in range(0, WARP_N, 2):
            if 0 <= x[i] < 1080 and 0 <= y[i] < 1920:
                gline(gl, (xp[i], yp[i]), (x[i], y[i]), np.array([0.8, 0.9, 1.0], np.float32), 1, float(b[i]) * 0.9)
        if self.spec.get("objet"):
            k = sstep(self.t_prochain - 0.3, self.t_prochain + 0.5, t)
            O.dessiner(cv, gl, self.spec["objet"], CX, CY_OBJ + 40, R_VIS * 0.8 * (0.85 + 0.15 * eout(
                (t - self.t_prochain) / 0.8)), k, t)
        compose_glow(cv, gl)
        a = sstep(self.s0, self.s0 + 0.6, t)
        txt(cv, "PROCHAIN ÉPISODE", 540, 500, 44, F_DBOLD, CYAN, a, 0, 10.0)
        b2 = sstep(self.t_prochain - 0.4, self.t_prochain + 0.2, t)
        lignes = self.spec.get("prochain", [])
        sz = 88
        for s in lignes:
            while sz > 50 and text_width(s.replace("*", ""), F_DBLACK, sz) > 820:
                sz -= 2
        for i, s in enumerate(lignes):
            ligne_mixte(cv, s, 540, 590 + i * 98, sz, F_DBLACK, WHITE, AMBER, b2)
        ys = 1205 if self.spec.get("objet") else 1000
        txt(cv, "Sources en description ↓", 540, ys, 34, F_SEMI, WHITE, sstep(self.t_sources - 0.2,
                                                                               self.t_sources + 0.3, t))
        return cv

    def moments(self):
        return [self.t_prochain + 0.6, self.t_fin]

    def evenements(self):
        return [dict(t=self.s0 - 0.1, type="montee", fin=self.t_prochain + 0.1),
                dict(t=self.t_prochain + 0.1, type="impact_final")]


TYPES = {"heros": Heros, "objet": Heros, "titre": Heros, "chiffre": Heros, "zoom": Zoom, "anneaux": Anneaux,
         "trajet": Trajet, "fin": Fin}


def creer(ctx, bloc, spec):
    k = spec.get("type", "heros")
    if k not in TYPES:
        raise KeyError(f"bloc {bloc} : type de scène inconnu {k!r} (types : {', '.join(TYPES)})")
    return TYPES[k](ctx, bloc, spec)
