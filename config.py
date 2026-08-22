"""
Central configuration for the FPL Optimizer.
Tweak these values to change squad rules or how predicted points are scored.
"""

# --- FPL API endpoints ---
BASE_URL = "https://fantasy.premierleague.com/api"
BOOTSTRAP_URL = f"{BASE_URL}/bootstrap-static/"
FIXTURES_URL = f"{BASE_URL}/fixtures/"
PLAYER_HISTORY_URL = f"{BASE_URL}/element-summary/{{player_id}}/"
ENTRY_URL = f"{BASE_URL}/entry/{{team_id}}/"
ENTRY_PICKS_URL = f"{BASE_URL}/entry/{{team_id}}/event/{{gw}}/picks/"

# --- Squad rules (official FPL rules) ---
BUDGET = 100.0          # starting budget in £m
SQUAD_SIZE = 15
MAX_PER_CLUB = 3
POSITION_LIMITS = {     # full 15-man squad composition
    "GKP": 2,
    "DEF": 5,
    "MID": 5,
    "FWD": 3,
}

# Valid starting-XI formations: (DEF, MID, FWD) — GKP is always 1
VALID_FORMATIONS = [
    (3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3),
    (4, 5, 1), (5, 4, 1), (5, 3, 2), (5, 2, 3),
]

# --- Prediction model weights (tune these to change strategy) ---
# predicted_points = a*form + b*points_per_game + c*fixture_score
#                     + d*ict_index_norm + e*minutes_reliability
WEIGHTS = {
    "form": 0.35,
    "points_per_game": 0.20,
    "fixture_score": 0.25,
    "ict_index": 0.10,
    "minutes_reliability": 0.10,
}

FIXTURE_LOOKAHEAD_GWS = 5   # how many upcoming gameweeks to factor into fixture_score

# Cache directory: use the system temp dir so this works both locally and on
# read-only serverless filesystems like Vercel (which only allow writes to /tmp).
import tempfile
import os
CACHE_DIR = os.path.join(tempfile.gettempdir(), "fpl_optimizer_cache")
CACHE_TTL_HOURS = 6         # how long cached API responses stay valid

# Minimum minutes-per-game (season avg) to trust a player's form fully
MIN_RELIABLE_MINUTES = 60
