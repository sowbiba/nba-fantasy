"""Job `backtest` : lecture seule (aucune écriture, aucun `sync_log`), et
rapport Markdown conforme aux règles du contrôleur (comparaison « contre mes
perfs », moyenne réelle officielle ET via les logs, contexte saison complète,
limites, conclusion factuelle)."""
from datetime import date, timedelta

import pytest

from engine.jobs.backtest import STRATEGIES, INJURY_MODES, main, render_report, run
from engine.strategy.value import FUTURE_DECAY
from tests.jobs.fakes import FakeRepo

SEASON = "2026-27"
PRIOR = "2025-26"
HOME, AWAY = "AAA", "BBB"
TEAMS = {1: HOME, 2: HOME, 3: AWAY, 4: AWAY}
BASE = {1: 50, 2: 40, 3: 30, 4: 20}
# Fenêtre à cheval sur novembre→décembre (mois x2) pour que `plan` pose un x2.
NIGHTS = [date(2026, 11, 27) + timedelta(days=i) for i in range(8)]  # → 2026-12-04


def _log_row(pid, d, minutes=30, ttfl=None, season=SEASON):
    ttfl = BASE[pid] if ttfl is None else ttfl
    return {"player_id": pid, "game_id": f"g_{pid}_{d.isoformat()}", "date": d.isoformat(), "season": season,
            "team": TEAMS[pid], "minutes": minutes, "ttfl_score": ttfl, "is_home": TEAMS[pid] == HOME}


def _game_row(d):
    return {"id": f"g_{d.isoformat()}", "date": d.isoformat(), "home_team": HOME, "away_team": AWAY,
            "game_type": "regular", "status": "final", "tip_off": None, "season": SEASON}


def _season_repo():
    """Petite saison synthétique : joueurs 1..4, un match AAA-BBB par soirée
    de `NIGHTS`, plus un peu d'historique de la saison précédente pour que
    les profils existent. Vrais picks de l'utilisateur posés sur les 3
    premières soirées, avec un écart volontaire officiel/logs sur l'une
    d'elles (correction jamais rescorée)."""
    players = [{"id": pid, "name": f"P{pid}", "position": "F", "team": TEAMS[pid], "active": True}
              for pid in BASE]
    games = [_game_row(d) for d in NIGHTS]
    logs = []
    for pid in BASE:
        for i in range(10):
            logs.append(_log_row(pid, date(2026, 3, 1) + timedelta(days=i), season=PRIOR))
        for d in NIGHTS:
            logs.append(_log_row(pid, d))
    picks = [
        {"id": 1, "player_id": 1, "game_id": f"g_1_{NIGHTS[0].isoformat()}", "date": NIGHTS[0].isoformat(),
         "mode": "regular", "season": SEASON, "actual_score": BASE[1], "is_x2": False},
        # Écart volontaire officiel (35) vs log (50, joueur 2) : soirée à
        # remonter dans "diverging_nights".
        {"id": 2, "player_id": 2, "game_id": f"g_2_{NIGHTS[1].isoformat()}", "date": NIGHTS[1].isoformat(),
         "mode": "regular", "season": SEASON, "actual_score": 35, "is_x2": False},
        {"id": 3, "player_id": 3, "game_id": f"g_3_{NIGHTS[2].isoformat()}", "date": NIGHTS[2].isoformat(),
         "mode": "regular", "season": SEASON, "actual_score": BASE[3], "is_x2": True},
    ]
    return FakeRepo(players=players, games=games, logs=logs, picks=picks)


class ReadOnlyRepo:
    """Enveloppe un `FakeRepo` : ne délègue que les méthodes `load_*` dont
    `load_season` a besoin ; tout le reste (écritures, journal `sync_log`,
    y compris une méthode future non encore imaginée) lève. Preuve
    structurelle, pas une énumération des écritures connues aujourd'hui."""
    _ALLOWED = {"load_players", "load_games_of_seasons", "load_game_logs", "load_picks", "load_second_chances"}

    def __init__(self, fake: FakeRepo):
        self._fake = fake

    def __getattr__(self, name):
        if name in self._ALLOWED:
            return getattr(self._fake, name)
        raise AssertionError(f"écriture interdite (ou méthode non lue) : {name}")


def _data():
    from engine.backtest.data import load_season
    return load_season(_season_repo(), SEASON)


def test_run_produit_les_lignes_attendues_et_un_ecart_officiel_logs():
    data = _data()
    result = run(data, NIGHTS[0], NIGHTS[-1])
    labels = [(r.label, r.mode) for r in result["rows"]]
    # officiel + logs (n/a) + (best_available, best_available_x2plan, plan défaut) × 2 modes = 8.
    assert ("Mes vrais picks (officiel)", "n/a") in labels
    assert ("Mes vrais picks (logs)", "n/a") in labels
    for strategy in STRATEGIES:
        label = strategy if strategy != "plan" else f"plan (decay={FUTURE_DECAY}, défaut)"
        for mode in INJURY_MODES:
            assert (label, mode) in labels
    assert len(result["rows"]) == 8
    # La soirée 2 (actual_score officiel 35 ≠ log 50) doit apparaître.
    assert NIGHTS[1] in result["diverging_nights"]
    assert len(result["diverging_nights"]) == 1


def test_run_ajoute_deux_lignes_par_decay_demande():
    data = _data()
    result = run(data, NIGHTS[0], NIGHTS[-1], decays=[0.97, 1.0])
    labels = [(r.label, r.mode) for r in result["rows"]]
    for decay in (0.97, 1.0):
        for mode in INJURY_MODES:
            assert (f"plan (decay={decay})", mode) in labels
    assert len(result["rows"]) == 8 + 2 * 2


def test_run_contexte_saison_complete_present():
    data = _data()
    result = run(data, NIGHTS[0], NIGHTS[-1])
    fs = result["full_season"]
    assert fs["start"] <= NIGHTS[0] and fs["end"] >= NIGHTS[-1]
    # 3 vrais picks posés sur toute la saison synthétique.
    assert len(fs["logs"].nights) == len(NIGHTS)
    assert sum(1 for n in fs["logs"].nights if n.player_id is not None) == 3


def test_contexte_saison_bornes_aux_soirees_de_saison_reguliere():
    # I-5 : un match de playoffs après la saison régulière (et un match de
    # présaison avant) ne doivent pas élargir les bornes affichées.
    repo = _season_repo()
    po_day = NIGHTS[-1] + timedelta(days=40)
    pre_day = NIGHTS[0] - timedelta(days=20)
    repo.games["g_po"] = {**_game_row(po_day), "id": "g_po", "game_type": "playoffs"}
    repo.games["g_pre"] = {**_game_row(pre_day), "id": "g_pre", "game_type": "preseason"}
    from engine.backtest.data import load_season
    data = load_season(repo, SEASON)
    fs = run(data, NIGHTS[0], NIGHTS[-1])["full_season"]
    assert (fs["start"], fs["end"]) == (NIGHTS[0], NIGHTS[-1])
    report = render_report(SEASON, NIGHTS[0], NIGHTS[-1], [], run(data, NIGHTS[0], NIGHTS[-1]))
    assert f"({NIGHTS[0].isoformat()} → {NIGHTS[-1].isoformat()})" in report


def test_report_contient_les_sections_et_la_conclusion_factuelle():
    data = _data()
    result = run(data, NIGHTS[0], NIGHTS[-1], decays=[0.97])
    report = render_report(SEASON, NIGHTS[0], NIGHTS[-1], [0.97], result)
    for heading in ("## Comparaison contre mes perfs", "## Contexte : ma moyenne sur toute la saison régulière",
                    "## Limites", "## Conclusion"):
        assert heading in report
    assert ("le plan bat le meilleur choix dans les deux modes" in report
           or "le plan ne bat pas le meilleur choix dans les deux modes" in report)
    assert "mode none : plan − meilleur choix" in report
    assert "mode dnp_oracle : plan − meilleur choix" in report
    assert "mode none : best_available_x2plan − best_available" in report
    assert "| best_available_x2plan | dnp_oracle |" in report
    # M-6 (zéros), M-2 (bruit), I-4 (officiel = logs), M-7 (seconde chance).
    assert "Zéros : soirées à 0 point, soirées sans pick comprises" in report
    assert f"sur {len(NIGHTS)} soirées" in report and "erreur type d'une différence de moyennes" in report
    assert "pas une vérification indépendante contre trashtalk.co" in report
    assert "Pas de seconde chance dans les simulations" in report
    assert "decay=0.97" in report


def test_le_job_ne_lit_que_le_repo_lecture_seule_et_n_ecrit_jamais(monkeypatch, tmp_path):
    readonly = ReadOnlyRepo(_season_repo())
    monkeypatch.setattr("engine.io.repo.SupabaseRepo.from_env", classmethod(lambda cls: readonly))

    out = tmp_path / "rapport.md"
    main(["--season", SEASON, "--from", NIGHTS[0].isoformat(), "--to", NIGHTS[-1].isoformat(),
          "--decay", "0.97", "--out", str(out)])

    assert out.exists()
    report = out.read_text(encoding="utf-8")
    assert "## Conclusion" in report
    assert "decay=0.97" in report   # parsing de --decay (liste séparée par virgules)


def test_run_amorce_les_simulations_avec_les_vrais_picks_pre_fenetre():
    # Un vrai pick posé 10 jours avant le début de la fenêtre, sur le
    # meilleur joueur (1), doit le bloquer (R3) pour toute la fenêtre : les
    # simulations (best_available, plan) ne doivent jamais le choisir,
    # contrairement à la saison de base où il est pické soir 1.
    repo = _season_repo()
    seed_date = NIGHTS[0] - timedelta(days=10)
    repo.picks.append({"id": 100, "player_id": 1, "game_id": f"g_1_{seed_date.isoformat()}",
                       "date": seed_date.isoformat(), "mode": "regular", "season": SEASON,
                       "actual_score": BASE[1], "is_x2": False})
    from engine.backtest.data import load_season
    data = load_season(repo, SEASON)

    result = run(data, NIGHTS[0], NIGHTS[-1])
    by = {(r.label, r.mode): r for r in result["rows"]}
    for strategy in STRATEGIES:
        label = strategy if strategy != "plan" else f"plan (decay={FUTURE_DECAY}, défaut)"
        for mode in INJURY_MODES:
            assert all(n.player_id != 1 for n in by[(label, mode)].result.nights)
    # Le pick d'amorçage (10 jours avant la fenêtre) n'apparaît dans aucun résultat.
    for row in result["rows"]:
        assert seed_date not in {n.night for n in row.result.nights}

    # Sans le seed (saison de base), le joueur 1 est bien choisi soir 1.
    baseline = run(_data(), NIGHTS[0], NIGHTS[-1])
    baseline_by = {(r.label, r.mode): r for r in baseline["rows"]}
    assert baseline_by[("best_available", "none")].result.nights[0].player_id == 1


def test_le_repo_lecture_seule_leve_sur_toute_ecriture():
    readonly = ReadOnlyRepo(_season_repo())
    with pytest.raises(AssertionError):
        readonly.upsert_players([])
    with pytest.raises(AssertionError):
        readonly.start_log("backtest")
