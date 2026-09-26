"""Postgres jetable pour tester le SQL des migrations.

La base est reconstruite de zéro (schema.sql puis chaque migration dans
l'ordre des fichiers), exactement comme le décrit l'en-tête de schema.sql.
Ignoré si TEST_DATABASE_URL n'est pas défini.
"""
import os
import pathlib

import pytest

psycopg = pytest.importorskip("psycopg")

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "supabase"
MIGRATIONS = sorted((SQL_DIR / "migrations").glob("*.sql"))

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _assert_local(url: str) -> None:
    """La fixture pg droppe le schéma public : ne jamais la laisser pointer
    ailleurs qu'une Postgres locale jetable."""
    host = psycopg.conninfo.conninfo_to_dict(url).get("host")
    if host not in _LOCAL_HOSTS:
        pytest.fail(
            f"TEST_DATABASE_URL pointe vers un host non local ({host!r}) : "
            "refus de dropper le schéma public. Utilise une Postgres locale "
            "jetable (localhost/127.0.0.1/::1)."
        )


def apply_migrations(conn) -> None:
    for path in MIGRATIONS:
        conn.execute(path.read_text())


@pytest.fixture(scope="session")
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL non défini (voir docs/operations.md, « Tests SQL »)")
    _assert_local(url)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade; create schema public;")
        conn.execute((SQL_DIR / "schema.sql").read_text())
        apply_migrations(conn)
        yield conn
