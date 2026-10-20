#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dossier de contre-vérification d'un reportage : narration, tous les textes affichés, ce que les images affirment,
calcul, sources (URL + extraits) et légende, en texte simple, pour un vérificateur qui n'a pas vu la recherche.

    python3 moteur/rp/dossier.py series/infiniment/epNN > /tmp/dossier_epNN.txt
"""
import json
import os
import sys


def lignes_scene(s):
    out = []
    for k in ("couverture", "titre"):
        if s.get(k):
            out.append(f"{k} : {' / '.join(s[k])}")
    for t in s.get("titres", []):
        out.append(f"titre (sur « {t.get('quand', 'debut')} ») : {' / '.join(t['lignes'])}")
    for i in s.get("infos", []):
        out.append(f"info (sur « {i.get('quand', 'debut')} ») : {i['texte']}")
    for ch in s.get("chiffres", []) + ([s["chiffre"]] if s.get("chiffre") else []):
        out.append(f"chiffre : {ch.get('prefixe', '')}{ch['valeur']}{ch.get('suffixe', '')} — {ch.get('unite', '')} "
                   f"(source affichée : {ch.get('source', '—')})")
    if s.get("objet"):
        out.append(f"objet dessiné : {json.dumps(s['objet'], ensure_ascii=False)}")
    for o in s.get("objets", []):
        out.append(f"objet dessiné : {json.dumps(o.get('objet'), ensure_ascii=False)}")
    for p in s.get("paliers", []):
        out.append(f"palier (sur « {p.get('quand')} ») : objet {p['objet'].get('type')}, titre "
                   f"{' / '.join(p.get('titre', []))}, info {p.get('info', '')}, règle 10^{p.get('expo')} m")
    for a in s.get("anneaux", []):
        out.append(f"anneau à l'échelle (rayon relatif {a['rayon']}) : {a.get('texte', '')}")
    if (s.get("centre") or {}).get("texte"):
        out.append(f"centre : {s['centre']['texte']}")
    if s.get("remplissage"):
        out.append(f"intérieur du grand cercle : {s['remplissage'].get('type')}")
    for k in ("depart", "arrivee"):
        if (s.get(k) or {}).get("texte"):
            out.append(f"{k} : {s[k]['texte']}")
    if s.get("mobile"):
        out.append(f"mobile : {s['mobile'].get('type')}" + (f", support étiré ×{s.get('etirement')}"
                                                              if s.get("etirement") else ""))
    if s.get("mesures"):
        out.append(f"mesures : {s['mesures'].get('aujourdhui')} / {s['mesures'].get('parcouru')}")
    if s.get("compteur"):
        c = s["compteur"]
        out.append(f"compteur : {c.get('de', 0)} → {c['a']} {c.get('unite', '')}")
    if s.get("prochain"):
        out.append("prochain épisode : " + " / ".join(s["prochain"]))
    if s.get("type") == "fin":
        out.append("textes fixes : PROCHAIN ÉPISODE ; Sources en description ↓")
    ex = s.get("expo")
    if isinstance(ex, (int, float)):
        out.append(f"règle des puissances de dix : {ex} (affichée : 10^{round(ex)} m)")
    elif isinstance(ex, list):
        out.append("règle des puissances de dix : " + ", ".join(f"{v} sur « {k} »" for k, v in ex))
    return out


def dossier(d):
    c = json.load(open(os.path.join(d, "episode.json"), encoding="utf-8"))
    o = ["=== NARRATION (lue par la voix, un paragraphe par bloc ; les sous-titres reprennent ces mots) ===",
         open(os.path.join(d, c["narration"]), encoding="utf-8").read().strip(), "",
         "=== TEXTES AFFICHÉS À L'ÉCRAN (par bloc ; *…* = mot en couleur) ===",
         f"En-tête permanent : {c.get('serie', 'INFINIMENT')} · ÉP. {c.get('numero')}"]
    for bl in c["blocs"]:
        s = c["scenes"].get(bl, {})
        plans = s if isinstance(s, list) else [s]
        for k, p in enumerate(plans):
            o.append(f"[{bl}{f' (plan {k + 1})' if len(plans) > 1 else ''}] type {p.get('type', 'heros')}")
            o += ["  - " + x for x in lignes_scene(p)]
    o += ["", "=== IMAGES (ce que les dessins affirment) ===", c.get("images", "(non renseigné)"),
          "", "=== CALCUL ===", c.get("calcul", "(non renseigné)"), "", "=== SOURCES ==="]
    for s in c.get("sources", []):
        o.append(f"- {s.get('editeur')} — {s.get('titre', '')} — {s.get('url')}")
        for e in s.get("extraits") or ([s["extrait"]] if s.get("extrait") else []):
            o.append(f"    extrait : « {e} »")
        if s.get("sert_a"):
            o.append(f"    sert à : {s['sert_a']}")
    pub = c.get("publication", {})
    o += ["", "=== LÉGENDE TIKTOK ===", pub.get("legende", "(manquante)"), "",
          "=== ANNONCE DU PROCHAIN ÉPISODE ===", str(c.get("prochain", "(non renseignée)"))]
    return "\n".join(o)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    print(dossier(sys.argv[1]))
