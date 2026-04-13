import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# ESPN injury endpoint template
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/injuries"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# NBA API request delay (avoid rate limiting)
NBA_API_DELAY = 0.6  # seconds between requests

# Scoring weights
WEIGHTS = {
    "weighted_avg": 0.35,
    "matchup": 0.25,
    "home_away": 0.10,
    "fatigue": 0.10,
    "trend": 0.10,
    "consistency": 0.10,
}

# Fatigue modifiers
FATIGUE = {
    "b2b": -0.08,
    "3_in_4": -0.12,
    "rest_3plus": 0.03,
}

# Injury modifiers on estimated score
INJURY_MODIFIER = {
    "Questionable": -0.15,
    "Day-To-Day": -0.10,
}

# Playoff strategy: burn threshold
# If best future spot > tonight + 10%, recommend saving
BURN_THRESHOLD = 0.10
