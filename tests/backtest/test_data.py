from datetime import date

from engine.backtest.data import (
    SeasonData,
    eligible_nights,
    load_season,
    logs_before,
    played_on,
    roster_before,
    score_on,
    team_before,
)
from engine.stats.profile import GameLog

SEASON = "2026-27"
PRIOR = "2025-26"


def _log(player_id, d, team, minutes=30, ttfl=25, season=SEASON, game_id=None):
    return GameLog(
        player_id=player_id, game_id=game_id or f"g_{player_id}_{d.isoformat()}",
        date=d, season=season, team=team, minutes=minutes, ttfl=ttfl, is_home=True,
    )


def _game(game_id, d, home, away, game_type="regular", status="final", tip_off=None, season=SEASON):
    return {"id": game_id, "date": d.isoformat(), "home_team": home, "away_team": away,
            "game_type": game_type, "status": status, "tip_off": tip_off, "season": season}


def _players():
    return {
        1: {"id": 1, "name": "Traded Player", "position": "G"},
        2: {"id": 2, "name": "Future Only", "position": "F"},
        3: {"id": 3, "name": "Zero Min", "position": "C"},
    }


def _season_data(logs, games, picks=None, second_chances=None):
    return SeasonData(
        season=SEASON, prior=PRIOR, players=_players(), games=games, logs=logs,
        picks=picks or [], second_chances=second_chances or [],
    )


def test_team_before_suit_le_transfert_bos_dal():
    logs = [
        _log(1, date(2026, 1, 5), "BOS"),
        _log(1, date(2026, 1, 20), "BOS"),
        _log(1, date(2026, 2, 10), "DAL"),
        _log(1, date(2026, 2, 20), "DAL"),
    ]
    data = _season_data(logs, [])
    assert team_before(data, 1, date(2026, 2, 5)) == "BOS"
    assert team_before(data, 1, date(2026, 2, 15)) == "DAL"


def test_team_before_avant_le_premier_log_retourne_la_premiere_equipe():
    logs = [_log(1, date(2026, 1, 5), "BOS"), _log(1, date(2026, 1, 20), "BOS")]
    data = _season_data(logs, [])
    assert team_before(data, 1, date(2025, 12, 1)) == "BOS"


def test_team_before_sans_log_retourne_none():
    data = _season_data([], [])
    assert team_before(data, 99, date(2026, 1, 1)) is None


def test_logs_before_exclut_le_jour_meme():
    logs = [_log(1, date(2026, 1, 5), "BOS"), _log(1, date(2026, 1, 6), "BOS")]
    data = _season_data(logs, [])
    result = logs_before(data, date(2026, 1, 6))
    assert [l.date for l in result] == [date(2026, 1, 5)]


def test_score_on_zero_minute_donne_zero():
    logs = [_log(3, date(2026, 1, 5), "BOS", minutes=0, ttfl=0)]
    data = _season_data(logs, [])
    assert score_on(data, 3, date(2026, 1, 5)) == 0


def test_score_on_absence_de_log_donne_zero():
    data = _season_data([], [])
    assert score_on(data, 3, date(2026, 1, 5)) == 0


def test_score_on_log_joue_retourne_le_score():
    logs = [_log(1, date(2026, 1, 5), "BOS", minutes=30, ttfl=42)]
    data = _season_data(logs, [])
    assert score_on(data, 1, date(2026, 1, 5)) == 42


def test_played_on():
    logs = [_log(1, date(2026, 1, 5), "BOS", minutes=30), _log(3, date(2026, 1, 5), "BOS", minutes=0)]
    data = _season_data(logs, [])
    assert played_on(data, 1, date(2026, 1, 5)) is True
    assert played_on(data, 3, date(2026, 1, 5)) is False
    assert played_on(data, 99, date(2026, 1, 5)) is False


def test_roster_before_exclut_un_joueur_dont_le_seul_log_est_apres_d():
    logs = [
        _log(1, date(2026, 1, 5), "BOS"),
        _log(2, date(2026, 1, 10), "DAL"),  # seul log de 2, après d
    ]
    data = _season_data(logs, [_game("g1", date(2025, 10, 1), "BOS", "LAL")])
    roster = roster_before(data, date(2026, 1, 6))
    assert 1 in roster
    assert 2 not in roster
    assert roster[1]["team"] == "BOS"
    assert roster[1]["injury_status"] is None


def test_eligible_nights_ignore_preseason_et_playin():
    games = [
        _game("g1", date(2026, 1, 1), "BOS", "LAL", game_type="preseason"),
        _game("g2", date(2026, 1, 2), "BOS", "LAL", game_type="regular"),
        _game("g3", date(2026, 1, 3), "BOS", "LAL", game_type="playin"),
    ]
    data = _season_data([], games)
    nights = eligible_nights(data, date(2026, 1, 1), date(2026, 1, 3))
    assert [n.date for n in nights] == [date(2026, 1, 2)]


def test_eligible_nights_respecte_la_fenetre_start_end():
    games = [
        _game("g1", date(2026, 1, 1), "BOS", "LAL"),
        _game("g2", date(2026, 1, 2), "BOS", "LAL"),
        _game("g3", date(2026, 1, 3), "BOS", "LAL"),
    ]
    data = _season_data([], games)
    nights = eligible_nights(data, date(2026, 1, 2), date(2026, 1, 2))
    assert [n.date for n in nights] == [date(2026, 1, 2)]


def test_eligible_nights_accepte_une_fin_lointaine():
    # Le contrôleur (tâche 6) passe une fenêtre d'au moins 35 jours devant D ;
    # l'aide ne doit pas plafonner en interne au-delà de `end` fourni.
    far = date(2026, 6, 1)
    games = [_game("g1", far, "BOS", "LAL")]
    data = _season_data([], games)
    nights = eligible_nights(data, date(2026, 1, 1), far)
    assert [n.date for n in nights] == [far]


class _FakeRepo:
    def __init__(self, players, games, logs, picks, second_chances):
        self._players = players
        self._games = games
        self._logs = logs
        self._picks = picks
        self._second_chances = second_chances

    def load_players(self):
        return self._players

    def load_games_of_seasons(self, seasons):
        assert seasons == [SEASON]
        return self._games

    def load_game_logs(self, seasons):
        assert seasons == [SEASON, PRIOR]
        return self._logs

    def load_picks(self, season):
        assert season == SEASON
        return self._picks

    def load_second_chances(self):
        return self._second_chances


def test_load_season_charge_et_assemble_les_donnees():
    players = [{"id": 1, "name": "A", "position": "G"}]
    games = [_game("g1", date(2026, 1, 2), "BOS", "LAL")]
    logs = [
        {"player_id": 1, "game_id": "g1", "date": "2026-01-02", "season": SEASON,
         "team": "BOS", "minutes": 30, "ttfl_score": 25, "is_home": True},
        {"player_id": 1, "game_id": "g0", "date": "2025-11-02", "season": PRIOR,
         "team": "BOS", "minutes": 20, "ttfl_score": 15, "is_home": False},
    ]
    picks = [{"id": 1, "player_id": 1, "game_id": "g1", "date": "2026-01-02",
              "mode": "regular", "season": SEASON, "actual_score": 25, "is_x2": False}]
    second_chances = [{"pick_id": 1, "player_id": 1, "bought_on": "2026-01-03", "expires_on": "2026-01-10"}]
    repo = _FakeRepo(players, games, logs, picks, second_chances)

    data = load_season(repo, SEASON)

    assert data.season == SEASON
    assert data.prior == PRIOR
    assert data.players == {1: {"id": 1, "name": "A", "position": "G"}}
    assert data.games == games
    assert len(data.logs) == 2
    assert all(isinstance(l, GameLog) for l in data.logs)
    assert data.picks == picks
    assert data.second_chances == second_chances
