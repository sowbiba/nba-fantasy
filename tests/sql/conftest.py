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


def ensure_supabase_roles(conn) -> None:
    """Les migrations révoquent/accordent des privilèges aux rôles Supabase
    (anon, authenticated, service_role) qui n'existent pas dans une Postgres
    jetable. Créés en NOLOGIN pour que les revoke/grant s'appliquent sans
    changer la migration elle-même (qui doit rester inchangée en prod).

    `service_role` reçoit en plus BYPASSRLS : c'est ce qui, en prod Supabase,
    fait que la clé service du backend Python outrepasse les policies RLS
    (schema.sql le documente : « Python backend uses service role key which
    bypasses RLS by default »). Sans cet attribut ici, un test « service_role
    lit tout » échouerait dès qu'une table n'a plus aucune policy anon."""
    for role in ("anon", "authenticated", "service_role"):
        conn.execute(
            "do $$ begin "
            f"if not exists (select 1 from pg_roles where rolname = '{role}') then "
            f"create role {role} nologin; "
            "end if; end $$;"
        )
    conn.execute("alter role service_role bypassrls;")


def grant_supabase_privileges(conn) -> None:
    """Réplique les GRANTs que Supabase pose une fois par projet (hors des
    fichiers de migration versionnés, donc absents d'ici) : lecture de toutes
    les tables/vues publiques pour anon et authenticated, tout pour
    service_role. Une policy RLS ne suffit pas : sans ce GRANT au niveau
    table, `set local role anon` échouerait sur « permission denied » quelle
    que soit la policy — ce qui masquerait un bug de policy plutôt que de le
    révéler dans les tests `set local role anon`."""
    conn.execute("grant usage on schema public to anon, authenticated, service_role;")
    conn.execute("grant select on all tables in schema public to anon, authenticated, service_role;")
    conn.execute("grant insert, update, delete on all tables in schema public to service_role;")
    conn.execute("grant usage, select on all sequences in schema public to anon, authenticated, service_role;")


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
        ensure_supabase_roles(conn)
        conn.execute((SQL_DIR / "schema.sql").read_text())
        apply_migrations(conn)
        grant_supabase_privileges(conn)
        yield conn
