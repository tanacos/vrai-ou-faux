# Format d'un script d'épisode (`episode.json`)

Un épisode = 4 idées reçues, chacune avec : l'affirmation, le verdict, une scène de fond, 2 à 4 panneaux d'explication et
au moins 2 sources. Le moteur calcule seul la chronologie (vidéo de 61 à 90 s), vérifie la mise en page et refuse tout
script qui déborde. Exemple complet : `episodes/003-espace/episode.json`.

```json
{
  "numero": 4,
  "slug": "sommeil",                       // court, sans accent ni espace (nom de dossier et de fichier)
  "theme": "le sommeil",
  "titre": ["4 IDÉES REÇUES", "SUR LE SOMMEIL"],
  "fond": "nuit",                          // fond par défaut des scènes
  "ambiance": "nature",                    // fond sonore : espace, nature, ocean, orage, feu, labo, ville, aucune
  "idees": [ { …idée… } × 4 ],
  "sources_ecran": "Inserm · Scientific American · …",    // 4 lignes maximum à l'écran
  "prochain": {"affirmation": "« … »"},     // annonce de l'épisode suivant (devient l'idée 1 du suivant)
  "publication": {"legende": "… Sources : … #vraioufaux …", "hashtags": ["#vraioufaux", …]}
}
```

## Une idée

```json
{
  "affirmation": "« On avale 8 araignées par an en dormant. »",   // entre guillemets français, 4 lignes max
  "verdict": "FAUX",                                               // VRAI ou FAUX, rien d'autre
  "scene": { "type": "pictogramme", "icone": "gi:spider", "marque": "barre", "fond": "nuit" },
  "panneaux": [ { "type": "texte", … }, … ],                       // 2 à 4
  "sources": [
    {"editeur": "Scientific American", "titre": "…", "url": "https://…", "extrait": "phrase exacte qui prouve le verdict"},
    {"editeur": "…autre éditeur…", "titre": "…", "url": "https://…", "extrait": "…"}
  ]
}
```

Règles de contenu, vérifiées par `fabriquer.py valider` :
- exactement 4 idées, au moins 2 sources par idée venant de 2 éditeurs différents, avec URL ;
- affirmations entre « … » ; aucun texte hors des zones sûres TikTok (audit image par image) ;
- durée totale entre 61 s (rémunération TikTok) et 90 s ;
- tout pictogramme doit exister (`python3 -m vf.icons chercher mot` depuis `moteur/`).

## Panneaux (zone de texte au-dessus de la scène)

| type | champs | usage |
|---|---|---|
| `texte` | `titre` (facultatif, en couleur), `texte` (gros), `sous_texte` (petit) | explication courte |
| `chiffre` | `titre`, `valeur` (nombre), `prefixe`, `suffixe` (" km", " %"), `decimales`, `legende`, `duree_comptage` | grand nombre qui se compte |
| `duo` | `titre`, `gauche: {valeur, legende, couleur}`, `droite: {…}` | deux valeurs à comparer |
| `barres` | `titre`, `sous_texte`, `lignes: [{libelle, valeur, affichage, couleur}]` (2 à 4), `reference: {valeur}`, `max`, `source` | comparaison chiffrée (occupe aussi la zone visuelle) |
| `citation` | `texte` (« … »), `auteur` | citation d'un organisme |

Longueurs conseillées : `texte` ≤ 70 caractères, `sous_texte` ≤ 55, `titre` ≤ 30. Le moteur réduit la taille si besoin et
signale une erreur s'il ne peut pas faire tenir le texte. `duree` (secondes) force la durée d'un panneau.

## Scènes (zone visuelle, centre de l'écran)

| type | champs | idéal pour |
|---|---|---|
| `pictogramme` | `icone`, `satellites` (0 à 4 petits pictos en orbite), `marque` (`barre` = interdit rouge, `coche` = pastille verte, `aucune`), `taille` | tout sujet ; objet principal de l'idée |
| `globe` | `marqueurs: [{lat, lon, libelle}]`, `orbite: {altitude_km, inclinaison, libelle}`, `visee`, `rayon`, `rotation` | géographie, espace, climat |
| `horizon` | `objet` (picto en orbite), `libelle` | vue depuis l'espace, atmosphère |
| `grille` | `icone`, `total` (≤ 200), `surlignes`, `colonnes`, `couleur_surligne`, `libelle`, `ordre: "hasard"` | proportions (« 1 sur 10 ») |
| `echelle` | `elements: [{icone, valeur, libelle, affichage}]` (2 ou 3) | tailles, hauteurs, distances |
| `frise` | `reperes: [{annee, libelle}]` (2 à 4) | histoire, dates |
| `duel` | `gauche: {icone, libelle}`, `droite: {…}`, `signe` (`vs`, `=`, `≠`, `>`, `<`), `signe_apres`, `gagnant` (`gauche`, `droite`, `aucun`) | comparaison A contre B |

Champs communs : `couleur` (`cyan`, `corail`, `vert`, `or`, `violet`) et `fond` (`nuit`, `espace`, `aurore`, `chaud`,
`ocean`, `labo`, `nature`).

## Pictogrammes

14 118 pictogrammes embarqués : Phosphor (MIT), Material (Apache 2.0), Remix (Apache 2.0), Ionicons (MIT), Bootstrap
(MIT), Game Icons (CC BY 3.0 : crédit ajouté automatiquement à la légende par `publier.py legende`).

```bash
cd moteur
python3 -m vf.icons chercher araignée lit          # noms disponibles (français ou anglais)
python3 -m vf.icons planche /tmp/p.png gi:spider pi:bed   # image de contrôle à regarder avant de valider
```

## Commandes

```bash
cd moteur
python3 fabriquer.py valider ../episodes/004-sommeil/episode.json
python3 fabriquer.py apercu  ../episodes/004-sommeil/episode.json /tmp/ep4      # apercu.png + pictogrammes.png
python3 fabriquer.py tout    ../episodes/004-sommeil/episode.json /tmp/ep4      # video.mp4 + rapport.json (~20 min)
```
`tout` reprend là où il s'est arrêté si la machine redémarre (tronçons de 10 s signés).
