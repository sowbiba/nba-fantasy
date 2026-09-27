"""Job `elo_report` (lecture seule) : rejoue une saison match par match pour
choisir les paramètres de l'Elo maison (spec
`docs/superpowers/specs/2026-09-28-l3a-elo-design.md` §1, tâche 3 du plan
L3a).

N'écrit jamais en base : ne charge les données que via `load_season`
(`engine.backtest.data`, elle-même limitée aux méthodes `load_*` de
`SupabaseRepo`). Le rapport Markdown est le seul artefact produit, sur
disque.

Rejeu : les matchs éligibles de la saison (`engine.stats.elo.is_countable`)
sont rejoués en ordre chronologique (date, id) depuis le début de la saison,
notes de départ 1500 — pas de fuite du futur, comme `ratings_before`. Pour
éviter le O(n²) d'un appel à `ratings_before(before=D)` à chaque soirée D,
les notes sont mises à jour de proche en proche avec `apply_game` (helper
incrémental de `engine.stats.elo`, aussi utilisé par `ratings_before`) : une
seule passe par (k, home_advantage) plutôt qu'une par soirée. Comme la mise
à jour des notes ne dépend jamais de `elo_per_share` (qui ne corrige que la
probabilité prédite, pas le résultat réellement observé), les 4 valeurs de
la grille `elo_per_share` sont évaluées sans rejouer les notes : un seul
passage par combinaison (k, home_advantage) suffit pour les 4.

Seuls les matchs de la fenêtre d'évaluation (défaut : à partir du 1er
décembre de la saison) comptent dans les métriques ; les matchs antérieurs
ne servent qu'à faire chauffer les notes depuis 1500.

Absents pour la correction blessures (calibration, pas de statuts en base
avant le rejeu) = joueurs de rotation de l'équipe (part de production
`team_shares` ≥ 5 %) sans minutes ce soir-là (log absent ou 0 minute) —
comme le mode `dnp_oracle` du backtest L2, mais sans l'heuristique
« a joué un de ses 5 derniers matchs » : ici on connaît déjà le vrai résultat
du soir (`played_on`), donc pas besoin d'oracle.
"""
import argparse
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from engine.backtest.data import SeasonData, load_season, played_on
from engine.stats.elo import (
    ABSENT_MIN_SHARE,
    EloParams,
    apply_game,
    as_date,
    game_season,
    is_countable,
    predict,
    team_shares,
)

K_GRID = (15.0, 20.0, 25.0)
HCA_GRID = (40.0, 70.0, 100.0)
SHARE_GRID = (0.0, 150.0, 300.0, 450.0)
PROB_EPS = 1e-9           # évite log(0) dans la perte logarithmique


def _default_from(season: str) -> date:
    """1er décembre de l'année de début de la saison (« 2025-26 » → 2025-12-01)."""
    return date(int(season[:4]), 12, 1)


def _eligible_games(games: list[dict]) -> list[dict]:
    """Matchs éligibles à l'Elo, triés (date, id) — même filtre et même ordre
    que `ratings_before` (R11/R12, pas de match reporté/sans score)."""
    eligible = [g for g in games if is_countable(g)]
    eligible.sort(key=lambda g: (as_date(g["date"]), g["id"]))
    return eligible


def _absent_shares_by_game(data: SeasonData, window_games: list[dict]) -> dict[str, dict[str, float]]:
    """Part des absents de rotation par équipe, par `game_id` — uniquement
    pour les matchs de la fenêtre d'évaluation (seuls ceux-là en ont besoin,
    voir `_replay`) ; ne dépend d'aucun paramètre de la grille, donc calculée
    une seule fois plutôt qu'à chaque (k, home_advantage). `team_shares(...,
    before=d)` ne regarde que les logs antérieurs au match (R7/pas de fuite) ;
    « absent » = pas de minutes CE soir-là (log manquant ou 0 minute), vérifié
    avec `played_on` (qui, lui, regarde bien le jour même — pas une fuite :
    le rapport évalue après coup, il ne prédit rien pour de vrai)."""
    result: dict[str, dict[str, float]] = {}
    for game in window_games:
        d = as_date(game["date"])
        shares_by_team = {}
        for team in (game["home_team"], game["away_team"]):
            shares = team_shares(data.logs, team, d)
            absent = sum(share for pid, share in shares.items()
                        if share >= ABSENT_MIN_SHARE and not played_on(data, pid, d))
            shares_by_team[team] = absent
        result[game["id"]] = shares_by_team
    return result


@dataclass(frozen=True)
class GridRow:
    k: float
    home_advantage: float
    elo_per_share: float
    n: int
    home_win_rate: float       # fréquence réelle de victoires à domicile sur la fenêtre
    accuracy: float            # part des matchs où le favori prédit (p > 0.5) l'a emporté
    brier: float
    log_loss: float
    margin_slope: float | None = None   # pente écart réel / écart attendu (M-4), None si non calculable


def _log_loss(y: float, p: float) -> float:
    p = min(max(p, PROB_EPS), 1 - PROB_EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _ols_slope(pairs: list[tuple[float, float]]) -> float | None:
    """Pente des moindres carrés de `y` (écart réel) sur `x` (écart Elo
    attendu avant-match) : `cov(x, y) / var(x)`. `None` si moins de 2 points
    ou si `x` est constant (pente indéfinie) — le rapport vérifie
    `points_per_elo` (≈1 attendu), pas une exigence produit (M-4)."""
    n = len(pairs)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    if var_x == 0:
        return None
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    return cov_xy / var_x


def _replay(data: SeasonData, eligible: list[dict], absent_shares: dict[str, dict[str, float]],
           from_date: date, k: float, hca: float, share_grid: tuple[float, ...] = SHARE_GRID) -> list[GridRow]:
    """Une seule passe chronologique pour (k, home_advantage) : rejoue les
    notes match par match (`apply_game`, incrémental — pas de rappel à
    `ratings_before`) et, pour chaque match de la fenêtre d'évaluation,
    calcule la prédiction des `elo_per_share` de `share_grid` (par défaut
    `SHARE_GRID`) avant de mettre les notes à jour avec le vrai résultat."""
    predictions: dict[float, list[tuple[float, float]]] = {eps: [] for eps in share_grid}
    margins: dict[float, list[tuple[float, float]]] = {eps: [] for eps in share_grid}   # (attendu, réel)
    ratings: dict[str, float] = {}

    for game in eligible:
        d = as_date(game["date"])
        if d >= from_date:
            absent = absent_shares[game["id"]]
            home_score, away_score = game["home_score"], game["away_score"]
            actual_home = 1.0 if home_score > away_score else 0.0
            actual_margin = float(home_score - away_score)
            for eps in share_grid:
                params = EloParams(k=k, home_advantage=hca, elo_per_share=eps)
                pred = predict(game, ratings, absent, params)
                predictions[eps].append((actual_home, pred.home_win_prob))
                margins[eps].append((pred.expected_margin, actual_margin))
        # Mise à jour des notes avec le vrai résultat — indépendante de
        # `elo_per_share` (qui ne corrige que la probabilité prédite, pas la
        # note elle-même). `home_advantage` influe sur la mise à jour (via
        # `win_prob`), donc une passe par (k, home_advantage), pas par
        # elo_per_share.
        apply_game(ratings, game, EloParams(k=k, home_advantage=hca))

    rows = []
    for eps in share_grid:
        pairs = predictions[eps]
        n = len(pairs)
        if n == 0:
            # M-1 : aucun match dans la fenêtre pour cette combinaison → perte
            # logarithmique infinie (jamais un minimum valide), pas 0.0 (qui
            # gagnerait `min()` à tort sur une fenêtre dégénérée).
            rows.append(GridRow(k, hca, eps, 0, 0.0, 0.0, 0.0, math.inf, None))
            continue
        home_win_rate = sum(y for y, _ in pairs) / n
        accuracy = sum(1 for y, p in pairs if (p > 0.5) == (y == 1.0)) / n
        brier = sum((p - y) ** 2 for y, p in pairs) / n
        log_loss = sum(_log_loss(y, p) for y, p in pairs) / n
        slope = _ols_slope(margins[eps])
        rows.append(GridRow(k, hca, eps, n, home_win_rate, accuracy, brier, log_loss, slope))
    return rows


def run(data: SeasonData, season: str, from_date: date | None = None, *,
       k_grid: tuple[float, ...] = K_GRID, hca_grid: tuple[float, ...] = HCA_GRID,
       share_grid: tuple[float, ...] = SHARE_GRID) -> dict:
    """Calcule la grille complète et la référence naïve (lecture seule,
    aucun accès réseau/base — `data` est déjà chargée). `k_grid`/`hca_grid`/
    `share_grid` permettent de rejouer sur une grille plus large que la
    grille par défaut (option CLI `--k`/`--hca`/`--eps`)."""
    from_date = from_date or _default_from(season)
    eligible = [g for g in _eligible_games(data.games) if game_season(g) == season]
    window_games = [g for g in eligible if as_date(g["date"]) >= from_date]
    absent_shares = _absent_shares_by_game(data, window_games)

    rows: list[GridRow] = []
    for k in k_grid:
        for hca in hca_grid:
            rows.extend(_replay(data, eligible, absent_shares, from_date, k, hca, share_grid))

    n_window = len(window_games)
    home_win_rate = (sum(1 for g in window_games if g["home_score"] > g["away_score"]) / n_window
                     if n_window else 0.0)
    naive_pairs = [(1.0 if g["home_score"] > g["away_score"] else 0.0, home_win_rate)
                  for g in window_games]
    naive_brier = (sum((p - y) ** 2 for y, p in naive_pairs) / n_window) if n_window else 0.0
    naive_log_loss = (sum(_log_loss(y, p) for y, p in naive_pairs) / n_window) if n_window else 0.0

    def _best(candidates: list[GridRow]) -> GridRow | None:
        # M-1 : une combinaison à `n = 0` a `log_loss = inf` — jamais un
        # minimum valide. Si TOUTES les candidates sont dégénérées (fenêtre
        # vide), il n'y a pas de « meilleur jeu » à rapporter.
        best_row = min(candidates, key=lambda r: r.log_loss) if candidates else None
        return best_row if best_row is not None and math.isfinite(best_row.log_loss) else None

    best = _best(rows)
    no_injury_rows = [r for r in rows if r.elo_per_share == 0.0]
    injury_rows = [r for r in rows if r.elo_per_share > 0.0]
    best_no_injury = _best(no_injury_rows)
    # « Apport de la correction blessures » = meilleur jeu AVEC correction
    # (elo_per_share > 0) contre le meilleur jeu SANS (elo_per_share = 0) —
    # littéralement la comparaison du brief, pas le minimum global (qui
    # inclurait elo_per_share = 0 et masquerait un apport négatif derrière un
    # gain à zéro).
    best_with_injury = _best(injury_rows)
    injury_gain = (best_no_injury.log_loss - best_with_injury.log_loss) \
        if best_no_injury and best_with_injury else 0.0

    return {
        "from_date": from_date,
        "n_window": n_window,
        "naive_home_win_rate": home_win_rate,
        "naive_brier": naive_brier,
        "naive_log_loss": naive_log_loss,
        "rows": rows,
        "best": best,
        "best_no_injury": best_no_injury,
        "best_with_injury": best_with_injury,
        "injury_gain": injury_gain,
        "k_grid": k_grid,
        "hca_grid": hca_grid,
    }


def render_report(season: str, result: dict) -> str:
    lines = [f"# Rapport Elo {season} — validation et choix des paramètres", ""]
    lines.append(f"Fenêtre d'évaluation : à partir du {result['from_date'].isoformat()} "
                 f"({result['n_window']} matchs). Notes rejouées depuis le début de la saison, "
                 "départ à 1500 pour chaque équipe.")
    lines.append("")

    lines += ["## Référence naïve — « l'équipe à domicile gagne »", ""]
    lines.append(f"Probabilité constante = fréquence de victoires à domicile observée sur la fenêtre "
                 f"({result['naive_home_win_rate']:.3f}) : Brier = {result['naive_brier']:.4f}, "
                 f"perte logarithmique = {result['naive_log_loss']:.4f}.")
    lines.append("")

    best = result["best"]
    if best is not None:
        lines += ["## Meilleur jeu de paramètres (perte logarithmique)", ""]
        lines.append(f"k = {best.k:g}, home_advantage = {best.home_advantage:g}, "
                     f"elo_per_share = {best.elo_per_share:g} → perte logarithmique = "
                     f"{best.log_loss:.4f} (Brier = {best.brier:.4f}, précision = "
                     f"{best.accuracy:.3f}, sur {best.n} matchs).")
        gain_vs_naive = result["naive_log_loss"] - best.log_loss
        lines.append(f"Écart à la référence naïve : {gain_vs_naive:+.4f} en perte logarithmique "
                     f"({'mieux' if gain_vs_naive > 0 else 'moins bien' if gain_vs_naive < 0 else 'égal'} "
                     "que la référence).")
        # M-2 : le minimum global n'est significatif que s'il n'est pas au
        # bord de la grille cherchée (sinon la vraie plage optimale est peut-
        # être hors grille) — averti seulement si la grille avait plus d'une
        # valeur (une grille à un seul point n'est pas une recherche).
        k_grid, hca_grid = result.get("k_grid") or (), result.get("hca_grid") or ()
        edges = []
        if len(k_grid) > 1 and best.k in (min(k_grid), max(k_grid)):
            edges.append(f"k = {best.k:g}")
        if len(hca_grid) > 1 and best.home_advantage in (min(hca_grid), max(hca_grid)):
            edges.append(f"home_advantage = {best.home_advantage:g}")
        if edges:
            lines.append(f"⚠ à la borne de la grille : {', '.join(edges)} — la vraie valeur optimale est "
                         "peut-être hors grille, élargir `--k`/`--hca` avant de figer les défauts.")
        # M-4 : vérifie `points_per_elo` (1/28 par défaut) — pente attendue ≈1
        # si l'échelle des points est correctement calibrée sur cette grille.
        if best.margin_slope is not None:
            lines.append(f"Pente écart réel / écart attendu (avant-match) = {best.margin_slope:.3f} "
                         "(≈1 attendu si `points_per_elo` est bien calibré sur ce jeu de paramètres).")
        lines.append("")

    lines += ["## Apport de la correction blessures", ""]
    best_no_injury = result["best_no_injury"]
    best_with_injury = result["best_with_injury"]
    if best_no_injury is not None and best_with_injury is not None:
        lines.append(f"Meilleur jeu avec correction (elo_per_share > 0) : k = {best_with_injury.k:g}, "
                     f"home_advantage = {best_with_injury.home_advantage:g}, "
                     f"elo_per_share = {best_with_injury.elo_per_share:g} → perte logarithmique = "
                     f"{best_with_injury.log_loss:.4f}. Meilleur jeu à elo_per_share = 0 (correction "
                     f"désactivée) : k = {best_no_injury.k:g}, home_advantage = "
                     f"{best_no_injury.home_advantage:g} → perte logarithmique = "
                     f"{best_no_injury.log_loss:.4f}.")
        gain = result["injury_gain"]
        if gain > 0:
            lines.append(f"Gain de la correction : {gain:+.4f} en perte logarithmique — la correction "
                         "blessures améliore la prédiction, à activer dans `EloParams` par défaut "
                         f"(elo_per_share = {best_with_injury.elo_per_share:g}).")
        else:
            lines.append(f"Écart : {gain:+.4f} en perte logarithmique — la correction blessures "
                         "n'améliore pas la prédiction sur cette fenêtre, à laisser désactivée "
                         "(`elo_per_share = 0`) par défaut.")
        lines.append("")

    lines += ["## Tableau complet", ""]
    lines += [
        "| k | home_advantage | elo_per_share | matchs | taux domicile réel | précision | Brier | "
        "perte log |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(result["rows"], key=lambda r: r.log_loss):
        lines.append(f"| {r.k:g} | {r.home_advantage:g} | {r.elo_per_share:g} | {r.n} | "
                     f"{r.home_win_rate:.3f} | {r.accuracy:.3f} | {r.brier:.4f} | {r.log_loss:.4f} |")
    lines.append("")

    lines += ["## Limites", ""]
    lines.append("- Absents de calibration = joueurs de rotation (part de production ≥ 5 %) sans "
                 "minutes ce soir-là — pas les statuts d'indisponibilité réels du jour (aucun historique "
                 "de statuts en base) : les rapports de blessures existaient avant le match dans la "
                 "réalité, cette proxy est donc optimiste (comme `dnp_oracle` au backtest L2), mais sans "
                 "fuite (le résultat du match lui-même n'entre jamais dans la correction).")
    lines.append("- Fenêtre d'évaluation par défaut à partir du 1er décembre : les deux premiers mois de "
                 "la saison chauffent les notes depuis 1500 sans compter dans les métriques.")
    lines.append("- Un seul jeu de paramètres est choisi par saison ; pas de validation croisée entre "
                 "saisons (une seule saison chargée en base à ce stade).")
    lines.append("")
    return "\n".join(lines)


def _parse_grid(raw: str | None, default: tuple[float, ...]) -> tuple[float, ...]:
    """`--k`/`--hca`/`--eps` : liste de flottants séparés par des virgules,
    pour rejouer le rapport sur une grille plus large que la grille par
    défaut (défaut : la grille du module, inchangée si l'option est omise)."""
    if raw is None or not raw.strip():
        return default
    return tuple(float(v.strip()) for v in raw.split(",") if v.strip())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rapport Elo en lecture seule : validation et choix des paramètres (grille k, "
                    "home_advantage, elo_per_share) sur une saison déjà jouée.")
    parser.add_argument("--season", required=True)
    parser.add_argument("--from", dest="from_date", default=None, help="AAAA-MM-JJ (défaut : 1er décembre)")
    parser.add_argument("--out", default=None, help="chemin du rapport Markdown "
                                                     "(défaut : docs/backtest/elo-<saison>.md)")
    parser.add_argument("--k", default=None, help="grille k séparée par des virgules "
                                                   f"(défaut : {','.join(f'{v:g}' for v in K_GRID)})")
    parser.add_argument("--hca", default=None, help="grille home_advantage séparée par des virgules "
                                                     f"(défaut : {','.join(f'{v:g}' for v in HCA_GRID)})")
    parser.add_argument("--eps", default=None, help="grille elo_per_share séparée par des virgules "
                                                     f"(défaut : {','.join(f'{v:g}' for v in SHARE_GRID)})")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    from engine.io.repo import SupabaseRepo

    args = _parse_args(argv)
    from_date = date.fromisoformat(args.from_date) if args.from_date else None
    out = Path(args.out) if args.out else Path(f"docs/backtest/elo-{args.season}.md")
    k_grid = _parse_grid(args.k, K_GRID)
    hca_grid = _parse_grid(args.hca, HCA_GRID)
    share_grid = _parse_grid(args.eps, SHARE_GRID)

    repo = SupabaseRepo.from_env()
    data = load_season(repo, args.season)

    result = run(data, args.season, from_date, k_grid=k_grid, hca_grid=hca_grid, share_grid=share_grid)
    report = render_report(args.season, result)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    best = result["best"]
    print(f"elo_report {args.season} : rapport écrit dans {out} ({result['n_window']} matchs, fenêtre "
         f"depuis {result['from_date'].isoformat()})")
    if best is not None:
        print(f"  Meilleur jeu : k={best.k:g} home_advantage={best.home_advantage:g} "
             f"elo_per_share={best.elo_per_share:g} (perte log = {best.log_loss:.4f})")


if __name__ == "__main__":
    main()
