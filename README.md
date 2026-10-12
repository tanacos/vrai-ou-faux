# Vrai ou faux ?

Fabrique automatique de la série TikTok **« Vrai ou faux ? »** : 4 idées reçues par épisode, un compte à rebours,
le verdict, l'explication et les sources. Les vidéos sont fabriquées, vérifiées et programmées sans intervention
humaine, avec une fenêtre de veto d'au moins 48 h.

## Comment ça marche

```
lundi et jeudi, 6 h 07 (Paris) ── routine Claude planifiée
   1. choisit le thème (l'idée n° 1 est celle annoncée à la fin de l'épisode précédent)
   2. vérifie chaque fait : 2 sources fiables minimum, extraits recopiés, chiffres sourcés
   3. écrit le script  episodes/NNN-theme/episode.json
   4. fabrique la vidéo (moteur/) : images, bande-son, encodage, 13 contrôles qualité
   5. dépose la vidéo dans la branche « videos » de ce dépôt (lien direct public)
   6. programme la publication TikTok dans Metricool, mercredi ou samedi vers 18 h, au moins 48 h plus tard
   7. met à jour journal.json et envoie un rapport
```
La procédure complète suivie par la routine est dans [`ROUTINE.md`](ROUTINE.md).

## Garder la main

- **Annuler un épisode** : supprimer la publication dans Metricool avant son heure de diffusion.
- **Mettre la série en pause** : désactiver la tâche planifiée dans Claude, ou créer un fichier nommé `PAUSE` à la
  racine de ce dépôt (bouton « Add file » sur GitHub). La routine s'arrête tant que ce fichier existe.
- **Orienter les sujets** : modifier [`sujets.md`](sujets.md).
- La routine n'ajoute rien si 3 épisodes sont déjà en attente.

## Contenu du dépôt

| Dossier / fichier | Rôle |
|---|---|
| `moteur/` | moteur de fabrication (Python : NumPy, OpenCV, SciPy, Pillow ; FFmpeg) ; `FORMAT.md` décrit les scripts |
| `episodes/` | un dossier par épisode : script JSON avec les sources et leurs extraits |
| `journal.json` | épisodes déjà faits, verdicts, dates de publication, prochaine affirmation annoncée |
| `config.json` | jours et heures de publication, délai de veto, taille maximale de la file |
| `sujets.md` | pistes de thèmes et interdits |
| `archives/` | scripts sur mesure des épisodes 1 (foudre) et 2 (cerveau) |
| branche `videos` | vidéos en attente de publication (MP4 1080 × 1920, 30 i/s, H.264 + AAC, −14,5 LUFS) ; retirées une fois publiées |

## Fabriquer un épisode à la main

```bash
cd moteur
python3 fabriquer.py valider ../episodes/003-espace/episode.json
python3 fabriquer.py apercu  ../episodes/003-espace/episode.json /tmp/ep3
python3 fabriquer.py tout    ../episodes/003-espace/episode.json /tmp/ep3
```

## Licences des éléments embarqués

Pictogrammes extraits du paquet react-icons 5.7.0 : Phosphor (MIT), Material Design (Apache 2.0), Ionicons 5 (MIT),
Remix Icon (Apache 2.0), Bootstrap Icons (MIT), Game Icons (CC BY 3.0 — le crédit « game-icons.net » est ajouté
automatiquement à la légende quand l'un d'eux est utilisé). Police : Inter (SIL OFL), fournie par le système.
Les vidéos sont étiquetées « contenu généré par IA » sur TikTok.
