"""TTFL score calculator.

Formula: (PTS + REB + AST + STL + BLK + FGM + 3PM + FTM)
       - (TOV + FG_miss + 3P_miss + FT_miss)
"""
from engine.rules.scoring import compute_ttfl_score  # R1, source unique


def compute_ttfl_from_game_log(log: dict) -> int:
    """Compute TTFL score from an nba_api game log dict."""
    return compute_ttfl_score(
        pts=log["PTS"], reb=log["REB"], ast=log["AST"],
        stl=log["STL"], blk=log["BLK"],
        fgm=log["FGM"], fga=log["FGA"],
        tpm=log["FG3M"], tpa=log["FG3A"],
        ftm=log["FTM"], fta=log["FTA"],
        tov=log["TOV"],
    )
