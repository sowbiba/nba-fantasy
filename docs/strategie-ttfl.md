# Stratégie de recommandation — décisions validées

*Journal des décisions de stratégie prises avec l'utilisateur. Les règles du jeu sont dans [regles-ttfl.md](regles-ttfl.md), et les données qui motivent ces décisions dans [audit-saison-2026-27.md](audit-saison-2026-27.md) §9.*

**Principe directeur** : la cible à battre est la moyenne de **34.0 en SR 2025-26, obtenue sans outil**. En PO 2026, la discipline de save a fait chuter la moyenne (21.1 contre 36.5). Tout mécanisme sophistiqué doit prouver qu'il bat le best-available.

## S1 — Espérance complète (SR) — validé 2026-09-26

Le moteur classe les joueurs sur leur **espérance complète**, pas sur le seul score projeté :

- `P(joue) × projection` pour la soirée ;
- **moins le coût d'un zéro** : si le joueur ne joue pas (R7), il est bloqué pour rien pendant `COOLDOWN_DAYS`. Ce coût = `(1 − P(joue)) × valeur perdue du joueur sur la fenêtre de cooldown`.

**Pourquoi** : les zéros représentent 17 picks sur 162 en SR 2025-26 (~3,6 pts/soirée perdus), la fuite n°1. Plusieurs étaient prévisibles (absences répétées, 2e soir d'un back-to-back). `P(joue)` doit donc intégrer le statut de blessure, le motif DNP récent **et** le back-to-back / *load management*.

## S2 — Anticipation : ventiler les picks sous cooldown (SR) — validé 2026-09-26

**Problème** : jouer ce soir le meilleur joueur « sur le papier » peut coûter un meilleur match du même joueur dans les 30 jours (un match facile à J+20). En SR, personne n'est éliminé : le coût d'un pick est précis, il bloque tous les matchs du joueur sur la fenêtre de cooldown. C'est pour ça que l'anticipation a du sens en SR, contrairement aux saves des PO (qui pariaient sur P(qualif) < 1).

**Conception** :
1. **Optimisation globale sur un horizon glissant de 31 jours** (une fenêtre de cooldown) : un joueur par soirée, total maximisé. Contraintes : R3 (un même joueur au plus une fois par fenêtre de 31 j, picks passés et réservations compris) et R9 (les réservations sont fixées).
2. **Seule la soirée du jour est engagée.** Le plan est recalculé à chaque sync. Les 14 premiers jours forment le brouillon de deck, les jours 15 à 31 ne servent qu'à la décision.
3. **Décote du futur selon son incertitude** : valeur à J+k = projection connue à l'avance (calendrier, domicile/extérieur, défense adverse, back-to-back, base de saison) × P(joueur toujours disponible et dans son rôle à J+k). Sans cette décote, l'optimiseur garde tout pour plus tard, c'est le piège des PO.
4. **Garde-fou** : backtest sur la SR 2025-26 (calendrier et scores réels), plan anticipé contre best-available. Le plan n'est activé que s'il bat le best-available.

## S3 — Bonus x2 intégré au plan (SR) — validé 2026-09-26

Pour chaque mois de novembre à avril, l'optimiseur du plan 31 jours choisit aussi **la soirée où poser le x2**. Il maximise la valeur doublée, pénalisée par le risque, parce que R10 double aussi un score négatif et fait perdre le x2 si le joueur ne joue pas. Le profil visé a un plancher élevé et une P(joue) élevée.

- Le choix du x2 peut influer sur l'affectation (garder une star régulière pour la soirée du x2).
- **Fin de mois** : si le x2 n'est pas encore posé, le moteur le force sur la meilleure option restante du mois, pour ne jamais le perdre.
- Le x2 est une donnée explicite (`is_x2` sur le pick), plus une heuristique.

**Pourquoi** : en 2025-26, 6 x2 sur 6 ont été utilisés, mais à +6 seulement au-dessus de la moyenne, avec un raté à 12.

## S4 — Playoffs : décision robuste par simulation du tableau — validé 2026-09-26

**Tension à gérer** :
- ne pas brûler trop tôt un joueur dont l'équipe peut aller loin ;
- ne pas garder indéfiniment un joueur dont l'équipe a peu de chances d'atteindre les Finales ;
- ne pas arriver en Finales avec seulement des choix de second rang, **quel que soit le finaliste**.

Cela dépend du potentiel de l'équipe (force, état de la série, blessures) et de l'adversité à chaque tour. Le troisième point est une **couverture de risque** qu'une simple espérance ne capture pas.

**Conception** :
1. **Modèle de force des équipes** → P(gagner un match) (force, avantage du terrain, blessures) → avec l'état de la série (Markov), P(atteindre chaque tour).
2. **Simulation du tableau** : quelques centaines de scénarios complets (affiches, nombre de matchs, jusqu'aux Finales).
3. **Décision du soir** : pour chaque candidat, meilleur total restant **dans chaque scénario** s'il est joué ce soir (optimiseur d'affectation avec les règles PO : R4, R5, R13). On retient le candidat au **meilleur total moyen**. Ça pousse à brûler à temps les joueurs d'équipes en danger, à garder ceux des équipes qui vont loin, et à préserver une option forte chez chaque finaliste plausible.
4. **Garde-fou** : rejouer les PO 2026 contre le best-available (36.5 sur les 10 premiers soirs). Activation seulement si c'est meilleur.

**Pas de save tax manuelle** : les réservations forcées en config (`TEAM_SAVE_RANKS`, reservation tax) sont supprimées. La couverture de risque vient du calcul, pas de réglages à la main.

**Commun avec la SR** : moteur de stats, optimiseur d'affectation, espérance complète (S1). **Ce qui diffère** : règles de disponibilité (R3 contre R4/R5) et horizon (31 j avec calendrier connu en SR, reste des PO avec calendrier simulé en PO).

## S5 — Force des équipes : Elo maison — validé 2026-09-26

- **Elo calculé à partir de nos données** (`games.home_score` / `away_score`) : mise à jour après chaque match, pondérée par l'écart de points, avec avantage du terrain.
- **Correction blessures** : la force de l'équipe est réduite de la part de production des joueurs importants absents.
- **Pronostic utilisateur** (`series_forecast`) conservé en ajustement manuel optionnel.
- **Usages** :
  - PO : P(gagner un match) → simulations du tableau (S4) ;
  - SR : l'écart de force attendu devient un facteur de projection (risque de large victoire → titulaires moins utilisés au 4e quart-temps).
- Validé par backtest sur 2025-26 : Elo contre résultats réels.

## S6 — Démarrage de saison et changements d'effectif — validé 2026-09-26

**Point de départ = saison précédente, fondu progressivement** : la projection d'un joueur part de ses stats 2025-26. Le poids de la saison en cours croît à chaque match joué, jusqu'à la remplacer entièrement (~15 matchs). Les rookies partent d'un prior bas avec une forte incertitude.

**Changements d'effectif (transferts, recrues, départs)** :
1. **Rôle du joueur** : l'efficacité (TTFL/min) de la saison précédente suit le joueur. Les **minutes attendues** sont recalculées dans l'effectif actuel (240 min par équipe réparties au prorata des minutes passées). Une équipe encombrée fait baisser tout le monde, le départ d'une star fait monter les autres. Même logique, plus prudente, pour l'usage.
2. **Elo d'intersaison** : régression d'environ 1/3 vers la moyenne, puis correction par le **solde de production** (arrivées − départs). Facteur K plus élevé sur les premiers matchs pour s'ajuster vite.
3. **Défense adverse** : profil de la saison précédente rapproché de la moyenne, d'autant plus que l'effectif a changé, puis recalculé rapidement sur la nouvelle saison.

**Prérequis de données** : `game_logs` doit porter l'**équipe du joueur au moment du match**. Backfill de l'historique via le match (`is_home` → `home_team` / `away_team`). Ça corrige aussi le bug d'attribution de `compute_team_defense` (audit §2).

## P1 — Écrans de l'app — validé 2026-09-26

1. **Ce soir** : pick conseillé avec son espérance complète (projection, P(joue), « pourquoi ce soir plutôt qu'à son meilleur soir du mois »), **heure de fermeture** du deck (R8), alerte « pose ton x2 ce soir », alternatives avec leur date de retour de cooldown.
2. **Deck 14 jours** : brouillon du plan à côté des réservations réelles. On valide un soir (→ réservation dans l'app, recopiée à la main sur trashtalk.co), on remplace un joueur jusqu'à la fermeture. Alertes : réservation sur un joueur passé « Out », ou (PO) sur un match fantôme.
3. **Joueur** : disponibilité (« dispo le JJ/MM »), ses meilleurs soirs dans les 31 prochains jours, ses stats.
4. **Picks** (écran conservé) : historique, moyenne sur toutes les soirées éligibles (sans pick = 0), x2 utilisés, zéros subis.
5. **Blessés** (écran conservé).
6. **Affichage des matchups** (conservé) : données défenseur contre joueur, ramenées à la saison en cours (ou à la série en PO) au lieu du cumul toutes saisons.
7. **PO uniquement** : probabilités d'aller au bout par équipe, « tes cartes par finaliste possible ». Séries et pronostics masqués en SR.
8. **Rappel avant fermeture** si aucun pick n'est validé pour la soirée.

L'app n'écrit jamais sur trashtalk.co : le pick y est toujours recopié à la main.

## P2 — Canal du rappel : push PWA, fallback Telegram — validé 2026-09-26

- **Web Push de la PWA** (iPhone 15 : iOS ≥ 16.4 requis). **Conditions iOS** : app ajoutée à l'écran d'accueil depuis Safari, manifest `display: standalone`, service worker, et demande de permission déclenchée **par un tap de l'utilisateur dans l'app installée** (jamais au chargement).
- **Fallback Telegram** si le push iOS ne fonctionne pas après un essai. Le module d'envoi doit donc avoir une interface commune aux deux canaux.
- **Timing** : rappel **2 h avant la fermeture**, relance **30 min avant** si aucun pick n'est validé. Fermeture = R8 (minuit Paris, ou 1er match si plus tôt). Nécessite un déclencheur horaire précis (le sync 4×/jour ne suffit pas), à traiter dans l'architecture.
