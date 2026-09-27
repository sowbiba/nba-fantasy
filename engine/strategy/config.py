"""Configuration de la stratégie régulière (activation L2b, spec §7)."""
from typing import Literal

# Règle d'activation spec §7 : passer à "plan" seulement si le backtest L2b
# le justifie et que l'utilisateur l'a validé.
TONIGHT_SOURCE: Literal["best_available", "plan"] = "best_available"

# Facteur « écart de force » (spec L3a §2) : règle d'activation §7 — passer
# à True seulement s'il bat les projections actuelles au backtest L2
# (« best_available + écart de force » > « best_available ») dans LES DEUX
# modes de blessures (none, dnp_oracle), et avec l'accord de l'utilisateur.
BLOWOUT_ENABLED: bool = False
