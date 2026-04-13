from sync.ttfl import compute_ttfl_score


def test_ttfl_score_basic():
    """Standard stat line: 30pts, 10reb, 8ast, 1stl, 2blk, 11/20fg, 3/7 3pt, 5/6ft, 3to"""
    score = compute_ttfl_score(
        pts=30, reb=10, ast=8, stl=1, blk=2,
        fgm=11, fga=20, tpm=3, tpa=7, ftm=5, fta=6, tov=3,
    )
    assert score == 53


def test_ttfl_score_monster_game():
    """Triple-double efficient game"""
    score = compute_ttfl_score(
        pts=45, reb=15, ast=12, stl=3, blk=1,
        fgm=18, fga=25, tpm=5, tpa=8, ftm=4, fta=4, tov=2,
    )
    assert score == 91


def test_ttfl_score_bad_game():
    """Inefficient low-scoring game"""
    score = compute_ttfl_score(
        pts=8, reb=2, ast=1, stl=0, blk=0,
        fgm=3, fga=12, tpm=1, tpa=6, ftm=1, fta=2, tov=4,
    )
    assert score == -3


def test_ttfl_score_zero_stats():
    """DNP or all zeros"""
    score = compute_ttfl_score(
        pts=0, reb=0, ast=0, stl=0, blk=0,
        fgm=0, fga=0, tpm=0, tpa=0, ftm=0, fta=0, tov=0,
    )
    assert score == 0


def test_compute_ttfl_from_game_log():
    """Test dict-based input matching nba_api game log format"""
    from sync.ttfl import compute_ttfl_from_game_log

    game_log = {
        "PTS": 25, "REB": 7, "AST": 5, "STL": 2, "BLK": 1,
        "FGM": 10, "FGA": 18, "FG3M": 3, "FG3A": 7, "FTM": 2, "FTA": 3, "TOV": 2,
    }
    score = compute_ttfl_from_game_log(game_log)
    assert score == 40
