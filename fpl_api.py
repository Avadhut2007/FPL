"""
Thin client for the official (unofficial-but-public) Fantasy Premier League API.
Handles caching so you don't hammer the endpoint every time you run the app.
"""
import json
import os
import time
from datetime import datetime, timedelta

import requests

import config

HEADERS = {"User-Agent": "Mozilla/5.0 (FPL-Optimizer/1.0)"}


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


def _get(url: str, cache_name: str = None, force_refresh: bool = False, retries: int = 3):
    """GET a URL with optional on-disk caching and simple retry/backoff."""
    if cache_name and not force_refresh:
        cached = _read_cache(cache_name)
        if cached is not None:
            return cached

    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
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
    """All players, teams, positions, gameweeks — the main data dump."""
    return _get(config.BOOTSTRAP_URL, cache_name="bootstrap", force_refresh=force_refresh)


def get_fixtures(force_refresh: bool = False) -> list:
    """Full season fixture list with difficulty ratings."""
    return _get(config.FIXTURES_URL, cache_name="fixtures", force_refresh=force_refresh)


def get_player_history(player_id: int, force_refresh: bool = False) -> dict:
    """Per-gameweek history + upcoming fixtures for one player."""
    url = config.PLAYER_HISTORY_URL.format(player_id=player_id)
    return _get(url, cache_name=f"player_{player_id}", force_refresh=force_refresh)


def get_entry_picks(team_id: int, gw: int, force_refresh: bool = False) -> dict:
    """Your own current squad for a given gameweek (needs your FPL team ID)."""
    url = config.ENTRY_PICKS_URL.format(team_id=team_id, gw=gw)
    return _get(url, cache_name=f"entry_{team_id}_{gw}", force_refresh=force_refresh)


def get_entry_info(team_id: int, force_refresh: bool = False) -> dict:
    """Team name, manager name, and overall rank/points for a given FPL team ID."""
    url = config.ENTRY_URL.format(team_id=team_id)
    return _get(url, cache_name=f"entry_info_{team_id}", force_refresh=force_refresh)


def get_current_gameweek(bootstrap: dict) -> int:
    """Find the next unfinished gameweek from the events list."""
    for event in bootstrap["events"]:
        if event.get("is_next"):
            return event["id"]
    # fallback: first event that isn't finished
    for event in bootstrap["events"]:
        if not event.get("finished"):
            return event["id"]
    return bootstrap["events"][-1]["id"]
