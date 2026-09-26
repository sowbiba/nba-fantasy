from datetime import date, datetime, timedelta, timezone

from engine.rules.calendar import PARIS, build_nights, closing_at, is_phantom


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_closing_at_minuit_paris_par_defaut():
    # Soirée US du 04/11, premier match 19:00 ET = 01:00 Paris le 05/11 → minuit.
    c = closing_at(date(2026, 11, 4), [_utc("2026-11-05T00:00:00")])
    assert c == datetime(2026, 11, 5, 0, 0, tzinfo=PARIS)


def test_closing_at_match_avance():
    # Noël : premier match 12:00 ET = 18:00 Paris → fermeture 18:00.
    c = closing_at(date(2026, 12, 25), [_utc("2026-12-25T17:00:00"), _utc("2026-12-26T01:00:00")])
    assert c == datetime(2026, 12, 25, 18, 0, tzinfo=PARIS)


def test_closing_at_sans_horaire_connu():
    assert closing_at(date(2026, 11, 4), [None]) == datetime(2026, 11, 5, 0, 0, tzinfo=PARIS)


def test_closing_at_changement_heure_hiver():
    # Nuit du 24 au 25/10/2026 : minuit est encore en heure d'été (UTC+2).
    c = closing_at(date(2026, 10, 24), [])
    assert c.utcoffset() == timedelta(hours=2)
    # Soirée du 25/10 : minuit du 26 est en heure d'hiver (UTC+1).
    assert closing_at(date(2026, 10, 25), []).utcoffset() == timedelta(hours=1)


def test_closing_at_changement_heure_ete():
    # Soirée du 28/03/2027 : minuit du 29 est en heure d'été (UTC+2).
    assert closing_at(date(2027, 3, 28), []).utcoffset() == timedelta(hours=2)


def _game(gid, d, home, away, gtype, season="2025-26", status="scheduled", series_id=None, tip=None):
    return {"id": gid, "date": d, "home_team": home, "away_team": away, "game_type": gtype,
            "season": season, "status": status, "series_id": series_id, "tip_off": tip}


SERIES_DONE = {"id": 7, "season": "2025-26", "round": 1, "home_team": "NYK", "away_team": "ATL",
               "home_wins": 4, "away_wins": 1, "status": "completed"}


def test_match_fantome_par_serie():
    g = _game("0042500106", "2026-04-30", "NYK", "ATL", "playoffs", series_id=7)
    assert is_phantom(g, [SERIES_DONE])


def test_match_fantome_par_paire_sans_lien_de_serie():
    g = _game("0042500107", "2026-05-02", "ATL", "NYK", "playoffs")
    assert is_phantom(g, [SERIES_DONE])


def test_match_joue_d_une_serie_terminee_n_est_pas_fantome():
    g = _game("0042500105", "2026-04-28", "NYK", "ATL", "playoffs", status="final", series_id=7)
    assert not is_phantom(g, [SERIES_DONE])


def test_match_sr_entre_deux_equipes_d_une_serie_terminee_n_est_pas_fantome():
    # Le bug B3 de l'audit : un NYK-ATL de saison régulière disparaissait.
    g = _game("0022600050", "2026-11-02", "NYK", "ATL", "regular", season="2026-27")
    assert not is_phantom(g, [SERIES_DONE])


def test_build_nights_mode_et_comptage():
    games = [
        _game("0022600001", "2026-10-20", "BOS", "NYK", "regular", season="2026-27", tip="2026-10-20T23:30:00+00:00"),
        _game("0022600002", "2026-10-20", "LAL", "GSW", "regular", season="2026-27", tip="2026-10-21T02:00:00+00:00"),
    ]
    [n] = build_nights(games, [])
    assert (n.date, n.season, n.mode, n.n_eligible_games, n.is_phantom) == (
        date(2026, 10, 20), "2026-27", "regular", 2, False)
    assert n.closing_at == datetime(2026, 10, 21, 0, 0, tzinfo=PARIS)


def test_build_nights_ignore_soiree_sans_match_eligible():
    # Week-end All-Star, jours de play-in, présaison : pas de soirée TTFL.
    games = [
        _game("0032500001", "2026-02-15", "EST", "WST", "allstar"),
        _game("0052500101", "2026-04-14", "MIA", "CHI", "playin"),
        _game("0012600001", "2026-10-05", "DEN", "LAL", "preseason", season="2026-27"),
    ]
    assert build_nights(games, []) == []


def test_build_nights_soiree_uniquement_fantome():
    games = [_game("0042500106", "2026-04-30", "NYK", "ATL", "playoffs", series_id=7)]
    [n] = build_nights(games, [SERIES_DONE])
    assert (n.mode, n.n_eligible_games, n.is_phantom) == ("playoffs", 0, True)


def test_build_nights_finale_nba_cup_est_une_soiree_sr():
    games = [_game("0062600001", "2026-12-15", "OKC", "MIL", "cup_final", season="2026-27")]
    [n] = build_nights(games, [])
    assert (n.mode, n.n_eligible_games) == ("regular", 1)
