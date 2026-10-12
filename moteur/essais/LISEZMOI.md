# Essais de non-régression du moteur

Deux épisodes **fictifs** (sources factices, jamais publiés) qui couvrent à eux deux les 7 scènes, les 5 panneaux et
des textes proches des longueurs maximales. Après toute modification de `moteur/vf/`, ils doivent rester valides,
tout comme les vrais épisodes :

```bash
cd moteur && ./essais/verifier.sh            # ≈ 4 min ; « tout est valide » attendu
python3 fabriquer.py apercu essais/toutes_scenes_a.json /tmp/essai_a   # puis regarder apercu.png
```
