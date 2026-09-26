import psycopg
import pytest


def test_reminders_sent_unique(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into reminders_sent (night, kind, key) values ('2026-10-21', 'no_pick_2h', '')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            with pg.transaction():
                pg.execute("insert into reminders_sent (night, kind, key) values ('2026-10-21', 'no_pick_2h', '')")


def test_push_subscriptions_endpoint_unique(pg):
    with pg.transaction(force_rollback=True):
        pg.execute("insert into push_subscriptions (endpoint, p256dh, auth) values ('https://x/1', 'k', 'a')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            with pg.transaction():
                pg.execute("insert into push_subscriptions (endpoint, p256dh, auth) values ('https://x/1', 'k', 'a')")


def test_rls_sans_policy(pg):
    rows = pg.execute(
        "select tablename from pg_policies where tablename in ('push_subscriptions', 'reminders_sent')"
    ).fetchall()
    assert rows == []
    enabled = pg.execute(
        "select relname, relrowsecurity from pg_class where relname in ('push_subscriptions', 'reminders_sent') order by relname"
    ).fetchall()
    assert enabled == [("push_subscriptions", True), ("reminders_sent", True)]
