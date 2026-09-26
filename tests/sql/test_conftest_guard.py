"""Garde-fou : la fixture pg ne doit jamais dropper le schéma public d'une
base autre qu'une Postgres locale jetable. Ce test ne se connecte à rien."""
import pytest

from tests.sql.conftest import _assert_local


def test_assert_local_refuse_un_host_distant():
    with pytest.raises(pytest.fail.Exception):
        _assert_local("postgresql://user:pw@db.abcxyz.supabase.co:5432/postgres")


def test_assert_local_accepte_localhost():
    _assert_local("postgresql://postgres:pg@localhost:55432/postgres")


def test_assert_local_accepte_127_0_0_1():
    _assert_local("postgresql://postgres:pg@127.0.0.1:55432/postgres")


def test_assert_local_accepte_ipv6_loopback():
    _assert_local("postgresql://postgres:pg@[::1]:55432/postgres")
