"""
Turns raw FPL API JSON into a clean pandas DataFrame ready for prediction.
"""
import pandas as pd

import config

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def build_team_lookup(bootstrap: dict) -> dict:
    """team id -> short name, e.g. 1 -> 'ARS'."""
    return {t["id"]: t["short_name"] for t in bootstrap["teams"]}


def build_fixture_difficulty(fixtures: list, current_gw: int, team_lookup: dict) -> dict:
    """
    For each team, average difficulty of their next FIXTURE_LOOKAHEAD_GWS fixtures.
    Lower FDR (1) = easy, higher (5) = hard. We return an inverted 0-1 'fixture_score'
    where 1.0 = easiest run of fixtures, 0.0 = hardest.
    Teams with a blank gameweek (no fixture) get a neutral 0.5 for that slot.
    """
    upcoming = [f for f in fixtures if not f["finished"] and f.get("event") is not None
                and f["event"] >= current_gw and f["event"] < current_gw + config.FIXTURE_LOOKAHEAD_GWS]

    team_fdrs = {team_id: [] for team_id in team_lookup}
    for f in upcoming:
        home, away = f["team_h"], f["team_a"]
        if home in team_fdrs:
            team_fdrs[home].append(f["team_h_difficulty"])
        if away in team_fdrs:
            team_fdrs[away].append(f["team_a_difficulty"])

    scores = {}
    for team_id, fdrs in team_fdrs.items():
        if not fdrs:
            scores[team_id] = 0.5
        else:
            avg_fdr = sum(fdrs) / len(fdrs)
            # invert & normalize: FDR ranges 1(easy)-5(hard) -> score 1(easy)-0(hard)
            scores[team_id] = round((5 - avg_fdr) / 4, 3)
    return scores


def build_player_dataframe(bootstrap: dict, fixtures: list, current_gw: int) -> pd.DataFrame:
    """Main entry point: returns one row per player with all features needed for scoring."""
    team_lookup = build_team_lookup(bootstrap)
    fixture_scores = build_fixture_difficulty(fixtures, current_gw, team_lookup)

    rows = []
    for p in bootstrap["elements"]:
        minutes = p["minutes"]
        # season so far — estimate games played from minutes (90 min/game baseline)
        gw_played = max(current_gw - 1, 1)
        avg_minutes_per_gw = minutes / gw_played if gw_played else 0

        rows.append({
            "id": p["id"],
            "name": f"{p['first_name']} {p['second_name']}",
            "web_name": p["web_name"],
            "team_id": p["team"],
            "team": team_lookup.get(p["team"], "UNK"),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "price": p["now_cost"] / 10.0,          # API stores price *10
            "selected_by_percent": float(p["selected_by_percent"]),
            "form": float(p["form"]) if p["form"] else 0.0,
            "points_per_game": float(p["points_per_game"]) if p["points_per_game"] else 0.0,
            "total_points": p["total_points"],
            "ict_index": float(p["ict_index"]) if p["ict_index"] else 0.0,
            "minutes": minutes,
            "avg_minutes_per_gw": avg_minutes_per_gw,
            "status": p["status"],                  # 'a'=available, 'i'=injured, 'd'=doubtful, 's'=suspended
            "chance_of_playing_next_round": p["chance_of_playing_next_round"],
            "fixture_score": fixture_scores.get(p["team"], 0.5),
        })

    df = pd.DataFrame(rows)
    return df


def filter_available_players(df: pd.DataFrame) -> pd.DataFrame:
    """Drop players who are injured/suspended/unlikely to play (keeps 'doubtful' with a flag)."""
    df = df.copy()
    # chance_of_playing_next_round: None means fully fit/unknown-fine, 0-100 otherwise
    df["chance_of_playing_next_round"] = df["chance_of_playing_next_round"].fillna(100)
    df = df[df["status"].isin(["a", "d"])]           # drop injured(i) and suspended(s)
    df = df[df["chance_of_playing_next_round"] >= 50]  # drop very unlikely starters
    return df.reset_index(drop=True)


def build_fixtures_list(bootstrap: dict, fixtures: list, current_gw: int, lookahead: int = 8) -> list:
    """
    Upcoming fixtures for every team, next `lookahead` gameweeks, with FDR
    (fixture difficulty rating 1=easy..5=hard) for the fixtures scroll box.
    """
    team_lookup = build_team_lookup(bootstrap)
    upcoming = [
        f for f in fixtures
        if not f["finished"] and f.get("event") is not None
        and current_gw <= f["event"] < current_gw + lookahead
    ]
    upcoming.sort(key=lambda f: (f["event"], f.get("kickoff_time") or ""))

    out = []
    for f in upcoming:
        out.append({
            "gw": f["event"],
            "home": team_lookup.get(f["team_h"], "UNK"),
            "away": team_lookup.get(f["team_a"], "UNK"),
            "home_difficulty": f["team_h_difficulty"],
            "away_difficulty": f["team_a_difficulty"],
            "kickoff": f.get("kickoff_time"),
        })
    return out


def build_team_squad(picks_data: dict, bootstrap: dict) -> list:
    """
    Full 15-man squad for a FotMob-style pitch display, built straight from
    bootstrap elements (not the filtered/available-only dataframe) so every
    picked player shows up even if injured/suspended.
    """
    team_lookup = build_team_lookup(bootstrap)
    elements_by_id = {p["id"]: p for p in bootstrap["elements"]}

    squad = []
    for pick in picks_data["picks"]:
        p = elements_by_id.get(pick["element"])
        if not p:
            continue
        squad.append({
            "id": p["id"],
            "name": p["web_name"],
            "team": team_lookup.get(p["team"], "UNK"),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "price": round(p["now_cost"] / 10.0, 1),
            "total_points": p["total_points"],
            "status": p["status"],
            "is_captain": pick["is_captain"],
            "is_vice_captain": pick["is_vice_captain"],
            "slot": pick["position"],   # 1-11 starting XI, 12-15 bench
        })
    return squad


STATUS_LABELS = {
    "a": "Available",
    "i": "Injured",
    "s": "Suspended",
    "d": "Doubtful",
    "u": "Unavailable",
    "n": "Not available",
}


def build_player_news(bootstrap: dict) -> list:
    """
    All player news straight from the FPL API's own per-player 'news' field —
    covers injuries, suspensions, loan/transfer moves, personal leave, and any
    other club-reported update, not just injuries. No external news source
    needed. Only players with a non-empty news blurb OR a non-'a' status are
    included (a fully fit player with nothing reported is skipped).
    Sorted with most recently updated news first.
    """
    team_lookup = build_team_lookup(bootstrap)
    items = []
    for p in bootstrap["elements"]:
        status = p["status"]
        news = (p.get("news") or "").strip()
        if status == "a" and not news:
            continue  # fully fit, nothing reported — not news

        items.append({
            "name": p["web_name"],
            "team": team_lookup.get(p["team"], "UNK"),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "status": status,
            "status_label": STATUS_LABELS.get(status, "Update"),
            "news": news or "No further details provided yet.",
            "chance_of_playing_next_round": p["chance_of_playing_next_round"],
            "news_added": p.get("news_added"),
        })

    items.sort(key=lambda x: x["news_added"] or "", reverse=True)
    return items
