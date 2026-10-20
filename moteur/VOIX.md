# Couche voix

Deux voix possibles ; tout le reste (montage, sous-titres, mixage, contrôles) se fait ici, de façon reproductible.

| | **Estelle (Kyutai TTS 1.6B)**, par défaut | Célian (ElevenLabs), facultative |
|---|---|---|
| Licence | poids CC BY 4.0 : usage commercial permis, mention « Voix de synthèse : Kyutai TTS (CC BY 4.0) » (ajoutée seule par `publier.py legende`) ; voix Estelle cédée en CC0 | offre gratuite : **aucun usage commercial** ; offre payante requise pour un compte rémunéré |
| Où elle tourne | dans la session de la routine (processeur), 20 à 40 min par épisode | serveurs ElevenLabs, via le connecteur + relais GitHub |
| Prérequis | accès réseau à PyPI, download.pytorch.org et Hugging Face (voir plus bas) | crédits (1 par caractère) |

`config.json` : `"voix_active": true`, `"voix_moteur": "kyutai-1.6b"`.

## Estelle : `moteur/voix_libre.py`

```bash
python3 moteur/voix_libre.py diagnostic                          # {"ok": true} si tout est prêt, sinon ce qui manque
python3 moteur/voix_libre.py generer DOSSIER_DE_L_EPISODE --declarer
```
- Texte lu : épisode « Vrai ou faux ? » → les blocs de `vf.voix.narration_quiz` (ouverture, affirmations,
  verdicts, panneaux, score, annonce ; clés `voix_*` du script pour corriger une lecture) ; reportage → le fichier
  `narration` (un paragraphe par bloc). Les nombres, unités et sigles sont écrits en lettres pour la voix
  seulement (`vf/nombres.py` : « 380 000 » → « trois cent quatre-vingt mille », « ADN » → « A-D-N ») ; l'écran et
  les sous-titres gardent les chiffres.
- Chaque bloc est généré séparément (0,5 s de silence entre deux blocs, bornes exactes notées dans
  `prise_mots.json` → `blocs` : le découpage du quiz se fait sur ces bornes, pas sur la transcription), puis relu
  par une transcription indépendante (faster-whisper medium) et refait (4 essais) s'il manque 3 mots ou plus, s'il
  s'en ajoute, ou s'il y a une syllabe parasite au début. Code de sortie 0 seulement si tout est vérifié ;
  `--declarer` écrit alors le champ `voix` dans `episode.json` (`"eclaircir": true` : étape « micro studio »).
- Mots horodatés : transcription indépendante de la prise entière (`voix/prise_mots.json`), alignée ensuite sur le
  script (`vf.voix.aligner`, ≥ 90 % exigé).

Mesures (GitHub Actions, 4 cœurs, 16 Go, 20/10/2026) : quiz « sommeil » (20 blocs, 81 s de voix) en 22 min, mémoire
maximale 7,2 Gio ; reportage INFINIMENT 2 (7 blocs, 88 s) en 19 min, 6,4 Gio ; tous les blocs vérifiés au premier
essai. Sur 2 cœurs, compter environ le double. Une session à 8 Go de mémoire est juste : si la génération est tuée
faute de mémoire, l'épisode sort sans voix (quiz) ou attend (reportage).

### Ce que l'environnement de la tâche planifiée doit autoriser

L'environnement par défaut des tâches planifiées refuse ces adresses (constaté le 20/10/2026 : `pip` et
Hugging Face bloqués, GitHub autorisé). Dans claude.ai/code, ouvrir les réglages de l'environnement utilisé par les
tâches « Vrai ou faux ? » et « INFINIMENT » → **Network access** → **Custom**, cocher « Also include default list of
common package managers », et ajouter :
```
download.pytorch.org
huggingface.co
*.huggingface.co
*.hf.co
```
(PyPI fait partie de la liste par défaut ; `*.hf.co` couvre les serveurs de fichiers de Hugging Face.)
Facultatif, pour gagner 2 à 3 minutes par run (installation mise en cache), dans **Setup script** :
```bash
#!/bin/bash
pip install --break-system-packages -q "moshi==0.2.11" sphn faster-whisper --extra-index-url https://download.pytorch.org/whl/cpu || true
command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg) || true
```
Les poids (≈ 4 Go pour la voix, 1,5 Go pour la transcription) se téléchargent au premier usage de chaque session.

GitHub Actions (branche `essai-voix`, workflows `voix-episode` et `controle-ecoute`) sert aux **essais** du moteur
seulement : les conditions de GitHub réservent ses machines à la construction et aux tests du logiciel, pas à la
production de chaque épisode.

## Contrôles

`python3 -m vf.voix verifier episodes/NNN-slug/episode.json` (quiz) : alignement ≥ 90 %, aucune coupe entre deux
blocs tombée dans la parole. La fabrication ajoute ensuite « synchro voix » (≤ 40 ms), « voix alignée sur le
script », « phrases découpées dans les silences », « phrases sans chevauchement ».

Ce que les contrôles ne garantissent pas : la prononciation exacte d'un nombre ou d'un nom propre. La
transcription de contrôle se trompe elle-même sur certains nombres français (« trois cent quatre-vingt mille »
transcrit « 300-420 000 » par Whisper medium et large-v3) : un écart de chiffres n'est pas compté comme un trou.
Pour un doute, le workflow d'essai `controle-ecoute` (Whisper large-v3) ou une écoute humaine tranchent.

## Corriger après coup sans régénérer

Une phrase à **supprimer** d'une prise déjà générée (fait contesté découvert après coup) se retire sans
régénérer : dans `episode.json` (série INFINIMENT), `voix.narration_prise` = texte lu dans la prise,
`voix.retraits` = `[{"bloc": "…", "phrase": "…"}]`, et `narration` = ce texte moins ces phrases. La fabrication coupe
la prise au milieu des silences qui encadrent la phrase (`vf.voix.retirer_phrase`) et refuse une coupe tombée dans la
parole. Une phrase à **reformuler** impose une nouvelle prise.

## ElevenLabs (facultatif, offre payante)

Procédure conservée pour mémoire (épisodes de démonstration `demos/004-sommeil-voix`, `series/infiniment/ep01`) :
`python3 -m vf.voix texte …` (texte à faire lire), `creative_generate_speech` (`eleven_v4`, voix Célian
`DGTOOUoGpoP6UZ9uSWfA`), rapatriement par `moteur/relais.py` (les sessions ne joignent pas le stockage
d'ElevenLabs ; le relais passe par une branche jetable du dépôt public, donc les prises relayées sont publiques),
horodatage par `creative_transcribe_audio`, champ `voix` du script. Offre gratuite : aucun usage commercial, même
après un abonnement (« before or after », https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform).
