# Règles TTFL — référence de l'application

*Validé avec l'utilisateur le 2026-09-26. Source : FAQ officielle (fantasy.trashtalk.co/?tpl=regles), complétée par les décisions ci-dessous pour les cas qu'elle ne couvre pas.*

Ce document est **la spécification des règles** du moteur. Chaque règle `Rn` doit correspondre à une fonction du module de règles et à des tests qui la verrouillent. **Toute modification d'une règle passe d'abord par ce document.**

Légende : **SR** = saison régulière, **PO** = playoffs.

| # | Règle | SR | PO | Source |
|---|---|:-:|:-:|---|
| R1 | **Score TTFL** = PTS + REB + AST + STL + BLK + FGM + 3PM + FTM − TOV − (FGA−FGM) − (3PA−3PM) − (FTA−FTM) | ✓ | ✓ | FAQ |
| R2 | **1 pick max par soirée.** Une date réservée ne peut pas être vidée, seulement remplacée. | ✓ | ✓ | FAQ |
| R3 | **Cooldown** : un joueur pické le jour J redevient disponible à **J+30** (`COOLDOWN_DAYS = 30`). La contrainte vaut **dans les deux sens** autour de chaque pick, réservations futures comprises. | ✓ | – | FAQ + **vérifié sur l'historique 2025-26** : 6 repicks acceptés à exactement 30 jours (Jokić 25/10→24/11, J. Brown, Durant, Cunningham, Maxey, Murray) |
| R4 | **Pick-and-drop** : un joueur pické une fois est perdu pour le reste des PO. | – | ✓ | FAQ |
| R5 | **Équipe éliminée** (play-in compris) : ses joueurs sont perdus pour les PO. Seuls les joueurs des équipes qualifiées sont disponibles. | – | ✓ | FAQ + décision |
| R6 | **Remise à zéro** au 1er match du 1er tour des PO : les picks de SR ne comptent plus pour la disponibilité. | – | ✓ | FAQ |
| R7 | **Joueur qui ne joue pas, ou match reporté/annulé le jour même** : 0 point **et** le lock s'applique quand même (30 j en SR, joueur consommé en PO). Pas de rattrapage si le match est reprogrammé. | ✓ | ✓ | FAQ |
| R8 | **Fermeture du deck** : 00:00 heure de Paris, ou l'heure du **premier match de la soirée** s'il est plus tôt. | ✓ | ✓ | FAQ |
| R9 | **Deck anticipé** : picks réservables jusqu'à 14 jours à l'avance et modifiables jusqu'à la fermeture. Une réservation bloque le joueur comme un pick (R3/R4). L'app suit le deck (statut « réservé »). | ✓ | ✓ | FAQ + décision |
| R10 | **Bonus x2** : 1 par mois, de novembre à avril (le mois se lit sur la date US du match). Perdu s'il n'est pas utilisé dans le mois. Double le score, y compris négatif. Perdu (et 0) si le joueur ne joue pas. Activable jusqu'à la fermeture. | ✓ | – | FAQ |
| R11 | **Soirées éligibles** : saison régulière (**NBA Cup comprise, finale incluse**) et playoffs. **Exclus** : présaison, play-in, All-Star. La date d'une soirée = date US du match. | ✓ | ✓ | Décision |
| R12 | **Play-in** : aucune soirée de pick entre la fin de la SR et le 1er match du 1er tour. | – | – | Décision |
| R13 | **Match fantôme** (G5-G7 d'une série terminée) : ce n'est pas une soirée TTFL. Une soirée sans match éligible n'existe pas (ni pick, ni 0). Une réservation posée sur un match fantôme doit déclencher une **alerte** pour la déplacer avant la fermeture. | – | ✓ | Décision |
| R14 | **Soirée éligible sans pick** = **0 réel** : compte dans le total et dans la moyenne, mais ne bloque aucun joueur. | ✓ | ✓ | Décision |
| R15 | **Bonus Seconde chance** (boutique, 600 TT$, acheté pour 1 semaine) : débloque avant la fin du cooldown un joueur qui a fait **0 pour absence**. Il doit être repické **dans les 7 jours**. Utilisé 2 fois en 2025-26 (Mobley 12/11→21/11, Giannis 08/03→17/03). | ✓ | – | Boutique TTFL |

## Définitions dérivées

- **Moyenne** = total des points / nombre de soirées éligibles écoulées depuis le début de la période (SR ou PO). Les soirées sans pick (R14) y comptent pour 0.
- **Joueur disponible pour la soirée D** :
  - en SR, aucun pick ni aucune réservation du joueur à moins de 30 jours de D, dans un sens ou dans l'autre, **sauf** Seconde chance active (R15) ;
  - en PO, jamais pické ni réservé depuis le début des PO, et équipe toujours qualifiée.
- **Mode de la soirée** (SR ou PO) : déduit du type de match NBA (R11/R12), jamais saisi à la main.

## Hors périmètre

- Bonus d'information de la boutique (Le Populaire, Le Chaud Patate, L'Espion) : aucun effet sur les règles.
- Économie TT$ (gains via succès, achats) : non modélisée. La Seconde chance est saisie à la main quand elle est achetée.

### Jeu en équipe

Classements hebdomadaires, mensuels et par périodes, divisions, brackets d'équipes : l'utilisateur joue en solo, ces règles n'affectent pas le moteur.
