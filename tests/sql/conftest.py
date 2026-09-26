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


def apply_migrations(conn) -> None:
    for path in MIGRATIONS:
        conn.execute(path.read_text())


@pytest.fixture(scope="session")
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL non défini (voir docs/operations.md, « Tests SQL »)")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade; create schema public;")
        conn.execute((SQL_DIR / "schema.sql").read_text())
        apply_migrations(conn)
        yield conn
