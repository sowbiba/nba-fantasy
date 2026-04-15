"""Generate POUR / CONTRE / VERDICT argumentaires for each player.

Philosophy: every reasoning factor the engine uses should be surfaced to the
user in plain French. The app is a strategic coach, not a black box.
"""


def generate_argumentaire(context: dict) -> tuple[list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []

    avg_l5 = context["avg_l5"] or 0
    avg_l10 = context.get("avg_l10", 0) or 0
    avg_season = context["avg_season"] or 0
    home_avg = context.get("home_avg", 0) or 0
    away_avg = context.get("away_avg", 0) or 0

    # --- Forme (L5 vs saison) ---
    if avg_season > 0:
        if avg_l5 > avg_season * 1.15:
            pct = round((avg_l5 / avg_season - 1) * 100)
            pros.append(
                f"🔥 En feu : {avg_l5:.1f} TTFL avg sur les 5 derniers (+{pct}% vs saison {avg_season:.1f})"
            )
        elif avg_l5 > avg_season * 1.05:
            pros.append(
                f"📈 Forme au-dessus de sa saison ({avg_l5:.1f} avg L5 vs {avg_season:.1f} saison)"
            )
        elif avg_l5 < avg_season * 0.85:
            pct = round((1 - avg_l5 / avg_season) * 100)
            cons.append(
                f"📉 En méforme : {avg_l5:.1f} avg L5 (-{pct}% vs saison {avg_season:.1f})"
            )

    # --- Floor / ceiling / régularité ---
    ceiling = context.get("ceiling", 0) or 0
    floor = context.get("floor", 0) or 0
    stddev = context.get("stddev", 0) or 0
    if ceiling >= 70 and avg_l5 >= 35:
        pros.append(
            f"💥 Ceiling explosif : a déjà fait {ceiling} TTFL dans ses 20 derniers matchs"
        )
    if stddev and stddev < 10 and avg_l5 >= 30:
        pros.append(
            f"🛡️ Joueur fiable : floor à {floor} TTFL (écart-type {stddev:.1f})"
        )
    elif stddev > 18:
        cons.append(
            f"🎲 Joueur volatile : floor {floor} / ceiling {ceiling} (écart-type {stddev:.1f})"
        )

    # --- Matchup défensif ---
    matchup_rank = context["matchup_rank"]
    position = context["matchup_position"]
    opponent = context["opponent"]
    if matchup_rank <= 3:
        pros.append(
            f"🎯 Matchup juteux : {opponent} encaisse le {matchup_rank}e plus de points TTFL aux {position}"
        )
    elif matchup_rank <= 8:
        pros.append(
            f"✓ Bon matchup : {opponent} est top {matchup_rank} en concession de TTFL aux {position}"
        )
    elif matchup_rank >= 25:
        cons.append(
            f"🧱 Matchup difficile : {opponent} est top {30 - matchup_rank + 1} défense aux {position}"
        )

    # --- Home / Away ---
    hw, aw = context["series_score"]
    game_num = context["game_number"]
    is_home = context["is_home"]
    if is_home:
        tight = abs(hw - aw) <= 1
        if tight and (hw + aw) >= 3:
            pros.append(
                f"🏠 Game {game_num} à domicile · série {hw}-{aw} (enjeu max, crowd factor)"
            )
        else:
            pros.append(f"🏠 Match à domicile (Game {game_num})")
        if home_avg and away_avg and (home_avg - away_avg) >= 4:
            pros.append(
                f"📊 Meilleur à domicile : {home_avg:.1f} vs {away_avg:.1f} à l'extérieur"
            )
    else:
        cons.append(f"✈️ Match à l'extérieur (Game {game_num})")
        if home_avg and away_avg and (home_avg - away_avg) >= 4:
            cons.append(
                f"📊 Performe moins bien en déplacement ({away_avg:.1f} vs {home_avg:.1f} à domicile)"
            )

    # --- Élimination ---
    elimination = context.get("elimination", "none")
    if elimination == "critical":
        pros.append(
            "🚨 RISQUE D'ÉLIMINATION : son équipe peut être sortie ce soir. "
            "Si tu ne le joues pas maintenant, tu le perds pour tout le reste des playoffs."
        )
    elif elimination == "high":
        pros.append(
            "⚠️ Série sous pression : une défaite ce soir et son équipe sera en match d'élimination"
        )

    # --- Match d'élimination / clôture (sous-cas) ---
    if hw == 3 or aw == 3:
        if (hw == 3 and not is_home) or (aw == 3 and is_home):
            pros.append(
                "🔥 Match d'élimination pour l'adversaire : intensité maximale des deux côtés"
            )
        elif elimination != "critical":
            pros.append(
                "🏁 Possible match de clôture : motivation pour finir la série"
            )

    # --- Fatigue / rest ---
    days_rest = context["days_rest"]
    if days_rest == 0:
        cons.append(
            "😴 Back-to-back : risque de fatigue et de minutes réduites (-8% attendu)"
        )
    elif days_rest >= 3:
        pros.append(
            f"💪 {days_rest} jours de repos : frais, devrait être au max de ses minutes"
        )

    # --- Blessé coéquipier (usage boost) ---
    teammate_out = context.get("teammate_out")
    if teammate_out:
        pros.append(
            f"⚡ Sans {teammate_out} (OUT) : usage et ballons en hausse, spot bonus"
        )

    # --- Statut joueur ---
    injury = context.get("injury_status")
    if injury:
        if injury == "Questionable":
            cons.append(
                "⚠️ Statut Questionable : risque de forfait, à vérifier 1h avant le match"
            )
        elif injury == "Day-To-Day":
            cons.append(
                "🔶 Statut GTD : peut jouer mais minutes potentiellement limitées"
            )

    # --- Stratégie : gestion du capital ---
    tier = context["tier"]
    elites = context["elites_remaining"]
    days = context["game_days_remaining"]
    ratio = elites / max(1, days)

    if tier == "elite":
        if ratio < 0.15:
            cons.append(
                f"💰 Capital tendu : seulement {elites} elites pour {days} jours de match "
                f"(ratio {ratio:.2f}/jour). Sûr que ce soir est le bon moment ?"
            )
        elif ratio < 0.25:
            cons.append(
                f"💰 {elites} elites restants pour {days} jours — à doser"
            )
        else:
            pros.append(
                f"💰 Capital large : {elites} elites pour {days} jours "
                f"({ratio:.2f}/jour), tu peux te permettre de le jouer"
            )
    elif tier == "solid":
        if ratio < 0.25:
            pros.append(
                "💡 Pick solide qui préserve tes elites pour des spots premium à venir"
            )
    elif tier == "filler":
        if ratio < 0.2:
            pros.append(
                "💡 Choix économique : garde tes cartouches pour les soirs à gros matchups"
            )

    # --- Position dans le classement ---
    rank = context.get("rank", 0)
    if rank == 1:
        pros.append("⭐ Meilleur score estimé du soir parmi tous les joueurs dispos")
    elif rank <= 3:
        pros.append(f"⭐ Top {rank} du soir — l'algo le place parmi les 3 meilleurs picks")

    return pros, cons


def generate_verdict(
    should_burn: bool,
    tier: str,
    tonight_score: float,
    best_future_description: str,
    elimination: str = "none",
    elites_remaining: int = 0,
    game_days_remaining: int = 0,
) -> str:
    """Produce a detailed verdict with explicit reasoning chain."""

    # Élimination critique : priorité absolue
    if elimination == "critical":
        return (
            f"🚨 JOUE-LE CE SOIR à {tonight_score:.0f} pts estimés. "
            f"Son équipe peut être éliminée aujourd'hui. Si tu ne l'utilises pas "
            f"maintenant, il disparaît de ton capital pour le reste des playoffs. "
            f"Même à un score moyen, c'est un pick obligatoire."
        )

    if tier == "filler":
        return (
            f"✅ Pick safe à {tonight_score:.0f} pts estimés. "
            "Bon choix pour un soir sans spot premium : tu fais des points sans entamer "
            "ton capital elite. Réserve tes meilleurs joueurs pour un soir avec plus de matchs "
            "ou de meilleurs matchups."
        )

    if should_burn:
        reason_parts = []
        if elimination == "high":
            reason_parts.append(
                "la série est sous pression — ne repousse pas indéfiniment"
            )
        if tier == "elite" and elites_remaining > 0 and game_days_remaining > 0:
            ratio = elites_remaining / max(1, game_days_remaining)
            if ratio >= 0.2:
                reason_parts.append(
                    f"tu as {elites_remaining} elites pour {game_days_remaining} jours "
                    f"({ratio:.2f}/jour), la marge est confortable"
                )
        reason = ". ".join(reason_parts) if reason_parts else (
            "pas de spot clairement meilleur dans le calendrier à venir"
        )
        return (
            f"✅ JOUE-LE. Score estimé : {tonight_score:.0f}. "
            f"Raison : {reason}. "
            f"Meilleur prochain spot identifié : {best_future_description}."
        )

    # Save
    reason_parts = []
    if tier == "elite" and elites_remaining <= 2 and game_days_remaining > 10:
        reason_parts.append(
            f"tu n'as plus que {elites_remaining} elites pour {game_days_remaining} jours "
            "de match, il faut les caler sur les meilleurs spots"
        )
    reason_parts.append(
        f"un meilleur spot est identifié : {best_future_description}"
    )
    return (
        f"⏸️ GARDE-LE. Score ce soir : {tonight_score:.0f}. "
        f"Raison : {'. '.join(reason_parts)}. "
        "Tu maximises ses points en le plaçant au bon moment."
    )
