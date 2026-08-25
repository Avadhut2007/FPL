"""
Turns raw FPL API JSON into clean, page-ready data:
  - build_player_dataframe / filter_available_players -> the scored player pool
  - build_team_squad          -> a manager's 15-man squad for the Transfers page
  - get_available_gameweeks   -> which gameweeks have fixtures
  - build_fdr_grid            -> team x gameweek fixture-difficulty grid
  - build_player_news         -> injuries/doubts/suspensions, for the News page
  - build_player_gw_history   -> a single player's points per gameweek this season
"""
import pandas as pd

import config

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

STATUS_LABELS = {
    "a": "Available", "d": "Doubtful", "i": "Injured",
    "s": "Suspended", "u": "Unavailable", "n": "Not available",
}


def team_crest_url(team_code) -> str:
    return config.TEAM_CREST_URL.format(team_code=team_code)


def player_photo_url(photo_field: str) -> str:
    """photo_field looks like '123456.jpg' — the numeric part is the code
    the media CDN actually keys off."""
    code = (photo_field or "0.jpg").split(".")[0]
    return config.PLAYER_PHOTO_URL.format(player_code=code)


def build_team_lookup(bootstrap: dict) -> dict:
    return {t["id"]: t["short_name"] for t in bootstrap["teams"]}


def build_team_crest_lookup(bootstrap: dict) -> dict:
    return {t["id"]: team_crest_url(t.get("code", t["id"])) for t in bootstrap["teams"]}


def build_fixture_difficulty(fixtures: list, current_gw: int, team_lookup: dict) -> dict:
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
            scores[team_id] = round((5 - avg_fdr) / 4, 3)
    return scores


def build_player_dataframe(bootstrap: dict, fixtures: list, current_gw: int) -> pd.DataFrame:
    team_lookup = build_team_lookup(bootstrap)
    crest_lookup = build_team_crest_lookup(bootstrap)
    fixture_scores = build_fixture_difficulty(fixtures, current_gw, team_lookup)

    rows = []
    for p in bootstrap["elements"]:
        minutes = p["minutes"]
        gw_played = max(current_gw - 1, 1)
        avg_minutes_per_gw = minutes / gw_played if gw_played else 0

        rows.append({
            "id": p["id"],
            "name": f"{p['first_name']} {p['second_name']}",
            "web_name": p["web_name"],
            "team_id": p["team"],
            "team": team_lookup.get(p["team"], "UNK"),
            "team_crest": crest_lookup.get(p["team"], ""),
            "photo": player_photo_url(p.get("photo")),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "price": p["now_cost"] / 10.0,
            "selected_by_percent": float(p["selected_by_percent"]),
            "form": float(p["form"]) if p["form"] else 0.0,
            "points_per_game": float(p["points_per_game"]) if p["points_per_game"] else 0.0,
            "total_points": p["total_points"],
            "ict_index": float(p["ict_index"]) if p["ict_index"] else 0.0,
            "minutes": minutes,
            "avg_minutes_per_gw": avg_minutes_per_gw,
            "status": p["status"],
            "chance_of_playing_next_round": p["chance_of_playing_next_round"],
            "fixture_score": fixture_scores.get(p["team"], 0.5),
        })

    return pd.DataFrame(rows)


def filter_available_players(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["chance_of_playing_next_round"] = df["chance_of_playing_next_round"].fillna(100)
    df = df[df["status"].isin(["a", "d"])]
    df = df[df["chance_of_playing_next_round"] >= 50]
    return df.reset_index(drop=True)


def build_team_squad(picks_data: dict, bootstrap: dict) -> list:
    team_lookup = build_team_lookup(bootstrap)
    crest_lookup = build_team_crest_lookup(bootstrap)
    elements_by_id = {e["id"]: e for e in bootstrap["elements"]}

    squad = []
    for pick in picks_data["picks"]:
        p = elements_by_id.get(pick["element"])
        if not p:
            continue
        squad.append({
            "id": p["id"],
            "name": p["web_name"],
            "team": team_lookup.get(p["team"], "UNK"),
            "team_crest": crest_lookup.get(p["team"], ""),
            "photo": player_photo_url(p.get("photo")),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "price": p["now_cost"] / 10.0,
            "status": p["status"],
            "status_label": STATUS_LABELS.get(p["status"], p["status"]),
            "news": p.get("news") or "",
            "slot": pick["position"],
            "is_captain": pick.get("is_captain", False),
            "is_vice_captain": pick.get("is_vice_captain", False),
        })
    return sorted(squad, key=lambda x: x["slot"])


def get_available_gameweeks(fixtures: list) -> list:
    gws = {f["event"] for f in fixtures if f.get("event") is not None}
    return sorted(gws)


def build_fdr_grid(bootstrap: dict, fixtures: list, current_gw: int, lookahead: int = 5) -> dict:
    """
    Team x gameweek fixture-difficulty grid for the Fixtures page — the
    classic "FDR ticker": one row per club, one column per upcoming gameweek,
    each cell showing the opponent (H/A) and a 1(easy)-5(hard) difficulty.
    """
    team_lookup = build_team_lookup(bootstrap)
    crest_lookup = build_team_crest_lookup(bootstrap)

    gws = list(range(current_gw, current_gw + lookahead))
    upcoming = [f for f in fixtures if f.get("event") in gws]

    # team_id -> {gw: {opponent, is_home, difficulty}}
    grid = {team_id: {} for team_id in team_lookup}
    for f in upcoming:
        gw = f["event"]
        home, away = f["team_h"], f["team_a"]
        if home in grid:
            grid[home][gw] = {
                "opponent": team_lookup.get(away, "UNK"),
                "is_home": True,
                "difficulty": f["team_h_difficulty"],
            }
        if away in grid:
            grid[away][gw] = {
                "opponent": team_lookup.get(home, "UNK"),
                "is_home": False,
                "difficulty": f["team_a_difficulty"],
            }

    rows = []
    for team_id, short_name in team_lookup.items():
        rows.append({
            "team": short_name,
            "team_crest": crest_lookup.get(team_id, ""),
            "fixtures": [grid[team_id].get(gw) for gw in gws],
        })
    rows.sort(key=lambda r: r["team"])

    return {"gameweeks": gws, "teams": rows}


def build_player_news(bootstrap: dict) -> list:
    team_lookup = build_team_lookup(bootstrap)
    crest_lookup = build_team_crest_lookup(bootstrap)
    items = []
    for p in bootstrap["elements"]:
        has_news = bool(p.get("news"))
        if not has_news and p["status"] == "a":
            continue
        items.append({
            "name": p["web_name"],
            "team": team_lookup.get(p["team"], "UNK"),
            "team_crest": crest_lookup.get(p["team"], ""),
            "photo": player_photo_url(p.get("photo")),
            "position": POSITION_MAP.get(p["element_type"], "UNK"),
            "status": p["status"],
            "status_label": STATUS_LABELS.get(p["status"], p["status"]),
            "chance_of_playing_next_round": p["chance_of_playing_next_round"],
            "news": p.get("news") or "",
        })

    order = {"i": 0, "s": 1, "d": 2, "u": 3, "n": 4, "a": 5}
    items.sort(key=lambda x: order.get(x["status"], 9))
    return items


def build_player_gw_history(history_data: dict) -> list:
    """This-season, gameweek-by-gameweek points for one player (for the
    Player Explorer's click-to-expand chart). history_data is the raw
    element-summary payload from fpl_api.get_player_history."""
    return [
        {"gw": g["round"], "points": g["total_points"], "minutes": g["minutes"]}
        for g in history_data.get("history", [])
    ]
