"""
Thin client for the official (unofficial-but-public) Fantasy Premier League API.
Handles caching so you don't hammer the endpoint every time you run the app.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

import config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://fantasy.premierleague.com/",
    "Origin": "https://fantasy.premierleague.com",
}

_session = requests.Session()
_session.headers.update(HEADERS)


def _cache_path(name: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"{name}.json")


def _read_cache(name: str):
    path = _cache_path(name)
    if not os.path.exists(path):
        return None
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    if age > timedelta(hours=config.CACHE_TTL_HOURS):
        return None
    with open(path, "r") as f:
        return json.load(f)


def _write_cache(name: str, data):
    with open(_cache_path(name), "w") as f:
        json.dump(data, f)


def _get(url: str, cache_name: str = None, force_refresh: bool = False, retries: int = 4):
    if cache_name and not force_refresh:
        cached = _read_cache(cache_name)
        if cached is not None:
            return cached

    last_err = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if cache_name:
                _write_cache(cache_name, data)
            return data
        except (requests.RequestException, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_err}")


def get_bootstrap_data(force_refresh: bool = False) -> dict:
    return _get(config.BOOTSTRAP_URL, cache_name="bootstrap", force_refresh=force_refresh)


def get_fixtures(force_refresh: bool = False) -> list:
    return _get(config.FIXTURES_URL, cache_name="fixtures", force_refresh=force_refresh)


def get_player_history(player_id: int, force_refresh: bool = False) -> dict:
    url = config.PLAYER_HISTORY_URL.format(player_id=player_id)
    return _get(url, cache_name=f"player_{player_id}", force_refresh=force_refresh)


def get_entry_picks(team_id: int, gw: int, force_refresh: bool = False) -> dict:
    url = config.ENTRY_PICKS_URL.format(team_id=team_id, gw=gw)
    return _get(url, cache_name=f"entry_{team_id}_{gw}", force_refresh=force_refresh)


def get_entry_info(team_id: int, force_refresh: bool = False) -> dict:
    url = config.ENTRY_URL.format(team_id=team_id)
    return _get(url, cache_name=f"entry_info_{team_id}", force_refresh=force_refresh)


def get_current_gameweek(bootstrap: dict) -> int:
    for event in bootstrap["events"]:
        if event.get("is_next"):
            return event["id"]
    for event in bootstrap["events"]:
        if not event.get("finished"):
            return event["id"]
    return bootstrap["events"][-1]["id"]


def get_next_deadline(bootstrap: dict) -> dict:
    """
    The next gameweek deadline that hasn't passed yet, for the Deadline
    Reminder widget. Deliberately does NOT rely on "is_next"/"finished" —
    a gameweek stays "not finished" for a while after its own deadline
    (while matches are still being played and bonus points processed), so
    that flag alone would keep showing a deadline that's already in the
    past. Instead this picks the first gameweek whose deadline_time is
    still in the future relative to right now.
    """
    now = datetime.now(timezone.utc)
    for event in bootstrap["events"]:
        deadline = datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
        if deadline > now:
            return {"gameweek": event["id"], "name": event["name"], "deadline_time": event["deadline_time"]}
    last = bootstrap["events"][-1]
    return {"gameweek": last["id"], "name": last["name"], "deadline_time": last["deadline_time"]}
