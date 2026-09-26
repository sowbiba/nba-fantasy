from tests.sql.conftest import apply_migrations


def test_migrations_rejouables(pg):
    # Une base déjà à jour doit accepter un second passage complet sans erreur.
    apply_migrations(pg)
