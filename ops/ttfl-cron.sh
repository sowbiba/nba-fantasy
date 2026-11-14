#!/usr/bin/env bash
# Lanceur des jobs TTFL locaux (cron du PC). Un seul job à la fois (verrou),
# sortie dans /tmp/ttfl-local.log, échec tracé dans ~/ttfl-sync-failures.log
# avec une notification bureau.
#   nightly : effectifs, calendrier, stats (3 semaines), matchups        — 23h50
#   morning : stats de la nuit (sans matchups) puis recos/plan/scores     — 7h30 et 9h00
#   retry   : stats des matchs encore incomplets                          — 9h30 → 12h00
#   daily   : blessures ESPN, scores, recos, plan                         — journée et soirée
set -u
cd "$(dirname "$0")/.." || exit 1
PY=./venv/bin/python
LOG=/tmp/ttfl-local.log
job="${1:-}"

run() {
  case "$job" in
    nightly) $PY -m engine.jobs.local_nightly ;;
    morning) $PY -m engine.jobs.local_nightly --no-matchups && $PY -m engine.jobs.daily_sync ;;
    retry)   $PY -m engine.jobs.local_nightly --retry-incomplete ;;
    daily)   $PY -m engine.jobs.daily_sync ;;
    *) echo "usage : $0 nightly|morning|retry|daily" >&2; return 2 ;;
  esac
}

# Attend au plus 15 min le job précédent ; au-delà, on passe son tour.
exec 9>/tmp/ttfl-sync.lock
if ! flock -w 900 9; then
  echo "$(date '+%F %T') TTFL $job : verrou occupé, tour passé" >> "$LOG"
  exit 0
fi
if ! run >> "$LOG" 2>&1; then
  echo "$(date '+%F %T') TTFL $job KO" >> "$HOME/ttfl-sync-failures.log"
  DISPLAY=:0 notify-send -u critical "TTFL $job KO" "voir $LOG" 2>/dev/null
  exit 1
fi
