import pytest

from engine.strategy.value import discount, future_value, lock_value, tonight_value


def test_discount():
    assert discount(0) == 1.0
    assert discount(10) == pytest.approx(0.985 ** 10)


def test_lock_value_meilleur_futur_decote_dans_la_fenetre():
    future = [(3, 40.0), (20, 60.0), (30, 90.0), (0, 99.0)]
    assert lock_value(future) == pytest.approx(max(0.985 ** 3 * 40, 0.985 ** 20 * 60))


def test_lock_value_sans_futur():
    assert lock_value([]) == 0.0


def test_tonight_value_exemple_s1():
    # Star à 60 % de jouer (50 projetés) contre joueur fiable (98 %, 40) :
    # le zéro possible gaspille aussi son blocage de 30 jours.
    star = tonight_value(0.6, 50.0, lock=45.0)
    fiable = tonight_value(0.98, 40.0, lock=30.0)
    assert star == pytest.approx(30.0 - 18.0)
    assert fiable == pytest.approx(39.2 - 0.6)
    assert fiable > star


def test_future_value():
    assert future_value(10, 0.9, 50.0) == pytest.approx(0.985 ** 10 * 45.0)
