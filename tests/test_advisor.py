from sync.advisor import generate_argumentaire, generate_verdict


def test_generate_argumentaire_has_pros_and_cons():
    context = {
        "player_name": "Nikola Jokic", "team": "DEN", "opponent": "OKC",
        "is_home": True, "avg_l5": 62.4, "avg_season": 54.1,
        "matchup_rank": 2, "matchup_position": "centers",
        "series_score": (2, 2), "game_number": 5, "tier": "elite",
        "elites_remaining": 3, "game_days_remaining": 18,
        "days_rest": 2, "stddev": 8, "floor": 45, "ceiling": 78,
        "injury_status": None, "teammate_out": None,
    }
    pros, cons = generate_argumentaire(context)
    assert len(pros) > 0
    assert len(cons) > 0
    assert any("feu" in p.lower() or "forme" in p.lower() or "avg" in p.lower() for p in pros)


def test_generate_argumentaire_injury_teammate():
    context = {
        "player_name": "Paul George", "team": "PHI", "opponent": "BOS",
        "is_home": False, "avg_l5": 45, "avg_season": 42,
        "matchup_rank": 15, "matchup_position": "forwards",
        "series_score": (1, 3), "game_number": 5, "tier": "solid",
        "elites_remaining": 4, "game_days_remaining": 20,
        "days_rest": 1, "stddev": 14, "floor": 20, "ceiling": 68,
        "injury_status": None, "teammate_out": "Joel Embiid",
    }
    pros, cons = generate_argumentaire(context)
    assert any("embiid" in p.lower() for p in pros)


def test_generate_verdict_burn():
    verdict = generate_verdict(
        should_burn=True, tier="elite", tonight_score=75,
        best_future_description="Game 7 DEN-OKC à domicile mercredi",
    )
    assert "JOUE" in verdict.upper() or "BON SOIR" in verdict.upper()


def test_generate_verdict_save():
    verdict = generate_verdict(
        should_burn=False, tier="elite", tonight_score=60,
        best_future_description="Game 5 vs MIL à domicile vendredi",
    )
    assert "GARDE" in verdict.upper() or "SAVE" in verdict.upper()
