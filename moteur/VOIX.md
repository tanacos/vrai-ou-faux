# Couche voix

Deux voix possibles ; tout le reste (montage, sous-titres, mixage, contrôles) se fait ici, de façon reproductible.

| | **Estelle (Kyutai TTS 1.6B)**, par défaut | Célian (ElevenLabs), facultative |
|---|---|---|
| Licence | poids CC BY 4.0 : usage commercial permis, mention « Voix de synthèse : Kyutai TTS (CC BY 4.0) » (ajoutée seule par `publier.py legende`) ; voix Estelle cédée en CC0 | offre gratuite : **aucun usage commercial** ; offre payante requise pour un compte rémunéré |
| Où elle tourne | dans la session de la routine (processeur), ≈ 20 min par épisode (5 min pour un paragraphe à refaire) | serveurs ElevenLabs, via le connecteur + relais GitHub |
| Prérequis | accès réseau à PyPI, download.pytorch.org et Hugging Face (voir plus bas) | crédits (1 par caractère) |

`config.json` : `"voix_active": true`, `"voix_moteur": "kyutai-1.6b"`.

## Estelle : `moteur/voix_libre.py`

```bash
python3 moteur/voix_libre.py diagnostic                          # {"ok": true} si tout est prêt, sinon ce qui manque
python3 moteur/voix_libre.py installer                           # paquets + ffmpeg, puis diagnostic (code 0 = prêt)
python3 moteur/voix_libre.py generer DOSSIER_DE_L_EPISODE --declarer
python3 moteur/voix_libre.py generer DOSSIER --declarer --refaire bloc1,bloc2   # ne refait que ces paragraphes
python3 moteur/voix_libre.py generer DOSSIER --declarer --refaire auto          # ceux dont le texte a changé
python3 moteur/voix_libre.py horodater DOSSIER                   # refait les mots horodatés d'une prise, bloc par bloc
```
- Environnement : `installer` crée un Python à part dans `/opt/voix-kyutai` (moshi impose numpy < 2.3, le moteur
  vidéo utilise un numpy récent) ; `diagnostic`, `generer` et `horodater` s'y relancent tout seuls. moshi 0.2.11 est
  installé sans ses dépendances puis complété une à une, avec sentencepiece ≥ 0.2.1 : la version 0.2.0 qu'il exige
  n'existe pas compilée pour Python 3.13 et sa compilation échoue (constaté le 21/10/2026).
- Texte lu : épisode « Vrai ou faux ? » → les blocs de `vf.voix.narration_quiz` (ouverture, affirmations,
  verdicts, panneaux, score, annonce ; clés `voix_*` du script pour corriger une lecture) ; reportage → le fichier
  `narration` (un paragraphe par bloc). Les nombres, unités et sigles sont écrits en lettres pour la voix
  seulement (`vf/nombres.py` : « 380 000 » → « trois cent quatre-vingt mille », « ADN » → « A-D-N ») ; l'écran et
  les sous-titres gardent les chiffres.
- Chaque bloc est généré séparément (0,5 s de silence entre deux blocs, bornes exactes notées dans
  `prise_mots.json` → `blocs` : le découpage du quiz se fait sur ces bornes, pas sur la transcription), puis relu
  par une transcription indépendante (faster-whisper medium) et refait (4 essais) s'il manque 3 mots ou plus, s'il
  s'en ajoute, ou s'il y a une syllabe parasite au début. Un bloc de 3 mots ou moins doit en plus être entendu mot
  pour mot et ne pas s'étirer (parole ≤ 0,32 s par mot + 0,4 s) : le 20/10/2026, un « Faux ! » isolé était sorti en
  « Fouuuu… » de 1,1 s ; le verdict se dit donc désormais « C'est faux ! » / « C'est vrai ! ». Code de sortie 0
  seulement si tout est vérifié ; `--declarer` écrit alors le champ `voix` dans `episode.json` (`"eclaircir": true` :
  étape « micro studio »).
- Mots horodatés : la transcription indépendante de **chaque bloc** (celle de la vérification), placée sur la prise
  (`voix/prise_mots.json`) ; un bloc repris par `--refaire` garde ses mots d'origine. Ils sont ensuite alignés sur le
  script **à l'intérieur de leur bloc** (`vf.voix.aligner_dans_blocs`, ≥ 90 % exigé) : un mot retrouvé hors de son
  bloc est rejeté, et les mots non retrouvés sont répartis sur la parole réelle de leur bloc. (Le 20/10/2026, la
  transcription d'une prise entière avait sauté « vers nous depuis presque 13,8 milliards d'années. Alors pourquoi
  46 milliards, et » : les sous-titres de ce passage auraient défilé en un éclair.)
- Mémoire : modèle de voix + transcription ≈ 7,5 Gio au maximum. Sur une machine de moins de 14 Gio, `generer`
  ajoute un fichier d'échange sur disque (`/var/tmp/voix_libre.swap`) pour que le pic ne fasse pas tuer le calcul.

Mesures (GitHub Actions, 4 cœurs, 16 Go, 20/10/2026) : quiz « sommeil » (20 blocs, 81 s de voix) en 22 min, mémoire
maximale 7,2 Gio ; reportage INFINIMENT 2 (7 blocs, 88 s) en 19 min, 6,4 Gio ; tous les blocs vérifiés au premier
essai. Sur 2 cœurs, compter environ le double. Une session à 8 Go de mémoire est juste : `generer` y ajoute un
fichier d'échange de 6 à 7 Go ; si la génération est tout de même tuée, l'épisode sort sans voix (quiz) ou attend
(reportage).

### Ce que l'environnement de la tâche planifiée doit autoriser

Les sessions des tâches planifiées créées depuis l'application Claude prennent leurs droits réseau dans **claude.ai →
Paramètres → Capacités** → « Exécution de code et création de fichiers » → accès réseau sortant (le proxy de la
session l'indique lui-même). Liste réglée par Nathan le 21/10/2026 (les « *. » ne sont pas pris en compte : chaque
nom exact compte) :
```
pypi.org, files.pythonhosted.org      (gestionnaires de paquets)
huggingface.co                        (adresses des fichiers du modèle)
us.aws.cdn.hf.co                      (serveur qui les envoie réellement)
download.pytorch.org                  (PyTorch pour processeur, ≈ 200 Mo…)
download-r2.pytorch.org               (… dont les fichiers sont servis ici)
```
Une tâche planifiée de type Claude Code (dépôt et environnement choisis dans claude.ai/code/routines) prend au
contraire ses droits dans son environnement : **Network access** → **Custom**, mêmes domaines. `voix_libre.py
diagnostic` télécharge 16 octets d'un vrai fichier du modèle : il dit en quelques secondes si tout passe, et sinon
quel serveur est refusé.

Mesures dans une session de tâche planifiée (2 cœurs Xeon avec AMX, 8 Go, 21/10/2026) : installation 47 s ;
téléchargement et chargement du modèle 284 s (5,3 Go, bfloat16, 3,4 Gio en mémoire) ; un paragraphe de 11,9 s
d'audio généré et vérifié en 115 s (≈ 10 fois le temps réel) ; mémoire maximale 5,7 Gio (fichier d'échange de
7 Go ajouté, inutilisé). Un épisode complet (≈ 85 s de voix) : ≈ 15 à 20 min de génération.

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
