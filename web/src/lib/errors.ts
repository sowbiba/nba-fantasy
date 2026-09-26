import { frDayMonth } from "./date";

type DbError = { code?: string; message?: string; details?: string } | null | undefined;

const DEFAULT = "Échec de l'enregistrement — réessaie.";

const UNAVAILABLE: Record<string, string> = {
  reserved_nearby: "Ce joueur est déjà réservé à moins de 30 jours de cette soirée.",
  playoffs_used: "Ce joueur a déjà été utilisé pendant ces playoffs.",
  team_eliminated: "Son équipe est éliminée.",
  not_qualified: "Son équipe n'est pas qualifiée pour les playoffs.",
};

/** Traduit les erreurs de la base (trigger picks_validate, contraintes x2)
 *  en messages lisibles. Ne renvoie jamais le message brut. */
export function pickErrorMessage(err: DbError): string {
  if (!err) return DEFAULT;
  const message = err.message ?? "";
  if (err.code === "P0001") {
    if (message.startsWith("player_unavailable:cooldown")) {
      return err.details && /^\d{4}-\d{2}-\d{2}$/.test(err.details)
        ? `Joueur bloqué jusqu'au ${frDayMonth(err.details)} (cooldown de 30 jours).`
        : "Joueur bloqué par le cooldown de 30 jours.";
    }
    if (message.startsWith("player_unavailable:")) {
      return UNAVAILABLE[message.split(":")[1]] ?? "Ce joueur n'est pas disponible ce soir-là.";
    }
    if (message.startsWith("night_not_eligible")) return "Cette soirée ne compte pas pour la TTFL (présaison, play-in…).";
    if (message.startsWith("player_not_in_game")) return "Ce joueur ne joue pas ce match.";
    if (message.startsWith("date_mismatch")) return "La date ne correspond pas au match.";
    if (message.startsWith("game_not_found")) return "Match introuvable.";
  }
  if (err.code === "23505") {
    return message.includes("picks_x2_month") ? "Tu as déjà utilisé ton x2 ce mois-ci." : "Tu as déjà un pick ce soir-là.";
  }
  if (err.code === "23514" && message.includes("picks_x2_window")) {
    return "Le x2 n'existe qu'en saison régulière, de novembre à avril.";
  }
  return DEFAULT;
}
