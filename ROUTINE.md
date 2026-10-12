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
3. **Garde-fous de départ** — arrête-toi proprement (rapport court, aucune action) si :
   - un fichier `PAUSE` existe à la racine du dépôt ;
   - Metricool (`getScheduledPosts`, brand `7381054`, sur les 30 prochains jours) contient déjà `file_max` (3)
     publications TikTok à venir ou plus : la file est pleine, inutile d'en ajouter.
4. Contrôle des sorties précédentes : dans `getScheduledPosts` (7 derniers jours), une publication dont l'heure est
   passée et qui figure encore avec un statut d'erreur ou en attente n'est pas sortie : signale-le en tête du rapport
   (ne la modifie pas toi-même).
5. Numéro de l'épisode : `journal.json → dernier_numero + 1`. L'idée n° 1 est **obligatoirement**
   `journal.json → prochaine_affirmation` (elle a été annoncée à la fin de l'épisode précédent).

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

## 6. Fabrication complète (≈ 15 à 25 min)

Lance-la en arrière-plan, puis surveille le journal toutes les 2 à 3 minutes :
```bash
cd /home/claude/vrai-ou-faux/moteur
setsid nohup python3 fabriquer.py tout ../episodes/NNN-slug/episode.json /tmp/epNNN/sortie \
  > /tmp/epNNN/fabrication.log 2>&1 < /dev/null & disown
tail -5 /tmp/epNNN/fabrication.log
```
- Si le processus a disparu sans ligne « terminé » (la machine peut redémarrer), relance **la même commande** : elle
  reprend aux tronçons déjà faits.
- Code de sortie / statut : `conforme` exigé. Sinon lis `rapport.json`, corrige (3 tentatives maximum), puis
  abandonne proprement si ça échoue encore.
- Regarde `planche.png` (outil Read) une dernière fois.

## 7. Hébergement et programmation

```bash
cd /home/claude/vrai-ou-faux
python3 moteur/publier.py heberger episodes/NNN-slug /tmp/epNNN/sortie/video.mp4   # -> lien direct public
python3 moteur/publier.py legende  episodes/NNN-slug /tmp/epNNN/sortie/rapport.json # -> légende finale
```
- Créneau : `getScheduledPosts` (brand `7381054`, 60 prochains jours, fuseau Europe/Paris) enregistré dans
  `/tmp/epNNN/posts.json`, puis `python3 moteur/publier.py creneau /tmp/epNNN/posts.json` (premier mercredi ou samedi
  libre à au moins 48 h). Affine l'heure avec `getBestTimeToPostByNetwork` (tiktok, ce jour-là) en restant dans
  `fenetre_horaire` ; à défaut, garde 18:00.
- La vidéo est déposée dans la branche `videos` du dépôt (les releases GitHub sont refusées aux sessions Claude) ;
  le lien `https://raw.githubusercontent.com/tanacos/vrai-ou-faux/videos/…mp4` est public. Metricool la télécharge
  et en garde sa propre copie ; la branche est nettoyée aux runs suivants.
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
