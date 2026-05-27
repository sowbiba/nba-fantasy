from sync.injuries import _normalize, match_injury_to_player


def _players():
    return [
        {"id": 1, "name": "Jalen Williams"},
        {"id": 2, "name": "Jaylin Williams"},
        {"id": 3, "name": "Shai Gilgeous-Alexander"},
        {"id": 4, "name": "PJ Washington"},
        {"id": 5, "name": "Jaren Jackson Jr."},
    ]


def test_normalize_accents_punctuation_suffix():
    assert _normalize("De'Aaron Fox") == "deaaron fox"
    assert _normalize("P.J. Washington") == "pj washington"
    assert _normalize("Nikola Jokić") == "nikola jokic"
    assert _normalize("Shai  Gilgeous-Alexander") == "shai gilgeousalexander"
    assert _normalize("Jaren Jackson Jr.") == "jaren jackson"


def test_exact_match():
    assert match_injury_to_player("Jalen Williams", _players()) == 1


def test_jalen_vs_jaylin_not_crossmatched():
    """The reported bug: same surname + first initial must NOT cross-match."""
    assert match_injury_to_player("Jalen Williams", _players()) == 1
    assert match_injury_to_player("Jaylin Williams", _players()) == 2


def test_punctuation_insensitive_match():
    # ESPN may send 'P.J.' while the DB stores 'PJ'.
    assert match_injury_to_player("P.J. Washington", _players()) == 4


def test_suffix_difference_matches():
    # ESPN 'Jaren Jackson Jr.' must match a DB 'Jaren Jackson Jr.' or bare.
    assert match_injury_to_player("Jaren Jackson", _players()) == 5
    assert match_injury_to_player("Jaren Jackson Jr.", _players()) == 5


def test_accent_insensitive_match():
    players = [{"id": 7, "name": "Nikola Jokić"}]
    assert match_injury_to_player("Nikola Jokic", players) == 7


def test_no_match_on_different_surname():
    assert match_injury_to_player("LeBron James", _players()) is None


def test_single_word_falls_back_to_surname():
    assert match_injury_to_player("Wembanyama", [{"id": 8, "name": "Victor Wembanyama"}]) == 8
