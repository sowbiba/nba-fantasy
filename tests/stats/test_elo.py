import random
from datetime import date

import pytest

from engine.stats.elo import (
    EloParams,
    GamePrediction,
    adjusted,
    expected_margin,
    mov_multiplier,
    predict,
    ratings_before,
    team_shares,
    win_prob,
)
from engine.stats.profile import GameLog

NO_HCA = EloParams(home_advantage=0.0)


def _game(gid, d, home, away, home_score=100, away_score=90, status="final",
         game_type="regular", season="2026-27"):
    return {
        "id": gid, "date": d, "home_team": home, "away_team": away,
        "status": status, "home_score": home_score, "away_score": away_score,
        "game_type": game_type, "season": season,
    }


def _log(pid, gid, d, team, minutes, ttfl, is_home=True, season="2026-27"):
    return GameLog(pid, gid, d, season, team, minutes, ttfl, is_home)


# --- win_prob / expected_margin ---------------------------------------

def test_win_prob_0_5_a_notes_egales_sans_avantage():
    assert win_prob(1500, 1500, NO_HCA) == pytest.approx(0.5)


def test_win_prob_avantage_du_terrain():
    p = EloParams(home_advantage=70.0)
    assert win_prob(1500, 1500, p) > 0.5


def test_expected_margin_nul_a_notes_egales_sans_avantage():
    assert expected_margin(1500, 1500, NO_HCA) == pytest.approx(0.0)


# --- mov_multiplier -----------------------------------------------------

def test_mov_multiplier_croit_avec_l_ecart():
    small = mov_multiplier(2, 0.0)
    big = mov_multiplier(20, 0.0)
    assert big > small


def test_mov_multiplier_plus_grand_quand_l_outsider_gagne():
    favorite_wins = mov_multiplier(10, 100.0)
    underdog_wins = mov_multiplier(10, -100.0)
    assert underdog_wins > favorite_wins


# --- ratings_before -----------------------------------------------------

def test_ratings_before_mise_a_jour_a_somme_nulle():
    games = [_game("g1", date(2026, 11, 1), "DEN", "LAL")]
    p = EloParams()
    before = ratings_before([], date(2026, 11, 1), p)
    after = ratings_before(games, date(2026, 11, 2), p)
    delta_home = after["DEN"] - before.get("DEN", 1500.0)
    delta_away = after["LAL"] - before.get("LAL", 1500.0)
    assert delta_home + delta_away == pytest.approx(0.0)
    assert delta_home > 0  # domicile gagnant


def test_ratings_before_ignore_les_matchs_du_jour_meme_et_apres():
    games = [
        _game("g1", date(2026, 11, 1), "DEN", "LAL"),
        _game("g2", date(2026, 11, 2), "BOS", "MIA"),
    ]
    p = EloParams()
    ratings = ratings_before(games, date(2026, 11, 2), p)
    assert "BOS" not in ratings and "MIA" not in ratings
    assert "DEN" in ratings and "LAL" in ratings


def test_ratings_before_ignore_les_matchs_sans_score():
    games = [_game("g1", date(2026, 11, 1), "DEN", "LAL", home_score=None, away_score=None)]
    p = EloParams()
    ratings = ratings_before(games, date(2026, 11, 2), p)
    assert ratings == {}


def test_ratings_before_ignore_la_presaison():
    games = [_game("g1", date(2026, 10, 5), "DEN", "LAL", game_type="preseason")]
    p = EloParams()
    ratings = ratings_before(games, date(2026, 10, 6), p)
    assert ratings == {}


def test_ratings_before_ordre_des_matchs_du_meme_jour_sans_effet():
    g1 = _game("g1", date(2026, 11, 1), "DEN", "LAL")
    g2 = _game("g2", date(2026, 11, 1), "BOS", "MIA")
    p = EloParams()
    a = ratings_before([g1, g2], date(2026, 11, 2), p)
    b = ratings_before([g2, g1], date(2026, 11, 2), p)
    assert a == b


def test_ratings_before_retour_vers_la_moyenne_au_changement_de_saison():
    p = EloParams(carryover=0.75, mean=1505.0)
    games_2526 = [_game("g1", date(2026, 1, 1), "DEN", "LAL", season="2025-26")]
    end_of_2526 = ratings_before(games_2526, date(2026, 1, 2), p)
    rating_2526 = end_of_2526["DEN"]

    games_next = games_2526 + [
        _game("g2", date(2026, 11, 1), "DEN", "BOS", season="2026-27"),
    ]
    ratings_2627 = ratings_before(games_next, date(2026, 11, 2), p)
    expected_before_g2 = p.carryover * rating_2526 + (1 - p.carryover) * p.mean
    # BOS n'a jamais été vue avant g2 : pas de régression pour elle, valeur
    # par défaut 1500 comme dans ratings_before.
    delta_home = ratings_2627["DEN"] - expected_before_g2
    delta_away = ratings_2627["BOS"] - 1500.0
    assert delta_home + delta_away == pytest.approx(0.0)
    assert ratings_2627["DEN"] != rating_2526  # a bien été régressée puis remise à jour


def test_ratings_before_regresse_avant_le_premier_match_de_la_saison_suivante():
    """Soir d'ouverture 2026-27 : aucun match 2026-27 encore joué, mais
    `before` est déjà dans la nouvelle saison. Les notes 2025-26 doivent
    être régressées même si la boucle n'a vu passer aucun changement de
    saison (Review Focus #2)."""
    p = EloParams(carryover=0.75, mean=1505.0)
    games_2526 = [_game("g1", date(2026, 1, 1), "DEN", "LAL", season="2025-26")]
    end_of_2526 = ratings_before(games_2526, date(2026, 1, 2), p)

    opening_night = ratings_before(games_2526, date(2026, 10, 21), p)
    for team, rating in end_of_2526.items():
        assert opening_night[team] == pytest.approx(p.carryover * rating + (1 - p.carryover) * p.mean)


def test_ratings_before_ordre_insensible_sur_plusieurs_jours_avec_equipes_partagees():
    games = [
        _game("g1", date(2026, 11, 1), "DEN", "LAL"),
        _game("g2", date(2026, 11, 3), "LAL", "BOS"),
        _game("g3", date(2026, 11, 5), "BOS", "DEN"),
        _game("g4", date(2026, 11, 7), "DEN", "MIA"),
        _game("g5", date(2026, 11, 7), "LAL", "PHX"),
        _game("g6", date(2026, 11, 9), "MIA", "BOS"),
    ]
    p = EloParams()
    reference = ratings_before(games, date(2026, 11, 10), p)
    shuffled = list(games)
    random.shuffle(shuffled)
    result = ratings_before(shuffled, date(2026, 11, 10), p)
    assert result == pytest.approx(reference)


def test_ratings_before_equipe_sans_match_recent_reste_a_1500():
    games = [_game("g1", date(2026, 11, 1), "DEN", "LAL")]
    p = EloParams()
    ratings = ratings_before(games, date(2026, 11, 2), p)
    assert "PHX" not in ratings  # jamais vue : absente, valeur par défaut gérée par l'appelant (predict)


# --- team_shares ----------------------------------------------------------

def test_team_shares_somme_a_1():
    logs = [
        _log(1, "g1", date(2026, 11, 1), "DEN", 30, 40),
        _log(2, "g1", date(2026, 11, 1), "DEN", 20, 20),
        _log(1, "g2", date(2026, 11, 3), "DEN", 30, 40),
        _log(2, "g2", date(2026, 11, 3), "DEN", 20, 20),
    ]
    shares = team_shares(logs, "DEN", date(2026, 11, 5))
    assert sum(shares.values()) == pytest.approx(1.0)
    assert shares[1] == pytest.approx(2 / 3)
    assert shares[2] == pytest.approx(1 / 3)


def test_team_shares_vide_sans_logs():
    assert team_shares([], "DEN", date(2026, 11, 5)) == {}


def test_team_shares_vide_si_production_totale_non_positive():
    logs = [_log(1, "g1", date(2026, 11, 1), "DEN", 10, -5)]
    assert team_shares(logs, "DEN", date(2026, 11, 5)) == {}


def test_team_shares_ignore_les_matchs_du_jour_meme_et_apres():
    logs = [
        _log(1, "g1", date(2026, 11, 1), "DEN", 30, 40),
        _log(1, "g2", date(2026, 11, 5), "DEN", 30, 40),  # jour même : ignoré
    ]
    shares = team_shares(logs, "DEN", date(2026, 11, 5))
    assert shares == {1: 1.0}


def test_team_shares_limite_a_la_fenetre():
    logs = []
    for i in range(20):
        logs.append(_log(1, f"g{i}", date(2026, 10, 1 + i), "DEN", 30, 10))
    logs.append(_log(2, "g20", date(2026, 10, 21), "DEN", 30, 100))
    shares = team_shares(logs, "DEN", date(2026, 10, 22), window=15)
    # Fenêtre = les 15 derniers matchs d'équipe (g6..g20) : joueur 1 dans g6..g19
    # (14 matchs, 10 pts), joueur 2 dans g20 seulement (100 pts) ; g0..g5 hors fenêtre.
    assert len(shares) == 2
    assert shares[1] == pytest.approx(140 / 240)
    assert shares[2] == pytest.approx(100 / 240)


# --- adjusted ---------------------------------------------------------

def test_adjusted_baisse_la_note():
    p = EloParams(elo_per_share=200.0)
    assert adjusted(1500.0, 0.3, p) == pytest.approx(1500.0 - 200.0 * 0.3)


def test_adjusted_sans_absent_inchange():
    p = EloParams(elo_per_share=200.0)
    assert adjusted(1500.0, 0.0, p) == pytest.approx(1500.0)


# --- predict -----------------------------------------------------------

def test_predict_coherent_avec_correction_blessures():
    p = EloParams(elo_per_share=200.0, home_advantage=70.0, points_per_elo=1 / 28)
    game = _game("g1", date(2026, 11, 10), "DEN", "LAL")
    ratings = {"DEN": 1550.0, "LAL": 1500.0}
    absent_share = {"DEN": 0.2, "LAL": 0.0}

    result = predict(game, ratings, absent_share, p)

    adj_home = 1550.0 - 200.0 * 0.2
    adj_away = 1500.0
    expected = (adj_home + 70.0 - adj_away) * (1 / 28)

    assert isinstance(result, GamePrediction)
    assert result.game_id == "g1"
    assert result.home_rating == 1550.0
    assert result.away_rating == 1500.0
    assert result.expected_margin == pytest.approx(expected)
    assert result.home_win_prob == pytest.approx(win_prob(adj_home, adj_away, p))


def test_predict_equipe_inconnue_note_par_defaut_1500():
    p = EloParams()
    game = _game("g1", date(2026, 11, 10), "DEN", "LAL")
    result = predict(game, {}, {}, p)
    assert result.home_rating == 1500.0
    assert result.away_rating == 1500.0
    assert result.home_win_prob == pytest.approx(win_prob(1500.0, 1500.0, p))
