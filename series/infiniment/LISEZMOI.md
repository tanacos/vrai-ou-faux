# INFINIMENT — de l'infiniment petit à l'infiniment grand

Série TikTok narrée (voix de synthèse « Estelle »), format mini-reportage, **un épisode par semaine** (routine
automatique : `ROUTINE_REPORTAGE.md` à la racine du dépôt). Une question qui intrigue, un voyage dans les échelles,
une révélation chiffrée et sourcée, une chute, l'annonce du prochain épisode. 80 à 90 s.

## La promesse

Un seul fait étonnant par épisode, démontré pas à pas, avec des chiffres qu'on peut vérifier (sources en
description). On montre l'échelle à chaque instant : la **règle des puissances de dix** en haut de l'écran est la
signature visuelle de la série (curseur de 10⁻¹⁵ m à 10²⁷ m).

## Structure d'un épisode (un paragraphe de narration = un bloc = une scène)

1. **Accroche** (≤ 3 s avant la première image forte, titre de couverture visible dès la 1re image) : la conclusion
   paradoxale, au conditionnel si c'est une expérience de pensée.
2. **Voyage d'échelle** : on descend (ou on monte) par paliers concrets, un mot = un palier = une image.
3. **Première surprise**, puis **la comparaison qui fait image** (stade / moustique, fourmi / élastique).
4. **Le chiffre clé** en très grand, avec sa source.
5. **L'explication** en 3 ou 4 étapes, le calcul affiché (≈, ≤ : jamais de fausse précision).
6. **Le retournement** (« Mais alors, pourquoi… ? »).
7. **Prochain épisode** dans l'autre sens d'échelle + « Les sources sont en description ».

## Ton

Tutoiement, phrases courtes, verbes d'action, une seule idée par phrase. 230 à 245 mots (≈ 85 s avec Estelle).
Nombres en chiffres dans la narration (les sous-titres les montrent ; la voix les lit en lettres). Ni points de
suspension ni balises (la voix Kyutai les rend mal) : une virgule, un deux-points. Pas d'emphase qui dépasse les
sources (leçons des contre-vérifications) :
- pas de « la physique est formelle » pour un ordre de grandeur : « un vrai calcul de physique » ;
- conditionnel pour une expérience de pensée ; « environ », « au moins », « presque » quand la source le dit ;
- pas de formule choc qui contredit ce qu'on vient d'expliquer (« tu n'as jamais touché ta chaise ») ;
- citer une agence mot pour mot : « matière d'étoile à neutrons », « pèserait environ » ;
- « l'étoile la plus proche » est le Soleil : dire « la plus proche après lui » ;
- les images aussi sont des affirmations : deux tailles comparées sont dessinées à l'échelle (la v1 de l'épisode 1
  montrait l'humanité 11 à 16 fois trop petite dans le sucre), un compteur n'affiche sa source qu'une fois arrivé au
  vrai chiffre, une analogie est présentée comme une image (« imagine… »).
- contre-vérifications du 20/10/2026 (épisodes 1 et 2) : la condition d'une expérience de pensée se dit dès
  l'accroche (« si on retirait le vide de ses atomes ») ; « au moins » seulement si le calcul le prouve
  (1 / 0,508 = 1,97 : « environ deux fois moins ») ; l'écran garde les nuances de la voix (« ≈ 46 », « la plus proche
  DU SOLEIL ») ; le fond diffus est la plus vieille lumière « qu'on puisse voir », « libérée » (pas émise) ; une
  carte inventée porte « ILLUSTRATION » (option `mention` des objets) ; la règle des puissances de dix suit la
  règle française de l'ordre de grandeur (a ≤ 5 → 10ⁿ : 4,4 × 10²⁶ m → 10²⁶) et suit l'objet à l'écran.

## Rigueur (comme « Vrai ou faux ? »)

- Chaque nombre dit ou affiché figure dans l'extrait d'une source (`episode.json` → `sources`), au moins deux
  éditeurs différents pour le fait central, calcul écrit dans `calcul`, ce que montrent les images dans `images`.
- Contre-vérification par un agent indépendant avant la voix (`python3 moteur/rp/dossier.py`) : zéro écart exigé.
- Une phrase fausse dans une prise déjà générée se retire sans régénérer (`voix.retraits`) ; une phrase à
  reformuler impose une nouvelle prise.

## Fabrication

Moteur générique (`moteur/rp`, format : `moteur/rp/FORMAT_REPORTAGE.md`) : les scènes sont décrites dans
`episode.json` (types `heros`, `zoom`, `anneaux`, `trajet`, `fin` ; objets dessinés : astres, galaxies, toile
cosmique, atome, molécule, cellule, verre d'eau…), la musique et les bruitages sont synthétisés d'après l'ambiance
de chaque scène. L'épisode 1, antérieur au moteur, garde son `rendu.py` et son `son.py` sur mesure.
```bash
python3 series/infiniment/fabriquer.py provisoire epNN   # scènes réglées avant la voix
python3 series/infiniment/fabriquer.py apercu     epNN
python3 moteur/voix_libre.py generer series/infiniment/epNN --declarer
python3 series/infiniment/fabriquer.py tout       epNN   # vidéo + contrôles (« conforme »)
```

## Voix

Estelle (Kyutai TTS 1.6B, poids CC BY 4.0, voix cédée en CC0). Depuis le 28/10/2026, la légende ne la mentionne
plus (décision de Nathan). Voir `moteur/VOIX.md` (prérequis réseau de l'environnement de la tâche).

## Épisodes

| N° | Dossier | Sujet | Statut |
|---|---|---|---|
| 1 | `ep01_estelle16` | L'humanité dans un sucre (vers le petit) | prêt (3 tours de contre-vérification, voix refaite le 21/10/2026) : non programmé le 24/10 ; fabriqué (conforme) et programmé par la routine du 27/10 pour le lundi 02/11/2026 18:00 |
| 2 | `ep02` | Le bord de l'univers observable (vers le grand) | prêt (3 tours, aucun écart au dernier ; voix refaite le 21/10/2026) : fabriqué (conforme) et programmé le 27/10 pour le lundi 09/11/2026 18:00 |
| 3 | à écrire | Au cœur d'un verre d'eau (annoncé à la fin de l'épisode 2) | — |

(`ep01` : version ElevenLabs, non commerciale ; `ep01_charles`, `ep01_estelle` : essais de voix.)

## Pistes d'épisodes (à vérifier avant écriture ; alterner petit / grand)

- Ép. 3 (annoncé) : un verre d'eau. Piste : y a-t-il plus d'atomes dans un verre d'eau que de verres d'eau dans
  tous les océans ? (nombre d'Avogadro, volume des océans : NOAA, USGS).
- Si le Soleil était une bille, où serait l'étoile la plus proche ?
- Un neutrino peut-il traverser la Terre sans rien toucher ?
- La lumière du Soleil que tu vois est-elle « en retard » ? (8 min pour venir de la surface, bien plus pour sortir
  du cœur).
- Un virus, une bactérie, une cellule : la même descente d'échelle, en biologie.
- Combien de Terres dans le Soleil, combien de Soleils dans la plus grosse étoile connue ?
- Le plus petit objet jamais photographié, la plus grande structure connue de l'univers.
