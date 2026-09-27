"""Configuration de la stratégie régulière (activation L2b, spec §7)."""
from typing import Literal

# Règle d'activation spec §7 : passer à "plan" seulement si le backtest L2b
# le justifie et que l'utilisateur l'a validé.
TONIGHT_SOURCE: Literal["best_available", "plan"] = "best_available"
