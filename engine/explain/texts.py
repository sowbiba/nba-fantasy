"""Argumentaires FR (saison régulière) des recommandations et du plan."""
from engine.strategy.planner import Cell

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def tier(rank: int) -> str:
    if rank <= 10:
        return "elite"
    return "solid" if rank <= 25 else "filler"


def describe_night(cell: Cell) -> str:
    sep = "vs" if cell.ctx.is_home else "@"
    return f"{_JOURS[cell.night.weekday()]} {cell.night:%d/%m} {sep} {cell.ctx.opponent}"


def reco_texts(rec, rank: int, player_name: str) -> tuple[list[str], list[str], str, list[str]]:
    c = rec.cell
    pros: list[str] = []
    cons: list[str] = []
    tags: list[str] = []
    if c.ctx.is_home:
        pros.append("🏠 Match à domicile")
        tags.append("home")
    else:
        cons.append("✈️ Match à l'extérieur")
    delta = round((c.ctx.opp_factor - 1.0) * 100)
    if delta >= 5:
        pros.append(f"🎯 Défense adverse faible à son poste (+{delta} %)")
    elif delta <= -5:
        cons.append(f"🛡️ Défense adverse solide à son poste ({delta} %)")
    if c.ctx.teammate_out and c.ctx.teammate_factor > 1.005:
        pros.append(f"🚀 {c.ctx.teammate_out} absent : plus de ballons (+{round((c.ctx.teammate_factor - 1) * 100)} %)")
        tags.append("coequipier_absent")
    if c.ctx.rest_days == 0:
        cons.append("😴 2e soir d'un back-to-back : risque de mise au repos")
        tags.append("b2b")
    elif c.ctx.rest_days is not None and c.ctx.rest_days >= 2:
        pros.append(f"🔋 {c.ctx.rest_days} jours de repos")
    if c.p_play < 0.95:
        cons.append(f"⚠️ Risque d'absence : {round(c.p_play * 100)} % de chances de jouer")
        tags.append("dnp_risk")
    else:
        pros.append(f"✅ {round(c.p_play * 100)} % de chances de jouer")
    blocage = f"🔒 Le jouer ce soir le bloque jusqu'au {rec.locked_until:%d/%m}"
    if rec.best_future is not None:
        blocage += f" (meilleur soir à venir : {describe_night(rec.best_future)}, {rec.best_future.projection:.0f} pts projetés)"
    cons.append(blocage)
    if rec.reserved_on is not None:
        cons.append(f"📌 Réservé le {rec.reserved_on:%d/%m} : le jouer ce soir libère cette soirée, à repourvoir")
        tags.append("reserve")
    if rank <= 3:
        tags.append("reco_du_soir")
    if rec.is_pick:
        tags.append("mon_pick")
    verdict = (f"{player_name} : {c.projection:.0f} pts projetés, valeur {c.value:.1f} "
               f"une fois le risque d'absence et le blocage de 30 jours pris en compte.")
    return pros, cons, verdict, tags


def plan_explanation(cell: Cell) -> str:
    return (f"{describe_night(cell)} · {cell.projection:.0f} pts projetés · "
            f"{round(cell.p_play * 100)} % de chances de jouer")


def challenge_explanation(cell: Cell, reserved: Cell | None, reserved_name: str) -> str:
    """Texte du plan quand il conteste une réservation : `cell` est le joueur
    que le plan préfère, `reserved` la cellule du joueur réservé ce soir-là
    (None : pas de match ou pas de profil)."""
    base = plan_explanation(cell)
    if reserved is None:
        return f"{base} · {reserved_name} n'a pas de match ce soir-là"
    if reserved.p_play <= 0:
        return f"{base} · {reserved_name} ne devrait pas jouer"
    gain = cell.p_play * cell.projection - reserved.p_play * reserved.projection
    return f"{base} · {gain:+.0f} pts attendus par rapport à {reserved_name}"
