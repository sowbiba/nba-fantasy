"""Job de backtest (lecture seule) : simule `best_available` et `plan`, dans
les deux modes de blessures (`none`, `dnp_oracle`), sur une fenêtre passée, et
compare le résultat aux vrais picks de l'utilisateur sur les mêmes soirées.

N'écrit jamais en base : n'appelle que les méthodes `load_*` de
`SupabaseRepo` (aucun `upsert_*`, aucun `sync_log`). Le rapport (Markdown)
est le seul artefact produit, sur disque.

Limites (voir aussi `docs/operations.md`) : pas d'historique des statuts de
blessures en base → deux bornes (« none » pessimiste, « dnp_oracle »
optimiste) plutôt qu'une vérité unique ; la saison 2024-25 n'est pas chargée
→ fenêtre par défaut février-avril de la saison en cours ; comparaison
restreinte à la saison régulière (R14, pas de x2 en playoffs).
"""
import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from engine.backtest.data import SeasonData, eligible_nights, load_season
from engine.backtest.simulate import (
    BacktestResult,
    NightResult,
    _last_regular_night_of_month,
    simulate,
    user_result,
)
from engine.rules.availability import COOLDOWN_DAYS, PickRow
from engine.rules.scoring import night_points
from engine.strategy.value import FUTURE_DECAY, X2_MONTHS

STRATEGIES = ("best_available", "plan")
INJURY_MODES = ("none", "dnp_oracle")
DEFAULT_WINDOW = (2, 4)   # février → avril : fenêtre par défaut (voir docstring module)
SEED_DAYS = COOLDOWN_DAYS   # amorce des simulations avec les vrais picks des 30 jours avant `start`


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _regular_dates(data: SeasonData, start: date, end: date) -> set[date]:
    """Soirées comptées (R14) sur la fenêtre : saison régulière seulement,
    non fantômes, avec au moins un match éligible — le même filtre que
    `simulate`/`user_result` appliquent en interne avant d'ajouter une
    ligne, restreint en plus aux soirées de saison régulière."""
    return {n.date for n in eligible_nights(data, start, end)
            if n.mode == "regular" and not n.is_phantom and n.n_eligible_games > 0}


def _only(result: BacktestResult, dates: set[date]) -> BacktestResult:
    return BacktestResult(result.strategy, result.injury_mode, [n for n in result.nights if n.night in dates])


def _official_user_result(data: SeasonData, start: date, end: date) -> BacktestResult:
    """Vrais picks de l'utilisateur, notés avec `picks.actual_score` (ce que
    l'application a réellement enregistré), pas avec les logs — R10/R14 : x2
    double même un score négatif, soirée sans pick (ou non scorée) = 0.
    `actual_score is None` (pick non encore scoré) compte 0 comme une soirée
    sans pick : sans conséquence sur les fenêtres de ce job, qui portent sur
    une saison déjà entièrement écoulée (`score_picks`, dans `daily_sync`,
    aurait déjà scoré tout pick dont le match est réglé)."""
    by_date: dict[date, dict] = {}
    for p in data.picks:
        d = _as_date(p["date"])
        if d not in by_date or (p.get("id") or 0) > (by_date[d].get("id") or 0):
            by_date[d] = p
    results = []
    for night in eligible_nights(data, start, end):
        if night.is_phantom or night.n_eligible_games <= 0:
            continue
        pick = by_date.get(night.date)
        if pick is None:
            results.append(NightResult(night.date, None, False, 0))
            continue
        points = night_points(pick.get("actual_score"), bool(pick.get("is_x2")))
        pid = pick.get("player_id")
        results.append(NightResult(night.date, int(pid) if pid is not None else None,
                                   bool(pick.get("is_x2")), points if points is not None else 0))
    return BacktestResult("user_officiel", "n/a", results)


def _seed_picks(data: SeasonData, start: date) -> list[PickRow]:
    """Vrais picks de l'utilisateur dans les `SEED_DAYS` jours avant `start` :
    amorcent l'historique de chaque simulation pour qu'elle démarre sous les
    mêmes contraintes que l'utilisateur (cooldown R3 dans les deux sens, x2
    déjà posé ce mois-ci, R10). Jamais notés, jamais dans les résultats —
    seul l'historique de picks simulé les voit."""
    window_start = start - timedelta(days=SEED_DAYS)
    seeds = []
    for p in data.picks:
        d = _as_date(p["date"])
        if window_start <= d < start:
            seeds.append(PickRow(int(p.get("id") or 0), int(p["player_id"]), d,
                                 p.get("mode") or "regular", p.get("season") or data.season,
                                 bool(p.get("is_x2"))))
    return seeds


def _season_bounds(data: SeasonData) -> tuple[date, date]:
    dates = [_as_date(g["date"]) for g in data.games]
    return min(dates), max(dates)


def _diverging_nights(official: BacktestResult, logs: BacktestResult) -> list[date]:
    by_official = {n.night: n.points for n in official.nights}
    by_logs = {n.night: n.points for n in logs.nights}
    return sorted(d for d in (set(by_official) & set(by_logs)) if by_official[d] != by_logs[d])


@dataclass(frozen=True)
class Row:
    label: str
    mode: str
    result: BacktestResult


def run(data: SeasonData, start: date, end: date, decays: list[float] | None = None) -> dict:
    """Calcule toutes les lignes du rapport (lecture seule, aucun accès
    réseau/base — `data` est déjà chargée)."""
    decays = list(decays or [])
    regular_dates = _regular_dates(data, start, end)
    seed_picks = _seed_picks(data, start)

    official = _only(_official_user_result(data, start, end), regular_dates)
    logs_based = _only(user_result(data, start, end), regular_dates)

    rows = [Row("Mes vrais picks (officiel)", "n/a", official),
            Row("Mes vrais picks (logs)", "n/a", logs_based)]

    for strategy in STRATEGIES:
        for mode in INJURY_MODES:
            res = _only(simulate(data, start, end, strategy, injury_mode=mode, seed_picks=seed_picks),
                       regular_dates)
            label = strategy if strategy != "plan" else f"plan (decay={FUTURE_DECAY}, défaut)"
            rows.append(Row(label, mode, res))
        if strategy == "plan":
            for decay in decays:
                for mode in INJURY_MODES:
                    res = _only(simulate(data, start, end, strategy, injury_mode=mode, decay=decay,
                                         seed_picks=seed_picks), regular_dates)
                    rows.append(Row(f"plan (decay={decay})", mode, res))

    diverging = _diverging_nights(official, logs_based)

    full_start, full_end = _season_bounds(data)
    full_regular_dates = _regular_dates(data, full_start, full_end)
    full_official = _only(_official_user_result(data, full_start, full_end), full_regular_dates)
    full_logs = _only(user_result(data, full_start, full_end), full_regular_dates)

    last_of_month = _last_regular_night_of_month(data)
    end_month = (end.year, end.month)
    x2_truncated = (end.month in X2_MONTHS and last_of_month.get(end_month) is not None
                   and last_of_month[end_month] > end)

    return {
        "rows": rows,
        "diverging_nights": diverging,
        "total_nights": len(official.nights),
        "full_season": {"start": full_start, "end": full_end, "officiel": full_official, "logs": full_logs},
        "x2_truncated_month": end_month if x2_truncated else None,
    }


def _verdict(by_mode: dict[tuple[str, str], "Row"]) -> tuple[str, dict[str, float]]:
    """Règle d'activation appliquée littéralement : plan − meilleur choix par
    mode, et le verdict binaire (« bat » seulement si les deux modes gagnent)."""
    diffs = {}
    for mode in INJURY_MODES:
        plan_row = by_mode[(f"plan (decay={FUTURE_DECAY}, défaut)", mode)]
        ba_row = by_mode[("best_available", mode)]
        diffs[mode] = plan_row.result.average - ba_row.result.average
    beats_both = all(diffs[m] > 0 for m in INJURY_MODES)
    verdict = "le plan bat le meilleur choix dans les deux modes" if beats_both \
        else "le plan ne bat pas le meilleur choix dans les deux modes"
    return verdict, diffs


def render_report(season: str, start: date, end: date, decays: list[float], data: dict) -> str:
    rows: list[Row] = data["rows"]
    lines = [f"# Backtest {season} — {start.isoformat()} → {end.isoformat()}", ""]

    lines += [
        "## Comparaison contre mes perfs (même fenêtre, mêmes soirées)",
        "",
        "| Stratégie | Mode blessures | Moyenne (R14) | Zéros | Gain x2 | Soirées |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r.label} | {r.mode} | {r.result.average:.2f} | {r.result.zeros} | "
                     f"{r.result.x2_gain:+d} | {len(r.result.nights)} |")
    lines.append("")
    n_div = len(data["diverging_nights"])
    lines.append(f"Écart officiel vs logs (même sélection, même x2, note différente) : {n_div} soirée(s) "
                 f"sur {data['total_nights']}"
                 + (f" ({', '.join(d.isoformat() for d in data['diverging_nights'])})." if n_div else "."))
    lines.append("")

    fs = data["full_season"]
    lines += [
        "## Contexte : ma moyenne sur toute la saison régulière",
        "",
        f"Saison régulière complète ({fs['start'].isoformat()} → {fs['end'].isoformat()}), mes vrais picks :",
        f"- officiel : {fs['officiel'].average:.2f} sur {len(fs['officiel'].nights)} soirées",
        f"- logs : {fs['logs'].average:.2f} sur {len(fs['logs'].nights)} soirées",
        "",
    ]

    lines += ["## Limites", ""]
    lines.append("- Aucun historique des statuts de blessures en base : deux bornes plutôt qu'une vérité "
                 "unique — `none` (personne n'est jamais déclaré blessé, pessimiste : le moteur pouvait "
                 "choisir un joueur qui ne jouera pas) et `dnp_oracle` (un joueur ayant DNP le soir même "
                 "après avoir joué au moins un de ses 5 derniers matchs est déclaré « Out », optimiste). "
                 "L'utilisateur avait l'information du jour en le pickant réellement : la comparaison "
                 "équitable est entre ces deux bornes, pas contre l'une des deux isolément.")
    lines.append("- Fenêtre février-avril par défaut : la saison 2024-25 n'est pas chargée en base, il y a "
                 "donc peu d'historique de profils avant février de la saison en cours.")
    lines.append(f"- Chaque simulation démarre amorcée par mes vrais picks des {SEED_DAYS} jours avant le "
                 "début de la fenêtre (cooldown R3 et x2 du mois en cours, R10) : la comparaison démarre "
                 "sous les mêmes contraintes que moi. Au-delà, l'historique simulé de chaque stratégie "
                 "diverge du mien au fil des soirées (chacune fait ses propres picks) : c'est voulu, "
                 "c'est ce qu'on compare.")
    if data["x2_truncated_month"] is not None:
        y, m = data["x2_truncated_month"]
        lines.append(f"- La fenêtre se termine avant la fin du mois {m:02d}/{y} (mois x2) : asymétrie en "
                     "faveur de `plan` pour ce mois — `best_available` (référence naïve) pose son x2 sur "
                     "la dernière soirée éligible du mois, hors fenêtre, donc perd le x2 de ce mois ; "
                     "`plan` (planificateur MILP, S3) peut le poser plus tôt dans le mois dès que la fin du "
                     "mois est visible dans son horizon de 35 jours, donc à l'intérieur de la fenêtre.")
    lines.append("- Saison régulière uniquement (R14, R10) : les soirées de playoffs, s'il y en a dans la "
                 "fenêtre, sont exclues du calcul.")
    lines.append("")

    lines += ["## Conclusion", ""]
    by_mode: dict[tuple[str, str], Row] = {(r.label, r.mode): r for r in rows}
    verdict, diffs = _verdict(by_mode)
    lines.append(f"- Règle d'activation : {verdict}.")
    for mode in INJURY_MODES:
        lines.append(f"  - mode {mode} : plan − meilleur choix = {diffs[mode]:+.2f}")

    ref = by_mode[("Mes vrais picks (logs)", "n/a")].result.average
    lines.append(f"- Écart à ma moyenne réelle (référence : mes picks notés via les logs, {ref:.2f}) :")
    for strategy_label in ("best_available", f"plan (decay={FUTURE_DECAY}, défaut)"):
        for mode in INJURY_MODES:
            avg = by_mode[(strategy_label, mode)].result.average
            lines.append(f"  - {strategy_label} / {mode} : {avg - ref:+.2f}")

    for decay in decays:
        lines.append(f"- decay={decay} (plan, diagnostic, hors règle d'activation) :")
        for mode in INJURY_MODES:
            plan_row = by_mode[(f"plan (decay={decay})", mode)]
            ba_row = by_mode[("best_available", mode)]
            lines.append(f"  - mode {mode} : plan − meilleur choix = "
                         f"{plan_row.result.average - ba_row.result.average:+.2f}")
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest en lecture seule (best_available/plan vs vrais picks).")
    parser.add_argument("--season", required=True)
    parser.add_argument("--from", dest="start", required=True, help="AAAA-MM-JJ")
    parser.add_argument("--to", dest="end", required=True, help="AAAA-MM-JJ")
    parser.add_argument("--decay", default=None, help="liste séparée par des virgules, ex: 0.97,0.985,1.0")
    parser.add_argument("--out", default=None, help="chemin du rapport Markdown (défaut : docs/backtest/<saison>-sr.md)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    from engine.io.repo import SupabaseRepo

    args = _parse_args(argv)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    decays = [float(x) for x in args.decay.split(",")] if args.decay else []
    out = Path(args.out) if args.out else Path(f"docs/backtest/{args.season}-sr.md")

    repo = SupabaseRepo.from_env()
    data = load_season(repo, args.season)

    result = run(data, start, end, decays)
    report = render_report(args.season, start, end, decays, result)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    by_mode = {(r.label, r.mode): r for r in result["rows"]}
    verdict, _diffs = _verdict(by_mode)
    print(f"backtest {args.season} {start}→{end} : rapport écrit dans {out} "
          f"({result['total_nights']} soirées, {len(result['diverging_nights'])} écart(s) officiel/logs)")
    print(f"  Règle d'activation : {verdict}.")


if __name__ == "__main__":
    main()
