# Lot L3a — Elo des équipes, écart de force, affichage connecté — complément de spec

Date : 2026-09-28. Complète `2026-09-26-moteur-sr-po-design.md` (S5 dans `docs/strategie-ttfl.md`). L3 est découpé : **L3a** (ce document, livré tout de suite) = Elo + correction blessures + facteur « écart de force » en saison régulière + affichage ; **L3b** (d'ici mi-mars) = tableau des séries, simulation du tableau (S4), décision PO, backtest PO, écran PO.

## 1. Elo maison (S5)

- Calculé match par match sur tous les matchs `regular`, `cup_final` et `playoffs` terminés avec scores, dans l'ordre chronologique : note de départ 1500 ; probabilité de victoire `1 / (1 + 10^(−(Rdom + HCA − Rext)/400))` ; mise à jour `K × multiplicateur d'écart × (résultat − probabilité)` avec multiplicateur d'écart de type FiveThirtyEight `((|écart| + 3)^0.8) / (7.5 + 0.006 × écart d'Elo du vainqueur)` ; entre deux saisons, retour partiel vers la moyenne (`R ← 0.75 R + 0.25 × 1505`).
- Écart de points attendu = `(Rdom + HCA − Rext) / 28`.
- Paramètres (K, HCA) choisis sur 2025-26 par la perte logarithmique des prédictions, en ne connaissant que les matchs antérieurs ; rapport consigné.
- **Correction blessures (SR et PO)** : la note d'une équipe pour un match est réduite de `ELO_PER_SHARE × part des absents`, où la part d'un joueur = sa part de la production de l'équipe (minutes × TTFL/min, moyenne récente) ; absents = statuts `Out`/`Doubtful`/`Out For Season`/`Suspended` le soir même (en prod) ; pour la calibration sur 2025-26, absents = joueurs de rotation sans minutes ce soir-là (les rapports de blessures existaient avant le match). `ELO_PER_SHARE` calibré sur 2025-26 ; activé seulement s'il améliore la perte logarithmique.

## 2. Facteur « écart de force » dans la projection (SR)

- Calibré sur les logs (saison courante + précédente, avant la date de décision) : variation des minutes par rapport à la moyenne du joueur selon l'écart de points final, séparément pour les titulaires (≥ 28 min de moyenne) et les autres ; appliqué avec l'écart **attendu** (Elo corrigé) : `facteur = 1 − a × max(0, |écart attendu| − t)` pour les titulaires, symétrique à la hausse bornée pour les remplaçants.
- Drapeau `BLOWOUT_ENABLED` (défaut `False`) : activé seulement s'il bat les projections actuelles au backtest L2 dans les deux modes de blessures (règle d'activation §7), avec l'accord de l'utilisateur.

## 3. Stockage et affichage

- Tables `team_elo(team, rating, games, updated_at)` et `game_predictions(game_id, home_win_prob, expected_margin, home_rating, away_rating, updated_at)` écrites par `daily_sync` ; **RLS sans lecture publique** (données du mode connecté).
- Mode connecté uniquement : colonne « Force » (Elo) dans l'onglet Classement, pour les 30 équipes, à tout moment ; chances de victoire des deux équipes pour chaque match de Ce soir. Lecture côté serveur via `ownerDb()` ; le test anti-fuite couvre les deux tables. Mode public inchangé.

## 4. Hors périmètre (L3b)

Séries 2026-27, simulation du tableau, décision PO, écran PO, backtest PO, pronostic manuel `series_forecast`.
