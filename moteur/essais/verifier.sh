#!/bin/sh
# Valide (audit image par image compris) les épisodes d'essai et tous les vrais épisodes du dépôt.
cd "$(dirname "$0")/.." || exit 1
ko=0
for f in essais/toutes_scenes_*.json ../episodes/*/episode.json; do
  if python3 fabriquer.py valider "$f" > /tmp/verif_$$.log 2>&1; then echo "OK      $f"; else echo "ERREUR  $f"; grep ERREUR /tmp/verif_$$.log; ko=1; fi
done
rm -f /tmp/verif_$$.log
[ $ko -eq 0 ] && echo "tout est valide"
exit $ko
