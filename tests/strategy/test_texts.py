from datetime import date

from engine.explain.texts import challenge_explanation, describe_night, plan_explanation, reco_texts, tier
from engine.stats.projection import GameContext
from engine.strategy.planner import Cell
from engine.strategy.regular import Recommendation


def _cell(night, is_home=True, rest=1, opp=1.1, p=0.98):
    return Cell(1, night, 50.0, p, 48.0, GameContext("WAS", is_home, rest, opp))


def test_tier():
    assert [tier(r) for r in (1, 10, 11, 25, 26)] == ["elite", "elite", "solid", "solid", "filler"]


def test_reco_texts_domicile_et_blocage():
    rec = Recommendation(_cell(date(2026, 11, 2)), 40.0, date(2026, 12, 2), _cell(date(2026, 11, 20), is_home=False))
    pros, cons, verdict, tags = reco_texts(rec, 1, "Nikola Jokic")
    assert any("domicile" in p for p in pros)
    assert any("02/12" in c for c in cons)
    assert "Jokic" in verdict
    assert "home" in tags and "reco_du_soir" in tags


def test_reco_texts_risques():
    rec = Recommendation(_cell(date(2026, 11, 2), rest=0, opp=0.9, p=0.55), 0.0, date(2026, 12, 2), None)
    pros, cons, _, tags = reco_texts(rec, 30, "X")
    assert any("back-to-back" in c for c in cons)
    assert any("55 %" in c for c in cons)
    assert "b2b" in tags and "dnp_risk" in tags


def test_describe_et_plan_explanation():
    c = _cell(date(2026, 11, 20), is_home=False)
    assert describe_night(c) == "vendredi 20/11 @ WAS"
    assert "50" in plan_explanation(c)


def test_reco_texts_tag_mon_pick():
    base = (_cell(date(2026, 11, 2)), 40.0, date(2026, 12, 2), None)
    assert "mon_pick" in reco_texts(Recommendation(*base, is_pick=True), 1, "X")[3]
    assert "mon_pick" not in reco_texts(Recommendation(*base), 1, "X")[3]


def test_reco_texts_joueur_reserve_plus_tard():
    rec = Recommendation(_cell(date(2026, 11, 2)), 40.0, date(2026, 12, 2), None, reserved_on=date(2026, 11, 24))
    _, cons, _, tags = reco_texts(rec, 5, "X")
    assert any("Réservé le 24/11" in c for c in cons)
    assert "reserve" in tags


def test_challenge_explanation():
    better = _cell(date(2026, 11, 20), p=1.0)                                       # 50 pts attendus
    reserved = Cell(2, date(2026, 11, 20), 40.0, 0.9, 30.0, GameContext("WAS", True, 1, 1.0))   # 36 attendus
    assert "+14 pts attendus par rapport à Y" in challenge_explanation(better, reserved, "Y")
    out = Cell(2, date(2026, 11, 20), 40.0, 0.0, 0.0, GameContext("WAS", True, 1, 1.0))
    assert "Y ne devrait pas jouer" in challenge_explanation(better, out, "Y")
    assert "Y n'a pas de match" in challenge_explanation(better, None, "Y")
