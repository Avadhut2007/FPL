"""
Non-FPL external data sources — kept separate from fpl_api.py since these
hit entirely different services (ESPN's public soccer API, BBC's RSS feed).
Neither requires an API key. Both fail soft: if the upstream service is down
or its shape changes, callers get an empty list/dict back rather than a 500.
"""
import re
import xml.etree.ElementTree as ET

import requests

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_live_scores(date_from: str = None, date_to: str = None) -> list:
    """
    Premier League fixtures + scores from ESPN's public (unofficial, no-key)
    soccer API. With no arguments, returns today's games. Pass date_from/
    date_to as 'YYYYMMDD' to cover a range instead — used by the Live
    Scores page to show every match in the current FPL gameweek, not just
    today's.
    """
    url = config.ESPN_SCOREBOARD_URL
    if date_from and date_to:
        url = f"{url}?dates={date_from}-{date_to}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    games = []
    for event in data.get("events", []):
        try:
            competition = event["competitions"][0]
            competitors = competition["competitors"]
            home = next(c for c in competitors if c["homeAway"] == "home")
            away = next(c for c in competitors if c["homeAway"] == "away")
            status = event["status"]["type"]

            games.append({
                "date": event.get("date", ""),
                "home_team": home["team"]["displayName"],
                "home_crest": home["team"].get("logo"),
                "home_score": home.get("score", "0"),
                "away_team": away["team"]["displayName"],
                "away_crest": away["team"].get("logo"),
                "away_score": away.get("score", "0"),
                "status": status.get("shortDetail", ""),
                "is_live": status.get("state") == "in",
                "is_finished": status.get("state") == "post",
            })
        except (KeyError, IndexError, StopIteration):
            continue

    games.sort(key=lambda g: g["date"])
    return games


def get_league_table() -> list:
    """Current Premier League standings from ESPN's public API."""
    try:
        resp = requests.get(config.ESPN_STANDINGS_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    table = []
    try:
        entries = data["children"][0]["standings"]["entries"]
    except (KeyError, IndexError):
        return []

    for entry in entries:
        try:
            stats = {s["name"]: s.get("displayValue") for s in entry["stats"]}
            table.append({
                "team": entry["team"]["displayName"],
                "crest": entry["team"].get("logos", [{}])[0].get("href"),
                "played": stats.get("gamesPlayed"),
                "won": stats.get("wins"),
                "drawn": stats.get("ties"),
                "lost": stats.get("losses"),
                "goal_diff": stats.get("pointDifferential"),
                "points": stats.get("points"),
                "rank": stats.get("rank"),
            })
        except (KeyError, IndexError):
            continue

    table.sort(key=lambda t: int(t["rank"]) if t["rank"] else 999)
    return table


def get_transfer_news(limit: int = 20) -> list:
    """
    Real-world football transfer headlines from BBC Sport's public RSS feed,
    filtered down to transfer-related keywords. Parsed directly from the RSS
    XML (no third-party parsing service needed, so nothing else can rate-limit
    or go down independently of BBC itself).
    """
    try:
        resp = requests.get(config.BBC_FOOTBALL_RSS_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []

    keyword_pattern = re.compile("|".join(config.TRANSFER_KEYWORDS), re.IGNORECASE)

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not keyword_pattern.search(title):
            continue
        items.append({
            "title": title,
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
        })
        if len(items) >= limit:
            break

    return items
