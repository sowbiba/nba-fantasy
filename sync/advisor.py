"""Generate POUR / CONTRE / VERDICT argumentaires for each player."""


def generate_argumentaire(context: dict) -> tuple[list[str], list[str]]:
    pros = []
    cons = []
    name = context["player_name"]
    avg_l5 = context["avg_l5"]
    avg_season = context["avg_season"]

    if avg_l5 > avg_season * 1.10:
        pct = round((avg_l5 / avg_season - 1) * 100)
        pros.append(f"En feu : {avg_l5:.1f} TTFL avg sur les 5 derniers matchs (+{pct}% vs saison)")
    elif avg_l5 < avg_season * 0.90:
        pct = round((1 - avg_l5 / avg_season) * 100)
        cons.append(f"En méforme : {avg_l5:.1f} TTFL avg L5 (-{pct}% vs saison {avg_season:.1f})")

    matchup_rank = context["matchup_rank"]
    position = context["matchup_position"]
    opponent = context["opponent"]
    if matchup_rank <= 5:
        pros.append(f"Matchup juteux : {opponent} encaisse le {matchup_rank}e plus de pts TTFL aux {position} en playoffs")
    elif matchup_rank >= 25:
        cons.append(f"Matchup difficile : {opponent} est top {30 - matchup_rank + 1} défense aux {position}")

    hw, aw = context["series_score"]
    game_num = context["game_number"]
    if context["is_home"]:
        series_desc = f"{hw}-{aw}"
        tight = abs(hw - aw) <= 1
        if tight:
            pros.append(f"Game {game_num} à domicile, série {series_desc} (enjeu max, crowd factor)")
        else:
            pros.append(f"Game {game_num} à domicile")
    else:
        cons.append(f"Match à l'extérieur (Game {game_num})")

    if hw == 3 or aw == 3:
        if (hw == 3 and not context["is_home"]) or (aw == 3 and context["is_home"]):
            pros.append("Match d'élimination pour l'adversaire : intensité max des deux côtés")
        else:
            pros.append("Possible match de clôture : motivation pour finir la série")

    days_rest = context["days_rest"]
    if days_rest == 0:
        cons.append("Back-to-back : risque de fatigue et minutes réduites")
    elif days_rest >= 3:
        pros.append(f"{days_rest} jours de repos : frais et reposé")

    floor = context["floor"]
    ceiling = context["ceiling"]
    stddev = context["stddev"]
    if stddev < 10:
        pros.append(f"Floor très haut : jamais sous {floor} TTFL sur les 20 derniers matchs")
    elif stddev > 18:
        cons.append(f"Joueur volatile : floor {floor}, ceiling {ceiling} (écart important)")

    teammate_out = context.get("teammate_out")
    if teammate_out:
        pros.append(f"Sans {teammate_out} : plus de ballons, usage en hausse")

    injury = context.get("injury_status")
    if injury:
        cons.append(f"Statut {injury} : risque de minutes limitées ou forfait de dernière minute")

    tier = context["tier"]
    elites = context["elites_remaining"]
    days = context["game_days_remaining"]
    if tier == "elite":
        cons.append(f"C'est un de tes {elites} elites restants pour ~{days} jours de match")
    elif tier == "solid":
        if elites > 3:
            pros.append("Pick solide qui préserve ton capital elite")
    elif tier == "filler":
        pros.append("Pick économique : garde tes cartouches pour les gros soirs")

    return pros, cons


def generate_verdict(should_burn: bool, tier: str, tonight_score: float, best_future_description: str) -> str:
    if tier == "filler":
        return (f"Pick safe à {tonight_score:.0f} estimé. "
                "Bon choix pour une soirée sans spot premium — préserve tes meilleurs joueurs.")
    if should_burn:
        return (f"Excellent spot ce soir ({tonight_score:.0f} estimé). "
                f"Recommandation : JOUE-LE. Meilleur prochain spot identifié : {best_future_description}.")
    else:
        return (f"Bon joueur mais meilleur spot à venir : {best_future_description}. "
                f"Recommandation : GARDE-LE pour maximiser son potentiel.")
