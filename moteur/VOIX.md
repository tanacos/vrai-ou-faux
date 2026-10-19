# Couche voix (ElevenLabs)

Une voix de synthèse ElevenLabs lit l'épisode ; tout le reste (montage, sous-titres, mixage, contrôles) se fait ici,
de façon reproductible. **Désactivée par défaut** dans la routine (`"voix_active": false` dans `config.json`) : voir
« Licence » avant de l'activer.

## Pourquoi un relais

Les sessions Claude ne joignent ni ElevenLabs ni son stockage (`storage.googleapis.com`) : la prise générée ne peut pas
être téléchargée directement. `moteur/relais.py` passe par GitHub, joignable des deux côtés : la session dépose l'URL
dans la branche jetable `relais`, un runner GitHub Actions télécharge le fichier et le dépose dans la même branche, la
session le récupère par git (10 à 40 s). **Le dépôt est public : les prises relayées le sont aussi.**
Les liens ElevenLabs sont signés pour **2 heures** ; un nouvel appel à `creative_get_flow_run_status` en redonne un.

## Procédure (épisode « Vrai ou faux ? »)

Le script final doit être prêt (étapes 1 à 5 de la routine) : la voix lit ce que l'écran montre.

1. **Texte à faire lire** (un paragraphe par bloc : ouverture, affirmation, verdict, chaque panneau, score, annonce) :
   ```bash
   cd moteur && python3 -m vf.voix texte ../episodes/NNN-slug/episode.json > /tmp/epNNN/narration.txt
   ```
   Le nombre de caractères s'affiche : c'est le coût en crédits d'**une** prise (≈ 1 100 pour un épisode).
   Pour corriger une lecture (nombre, sigle, liaison), ajoute dans le script `voix_intro`, `voix_score`,
   `voix_prochain`, idée.`voix_affirmation` / `voix_verdict`, ou panneau.`voix` (`""` = panneau muet), jamais en
   changeant le texte affiché. Exemple : `"voix": "En moyenne, moins de cinq pour cent."`.
2. **Génération** (connecteur ElevenLabs) : `creative_create_flow` (un flow par épisode), puis
   `creative_generate_speech` avec ce flow, `model_id: "eleven_v4"`, `voice_id: "DGTOOUoGpoP6UZ9uSWfA"` (Célian,
   voix française posée), le texte de l'étape 1, `generations_count: 1` (2 si les crédits le permettent, pour pouvoir
   écarter une prise ratée). Interroge `creative_get_flow_run_status` jusqu'à `all_completed`.
3. **Rapatriement de la prise** :
   ```bash
   python3 moteur/relais.py recuperer episodes/NNN-slug/voix "prise.mp3=<content_url>"
   ```
4. **Horodatage mot à mot** : `creative_add_flow_asset_node` (`modality: "audio"`, `generation_id` de la prise retenue)
   → `creative_transcribe_audio` (`eleven_scribe_v1`, `connect_from: [node_id]`, 0 crédit constaté) → statut →
   `python3 moteur/relais.py recuperer episodes/NNN-slug/voix "prise_mots.json=<words_download_url>"`.
5. **Déclaration dans le script** (`episode.json`) :
   ```json
   "voix": {"fournisseur": "ElevenLabs", "modele": "eleven_v4", "voice_id": "DGTOOUoGpoP6UZ9uSWfA", "nom": "Célian",
            "tempo": 1.03, "prise": "voix/prise.mp3", "mots": "voix/prise_mots.json"}
   ```
   `tempo` accélère sans changer la hauteur (1,00 à 1,06).
6. **Contrôle de la prise**, puis aperçu et fabrication habituels :
   ```bash
   cd moteur && python3 -m vf.voix verifier ../episodes/NNN-slug/episode.json    # "ok": true exigé
   ```
   La chronologie s'allonge seule pour laisser chaque phrase se finir (épisode de 4 idées : ≈ 85 s au lieu de 74).
   Si `valider` signale un dépassement de 90 s, raccourcis des panneaux ou leur texte lu (`voix`).

Le contrôle qualité de `fabriquer.py tout` ajoute alors quatre vérifications : « synchro voix » (décalage ≤ 40 ms
entre la piste voix attendue et la vidéo finale), « voix alignée sur le script » (≥ 90 % des mots),
« phrases découpées dans les silences », « phrases sans chevauchement ».

## Série INFINIMENT (reportage narré)

Voir `series/infiniment/fabriquer.py` : la narration est un fichier texte (balises d'interprétation eleven_v4 entre
crochets, `[curious]`, `[pause]`…), la voix pilote toute la chronologie (`chrono.json` : blocs, repères au mot près,
sous-titres), puis `fabriquer.py tout` rend, mixe et contrôle.

## Voix libre et gratuite : Kyutai Pocket TTS (`moteur/voix_libre.py`)

Alternative sans abonnement, utilisable commercialement : poids du modèle sous CC BY 4.0 (mention « Voix :
Kyutai Pocket TTS (CC BY 4.0) » dans la légende), voix « estelle » (enregistrement de Kyutai cédé en CC0). Chaque
paragraphe est relu par une transcription indépendante (faster-whisper) et refait s'il manque un passage : lors des
essais du 19/10/2026, sans cette vérification, une prise sur trois commençait par une syllabe parasite, et des
morceaux trop longs (120 jetons) ont fait sauter une phrase entière dans trois prises sur trois. Réglages retenus
pour un ton « reportage » : paragraphes entiers (80 jetons au plus), température 0,4, ponctuation sans points de
suspension (`narration_v5_tv.txt`), débit posé au montage (`"tempo": 0.92`, `"pauses": 1.4` dans `voix`).

Où la faire tourner : le modèle doit être installé (PyPI, index PyTorch CPU) et ses poids téléchargés (Hugging Face),
ce que l'environnement par défaut de la routine bloque. Il faut donc élargir l'accès réseau de l'environnement
(niveau « Custom » avec ces domaines, ou « Full ») et installer les paquets par un script de démarrage. Les essais
ont tourné sur GitHub Actions (branche `essai-voix`), ce qui convient pour tester mais pas pour produire chaque
semaine : les conditions de GitHub réservent ses machines à la construction et aux tests du logiciel.

## Corriger après coup sans régénérer

Une phrase à **supprimer** d'une prise déjà générée (fait contesté découvert après coup) se retire sans dépenser de
crédits : dans `episode.json` (série INFINIMENT), `voix.narration_prise` = texte lu dans la prise,
`voix.retraits` = `[{"bloc": "…", "phrase": "…"}]`, et `narration` = ce texte moins ces phrases. La fabrication coupe
la prise au milieu des silences qui encadrent la phrase (`vf.voix.retirer_phrase`) et refuse une coupe tombée dans la
parole. Une phrase à **reformuler** impose une nouvelle prise.

## Ce que les contrôles ne garantissent pas

- La « transcription » d'une prise générée renvoie le texte demandé (balises comprises) avec des horodatages : c'est un
  **alignement forcé**, pas une reconnaissance indépendante. Un mot sauté ou mal prononcé n'abaisse donc pas le taux
  d'alignement. `verifier` liste les mots dont l'intervalle ne contient presque pas de voix (`mots_a_ecouter`), mais
  **seule une écoute garantit la prononciation** (chiffres, noms propres, liaisons).
- Le traitement de la voix (égalisation, compression, -16,5 LUFS) et le mixage (-14,5 LUFS, crête ≤ -3 dBTP) sont
  mesurés, pas écoutés.

## Licence et coûts (vérifié le 19/10/2026)

- **Offre gratuite** : **aucun usage commercial**, et un contenu créé hors abonnement payant ne devient jamais
  commercial (« before or after ») ; mention `elevenlabs.io` obligatoire dans le titre. Source : ElevenLabs, « Can I
  publish the content I generate on the platform? »
  (https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform).
  10 000 crédits par mois (comparatif cité plus bas) ; coût mesuré : 1 crédit par caractère (prise de 1 061
  caractères facturée 1 061 crédits).
- **Offres payantes** : licence commerciale incluse, sauf « Beta Services » (même page). Starter : 30 000 crédits pour
  5 $/mois d'après un comparatif de mars 2026 (https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/),
  à confirmer sur https://elevenlabs.io/pricing.
- Un compte TikTok rémunéré (programme Creator Rewards, d'où la durée minimale de 61 s) est à traiter comme un usage
  commercial (déduction : la page d'ElevenLabs ne cite pas TikTok) : n'active pas la voix sur la routine avant un
  abonnement payant, et **régénère** alors les prises (celles de l'offre gratuite restent non commerciales).
- La routine déclare déjà le contenu comme généré par IA (`isAigc: true`).
