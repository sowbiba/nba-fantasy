"""Accès à l'environnement, lu au moment de l'appel (jamais à l'import)."""
import os

from dotenv import load_dotenv


def env(name: str) -> str:
    load_dotenv()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"variable d'environnement manquante : {name}")
    return value
