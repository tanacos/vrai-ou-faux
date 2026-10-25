# Procédure de la routine « INFINIMENT » (mini-reportage hebdomadaire)

Tu es la routine automatique de la série TikTok « INFINIMENT » de Nathan : un mini-reportage narré par semaine,
« de l'infiniment petit à l'infiniment grand ». À chaque déclenchement (samedi matin), tu fabriques **un** épisode,
tu le vérifies, puis tu le programmes dans Metricool au moins 48 h plus tard (lundi 18:00 par défaut) : Nathan garde
une fenêtre de veto. Personne ne relit ton travail avant la publication : la rigueur des faits est ta première
responsabilité. La série « Vrai ou faux ? » a sa propre routine (ROUTINE.md) : ne touche ni à son journal ni à ses
publications.

Si le message de déclenchement contient **MODE ESSAI**, fais tout, mais crée la publication Metricool en
**brouillon** (`"draft": true`) et note `"statut": "brouillon (essai)"` dans le journal. En mode essai seulement, le
garde-fou « file pleine » ne s'applique pas ; les fichiers `PAUSE` et `PAUSE_REPORTAGE` restent respectés.

## 0. Préparer l'espace de travail

1. Rattache le dépôt (outil `add_repo`, owner `tanacos`, repo `vrai-ou-faux`, accès `push`), puis clone-le
   (`git clone --depth 1 https://github.com/tanacos/vrai-ou-faux /home/claude/vrai-ou-faux`).
2. Lis `config.json` (section `reportage`), `journal_reportages.json`, `series/infiniment/LISEZMOI.md` (la bible de
   la série, ses leçons et ses pistes), `moteur/rp/FORMAT_REPORTAGE.md` (format des scènes), `journal.json` (thèmes
   déjà traités par « Vrai ou faux ? », à ne pas répéter).
   Ajoute tout de suite une ligne en tête du tableau de `journal_des_runs_reportage.md` (date et heure de Paris,
   mode, « démarré »), puis `git commit` et `git push origin HEAD:main`. Tu complètes cette ligne à la fin.
3. **État de départ** : `getScheduledPosts` (brand `7381054`, fuseau `Europe/Paris`, de maintenant à J+60), réponse
   brute enregistrée dans `/tmp/posts.json` (outil Write), puis :
   ```bash
   cd /home/claude/vrai-ou-faux && python3 moteur/publier.py etat --serie infiniment /tmp/posts.json
   ```
   Décide d'après cette sortie, **dans cet ordre** :
   - `pause: true` → arrêt propre (rapport : « série en pause »).
   - `orphelins` non vide → un run précédent a été interrompu **après** avoir programmé : ne fabrique rien.
     Rattache chaque orphelin à l'épisode du journal dont le titre correspond à sa légende
     (`python3 moteur/publier.py journal <dossier> --statut programmé --publication <dateTime> --metricool_id <id>
     --metricool_uuid <uuid>`), puis étape 9. Si aucun ne correspond, ne touche à rien et signale-le.
   - `file_pleine: true` (hors MODE ESSAI) → arrêt propre : rien à faire.
   - `action: "reprendre"` → l'épisode `numero` (dossier `dossier`) est déjà écrit et a passé la
     contre-vérification : ne refais ni la recherche ni le script.
     - statut `en attente de voix` : reprends à l'étape 6 (voix), puis 7 à 10 ;
     - statut `voix faite` : reprends à l'étape 7 ;
     - statut `fabriqué` : refabrique la vidéo (étape 7, commande `tout` seulement), puis étape 8 ;
     - statut `hébergé` : la vidéo est déjà en ligne (champ `video`) ; à l'étape 8, commence à `legende`.
   - `action: "nouveau"` → épisode `numero`. Le sujet est **obligatoirement** `sujet_impose` s'il existe (annoncé à
     la fin de l'épisode précédent). Fais les étapes 1 à 9.

## 1. Sujet

- Un seul fait étonnant, démontrable en 80 à 90 s, avec des chiffres vérifiables, qui se raconte sur l'échelle des
  tailles (de 10⁻¹⁵ m à 10²⁶ m) : voir « La promesse » et « Pistes » dans `series/infiniment/LISEZMOI.md`.
- Jamais un sujet déjà traité (journal des deux séries). Alterne le sens : après un épisode vers le grand, un vers
  le petit (et inversement).
- Interdits : ceux de `sujets.md` (santé, politique, religion, drames, personnes privées, marques…).

## 2. Recherche et vérification des faits (étape décisive)

Comme pour « Vrai ou faux ? » (ROUTINE.md, étape 2) : `WebSearch` puis **lecture** des pages (`WebFetch`), au moins
**2 sources fiables d'éditeurs différents** pour le fait central, au moins une pour chaque autre fait (agences
spatiales, instituts de recherche, universités, encyclopédies reconnues, grands médias scientifiques). Wikipédia
sert seulement à trouver les sources primaires. Recopie dans `sources[].extraits` les phrases exactes. **Chaque
nombre dit ou affiché figure dans un extrait ou découle d'un calcul écrit dans `calcul`** (vérifie le calcul avec
un outil, pas de tête). Au moindre doute non résolu, change de sujet. Vérifie aussi que le sujet que tu annonceras
pour l'épisode suivant (`prochain`) a au moins 2 sources : il engage la semaine suivante.

## 3. Script

Crée `series/infiniment/epNN/` (NN sur 2 chiffres) en suivant `moteur/rp/FORMAT_REPORTAGE.md` et l'exemple
`series/infiniment/ep02/` :
- `narration.txt` : 7 à 9 paragraphes (blocs), **230 à 245 mots** au total (≈ 85 s avec la voix Estelle), tutoiement,
  phrases courtes, une idée par phrase, structure de la bible (accroche paradoxale, voyage d'échelle, chiffre clé,
  explication, retournement, « Prochain épisode : … Les sources sont en description. »). Nombres en chiffres, sans
  points de suspension ni balises.
- `episode.json` : `blocs`, `scenes` (une scène ou une liste de plans par bloc), `voix_libre`, `sources`, `calcul`,
  `images`, `publication` (légende : accroche + « INFINIMENT, épisode N : de l'infiniment petit à l'infiniment
  grand. » + l'explication en une phrase + « Sources : … » + « Voix de synthèse : Kyutai TTS (CC BY 4.0) » + mots-dièse
  dont `#infiniment`), `prochain`.
- Les images sont des affirmations : tailles comparées à l'échelle, couleurs fidèles quand elles sont connues,
  « pas à l'échelle » écrit quand c'est le cas.

## 4. Aperçu sans voix et corrections

```bash
cd /home/claude/vrai-ou-faux
python3 series/infiniment/fabriquer.py provisoire series/infiniment/epNN
python3 series/infiniment/fabriquer.py valider    series/infiniment/epNN    # "ok": true exigé
python3 series/infiniment/fabriquer.py apercu     series/infiniment/epNN    # « aucun problème » exigé
```
Regarde `series/infiniment/epNN/sortie/planche.png` (outil Read) : chaque moment a un visuel, rien ne se
chevauche, les textes sont lisibles, le visuel dit la même chose que la voix. Corrige jusqu'à ce que ce soit propre.

## 5. Contre-vérification indépendante (obligatoire, avant la voix)

```bash
python3 moteur/rp/dossier.py series/infiniment/epNN > /tmp/dossier_epNN.txt
```
Lance un agent (outil `Agent`, type `general-purpose`) qui n'a pas vu ta recherche, avec cette consigne : « Lis
/tmp/dossier_epNN.txt. Ouvre chaque URL (WebFetch) et vérifie que chaque extrait y figure ; vérifie que chaque phrase
de la narration, chaque texte affiché, chaque nombre (refais les calculs), chaque puissance de dix et la légende sont
confirmés par les sources ; signale toute formulation qui exagère les sources ou qui serait contestable par un
spécialiste, et toute image qui affirme quelque chose de faux. Rends la liste des écarts avec une correction pour
chacun, ou « aucun écart ». » Zéro écart exigé : corrige, refais l'aperçu, refais vérifier (2 tours au maximum).
Au moindre doute non résolu, **ne publie pas** : abandonne proprement et signale-le.

## 6. Voix (Estelle, Kyutai TTS 1.6B)

```bash
python3 moteur/voix_libre.py diagnostic
```
- Si `"ok": false` : `python3 moteur/voix_libre.py installer` (paquets PyPI + index CPU de PyTorch, ffmpeg ; 2 à
  5 min), qui refait le diagnostic. S'il reste négatif (accès réseau à PyPI, à download.pytorch.org ou à Hugging Face
  refusé) : **arrête-toi là**. Pousse le dossier de l'épisode (statut `en attente de voix` dans le journal :
  `python3 moteur/publier.py journal series/infiniment/epNN --statut "en attente de voix"`), et explique dans le
  rapport que l'environnement de la tâche doit autoriser ces domaines (voir `moteur/VOIX.md`). Aucune publication
  sans voix pour ce format.
- Sinon, génère en arrière-plan (20 à 45 min) et surveille avec une seule commande toutes les 8 minutes :
  ```bash
  setsid nohup python3 moteur/voix_libre.py generer series/infiniment/epNN --declarer --refaire auto \
    > /tmp/voix_epNN.log 2>&1 < /dev/null & disown
  sleep 480; tail -3 /tmp/voix_epNN.log
  ```
  (`--refaire auto` : s'il existe déjà une prise vérifiée, seuls les paragraphes dont le texte a changé sont
  refaits ; sinon tout est généré.) Exigé : une dernière ligne avec `"tout_verifie": true` et `"declare": true`
  (chaque paragraphe relu par une transcription indépendante). Un paragraphe non vérifié après 4 essais : reformule-le légèrement dans
  `narration.txt` sans toucher à aucun fait ni nombre, puis ne régénère que lui (`… generer series/infiniment/epNN
  --declarer --refaire <bloc>`) et signale la reformulation dans le rapport. Processus disparu sans dernière ligne :
  relance la même commande une fois. Ajoute dans `episode.json` → `voix` des `respirations` (0,8 à 1,3 s après les
  révélations).
- Point de sauvegarde : `python3 moteur/publier.py journal series/infiniment/epNN --statut "voix faite"`, commit, push.

## 7. Fabrication complète (≈ 25 à 40 min)

```bash
python3 series/infiniment/fabriquer.py voix   series/infiniment/epNN      # alignement ≥ 90 % exigé
python3 series/infiniment/fabriquer.py valider series/infiniment/epNN
setsid nohup python3 series/infiniment/fabriquer.py tout series/infiniment/epNN > /tmp/fab_epNN.log 2>&1 < /dev/null & disown
sleep 480; tail -3 /tmp/fab_epNN.log
```
- Si le processus disparaît sans « terminé », relance la même commande : elle reprend aux tronçons déjà faits.
- Statut `conforme` exigé (`sortie/rapport.json` : zones sûres, textes sans chevauchement, synchro voix, niveaux).
  Sinon corrige (3 tentatives maximum), puis abandonne proprement.
- Regarde `sortie/planche.png` une dernière fois.
- Point de sauvegarde :
  ```bash
  cp series/infiniment/epNN/sortie/planche.png series/infiniment/epNN/planche.png
  cp series/infiniment/epNN/sortie/rapport.json series/infiniment/epNN/rapport_qc.json
  python3 moteur/publier.py journal series/infiniment/epNN --statut fabriqué
  git add -A && git commit -q -m "INFINIMENT NN : fabriqué" && git push origin HEAD:main
  ```

## 8. Hébergement et programmation

```bash
python3 moteur/publier.py heberger series/infiniment/epNN series/infiniment/epNN/sortie/video.mp4
python3 moteur/publier.py journal  series/infiniment/epNN --statut hébergé --video <lien direct>
git add -A && git commit -q -m "INFINIMENT NN : vidéo hébergée" && git push origin HEAD:main
python3 moteur/publier.py legende  series/infiniment/epNN
```
- Si la sortie de `heberger` contient `alerte`, recopie-la en tête du rapport.
- **Anti-doublon** : juste avant `createScheduledPost`, relis `getScheduledPosts` ; si une publication porte déjà la
  légende de cet épisode, ne la recrée pas : reprends son `id` et son `uuid` pour l'étape 9.
- Créneau : `getScheduledPosts` (60 prochains jours) enregistré dans `/tmp/posts.json`, puis
  `python3 moteur/publier.py creneau --serie infiniment /tmp/posts.json` (premier lundi libre à au moins 48 h).
  Affine l'heure avec `getBestTimeToPostByNetwork` (tiktok, ce jour-là) dans `fenetre_horaire` ; à défaut 18:00.
- `createScheduledPost` (`blogId` 7381054), champ `info` comme pour « Vrai ou faux ? » (ROUTINE.md, étape 7) :
  `autoPublish: true`, `draft: false` (true en MODE ESSAI), `providers: [{"network": "tiktok"}]`, `media: [lien
  direct]`, `text: légende`, `publicationDate: {dateTime, timezone: "Europe/Paris"}`, `tiktokData: {privacyOption:
  "PUBLIC_TO_EVERYONE", title: légende, isAigc: false, disableComment: false,
  disableDuet: false, disableStitch: false, autoAddMusic: false, commercialContentThirdParty: false,
  commercialContentOwnBrand: false}`, plus `descendants: []`, `firstCommentText: ""`, `hasNotReadNotes: false`,
  `mediaAltText: []`, `shortener: false`, `smartLinkData: {ids: []}`.
- `isAigc` reste à `false` : Nathan a demandé le 25/10/2026 de ne plus activer l'étiquette TikTok « contenu généré par
  IA ». Ne la réactive pas. La mention « Voix de synthèse : Kyutai TTS (CC BY 4.0) » reste obligatoire dans la légende.
- Vérifie avec `getScheduledPosts` que la publication existe et que son `media` pointe vers `static.metricool.com`.

## 9. Journal et sauvegarde

```bash
python3 moteur/publier.py journal series/infiniment/epNN --statut programmé --publication <date ISO> \
  --metricool_id <id> --metricool_uuid <uuid> --video <lien direct>
git add -A && git commit -m "INFINIMENT NN : <titre>" && git push origin HEAD:main
```
Pousse toujours sur `main`, jamais sur une branche `claude/…`. Push refusé : `git pull --rebase origin main` puis
`git push origin HEAD:main`. Ne force jamais un push. Complète la ligne de `journal_des_runs_reportage.md`.

## 10. Rapport final (court, en français)

Titre de l'épisode, date et heure de publication, lien de la vidéo, le fait central et ses sources principales,
le sujet annoncé pour la semaine suivante, et : « Pour l'annuler, supprime la publication dans Metricool avant
cette heure. » En cas d'arrêt : ce qui a bloqué, ce qui n'a **pas** été publié, et ce qu'il faut faire.

## Interdits absolus

- Publier sans `statut: conforme` ou sans « aucun écart » de la contre-vérification (étape 5), ou sans voix vérifiée.
- Modifier ou supprimer une publication Metricool existante (seule exception : ta propre publication de ce run).
- Dépasser `reportage.file_max` publications en attente ; publier à moins de 48 h.
- Donner des conseils médicaux, juridiques ou financiers ; traiter de politique, de religion, de drames, de
  personnes privées ; reprendre des marques ou des images protégées (tout est dessiné par le moteur).
- Inventer une source, un extrait ou un chiffre.
- Utiliser GitHub Actions pour fabriquer l'épisode (réservé aux essais du logiciel).
