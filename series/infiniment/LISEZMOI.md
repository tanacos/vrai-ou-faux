# INFINIMENT — de l'infiniment petit à l'infiniment grand

Série TikTok narrée (voix ElevenLabs), format reportage : une question qui intrigue, une descente ou une montée dans
les échelles, une révélation chiffrée et sourcée, une chute, l'annonce du prochain épisode. 80 à 95 s.

## La promesse

Un seul fait étonnant par épisode, démontré pas à pas, avec des chiffres qu'on peut vérifier (sources en
description). On montre l'échelle à chaque instant : la **règle des puissances de dix** en haut de l'écran est la
signature visuelle de la série (curseur de 10⁻¹⁵ m à 10²⁶ m).

## Structure d'un épisode (blocs de narration = scènes)

1. **Accroche** (≤ 3 s avant la première image forte) : la conclusion paradoxale, au conditionnel si c'est une
   expérience de pensée (« Toute l'humanité… pourrait tenir dans un morceau de sucre »).
2. **Voyage d'échelle** : on descend (ou on monte) par paliers concrets, un mot = un palier = une image.
3. **Première surprise**, puis **la comparaison qui fait image** (stade / moustique).
4. **Le chiffre clé** en très grand, avec sa source.
5. **L'expérience** : le raisonnement en 3 ou 4 étapes, le calcul affiché (≈, ≤ : jamais de fausse précision).
6. **La preuve que ça existe** (objet réel), puis **le retournement** (« Mais alors, pourquoi… ? »).
7. **Prochain épisode** dans l'autre sens d'échelle + « Les sources sont en description ».

## Ton

Tutoiement, phrases courtes, verbes d'action, une seule idée par phrase. Balises eleven_v4 avec parcimonie
(`[curious]` à l'ouverture, `[dramatically]` pour la révélation, `[pause]` avant la chute). Pas d'emphase qui
dépasse les sources : leçons de la contre-vérification de l'épisode 1 :
- pas de « la physique est formelle » pour un ordre de grandeur : « un vrai calcul de physique » ;
- conditionnel pour une expérience de pensée ; « environ », « au moins », « presque » quand la source le dit ;
- pas de formule choc qui contredit ce qu'on vient d'expliquer (« tu n'as jamais touché ta chaise ») ;
- citer la NASA mot pour mot : « matière d'étoile à neutrons », « pèserait environ ».

## Rigueur (comme la série « Vrai ou faux ? »)

- Chaque nombre dit ou affiché figure dans l'extrait d'une source (`episode.json` → `sources`), au moins deux éditeurs
  différents pour le fait central, calcul écrit dans `calcul`.
- Contre-vérification par un agent indépendant avant publication : zéro écart exigé (voir `verification` dans
  `ep01/episode.json`).
- Une phrase fausse dans une prise déjà générée se retire sans régénérer (`voix.retraits`) ; une phrase à reformuler
  impose une nouvelle prise (`narration_vN.txt`).

## Fabrication

```bash
python3 series/infiniment/fabriquer.py voix   series/infiniment/epNN   # chronologie calée sur la voix
python3 series/infiniment/fabriquer.py apercu series/infiniment/epNN   # planche + audit des zones sûres
python3 series/infiniment/fabriquer.py tout   series/infiniment/epNN   # vidéo + 15 contrôles (≈ 20 min)
```
Voix : voir `moteur/VOIX.md` (génération ElevenLabs, relais GitHub, horodatage). Chaque épisode a son `rendu.py`
(scènes) et son `son.py` (musique et bruitages), pilotés par les repères « bloc:mot » de `chrono.json`.

## Pistes d'épisodes (à vérifier avant écriture)

- Ép. 2 (annoncé) : le bord de l'univers observable.
- Combien d'atomes dans un verre d'eau, comparé au nombre de verres d'eau dans les océans ?
- Si le Soleil était une bille, où serait l'étoile la plus proche ?
- Un neutrino peut-il traverser la Terre sans rien toucher ?
- La lumière que tu vois du Soleil est-elle « en retard » ?
- Un virus, une bactérie, une cellule : la même descente d'échelle qu'à l'épisode 1, en biologie.

## Licence de la voix

Prises générées avec l'offre gratuite d'ElevenLabs : usage non commercial, « elevenlabs.io » dans le titre. Pour un
compte rémunéré : abonnement payant et **nouvelle prise** (voir `moteur/VOIX.md`).
