"""
Central configuration for the FPL Optimizer.

Tweak these values to change squad rules or how predicted points are scored.
"""

import os


# ============================================================
# FPL API
# ============================================================

BASE_URL = "https://fantasy.premierleague.com/api"

BOOTSTRAP_URL = f"{BASE_URL}/bootstrap-static/"
FIXTURES_URL = f"{BASE_URL}/fixtures/"
PLAYER_HISTORY_URL = f"{BASE_URL}/element-summary/{{player_id}}/"
ENTRY_URL = f"{BASE_URL}/entry/{{team_id}}/"
ENTRY_PICKS_URL = f"{BASE_URL}/entry/{{team_id}}/event/{{gw}}/picks/"


# ============================================================
# SQUAD SETTINGS
# ============================================================

BUDGET = 100.0
SQUAD_SIZE = 15
MAX_PER_CLUB = 3

POSITION_LIMITS = {
    "GKP": 2,
    "DEF": 5,
    "MID": 5,
    "FWD": 3,
}

VALID_FORMATIONS = [
    (3, 4, 3),
    (3, 5, 2),
    (4, 4, 2),
    (4, 3, 3),
    (4, 5, 1),
    (5, 4, 1),
    (5, 3, 2),
    (5, 2, 3),
]


# ============================================================
# PREDICTION WEIGHTS
# ============================================================

WEIGHTS = {
    "form": 0.35,
    "points_per_game": 0.20,
    "fixture_score": 0.25,
    "ict_index": 0.10,
    "minutes_reliability": 0.10,
}

FIXTURE_LOOKAHEAD_GWS = 5
MIN_RELIABLE_MINUTES = 60


# ============================================================
# CACHE
# ============================================================

# Vercel's deployed filesystem is read-only.
# /tmp is writable and is appropriate for short-lived serverless cache.
CACHE_DIR = "/tmp/fpl_cache" if os.environ.get("VERCEL") else "data"

CACHE_TTL_HOURS = 6


# ============================================================
# PREMIER LEAGUE MEDIA
# ============================================================

TEAM_CREST_URL = (
    "https://resources.premierleague.com/"
    "premierleague/badges/70/t{team_code}@2x.png"
)

PLAYER_PHOTO_URL = (
    "https://resources.premierleague.com/"
    "premierleague/photos/players/110x140/p{player_code}.png"
)


# ============================================================
# ESPN DATA SOURCES
# ============================================================

# Primary scoreboard endpoint.
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/"
    "apis/site/v2/sports/soccer/eng.1/scoreboard"
)

# Backup scoreboard host.
ESPN_SCOREBOARD_FALLBACK_URL = (
    "https://site.web.api.espn.com/"
    "apis/site/v2/sports/soccer/eng.1/scoreboard"
)

# Primary standings endpoint.
ESPN_STANDINGS_URL = (
    "https://site.api.espn.com/"
    "apis/v2/sports/soccer/eng.1/standings"
)

# Backup standings host.
ESPN_STANDINGS_FALLBACK_URL = (
    "https://site.web.api.espn.com/"
    "apis/v2/sports/soccer/eng.1/standings"
)

# ESPN Core API fallback.
ESPN_CORE_STANDINGS_URL = (
    "https://sports.core.api.espn.com/"
    "v2/sports/soccer/leagues/eng.1/standings"
)

# All scoreboard sources.
ESPN_SCOREBOARD_URLS = [
    ESPN_SCOREBOARD_URL,
    ESPN_SCOREBOARD_FALLBACK_URL,
]

# All standings sources.
ESPN_STANDINGS_URLS = [
    ESPN_STANDINGS_URL,
    ESPN_STANDINGS_FALLBACK_URL,
    ESPN_CORE_STANDINGS_URL,
]


# ============================================================
# BBC TRANSFER NEWS
# ============================================================

BBC_FOOTBALL_RSS_URL = (
    "https://feeds.bbci.co.uk/sport/football/rss.xml"
)

TRANSFER_KEYWORDS = [
    "sign",
    "signs",
    "signing",
    "transfer",
    "loan",
    "medical",
    "deal",
    "move to",
    "fee agreed",
    "bid",
    "target",
    "linked",
    "join",
    "joins",
    "leave",
    "leaves",
    "release",
    "released",
    "contract",
]
