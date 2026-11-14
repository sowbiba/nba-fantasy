from engine.stats.availability_prob import dnp_risk_factor


def _logs(*minutes):
    """Build gamelog dicts ordered most-recent-first, like db.get_player_game_logs."""
    return [{"minutes": m} for m in minutes]


def test_no_logs_returns_one():
    assert dnp_risk_factor([]) == 1.0


def test_clean_three_games_returns_one():
    assert dnp_risk_factor(_logs(32, 28, 30)) == 1.0


def test_three_consecutive_dnp_strongest_penalty():
    assert dnp_risk_factor(_logs(0, 0, 0)) == 0.30


def test_two_of_three_dnp_mid_penalty():
    assert dnp_risk_factor(_logs(0, 0, 25)) == 0.55
    assert dnp_risk_factor(_logs(0, 25, 0)) == 0.55
    assert dnp_risk_factor(_logs(25, 0, 0)) == 0.55


def test_only_most_recent_dnp_is_higher_alert_than_older():
    """Missing the last game is a stronger signal than an older 0-min outing."""
    most_recent = dnp_risk_factor(_logs(0, 28, 30))
    older = dnp_risk_factor(_logs(28, 0, 30))
    assert most_recent == 0.75
    assert older == 0.90
    assert most_recent < older


def test_partial_history_all_dnp_flags():
    """Two-game history both DNP — flag even without 3 logs."""
    assert dnp_risk_factor(_logs(0, 0)) == 0.55
    assert dnp_risk_factor(_logs(0)) == 0.55


def test_partial_history_clean_does_not_flag():
    assert dnp_risk_factor(_logs(28, 30)) == 1.0
    assert dnp_risk_factor(_logs(28)) == 1.0


def test_handles_none_minutes_as_dnp():
    """A log row with minutes=None should count as DNP, not crash."""
    assert dnp_risk_factor([{"minutes": None}, {"minutes": None}, {"minutes": None}]) == 0.30


def test_ignores_logs_beyond_window():
    """Only the 3 most recent logs matter."""
    assert dnp_risk_factor(_logs(28, 30, 32, 0, 0, 0)) == 1.0


from engine.stats.availability_prob import future_p_play, p_play, play_probability


def test_play_probability_statuts():
    assert play_probability(None) == 1.0
    assert play_probability("Questionable") == 0.55
    assert play_probability("Out") == 0.0
    assert play_probability("Statut inconnu") == 1.0


def test_p_play_combine_statut_dnp_et_back_to_back():
    logs = [{"minutes": 34}, {"minutes": 33}, {"minutes": 35}]
    assert p_play(injury_status=None, recent_logs=logs, is_b2b_second=False, exp_minutes=34) == 1.0
    assert p_play(injury_status="Questionable", recent_logs=logs, is_b2b_second=True, exp_minutes=34) == 0.55 * 0.89


def test_p_play_back_to_back_sans_effet_pour_un_remplacant():
    logs = [{"minutes": 18}] * 3
    assert p_play(injury_status=None, recent_logs=logs, is_b2b_second=True, exp_minutes=18) == 0.955


def test_future_p_play():
    assert future_p_play(injury_status=None, availability_rate=0.9, is_b2b_second=False, exp_minutes=30) == 0.9
    assert future_p_play(injury_status="Out For Season", availability_rate=0.9,
                         is_b2b_second=False, exp_minutes=30) == 0.0
    assert future_p_play(injury_status=None, availability_rate=1.0, is_b2b_second=True, exp_minutes=36) == 0.89


# --- Blessés signalés : aucun risque (préférence utilisateur 2026-11) -------

from datetime import date

import pytest

from engine.stats.availability_prob import INJURY_SAFETY_DAYS

RETURN = date(2026, 12, 21)


def _fpp(status, night, return_date=None, days_ahead=10, rate=0.9):
    return future_p_play(injury_status=status, availability_rate=rate, is_b2b_second=False, exp_minutes=34,
                         night=night, return_date=return_date, days_ahead=days_ahead)


def test_future_p_play_out_nul_avant_la_date_de_retour():
    """Edwards 2026-11 : Out (genou), retour estimé 21/12 — le moteur le
    planifiait à 100 % le 08/11 car seul le taux de présence comptait."""
    assert _fpp("Out", date(2026, 11, 8), RETURN, days_ahead=1) == 0.0
    assert _fpp("Out", date(2026, 12, 20), RETURN, days_ahead=43) == 0.0


def test_future_p_play_ecarte_les_7_jours_qui_suivent_le_retour():
    """Pas de pari sur une reprise : écarté tant que le retour date de moins de 7 j."""
    assert INJURY_SAFETY_DAYS == 7
    assert _fpp("Out", RETURN, RETURN) == 0.0
    assert _fpp("Out", date(2026, 12, 27), RETURN) == 0.0


def test_future_p_play_normal_7_jours_apres_le_retour():
    assert _fpp("Out", date(2026, 12, 28), RETURN) == pytest.approx(0.9)


def test_future_p_play_tout_statut_signale_compte():
    """Questionable / Day-To-Day avec date de retour : même règle que Out."""
    assert _fpp("Questionable", date(2026, 12, 22), RETURN) == 0.0
    assert _fpp("Day-To-Day", date(2026, 12, 28), RETURN) == pytest.approx(0.9)


def test_future_p_play_signale_sans_date_nul_les_7_premiers_jours():
    assert _fpp("Out", date(2026, 11, 10), None, days_ahead=3) == 0.0
    assert _fpp("Day-To-Day", date(2026, 11, 14), None, days_ahead=7) == 0.0
    assert _fpp("Out", date(2026, 11, 20), None, days_ahead=13) == pytest.approx(0.9)


def test_future_p_play_quarantaine_maintenue_apres_levee_du_statut():
    """ESPN retire le joueur de sa liste le jour de son retour : sans la
    date de retour conservée, il revenait à 100 % dès son premier match."""
    assert _fpp(None, date(2026, 12, 22), RETURN) == 0.0
    assert _fpp(None, date(2026, 12, 28), RETURN) == pytest.approx(0.9)


# --- Le soir même : même règle « aucun risque » ------------------------------

from engine.stats.availability_prob import tonight_p_play

TONIGHT = date(2026, 11, 14)


def _tpp(status, return_date=None, logs=(), b2b=False):
    return tonight_p_play(injury_status=status, recent_logs=list(logs), is_b2b_second=b2b, exp_minutes=34,
                          night=TONIGHT, return_date=return_date)


def test_tonight_p_play_tout_statut_signale_est_ecarte():
    for status in ("Probable", "Day-To-Day", "Questionable", "Game-Time Decision", "Out", "OUT", "Inconnu"):
        assert _tpp(status) == 0.0
        assert _tpp(status, return_date=date(2026, 10, 1)) == 0.0   # date de retour périmée : toujours signalé


def test_tonight_p_play_quarantaine_sans_statut():
    assert _tpp(None, return_date=date(2026, 11, 10)) == 0.0     # revenu depuis 4 j
    assert _tpp(None, return_date=date(2026, 11, 7)) == 1.0      # revenu depuis 7 j


def test_tonight_p_play_sain_garde_dnp_et_back_to_back():
    assert _tpp(None) == 1.0
    assert _tpp(None, logs=[{"minutes": 0}, {"minutes": 30}, {"minutes": 30}]) == 0.75
    assert _tpp(None, b2b=True) == pytest.approx(0.89)


def test_back_to_back_risque_de_repos_dans_p_joue():
    """Le 2e soir, le risque est la mise au repos : plus le joueur pèse, plus
    il est ménagé (40+ TTFL : 80,6 % rejouent). Paliers prudents pour les
    titulaires : la décote totale d'avant (0,96 × 0,93), pas moins."""
    def f(minutes, base):
        return tonight_p_play(injury_status=None, recent_logs=[], is_b2b_second=True, exp_minutes=minutes, base=base)
    assert f(36, 45) == 0.88
    assert f(34, 37) == 0.89
    assert f(27, 36) == 0.89      # star à moins de 30 min : ménagée quand même
    assert f(32, 28) == 0.89
    assert f(22, 18) == 0.955
    assert tonight_p_play(injury_status=None, recent_logs=[], is_b2b_second=False, exp_minutes=36, base=45) == 1.0
    assert future_p_play(injury_status=None, availability_rate=1.0, is_b2b_second=True, exp_minutes=36, base=45) == 0.88
