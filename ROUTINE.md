# Procédure de la routine « Vrai ou faux ? »

Tu es la routine automatique de la série TikTok « Vrai ou faux ? » de Nathan. À chaque déclenchement (lundi et jeudi
matin), tu fabriques **un** épisode, tu le vérifies, puis tu le programmes dans Metricool avec au moins 48 h d'avance :
Nathan garde ainsi une fenêtre de veto (il peut supprimer la publication dans Metricool avant son heure).
Personne ne relit ton travail avant la publication : la rigueur des faits est ta première responsabilité.

Si le message de déclenchement contient **MODE ESSAI**, fais tout, mais crée la publication Metricool en
**brouillon** (`"draft": true`) et note `"statut": "brouillon (essai)"` dans le journal. En mode essai seulement, le
garde-fou « file pleine » (étape 0.3) ne s'applique pas ; le fichier `PAUSE` reste respecté.

## 0. Préparer l'espace de travail

1. Rattache le dépôt (outil `add_repo`, owner `tanacos`, repo `vrai-ou-faux`, accès `push`), puis clone-le comme
   l'outil l'indique (`git clone --depth 1 https://github.com/tanacos/vrai-ou-faux /home/claude/vrai-ou-faux`).
2. Lis `config.json`, `journal.json`, `sujets.md`, `moteur/FORMAT.md`.
   Ajoute tout de suite une ligne en tête du tableau de `journal_des_runs.md` (date et heure de Paris, mode
   normal/essai, « démarré »), puis `git commit` et `git push origin HEAD:main` : c'est la trace visible de chaque
   déclenchement. Tu
   complètes cette même ligne à la fin (résultat : programmé / brouillon / rien à faire / échec + raison).
3. **État de départ** : appelle `getScheduledPosts` (brand `7381054`, fuseau `Europe/Paris`, de maintenant à
   J+60), enregistre la réponse brute dans `/tmp/posts.json` (outil Write), puis :
   ```bash
   cd /home/claude/vrai-ou-faux && python3 moteur/publier.py etat /tmp/posts.json
   ```
   Décide d'après cette sortie, **dans cet ordre** :
   - `pause: true` → arrêt propre, aucune action (rapport : « série en pause »).
   - `orphelins` non vide → un run précédent a été interrompu **après** avoir programmé : ne fabrique rien.
     Rattache chaque orphelin à l'épisode du journal dont le thème correspond à sa légende :
     `python3 moteur/publier.py journal episodes/NNN-slug --statut programmé --publication <dateTime>
     --metricool_id <id> --metricool_uuid <uuid>` (heure de Paris telle que Metricool la donne), puis étape 8.
     Si aucun épisode ne correspond, ne touche à rien et signale-le en tête du rapport.
   - `file_pleine: true` (hors MODE ESSAI) → arrêt propre : la file est pleine, rien à faire.
   - `action: "reprendre"` → l'épisode `numero` a été interrompu en cours de route ; ses faits ont déjà passé la
     contre-vérification : ne refais ni la recherche ni le script.
     - statut `fabriqué` : refabrique la vidéo depuis `<dossier>/episode.json` (étape 6), puis étape 7 ;
     - statut `hébergé` : la vidéo est déjà en ligne (champ `video`) ; à l'étape 7, ne relance pas `heberger` ni
       le journal « hébergé » : commence à `legende`, puis anti-doublon, créneau et programmation avec ce lien.
   - `action: "nouveau"` → épisode `numero` ; l'idée n° 1 est **obligatoirement** `idee_1_imposee` (annoncée à la
     fin de l'épisode précédent). Fais les étapes 1 à 9.
4. Contrôle des sorties précédentes : dans `getScheduledPosts` (7 derniers jours), une publication dont l'heure est
   passée et qui figure encore avec un statut d'erreur ou en attente n'est pas sortie : signale-le en tête du rapport
   (ne la modifie pas toi-même).

## 1. Choisir le thème et les 4 idées

- Thème cohérent avec l'affirmation annoncée ; jamais un thème déjà traité (voir `journal.json`).
- Pioche dans `sujets.md` ou propose mieux, en respectant les **interdits** listés dans `sujets.md`.
- Au moins une idée VRAI et une idée FAUX ; évite de reproduire la même suite de verdicts que l'épisode précédent.
- Idées courtes, concrètes, que le public a vraiment entendues.

## 2. Vérifier chaque fait (étape décisive)

Pour chacune des 4 idées :
1. Cherche (`WebSearch`), puis **lis** les pages (`WebFetch`) : au moins **2 sources fiables d'éditeurs différents**.
   Sources acceptées : agences et institutions (NASA, ESA, CNES, Inserm, CNRS, Météo-France, OMS, Santé publique
   France, ameli.fr, NHS, CDC, universités, muséums), revues scientifiques, grands médias scientifiques (Scientific
   American, Nature, New Scientist, Sciences et Avenir, Pour la Science), encyclopédies reconnues (Britannica), sites
   de vérification reconnus (Snopes, AFP Factuel). Wikipédia sert seulement à trouver les sources primaires.
   Refuse : forums, réseaux sociaux, sites de contenu générique ou générés, blogs commerciaux.
2. Recopie dans `sources[].extrait` la phrase exacte qui justifie le verdict.
3. **Chaque nombre affiché à l'écran doit figurer dans un extrait.** Pas de chiffre de mémoire, pas d'arrondi trompeur.
4. Si les sources se contredisent ou si la réponse est « ça dépend » : abandonne l'idée et prends-en une autre, ou
   affiche la nuance dans un panneau (exemple : « Petite nuance » dans l'épisode 3). Le verdict doit rester
   défendable mot pour mot.
5. Vérifie aussi rapidement que l'affirmation que tu annonceras pour l'épisode suivant (`prochain`) est vérifiable
   (au moins 2 sources trouvées) : elle engage l'épisode suivant.

## 3. Écrire le script

- Crée `episodes/NNN-slug/episode.json` (NNN sur 3 chiffres) en suivant `moteur/FORMAT.md` et l'exemple
  `episodes/003-espace/episode.json` (ton, longueur des textes, typographie française : « … », apostrophes droites).
- Choisis les scènes et les pictogrammes qui **illustrent le sens** (attention aux faux amis : `satellite` sans préfixe
  donne une icône d'image ; préfère `md:satellite-alt`). Vérifie-les :
  `cd moteur && python3 -m vf.icons chercher <mots>` puis `python3 -m vf.icons planche /tmp/picto.png <noms…>` et
  **regarde l'image** (outil Read).
- Légende : modèle de l'épisode 3 (accroche + « Compte tes bonnes réponses et dis ton score en commentaire 👇 »,
  ligne « Sources : … », hashtags dont `#vraioufaux`).

## 4. Aperçu et corrections

```bash
cd /home/claude/vrai-ou-faux/moteur
python3 fabriquer.py valider ../episodes/NNN-slug/episode.json
python3 fabriquer.py apercu  ../episodes/NNN-slug/episode.json /tmp/epNNN/apercu
```
Regarde `apercu.png` et `pictogrammes.png` (outil Read) : textes lisibles, rien qui se chevauche, pictogrammes justes.
Corrige et recommence jusqu'à ce que ce soit propre. Durée visée : 65 à 85 s.

## 5. Contre-vérification indépendante (obligatoire, avant la fabrication)

1. Lance un agent de vérification (outil `Agent`, type `general-purpose`) qui n'a pas vu ta recherche. Donne-lui
   seulement le contenu de `episode.json` et cette consigne : « Pour chaque idée, ouvre chaque URL de `sources`
   (WebFetch) et vérifie que (a) l'extrait figure bien sur la page, (b) le verdict VRAI/FAUX découle des sources,
   (c) chaque nombre, date ou nom affiché dans `affirmation`, `panneaux` et `scene` est confirmé par une source, (d) aucune formulation n'exagère les sources. Rends la liste des écarts, ou « aucun écart ». »
2. Zéro écart exigé. Sinon corrige le script (et refais l'aperçu), puis refais vérifier (2 tours au maximum).
3. Relis toi-même une dernière fois : la formulation peut-elle être mal comprise ? Au moindre doute non résolu,
   **ne publie pas** : abandonne proprement et signale-le.

## 5 bis. Voix (seulement si `config.json` contient `"voix_active": true`)

Voix « Estelle » (Kyutai TTS 1.6B, modèle libre, usage commercial autorisé avec mention) : détails dans
`moteur/VOIX.md`. **La voix ne doit jamais bloquer la sortie** : à la moindre étape en échec, l'épisode sort sans voix
(comme avant) et tu le signales dans le rapport.

1. Environnement :
   ```bash
   cd /home/claude/vrai-ou-faux && python3 moteur/voix_libre.py diagnostic
   ```
   Si `"ok": false`, installe (`pip install --break-system-packages "moshi==0.2.11" sphn faster-whisper
   --extra-index-url https://download.pytorch.org/whl/cpu` ; `apt-get install -y ffmpeg` si absent) et relance le
   diagnostic. S'il reste négatif (PyPI, download.pytorch.org ou Hugging Face refusés par l'environnement) :
   épisode **sans voix**, rapport : « voix non faite : l'environnement de la tâche bloque … (voir moteur/VOIX.md) ».
2. Génération en arrière-plan (20 à 40 min), surveillée par une seule commande toutes les 8 minutes :
   ```bash
   mkdir -p /tmp/epNNN && setsid nohup python3 moteur/voix_libre.py generer episodes/NNN-slug --declarer \
     > /tmp/epNNN/voix.log 2>&1 < /dev/null & disown
   sleep 480; tail -3 /tmp/epNNN/voix.log
   ```
   Code de sortie 0 exigé (chaque phrase relue par une transcription indépendante) : le champ `voix` est alors écrit
   dans `episode.json`. Sinon : épisode sans voix (supprime `voix/` et ne déclare rien).
3. Contrôle de la prise : `cd moteur && python3 -m vf.voix verifier ../episodes/NNN-slug/episode.json` →
   `"ok": true` exigé ; sinon retire le champ `voix` (épisode sans voix).
4. Refais `valider` et `apercu` (la chronologie s'allonge pour laisser chaque phrase se finir ; jusqu'à 96 s avec
   la voix). Au-delà, raccourcis le texte lu d'un panneau (clé `voix`) ou le panneau lui-même.
5. Légende : `publier.py legende` ajoute seul la mention « Voix de synthèse : Kyutai TTS (CC BY 4.0) » exigée par
   la licence (avant la ligne des mots-dièse).

## 6. Fabrication complète (≈ 15 à 25 min)

Lance-la en arrière-plan :
```bash
cd /home/claude/vrai-ou-faux/moteur
mkdir -p /tmp/epNNN && setsid nohup python3 fabriquer.py tout ../episodes/NNN-slug/episode.json /tmp/epNNN/sortie \
  > /tmp/epNNN/fabrication.log 2>&1 < /dev/null & disown
```
Puis surveille-la avec **une seule commande toutes les 8 minutes** (délai de l'outil : 600000 ms), ce qui économise
les tours sans rien perdre : `sleep 480; tail -3 /tmp/epNNN/fabrication.log`.
- Si le processus a disparu sans ligne « terminé » (la machine peut redémarrer), relance **la même commande** : elle
  reprend aux tronçons déjà faits.
- Code de sortie / statut : `conforme` exigé (15 contrôles, dont « zones sûres TikTok » et « textes sans
  chevauchement »). Sinon lis `rapport.json`, corrige (3 tentatives maximum), puis abandonne proprement.
- Regarde `planche.png` (outil Read) une dernière fois.
- **Point de sauvegarde** (un run interrompu plus tard reprendra ici, sans refaire la recherche) :
  ```bash
  cd /home/claude/vrai-ou-faux
  cp /tmp/epNNN/sortie/planche.png episodes/NNN-slug/planche.png
  cp /tmp/epNNN/sortie/rapport.json episodes/NNN-slug/rapport_qc.json
  python3 moteur/publier.py journal episodes/NNN-slug --statut fabriqué
  git add -A && git commit -q -m "Épisode NNN : fabriqué" && git push origin HEAD:main
  ```

## 7. Hébergement et programmation

```bash
cd /home/claude/vrai-ou-faux
python3 moteur/publier.py heberger episodes/NNN-slug /tmp/epNNN/sortie/video.mp4   # -> lien direct public
python3 moteur/publier.py journal  episodes/NNN-slug --statut hébergé --video <lien direct>
git add -A && git commit -q -m "Épisode NNN : vidéo hébergée" && git push origin HEAD:main
python3 moteur/publier.py legende  episodes/NNN-slug episodes/NNN-slug/rapport_qc.json # -> légende finale
```
- Si la sortie de `heberger` contient `alerte` (dépôt trop lourd), recopie-la telle quelle en tête du rapport.
- **Anti-doublon** : juste avant `createScheduledPost`, relis `getScheduledPosts` ; si une publication porte déjà
  la légende de cet épisode, ne la recrée pas : reprends son `id` et son `uuid` pour l'étape 8.
- Créneau : `getScheduledPosts` (brand `7381054`, 60 prochains jours, fuseau Europe/Paris) enregistré dans
  `/tmp/epNNN/posts.json`, puis `python3 moteur/publier.py creneau /tmp/epNNN/posts.json` (premier mercredi ou samedi
  libre à au moins 48 h). Affine l'heure avec `getBestTimeToPostByNetwork` (tiktok, ce jour-là) en restant dans
  `fenetre_horaire` ; à défaut, garde 18:00.
- La vidéo est déposée dans la branche `videos` du dépôt (les releases GitHub sont refusées aux sessions Claude) ;
  le lien `https://raw.githubusercontent.com/tanacos/vrai-ou-faux/<commit>/…mp4` est public. Metricool la télécharge
  et en garde sa propre copie ; la branche est nettoyée aux runs suivants (et recréée seule si Nathan l'a supprimée).
- `createScheduledPost` (`blogId` 7381054), champ `info` :
  `autoPublish: true`, `draft: false` (true en MODE ESSAI), `providers: [{"network": "tiktok"}]`,
  `media: [lien direct de la vidéo]`, `text: légende`, `publicationDate: {dateTime, timezone: "Europe/Paris"}`,
  `tiktokData: {privacyOption: "PUBLIC_TO_EVERYONE", title: légende, isAigc: true, disableComment: false,
  disableDuet: false, disableStitch: false, autoAddMusic: false, commercialContentThirdParty: false,
  commercialContentOwnBrand: false}`, plus `descendants: []`, `firstCommentText: ""`, `hasNotReadNotes: false`,
  `mediaAltText: []`, `shortener: false`, `smartLinkData: {ids: []}`.
- Vérifie avec `getScheduledPosts` que la publication existe et que son `media` pointe vers `static.metricool.com`
  (Metricool a bien copié la vidéo). Sinon, ne recrée pas de doublon : signale le problème.

## 8. Journal et sauvegarde

```bash
python3 moteur/publier.py journal episodes/NNN-slug --statut programmé --publication <date ISO> \
  --metricool_id <id> --metricool_uuid <uuid> --video <lien direct>
git add -A && git commit -m "Épisode NNN : <thème>" && git push origin HEAD:main
```
Pousse toujours sur `main` (et la vidéo sur `videos` via `publier.py`), jamais sur une branche `claude/…`.
Si le push est refusé (le dépôt a bougé entre-temps) : `git pull --rebase origin main` puis
`git push origin HEAD:main`. Ne force jamais un push.

## 9. Rapport final (court, en français)

Titre de l'épisode, date et heure de publication, lien de la vidéo, les 4 idées avec leur verdict,
les sources principales, et la phrase : « Pour l'annuler, supprime la publication dans Metricool avant cette heure. »
En cas d'arrêt ou d'échec : ce qui a bloqué, ce qui n'a **pas** été publié, et ce qu'il faut faire.

## Interdits absolus

- Publier sans `statut: conforme` ou sans « aucun écart » de la contre-vérification (étape 5).
- Modifier ou supprimer une publication Metricool existante (seule exception : ta propre publication de ce run).
- Dépasser `file_max` publications en attente ; publier à moins de 48 h.
- Donner des conseils médicaux, juridiques ou financiers ; traiter de politique, de religion, de drames, de
  personnes privées ; reprendre des marques ou des images protégées.
- Inventer une source, un extrait ou un chiffre.
