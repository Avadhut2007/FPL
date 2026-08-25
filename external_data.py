"""
External football data sources.

This module handles:

- ESPN Premier League live scores
- ESPN Premier League standings
- BBC Football transfer news

All external sources fail safely so one unavailable provider
does not break the Flask application.
"""

import json
import os
import re
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta

import requests

import config


# ============================================================
# REQUEST HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espn.com/",
}


# ============================================================
# CACHE HELPERS
# ============================================================

def _cache_path(name: str) -> str:
    """
    Return the cache file path.

    On Vercel this uses /tmp because the deployed filesystem
    is read-only apart from temporary storage.
    """

    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
    except OSError:
        pass

    return os.path.join(
        config.CACHE_DIR,
        f"{name}.json",
    )


def _read_cache(name: str, ttl_seconds: int):
    """
    Return cached JSON if it exists and has not expired.
    """

    try:
        path = _cache_path(name)

        if not os.path.exists(path):
            return None

        modified_time = os.path.getmtime(path)

        age = (
            datetime.now()
            - datetime.fromtimestamp(modified_time)
        )

        if age > timedelta(seconds=ttl_seconds):
            return None

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception:
        return None


def _write_cache(name: str, data):
    """
    Write JSON data to cache.

    Cache failures should never break the application.
    """

    try:
        path = _cache_path(name)

        with open(
            path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(data, file)

    except Exception:
        pass


# ============================================================
# JSON REQUEST HELPER
# ============================================================

def _get_json(
    urls,
    cache_name: str,
    cache_ttl_seconds: int,
    retries: int = 1,
    timeout: int = 5,
):
    """
    Fetch JSON from one or more URLs.

    Behaviour:

    1. Check cache first.
    2. Try the primary source.
    3. Try fallback sources.
    4. Retry each source if requested.
    5. Cache successful responses.
    6. Raise one useful error if everything fails.
    """

    cached = _read_cache(
        cache_name,
        cache_ttl_seconds,
    )

    if cached is not None:
        return cached

    if isinstance(urls, str):
        urls = [urls]

    errors = []

    for url in urls:

        for attempt in range(retries):

            try:
                response = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=timeout,
                )

                response.raise_for_status()

                data = response.json()

                if not data:
                    raise RuntimeError(
                        "Upstream returned empty JSON"
                    )

                _write_cache(
                    cache_name,
                    data,
                )

                return data

            except Exception as error:

                errors.append(
                    f"{url} -> "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                if attempt < retries - 1:
                    time.sleep(0.5)

    raise RuntimeError(
        "All data sources failed: "
        + " | ".join(errors)
    )


# ============================================================
# LIVE SCORES
# ============================================================

def get_live_scores(
    date_from: str = None,
    date_to: str = None,
) -> list:
    """
    Get Premier League fixtures and scores from ESPN.

    If date_from/date_to are provided they must be YYYYMMDD.

    Multiple ESPN hosts are attempted automatically.
    """

    urls = list(config.ESPN_SCOREBOARD_URLS)

    if date_from and date_to:
        urls = [
            f"{url}?dates={date_from}-{date_to}"
            for url in urls
        ]

    cache_name = (
        f"live_scores_"
        f"{date_from or 'today'}_"
        f"{date_to or 'today'}"
    )

    try:
        data = _get_json(
            urls=urls,
            cache_name=cache_name,
            cache_ttl_seconds=60,
            retries=1,
            timeout=5,
        )

    except Exception:
        return []

    games = []

    for event in data.get("events", []):

        try:
            competitions = event.get(
                "competitions",
                [],
            )

            if not competitions:
                continue

            competition = competitions[0]

            competitors = competition.get(
                "competitors",
                [],
            )

            home = next(
                (
                    competitor
                    for competitor in competitors
                    if competitor.get("homeAway") == "home"
                ),
                None,
            )

            away = next(
                (
                    competitor
                    for competitor in competitors
                    if competitor.get("homeAway") == "away"
                ),
                None,
            )

            if not home or not away:
                continue

            event_status = event.get(
                "status",
                {},
            )

            status = event_status.get(
                "type",
                {},
            )

            home_team = home.get(
                "team",
                {},
            )

            away_team = away.get(
                "team",
                {},
            )

            games.append(
                {
                    "date": event.get(
                        "date",
                        "",
                    ),

                    "home_team": home_team.get(
                        "displayName",
                        "Unknown",
                    ),

                    "home_crest": home_team.get(
                        "logo"
                    ),

                    "home_score": home.get(
                        "score",
                        "0",
                    ),

                    "away_team": away_team.get(
                        "displayName",
                        "Unknown",
                    ),

                    "away_crest": away_team.get(
                        "logo"
                    ),

                    "away_score": away.get(
                        "score",
                        "0",
                    ),

                    "status": status.get(
                        "shortDetail",
                        status.get(
                            "description",
                            "",
                        ),
                    ),

                    "is_live": (
                        status.get("state")
                        == "in"
                    ),

                    "is_finished": (
                        status.get("state")
                        == "post"
                    ),
                }
            )

        except Exception:
            continue

    games.sort(
        key=lambda game: game.get(
            "date",
            "",
        )
    )

    return games


# ============================================================
# STANDINGS HELPERS
# ============================================================

def _extract_display_value(stat):
    """
    ESPN statistics can expose either displayValue or value.
    """

    if not isinstance(stat, dict):
        return None

    value = stat.get(
        "displayValue"
    )

    if value is None:
        value = stat.get(
            "value"
        )

    return value


def _normalise_stat(value):
    """
    Convert numeric values where possible.
    """

    if value is None:
        return None

    if isinstance(
        value,
        (int, float),
    ):
        return value

    return str(value)


def _parse_standard_espn_standings(data):
    """
    Parse ESPN's normal /apis/v2 standings response.
    """

    children = data.get(
        "children",
        [],
    )

    if not children:
        return []

    standings = children[0].get(
        "standings",
        {},
    )

    entries = standings.get(
        "entries",
        [],
    )

    table = []

    for entry in entries:

        try:
            team = entry.get(
                "team",
                {},
            )

            stats = {}

            for stat in entry.get(
                "stats",
                [],
            ):

                name = stat.get(
                    "name"
                )

                if name:
                    stats[name] = (
                        _extract_display_value(
                            stat
                        )
                    )

            logos = team.get(
                "logos",
                [],
            )

            crest = None

            if logos:
                crest = logos[0].get(
                    "href"
                )

            table.append(
                {
                    "team": team.get(
                        "displayName",
                        team.get(
                            "name",
                            "Unknown",
                        ),
                    ),

                    "crest": crest,

                    "played": _normalise_stat(
                        stats.get(
                            "gamesPlayed"
                        )
                    ),

                    "won": _normalise_stat(
                        stats.get(
                            "wins"
                        )
                    ),

                    "drawn": _normalise_stat(
                        stats.get(
                            "ties"
                        )
                    ),

                    "lost": _normalise_stat(
                        stats.get(
                            "losses"
                        )
                    ),

                    "goal_diff": _normalise_stat(
                        stats.get(
                            "pointDifferential"
                        )
                    ),

                    "points": _normalise_stat(
                        stats.get(
                            "points"
                        )
                    ),

                    "rank": _normalise_stat(
                        stats.get(
                            "rank"
                        )
                    ),
                }
            )

        except Exception:
            continue

    return table


def _parse_core_espn_standings(data):
    """
    Fallback parser for ESPN Core standings data.

    Different ESPN Core responses can have slightly different shapes,
    so this parser accepts both direct items and common nested forms.
    """

    items = data.get(
        "items",
        [],
    )

    table = []

    for item in items:

        try:
            team = item.get(
                "team",
                {},
            )

            if not team:
                continue

            stats = {}

            for stat in item.get(
                "stats",
                [],
            ):
                name = stat.get("name")

                if name:
                    stats[name] = _extract_display_value(
                        stat
                    )

            table.append(
                {
                    "team": team.get(
                        "displayName",
                        team.get(
                            "name",
                            "Unknown",
                        ),
                    ),

                    "crest": team.get(
                        "logo"
                    ),

                    "played": _normalise_stat(
                        stats.get("gamesPlayed")
                    ),

                    "won": _normalise_stat(
                        stats.get("wins")
                    ),

                    "drawn": _normalise_stat(
                        stats.get("ties")
                    ),

                    "lost": _normalise_stat(
                        stats.get("losses")
                    ),

                    "goal_diff": _normalise_stat(
                        stats.get("pointDifferential")
                    ),

                    "points": _normalise_stat(
                        stats.get("points")
                    ),

                    "rank": _normalise_stat(
                        item.get("rank")
                    ),
                }
            )

        except Exception:
            continue

    return table


def get_league_table() -> list:
    """
    Get the current Premier League table.

    Tries multiple ESPN endpoints and caches successful results
    for five minutes.
    """

    try:
        data = _get_json(
            urls=config.ESPN_STANDINGS_URLS,
            cache_name="standings",
            cache_ttl_seconds=300,
            retries=1,
            timeout=5,
        )

    except Exception:
        return []

    table = _parse_standard_espn_standings(
        data
    )

    if not table:
        table = _parse_core_espn_standings(
            data
        )

    def rank_value(row):

        rank = row.get(
            "rank"
        )

        try:
            return int(rank)
        except (
            TypeError,
            ValueError,
        ):
            return 999

    table.sort(
        key=rank_value
    )

    return table


# ============================================================
# TRANSFER NEWS
# ============================================================

def get_transfer_news(
    limit: int = 20,
) -> list:
    """
    Get transfer-related football headlines from BBC Sport RSS.
    """

    try:
        response = requests.get(
            config.BBC_FOOTBALL_RSS_URL,
            headers=HEADERS,
            timeout=8,
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.content
        )

    except Exception:
        return []

    keyword_pattern = re.compile(
        "|".join(
            re.escape(keyword)
            for keyword in config.TRANSFER_KEYWORDS
        ),
        re.IGNORECASE,
    )

    items = []

    for item in root.findall(
        ".//item"
    ):

        title = (
            item.findtext(
                "title"
            )
            or ""
        ).strip()

        if not keyword_pattern.search(
            title
        ):
            continue

        items.append(
            {
                "title": title,

                "link": (
                    item.findtext(
                        "link"
                    )
                    or ""
                ).strip(),

                "published": (
                    item.findtext(
                        "pubDate"
                    )
                    or ""
                ).strip(),
            }
        )

        if len(items) >= limit:
            break

    return items
