"""Job `elo_report` : lecture seule (aucune écriture), rejeu cohérent
(la ligne « meilleure » est bien le minimum de perte logarithmique du
tableau, y compris restreint à `elo_per_share = 0`), et rapport Markdown
avec les sections attendues (référence naïve, meilleur jeu, apport de la
correction blessures, tableau complet).

Saison synthétique : deux équipes AAA/BBB, alternance domicile/extérieur.
AAA a un joueur vedette (id 1, ~55 % de la production de l'équipe) : quand
il joue, AAA gagne largement ; un match sur quatre, il est absent (aucun
log ce soir-là) et AAA perd d'un petit écart. Sans la correction blessures,
l'Elo de AAA (dopé par ses victoires quand la vedette joue) prédit à tort
la victoire de AAA sur ces matchs « vedette absente » ; avec la correction
(`elo_per_share` assez grand), la prédiction s'inverse correctement — la
grille doit donc choisir un jeu avec `elo_per_share > 0`."""
from datetime import date, timedelta

import pytest

from engine.jobs.elo_report import K_GRID, SHARE_GRID, main, render_report, run
from engine.stats.profile import GameLog
from tests.jobs.fakes import FakeRepo

SEASON = "2025-26"
AAA, BBB = "AAA", "BBB"
N_GAMES = 60
STAR_ABSENT_EVERY = 4
START = date(2025, 11, 1)


def _game_row(i: int, d: date) -> dict:
    home_is_aaa = i % 2 == 0
    home, away = (AAA, BBB) if home_is_aaa else (BBB, AAA)
    star_absent = i % STAR_ABSENT_EVERY == 0
    if star_absent:
        # AAA (vedette absente) perd d'un petit écart, qu'elle soit domicile ou extérieur.
        home_score, away_score = (95, 105) if home_is_aaa else (105, 95)
    else:
        # AAA (vedette présente) gagne largement.
        home_score, away_score = (115, 95) if home_is_aaa else (95, 115)
    return {
        "id": f"g{i}", "date": d.isoformat(), "home_team": home, "away_team": away,
        "status": "final", "home_score": home_score, "away_score": away_score,
        "game_type": "regular", "season": SEASON, "tip_off": None,
    }


def _log_rows(i: int, d: date) -> list[dict]:
    home_is_aaa = i % 2 == 0
    star_absent = i % STAR_ABSENT_EVERY == 0
    gid = f"g{i}"
    rows = []
    if not star_absent:
        rows.append({"player_id": 1, "game_id": gid, "date": d.isoformat(), "season": SEASON,
                    "team": AAA, "minutes": 35, "ttfl_score": 40, "is_home": home_is_aaa})
    rows.append({"player_id": 2, "game_id": gid, "date": d.isoformat(), "season": SEASON,
                "team": AAA, "minutes": 20, "ttfl_score": 10, "is_home": home_is_aaa})
    rows.append({"player_id": 3, "game_id": gid, "date": d.isoformat(), "season": SEASON,
                "team": AAA, "minutes": 20, "ttfl_score": 10, "is_home": home_is_aaa})
    rows.append({"player_id": 4, "game_id": gid, "date": d.isoformat(), "season": SEASON,
                "team": BBB, "minutes": 30, "ttfl_score": 20, "is_home": not home_is_aaa})
    rows.append({"player_id": 5, "game_id": gid, "date": d.isoformat(), "season": SEASON,
                "team": BBB, "minutes": 30, "ttfl_score": 20, "is_home": not home_is_aaa})
    return rows


def _season_repo() -> FakeRepo:
    players = [
        {"id": 1, "name": "Vedette", "team": AAA, "position": "G", "active": True},
        {"id": 2, "name": "Role2", "team": AAA, "position": "F", "active": True},
        {"id": 3, "name": "Role3", "team": AAA, "position": "F", "active": True},
        {"id": 4, "name": "B4", "team": BBB, "position": "G", "active": True},
        {"id": 5, "name": "B5", "team": BBB, "position": "F", "active": True},
    ]
    games, logs = [], []
    for i in range(N_GAMES):
        d = START + timedelta(days=i)
        games.append(_game_row(i, d))
        logs.extend(_log_rows(i, d))
    return FakeRepo(players=players, games=games, logs=logs)


def _data():
    from engine.backtest.data import load_season
    return load_season(_season_repo(), SEASON)


class ReadOnlyRepo:
    """Enveloppe un `FakeRepo` : ne délègue que les méthodes `load_*` dont
    `load_season` a besoin ; tout le reste lève — même garde que
    `tests/jobs/test_backtest_job.py`."""
    _ALLOWED = {"load_players", "load_games_of_seasons", "load_game_logs", "load_picks", "load_second_chances"}

    def __init__(self, fake: FakeRepo):
        self._fake = fake

    def __getattr__(self, name):
        if name in self._ALLOWED:
            return getattr(self._fake, name)
        raise AssertionError(f"écriture interdite (ou méthode non lue) : {name}")


def test_run_fenetre_par_defaut_1er_decembre():
    data = _data()
    result = run(data, SEASON)
    assert result["from_date"] == date(2025, 12, 1)
    # Matchs de décembre uniquement (30 derniers jours de la saison synthétique).
    assert result["n_window"] == sum(1 for i in range(N_GAMES) if START + timedelta(days=i) >= date(2025, 12, 1))


def test_run_meilleure_ligne_coherente_avec_le_tableau():
    data = _data()
    result = run(data, SEASON)
    rows = result["rows"]
    assert len(rows) == len(K_GRID) * 3 * len(SHARE_GRID)  # HCA_GRID a 3 valeurs

    best = result["best"]
    assert best is not None
    assert all(best.log_loss <= r.log_loss for r in rows)   # vrai minimum global

    best_no_injury = result["best_no_injury"]
    assert best_no_injury is not None
    assert best_no_injury.elo_per_share == 0.0
    no_injury_rows = [r for r in rows if r.elo_per_share == 0.0]
    assert all(best_no_injury.log_loss <= r.log_loss for r in no_injury_rows)

    best_with_injury = result["best_with_injury"]
    assert best_with_injury is not None
    assert best_with_injury.elo_per_share > 0.0
    injury_rows = [r for r in rows if r.elo_per_share > 0.0]
    assert all(best_with_injury.log_loss <= r.log_loss for r in injury_rows)

    assert result["injury_gain"] == pytest.approx(best_no_injury.log_loss - best_with_injury.log_loss)


def test_run_la_correction_blessures_gagne_sur_cette_saison_synthetique():
    """La vedette absente un match sur quatre, sans corrélation avec le
    résultat autrement, doit faire gagner `elo_per_share > 0` : sans
    correction, l'Elo de AAA (dopé par ses victoires vedette-présente)
    prédit à tort la victoire sur les matchs vedette-absente."""
    data = _data()
    result = run(data, SEASON)
    assert result["best"].elo_per_share > 0.0   # le minimum global choisit une correction active
    assert result["best_with_injury"].elo_per_share > 0.0
    assert result["injury_gain"] > 0.0
    assert result["best_with_injury"].log_loss < result["best_no_injury"].log_loss


def test_run_reference_naive_calculee_sur_la_fenetre():
    data = _data()
    result = run(data, SEASON)
    assert 0.0 < result["naive_home_win_rate"] < 1.0
    assert result["naive_log_loss"] > 0.0
    # Référence naïve indépendante de l'Elo : moins bonne que le meilleur jeu corrigé.
    assert result["naive_log_loss"] > result["best"].log_loss


def test_render_report_contient_les_sections_attendues():
    data = _data()
    result = run(data, SEASON)
    report = render_report(SEASON, result)
    for heading in ("## Référence naïve", "## Meilleur jeu de paramètres",
                    "## Apport de la correction blessures", "## Tableau complet", "## Limites"):
        assert heading in report
    best = result["best"]
    assert f"k = {best.k:g}" in report
    assert f"elo_per_share = {best.elo_per_share:g}" in report
    assert "la correction blessures améliore la prédiction" in report
    # Tableau : une ligne par combinaison de la grille.
    assert report.count("\n|") >= len(result["rows"])


def test_le_job_ne_lit_que_le_repo_lecture_seule_et_n_ecrit_jamais(monkeypatch, tmp_path):
    readonly = ReadOnlyRepo(_season_repo())
    monkeypatch.setattr("engine.io.repo.SupabaseRepo.from_env", classmethod(lambda cls: readonly))

    out = tmp_path / "rapport.md"
    main(["--season", SEASON, "--out", str(out)])

    assert out.exists()
    report = out.read_text(encoding="utf-8")
    assert "## Meilleur jeu de paramètres" in report


def test_le_repo_lecture_seule_leve_sur_toute_ecriture():
    readonly = ReadOnlyRepo(_season_repo())
    with pytest.raises(AssertionError):
        readonly.upsert_players([])
    with pytest.raises(AssertionError):
        readonly.start_log("elo_report")


def test_main_accepte_from_explicite(tmp_path, monkeypatch):
    readonly = ReadOnlyRepo(_season_repo())
    monkeypatch.setattr("engine.io.repo.SupabaseRepo.from_env", classmethod(lambda cls: readonly))
    out = tmp_path / "rapport.md"
    main(["--season", SEASON, "--from", "2025-11-15", "--out", str(out)])
    report = out.read_text(encoding="utf-8")
    assert "2025-11-15" in report


def test_run_grille_personnalisee_via_k_hca_eps():
    # `run(..., k_grid=..., hca_grid=..., share_grid=...)` rejoue exactement
    # cette grille (pas la grille par défaut du module).
    data = _data()
    result = run(data, SEASON, k_grid=(30.0,), hca_grid=(80.0,), share_grid=(0.0, 500.0))
    assert len(result["rows"]) == 2
    assert {r.k for r in result["rows"]} == {30.0}
    assert {r.home_advantage for r in result["rows"]} == {80.0}
    assert {r.elo_per_share for r in result["rows"]} == {0.0, 500.0}


def test_main_accepte_k_hca_eps_pour_elargir_la_grille(tmp_path, monkeypatch):
    readonly = ReadOnlyRepo(_season_repo())
    monkeypatch.setattr("engine.io.repo.SupabaseRepo.from_env", classmethod(lambda cls: readonly))
    out = tmp_path / "rapport.md"
    main(["--season", SEASON, "--out", str(out), "--k", "30", "--hca", "50,90", "--eps", "0,600"])
    report = out.read_text(encoding="utf-8")
    # Grille 1 × 2 × 2 = 4 lignes dans le tableau complet, aucune des valeurs
    # par défaut (ex. k = 20) ne doit y apparaître.
    assert report.count("\n| 30 |") == 4
    assert "| 20 |" not in report


def test_parse_args_grille_par_defaut_si_options_omises():
    from engine.jobs.elo_report import _parse_args, _parse_grid

    args = _parse_args(["--season", SEASON])
    assert _parse_grid(args.k, K_GRID) == K_GRID
    assert _parse_grid(args.hca, (40.0, 70.0, 100.0)) == (40.0, 70.0, 100.0)
