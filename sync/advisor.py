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

    # --- DNP récent (indépendant du flag ESPN) ---
    dnp_factor = context.get("dnp_risk_factor", 1.0)
    if dnp_factor < 1.0:
        recent_min = context.get("recent_minutes") or []
        dnp_count = sum(1 for m in recent_min if m == 0)
        total = len(recent_min)
        if dnp_count >= 2:
            cons.append(
                f"🚑 DNP récents ({dnp_count}/{total} derniers matchs à 0 min) : "
                f"statut ESPN n'a peut-être pas été mis à jour, à vérifier"
            )
        elif dnp_count == 1 and recent_min and recent_min[0] == 0:
            cons.append(
                "🚑 N'a pas joué le dernier match : possible blessure non encore "
                "officialisée, à vérifier 1h avant le match"
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

    # --- Watchlist perso + surge Game 3 ---
    priority = context.get("watchlist_priority")
    if priority:
        stars = "★" * (4 - priority)
        pros.append(
            f"{stars} Must-play perso (priorité {priority}) — "
            "tu l'as flaggué pour ces playoffs"
        )
    if context.get("game3_surge"):
        pros.append(
            "🔥 Spot idéal : retour à domicile après 0-2, "
            "franchise en mode survie (boost +12%)"
        )

    # --- Réservation (élite de prétendant profond, tour précoce) ---
    reservation_penalty = context.get("reservation_penalty", 0) or 0
    if reservation_penalty >= 0.3:
        pct = round(reservation_penalty * 100)
        cons.append(
            f"💰 Profil à préserver : score docké -{pct}% par l'algo — "
            "élite d'un prétendant qui va loin, idéalement gardé pour R3/R4"
        )
    elif reservation_penalty >= 0.1:
        pct = round(reservation_penalty * 100)
        cons.append(
            f"💰 Pénalité de réservation -{pct}% — pas le moment optimal mais pas non plus à sacrifier"
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


def generate_plan_argumentaire(context: dict) -> tuple[list[str], list[str]]:
    """Pour/Contre for a future plan entry (J+1 … J+N).

    Narrower than `generate_argumentaire` on purpose: no injury status and
    no teammate-out are reliable days in advance. We focus on stable signals
    (season form, splits, series context, reservation/capital).
    """
    pros: list[str] = []
    cons: list[str] = []

    avg_l5 = context.get("avg_l5", 0) or 0
    avg_season = context.get("avg_season", 0) or 0
    home_avg = context.get("home_avg", 0) or 0
    away_avg = context.get("away_avg", 0) or 0
    ceiling = context.get("ceiling", 0) or 0
    floor = context.get("floor", 0) or 0
    stddev = context.get("stddev", 0) or 0

    # --- Forme récente ---
    if avg_season > 0:
        if avg_l5 > avg_season * 1.15:
            pct = round((avg_l5 / avg_season - 1) * 100)
            pros.append(
                f"🔥 En feu : {avg_l5:.1f} TTFL avg L5 (+{pct}% vs saison {avg_season:.1f})"
            )
        elif avg_l5 > avg_season * 1.05:
            pros.append(
                f"📈 Forme au-dessus de sa saison ({avg_l5:.1f} avg L5 vs {avg_season:.1f})"
            )
        elif avg_l5 < avg_season * 0.85:
            pct = round((1 - avg_l5 / avg_season) * 100)
            cons.append(
                f"📉 En méforme : {avg_l5:.1f} avg L5 (-{pct}% vs saison {avg_season:.1f})"
            )

    # --- Fiabilité ---
    if stddev and stddev < 10 and avg_l5 >= 30:
        pros.append(
            f"🛡️ Joueur fiable : floor {floor:.0f} TTFL (écart-type {stddev:.1f})"
        )
    elif stddev > 18:
        cons.append(
            f"🎲 Joueur volatile : floor {floor:.0f} / ceiling {ceiling:.0f} (écart-type {stddev:.1f})"
        )

    # --- Matchup (opp TTFL vs league avg) ---
    opp_ttfl = context.get("opp_ttfl_at_position", 0) or 0
    league_avg = context.get("league_avg_ttfl", 40)
    opponent = context.get("opponent", "?")
    position_label = {"G": "guards", "F": "forwards", "C": "centers"}.get(
        context.get("position", ""), ""
    )
    if opp_ttfl and league_avg:
        delta = (opp_ttfl - league_avg) / league_avg
        if delta >= 0.10:
            pct = round(delta * 100)
            pros.append(
                f"🎯 Matchup juteux : {opponent} concède +{pct}% TTFL aux {position_label}"
            )
        elif delta >= 0.04:
            pros.append(
                f"✓ Matchup favorable : {opponent} au-dessus de la moyenne TTFL encaissée aux {position_label}"
            )
        elif delta <= -0.10:
            pct = round(-delta * 100)
            cons.append(
                f"🧱 Matchup difficile : {opponent} concède -{pct}% TTFL aux {position_label}"
            )

    # --- Home / Away ---
    is_home = context.get("is_home", False)
    game_number = context.get("game_number")
    hw, aw = context.get("series_score", (0, 0))
    if is_home:
        tight = abs(hw - aw) <= 1
        if tight and (hw + aw) >= 3 and game_number:
            pros.append(
                f"🏠 Game {game_number} à domicile · série {hw}-{aw} (enjeu max, crowd factor)"
            )
        elif game_number:
            pros.append(f"🏠 Match à domicile (Game {game_number})")
        else:
            pros.append("🏠 Match à domicile")
        if home_avg and away_avg and (home_avg - away_avg) >= 4:
            pros.append(
                f"📊 Meilleur à domicile : {home_avg:.1f} vs {away_avg:.1f} à l'extérieur"
            )
    else:
        if game_number:
            cons.append(f"✈️ Match à l'extérieur (Game {game_number})")
        else:
            cons.append("✈️ Match à l'extérieur")
        if home_avg and away_avg and (home_avg - away_avg) >= 4:
            cons.append(
                f"📊 Performe moins en déplacement ({away_avg:.1f} vs {home_avg:.1f})"
            )

    # --- Watchlist perso + surge Game 3 ---
    priority = context.get("watchlist_priority")
    if priority:
        stars = "★" * (4 - priority)
        pros.append(
            f"{stars} Must-play perso (priorité {priority}) — flaggué pour ces playoffs"
        )
    if context.get("game3_surge"):
        pros.append(
            "🔥 Spot idéal : retour à domicile après 0-2, "
            "franchise en mode survie (boost +12%)"
        )

    # --- Élimination / enjeu série ---
    elimination = context.get("elimination", "none")
    if elimination == "critical":
        pros.append(
            "🚨 Match couperet : son équipe peut être éliminée ce jour-là. "
            "Si tu ne le joues pas à cette date, il disparaît du reste des playoffs."
        )
    elif elimination == "high":
        pros.append(
            "⚠️ Série sous pression : une défaite et son équipe sera en match couperet"
        )

    if hw == 3 or aw == 3:
        if (hw == 3 and not is_home) or (aw == 3 and is_home):
            pros.append(
                "🔥 Match couperet pour l'adversaire : intensité maximale des deux côtés"
            )
        elif elimination != "critical":
            pros.append(
                "🏁 Possible match de clôture : motivation pour finir la série"
            )

    # --- Réservation / capital ---
    reservation_penalty = context.get("reservation_penalty", 0) or 0
    if reservation_penalty >= 0.3:
        pct = round(reservation_penalty * 100)
        cons.append(
            f"💰 Profil à préserver : score docké -{pct}% par l'algo "
            "(élite d'un prétendant profond, idéalement gardé pour les tours suivants)"
        )
    elif reservation_penalty >= 0.1:
        pct = round(reservation_penalty * 100)
        cons.append(
            f"💰 Pénalité de réservation -{pct}% — l'algo préfèrerait le garder mais ce créneau reste le meilleur spot identifié"
        )

    return pros, cons


def generate_plan_verdict(context: dict) -> str:
    """Verdict conditionnel pour une entrée du plan.

    Combine les familles A (risque sur ce pick), B (risque collatéral), C
    (répartition / pool) en sélectionnant la phrase qui capture le facteur
    dominant. Le verdict est forward-looking : il répond "pourquoi ce jour
    plutôt qu'attendre" et "qu'est-ce que tu risques de perdre".
    """
    day_label = context.get("day_label", "ce jour-là")
    score = context.get("estimated_score", 0) or 0
    elimination = context.get("elimination", "none")
    is_home = context.get("is_home", False)
    game_number = context.get("game_number")
    hw, aw = context.get("series_score", (0, 0))
    team = context.get("team", "son équipe")

    pick_prob = context.get("pick_probability", 1.0) or 1.0
    p_team_elim = context.get("p_team_eliminated", 0.0) or 0.0
    p_team_adv = context.get("p_team_advances", 1.0) or 1.0
    expected_remaining = context.get("expected_remaining_after", 0.0) or 0.0
    reservation = context.get("reservation_penalty", 0.0) or 0.0
    priority = context.get("watchlist_priority")
    alts = context.get("tier_alternatives_at_risk", []) or []
    stddev = context.get("stddev", 0) or 0
    avg_l5 = context.get("avg_l5", 0) or 0
    opp_ttfl = context.get("opp_ttfl_at_position", 0) or 0
    league_avg = context.get("league_avg_ttfl", 40) or 40
    position_label = {"G": "guards", "F": "forwards", "C": "centers"}.get(
        context.get("position", ""), context.get("position", "")
    )
    opponent = context.get("opponent", "?")
    tier_label = (
        {1: "★★★", 2: "★★", 3: "★"}.get(priority, "") if priority else ""
    )

    # ---- Famille A : risque sur CE pick ----
    if elimination == "critical":
        return (
            "Pick obligatoire ce soir : son équipe peut être éliminée, "
            "sinon c'est un capital gâché pour le reste des playoffs."
        )

    # A.1 : Le match candidat lui-même a une probabilité d'avoir lieu < 0.7
    # (typiquement G6/G7). On le justifie par "fenêtre la plus sûre" si le
    # joueur est sur la watchlist.
    if pick_prob < 0.7 and priority in (1, 2):
        return (
            f"Match incertain ({round(pick_prob * 100)}% qu'il ait lieu) — "
            f"fenêtre la plus sûre identifiée cette semaine pour ce {tier_label}. "
            f"Au-delà, soit la série se termine, soit tu changes de tour."
        )

    # A.2 : Le match aura lieu (pick_prob élevé) MAIS l'équipe risque
    # l'élimination dans la série en cours — donc différer = potentiellement
    # perdre le joueur pour le reste des playoffs.
    if priority == 1 and p_team_elim >= 0.4 and pick_prob >= 0.85:
        risk_pct = round(p_team_elim * 100)
        return (
            f"Si tu ne le joues pas maintenant, {risk_pct}% de risque que "
            f"{team} soit éliminée avant que tu puisses l'utiliser ailleurs. "
            f"★★★ à sécuriser."
        )

    # ---- Famille B : risque collatéral sur d'autres ★★★ ----
    if alts and p_team_elim >= 0.35:
        other = alts[0]
        return (
            f"En le jouant maintenant tu sécurises ce slot. "
            f"Si {team} perd ce soir tu risques aussi de bloquer {other} — "
            f"préfère le pick safe avant que la série bascule."
        )

    # Joueur d'une équipe favorite avec beaucoup de matchs futurs : il est
    # différable, mais cette fenêtre reste la meilleure du window 7j.
    if reservation >= 0.4 and expected_remaining >= 4:
        return (
            f"Différable ({team} avance probablement, ~{expected_remaining:.1f} matchs "
            f"encore devant lui), mais cette fenêtre reste le meilleur rendement "
            f"de la semaine sans cramer un spot premium."
        )

    # ---- Famille C : répartition / pool / matchup ----
    if stddev > 18 and opp_ttfl >= league_avg * 1.10:
        return (
            f"Profil volatil (σ={stddev:.0f}) mais matchup ({opp_ttfl:.0f} TTFL "
            f"concédé aux {position_label}) compense largement."
        )

    if opp_ttfl >= league_avg * 1.15:
        return (
            f"Matchup défensif favorable contre {opponent} ({opp_ttfl:.0f} TTFL "
            f"concédé aux {position_label}). Forme L5 {avg_l5:.0f}."
        )

    if priority == 3 or (priority == 2 and pick_prob >= 0.9):
        return (
            f"Pick safe (P {round(pick_prob*100)}%) — libère tes ★★★ pour des "
            f"matchs plus rentables ou plus serrés en R2/R3."
        )

    if reservation >= 0.2:
        pct = round(reservation * 100)
        return (
            f"Pick rare malgré une réserve -{pct}% — meilleure fenêtre "
            f"identifiée d'ici la fin de la série."
        )

    # Fallback : justification sobre
    place = "domicile" if is_home else "extérieur"
    g_str = f", G{game_number}" if game_number else ""
    return (
        f"{place.capitalize()} vs {opponent}{g_str}, forme L5 {avg_l5:.0f}. "
        f"Aucun autre créneau de la fenêtre ne fait mieux sans sacrifier un spot premium."
    )
