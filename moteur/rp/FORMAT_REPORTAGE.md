# Format d'un mini-reportage (moteur générique `moteur/rp`)

Un épisode = un dossier `series/infiniment/epNN/` avec :

- `narration.txt` : le texte lu, **un paragraphe par bloc** (ligne vide entre deux blocs). Les sous-titres
  reprennent ces mots tels qu'écrits : écris les nombres en chiffres (« 13,8 milliards », « 380 000 ») ; la voix les
  lit en lettres toute seule (`moteur/vf/nombres.py`). Pas de balises entre crochets, pas de points de suspension
  (la voix Kyutai les rend mal) : une virgule ou un deux-points.
- `episode.json` : description complète (ci-dessous).
- `voix/prise.mp3`, `voix/prise_mots.json` : produits par `moteur/voix_libre.py generer DOSSIER --declarer`.
- `chrono.json` : produit par `fabriquer.py provisoire` (estimé, sans voix) puis `fabriquer.py voix` (réel).

## episode.json

```json
{
 "serie": "INFINIMENT", "numero": 3, "slug": "verre-eau", "titre": "…",
 "narration": "narration.txt",
 "blocs": ["hook", "descente", "…", "outro"],
 "scenes": {"hook": {…}, "descente": {…}, "…": […], "outro": {"type": "fin", …}},
 "voix_libre": {"moteur": "kyutai-1.6b"},
 "voix": {… écrit par voix_libre.py --declarer ; ajoute "respirations": {"hook": 0.8} …},
 "sources": [{"editeur", "titre", "url", "extraits": ["phrase exacte", …], "sert_a": "…"}],
 "calcul": "chaque nombre dérivé, calcul écrit",
 "images": "ce que les dessins affirment (échelles, couleurs) et ce qui est seulement illustratif",
 "publication": {"titre": "…", "legende": "Accroche. INFINIMENT, épisode N.\nSources : …\n#infiniment …",
                 "hashtags": […], "contenu_ia": false},   // légende simple depuis le 28/10/2026
 "prochain": "sujet annoncé à la fin (il engage l'épisode suivant)"
}
```

`blocs` : un identifiant par paragraphe de `narration.txt`, dans l'ordre. Chaque bloc a une scène dans `scenes` ;
une **liste** de scènes découpe le bloc en plusieurs plans : le plan 2 et les suivants ont `"a_partir_de": "mot"`.

## Repères (« quand »)

Tout élément apparaît sur un mot de la narration de **son bloc** :
- `"mot"` : le mot tel qu'il se lit, sans accents ni ponctuation ni apostrophe (« Andromède » → `"andromede"`,
  « d'années-lumière » → `"anneeslumiere"` ou `"danneeslumiere"`, « 13,8 » → `"138"`, « 380 000 » → `"380000"`) ;
- `"mot#2"` : 2e occurrence dans le bloc ; `"mot+0.4"` : 0,4 s après le début du mot ;
- `"debut"`, `"fin"` : premier et dernier mot du bloc ; un nombre : secondes après le premier mot.
`fabriquer.py valider` liste tout repère introuvable (le corriger : un élément mal calé ment à l'écran).
Dans la première scène, ce qui commence au premier mot est visible dès la première image (miniature TikTok) :
mets-y `"couverture"` (titre de la miniature) et un objet dès `"debut"`.

## Champs communs à toutes les scènes

- `titre` : `["LIGNE 1", "LIGNE *2*"]` (1 ou 2 lignes, majuscules ; `*…*` = couleur d'accent), ou `titres` :
  `[{"quand": "mot", "lignes": […]}, …]` qui se remplacent. Titre court (≤ 22 signes par ligne conseillé).
- `infos` : `[{"quand": "mot", "texte": "SA LUMIÈRE : ≈ 8 MIN"}]` (une ligne sous le titre, y ≈ 690).
- `chiffres` : `[{"quand": "380000", "valeur": 380000, "decimales": 0, "prefixe": "≈ ", "unite": "ANS APRÈS LE *BIG BANG*",
  "source": "NASA, ESA", "compter": true}]` : grand nombre à la place du titre (le titre s'efface avant) ; le
  compteur part de `de` (0) ; la source n'apparaît qu'une fois le vrai chiffre atteint. Pour un très grand nombre,
  `"affichage": "≈ 2,5 × 10²⁵"` (texte fixe, sans compteur) ; `"valeur"` reste obligatoire (pour le dossier).
- `expo` : puissance de dix (en mètres) montrée par la règle en haut, ex. `26.64` pour 4,4 × 10²⁶ m, ou une liste
  `[["mot", 11.2], ["mot2", 16.6]]` ; absent = règle masquée (scène hors échelle, analogie).
- `ambiance` : `mystere` | `emerveillement` | `calme` | `tension` | `resolution` | `triomphe` (musique).
- `impacts` : `["mot", …]` : coup sourd + onde lumineuse (révélation).

## Types de scènes

**`heros`** (aussi `objet`, `titre`, `chiffre`) : un objet au centre (et/ou des chiffres).
`objet` + `objet_quand` (défaut : début) + `objet_jusqua` ; `objets: [{"objet", "quand", "dx", "dy", "taille",
"echelle": [0.6, 1.0]}]` ; `echelle` : croissance de l'objet pendant la scène ; `zoom_lent` (0,06 par défaut).

**`zoom`** : voyage d'échelle par paliers. `sens`: `sortie` (vers le grand) ou `entree` (vers le petit) ; `objet`
avant le premier palier ; `expo_depart` ; `paliers: [{"quand", "objet", "titre", "info", "expo"}]`.

**`anneaux`** : cercles concentriques **à l'échelle** autour d'un centre. `centre: {"texte": "NOUS", "quand"}` ;
`anneaux: [{"quand", "rayon", "texte", "couleur", "style": "pointille"}]` (le plus grand rayon remplit le cadre) ;
`remplissage` (objet dans le grand cercle, ex. `{"type": "univers"}`) + `remplissage_quand` ;
`au_dela: {"quand"}` (le cercle devient pointillé, l'espace continue au-delà).

**`trajet`** : un mobile va du départ (gauche) à l'arrivée (droite). `depart`/`arrivee: {"objet", "texte"}` ;
`mobile` (objet, ex. `{"type": "fourmi"}` ou `{"type": "lumiere"}`) ; `debut`, `fin` (repères) ; `etirement` (S > 1 :
le support s'étire pendant le trajet, image de l'expansion) ; `mesures: {"quand", "aujourdhui", "parcouru"}` ;
`compteur: {"de", "a", "decimales", "unite"}` (minuteur pendant le trajet).

**`fin`** : `prochain: ["AU CŒUR", "D'UN *VERRE D'EAU*"]`, `quand` (mot où le titre apparaît), `sources_quand`,
`objet` facultatif (aperçu du prochain épisode). Sous-titres masqués.

## Objets (`{"type": …}`)

`soleil`, `etoile` (`couleur`), `terre`, `lune`, `planete` (`couleur`, `anneau`), `cmb` (fond diffus, carte
illustrative), `galaxie` (`inclinaison` 0 face … 0,8 tranche, `angle`, `eclat`), `univers` (toile cosmique),
`trou_noir`, `atome` (noyau pas à l'échelle : le dire), `molecule` (H₂O), `cellule`, `virus`, `goutte`, `verre`,
`sucre`, `fourmi`, `lumiere`, `point`, `icone` (`nom` : pictogramme de `moteur/vf/icons.py`, vérifier avec
`python3 -m vf.icons chercher …`). Options : `taille` (1 = 185 px de rayon), `couleur` (cyan, ambre, blanc, vert,
corail, violet, clair, bleu, or, rouge, rose, gris), `mention` (petit texte sous l'objet : `"ILLUSTRATION"` pour une
carte ou une texture inventée, `"PAS À L'ÉCHELLE"`, `"AGRANDI"`).

La règle affiche l'ordre de grandeur à la française : a × 10ⁿ avec a ≤ 5 → 10ⁿ, sinon 10ⁿ⁺¹ (`expo` 26,64, soit
4,4 × 10²⁶ m → « 10²⁶ m ») ; `dossier.py` donne la valeur affichée de chaque `expo` pour la contre-vérification.

**Une image est une affirmation** : deux tailles comparées sont dessinées à l'échelle (scène `anneaux`, ou deux
objets de `taille` proportionnelle) ; si l'échelle réelle rend un objet invisible, l'écrire (« agrandi »,
« pas à l'échelle ») dans une info ; décrire dans `images` ce qui est illustratif.

## Commandes

```bash
python3 series/infiniment/fabriquer.py provisoire series/infiniment/epNN   # chronologie estimée (sans voix)
python3 series/infiniment/fabriquer.py valider    series/infiniment/epNN   # repères, objets, durée
python3 series/infiniment/fabriquer.py apercu     series/infiniment/epNN   # sortie/planche.png + audit (0 problème)
python3 moteur/rp/dossier.py series/infiniment/epNN                        # dossier pour la contre-vérification
python3 moteur/voix_libre.py generer series/infiniment/epNN --declarer     # voix (20 à 40 min)
python3 series/infiniment/fabriquer.py voix       series/infiniment/epNN   # chronologie réelle
python3 series/infiniment/fabriquer.py tout       series/infiniment/epNN   # vidéo + contrôles (« conforme »)
```
