"""
FPL Squad Lab — Flask web app.
Wraps the existing optimizer pipeline (fpl_api, data_processor, predictor,
optimizer) plus external_data (ESPN scores/standings, BBC transfer news)
behind a small JSON API, served as a multi-page dark-themed site.
"""
import os
import stat
from datetime import datetime

from flask import Flask, jsonify, render_template, request
import concurrent.futures

import config
import data_processor
import external_data
import fpl_api
import optimizer
import predictor


def _fix_cbc_permissions():
    """
    Walk PuLP's install directory and chmod +x any solver binaries.
    On serverless platforms, files are often re-packaged and lose their
    execute permission, which makes PuLP fail with a "solver not found" or
    "permission denied" error even though the binary is right there.
    Runs once at import time, before any request touches the optimizer.
    """
    try:
        import pulp
        pulp_dir = os.path.dirname(pulp.__file__)
        for root, _dirs, files in os.walk(pulp_dir):
            for fname in files:
                if "cbc" in fname.lower() and not fname.endswith((".py", ".pyc", ".txt", ".md")):
                    fpath = os.path.join(root, fname)
                    try:
                        st = os.stat(fpath)
                        os.chmod(fpath, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                    except OSError:
                        pass
    except Exception:
        pass  # best-effort — if this fails, the app will still try to run


_fix_cbc_permissions()

app = Flask(__name__)

# Two caches: one for the AVAILABLE-only pool (used for the open transfer
# market — Squad Builder, Transfer suggestions), one for the FULL pool
# including injured/unavailable players (needed so your own squad's Best XI
# picker can see every player you own, not just the ones fit to play).
# Predicted points are normalized min-max across whatever dataframe they're
# computed on, so these two pools are cached and scored separately rather
# than filtering after the fact.
_df_cache = {"df": None, "gw": None}
_full_df_cache = {"df": None, "gw": None}


def get_scored_dataframe(force_refresh=False):
    if _df_cache["df"] is not None and not force_refresh:
        return _df_cache["df"], _df_cache["gw"]

    bootstrap = fpl_api.get_bootstrap_data(force_refresh=force_refresh)
    fixtures = fpl_api.get_fixtures(force_refresh=force_refresh)
    current_gw = fpl_api.get_current_gameweek(bootstrap)

    df = data_processor.build_player_dataframe(bootstrap, fixtures, current_gw)
    df = data_processor.filter_available_players(df)
    df = predictor.compute_predicted_points(df)

    _df_cache["df"] = df
    _df_cache["gw"] = current_gw
    return df, current_gw


def get_full_scored_dataframe(force_refresh=False):
    """Every player (including injured/suspended/unavailable), scored with
    the same predictor — used for Your Team's Best XI picker, so a squad
    member who's flagged doubtful still shows up correctly rather than
    vanishing from their own squad view."""
    if _full_df_cache["df"] is not None and not force_refresh:
        return _full_df_cache["df"], _full_df_cache["gw"]

    bootstrap = fpl_api.get_bootstrap_data(force_refresh=force_refresh)
    fixtures = fpl_api.get_fixtures(force_refresh=force_refresh)
    current_gw = fpl_api.get_current_gameweek(bootstrap)

    df = data_processor.build_player_dataframe(bootstrap, fixtures, current_gw)
    df = predictor.compute_predicted_points(df)

    _full_df_cache["df"] = df
    _full_df_cache["gw"] = current_gw
    return df, current_gw


def player_to_dict(row):
    return {
        "id": int(row["id"]),
        "name": row["web_name"],
        "team": row["team"],
        "team_crest": row.get("team_crest", ""),
        "photo": row.get("photo", ""),
        "position": row["position"],
        "price": round(float(row["price"]), 1),
        "predicted_points": round(float(row["predicted_points"]), 2),
        "form": round(float(row["form"]), 1),
        "value": round(float(row["value"]), 2),
    }


# ================= PAGES =================

@app.route("/")
def index():
    return render_template("index.html", active="home")


@app.route("/squad")
def squad_page():
    return render_template("squad.html", active="squad")


@app.route("/your-team")
def your_team_page():
    return render_template("your_team.html", active="your-team")


@app.route("/chart")
def chart_page():
    return render_template("chart.html", active="chart")


@app.route("/news")
def news_page():
    return render_template("news.html", active="news")


@app.route("/fixtures")
def fixtures_page():
    return render_template("fixtures.html", active="fixtures")


@app.route("/history")
def history_page():
    return render_template("history.html", active="history")


@app.route("/live-scores")
def live_scores_page():
    return render_template("live_scores.html", active="live-scores")


@app.route("/transfer-news")
def transfer_news_page():
    return render_template("transfer_news.html", active="transfer-news")


# ================= API =================

@app.route("/api/squad")
def api_squad():
    budget = request.args.get("budget", default=config.BUDGET, type=float)
    force_refresh = request.args.get("refresh", default="0") == "1"

    try:
        df, gw = get_scored_dataframe(force_refresh=force_refresh)
        squad = optimizer.pick_best_squad(df, budget=budget)
        starting_xi, bench, captain, vice_captain, formation = optimizer.pick_best_starting_xi(squad)

        total_points = float(starting_xi["predicted_points"].sum() + captain["predicted_points"])

        return jsonify({
            "ok": True,
            "gameweek": gw,
            "formation": formation,
            "budget_used": round(float(squad["price"].sum()), 1),
            "budget_total": budget,
            "projected_points": round(total_points, 1),
            "captain": player_to_dict(captain),
            "vice_captain": player_to_dict(vice_captain),
            "starting_xi": [player_to_dict(r) for _, r in starting_xi.iterrows()],
            "bench": [player_to_dict(r) for _, r in bench.iterrows()],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/top")
def api_top():
    n = request.args.get("n", default=30, type=int)
    position = request.args.get("position", default=None, type=str)

    try:
        df, gw = get_scored_dataframe()
        if position and position != "ALL":
            df = df[df["position"] == position]
        top = df.head(n)
        return jsonify({
            "ok": True,
            "gameweek": gw,
            "players": [player_to_dict(r) for _, r in top.iterrows()],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/player-history/<int:player_id>")
def api_player_history(player_id):
    """This-season gameweek-by-gameweek points for one player, for the
    Player Explorer's click-to-expand chart."""
    try:
        history_data = fpl_api.get_player_history(player_id)
        gw_history = data_processor.build_player_gw_history(history_data)
        return jsonify({"ok": True, "history": gw_history})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/transfers")
def api_transfers():
    team_id = request.args.get("team_id", type=int)
    free_transfers = request.args.get("free_transfers", default=1, type=int)
    budget_bank = request.args.get("budget_bank", default=0.0, type=float)

    if not team_id:
        return jsonify({"ok": False, "error": "team_id is required"}), 400

    try:
        df, gw = get_scored_dataframe()
        picks_data = fpl_api.get_entry_picks(team_id, max(gw - 1, 1))
        current_ids = [p["element"] for p in picks_data["picks"]]

        if not budget_bank:
            budget_bank = picks_data.get("entry_history", {}).get("bank", 0) / 10.0

        suggestions = optimizer.suggest_transfers(
            current_ids, df, free_transfers=free_transfers, budget_bank=budget_bank,
            history_fetcher=fpl_api.get_player_history,
        )
        return jsonify({"ok": True, "gameweek": gw, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/best-lineup/<int:team_id>")
def api_best_lineup(team_id):
    """
    Best starting XI + captain/vice-captain FROM YOUR OWN 15-MAN SQUAD —
    reuses optimizer.pick_best_starting_xi exactly as-is (the same function
    the Squad Builder uses), just scoped to the players you already own
    instead of the whole transfer market. No new scoring logic.
    """
    try:
        full_df, gw = get_full_scored_dataframe()
        picks_data = fpl_api.get_entry_picks(team_id, max(gw - 1, 1))
        current_ids = [p["element"] for p in picks_data["picks"]]

        squad_df = full_df[full_df["id"].isin(current_ids)].copy()

        # Players who definitely won't play (injured/suspended/unavailable)
        # shouldn't be picked to start or captained, even if their scored
        # points look decent — zero them out so the same picker naturally
        # benches them. Doubtful ("d") players are left as-is since they
        # might still play.
        squad_df.loc[squad_df["status"].isin(["i", "s", "u", "n"]), "predicted_points"] = 0.0

        starting_xi, bench, captain, vice_captain, formation = optimizer.pick_best_starting_xi(squad_df)

        return jsonify({
            "ok": True,
            "gameweek": gw,
            "formation": formation,
            "captain": player_to_dict(captain),
            "vice_captain": player_to_dict(vice_captain),
            "starting_xi": [player_to_dict(r) for _, r in starting_xi.iterrows()],
            "bench": [player_to_dict(r) for _, r in bench.iterrows()],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/injury-tracker/<int:team_id>")
def api_injury_tracker(team_id):
    """
    For every injured/doubtful/suspended player in this manager's squad,
    suggest a replacement — reusing optimizer.suggest_transfers exactly as-is
    (via target_ids), no separate scoring logic.
    """
    try:
        df, gw = get_scored_dataframe()
        bootstrap = fpl_api.get_bootstrap_data()
        picks_data = fpl_api.get_entry_picks(team_id, max(gw - 1, 1))
        squad = data_processor.build_team_squad(picks_data, bootstrap)

        flagged = [p for p in squad if p["status"] != "a"]
        if not flagged:
            return jsonify({"ok": True, "gameweek": gw, "flagged_players": [], "suggestions": []})

        current_ids = [p["id"] for p in squad]
        target_ids = [p["id"] for p in flagged]
        budget_bank = picks_data.get("entry_history", {}).get("bank", 0) / 10.0

        suggestions = optimizer.suggest_transfers(
            current_ids, df, budget_bank=budget_bank,
            history_fetcher=fpl_api.get_player_history,
            target_ids=target_ids,
        )

        return jsonify({
            "ok": True,
            "gameweek": gw,
            "flagged_players": flagged,
            "suggestions": suggestions,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/team/<int:team_id>")
def api_team(team_id):
    try:
        bootstrap = fpl_api.get_bootstrap_data()
        gw = fpl_api.get_current_gameweek(bootstrap)
        entry_info = fpl_api.get_entry_info(team_id)
        picks_data = fpl_api.get_entry_picks(team_id, max(gw - 1, 1))
        squad = data_processor.build_team_squad(picks_data, bootstrap)

        manager_name = f"{entry_info.get('player_first_name', '')} {entry_info.get('player_last_name', '')}".strip()

        return jsonify({
            "ok": True,
            "gameweek": gw,
            "team_name": entry_info.get("name", "Unknown FC"),
            "manager_name": manager_name or "Unknown Manager",
            "overall_points": entry_info.get("summary_overall_points"),
            "overall_rank": entry_info.get("summary_overall_rank"),
            "bank": picks_data.get("entry_history", {}).get("bank", 0) / 10.0,
            "squad": squad,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/deadline")
def api_deadline():
    """Next gameweek deadline, for the Deadline Reminder widget's countdown
    and "Add to Google Calendar" button."""
    try:
        bootstrap = fpl_api.get_bootstrap_data()
        deadline = fpl_api.get_next_deadline(bootstrap)
        return jsonify({"ok": True, **deadline})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/fixtures")
def api_fixtures():
    """Team x gameweek FDR grid for the Fixtures page."""
    lookahead = request.args.get("lookahead", default=5, type=int)
    try:
        bootstrap = fpl_api.get_bootstrap_data()
        fixtures = fpl_api.get_fixtures()
        current_gw = fpl_api.get_current_gameweek(bootstrap)
        grid = data_processor.build_fdr_grid(bootstrap, fixtures, current_gw, lookahead=lookahead)
        return jsonify({"ok": True, "current_gameweek": current_gw, **grid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chart-data")
def api_chart_data():
    n = request.args.get("n", default=12, type=int)
    position = request.args.get("position", default="ALL", type=str)
    metric = request.args.get("metric", default="predicted_points", type=str)

    try:
        df, gw = get_scored_dataframe()
        if position != "ALL":
            df = df[df["position"] == position]

        sort_col = "total_points" if metric == "total_points" else "predicted_points"
        top = df.sort_values(sort_col, ascending=False).head(n)

        return jsonify({
            "ok": True,
            "gameweek": gw,
            "labels": top["web_name"].tolist(),
            "predicted_points": [round(float(x), 2) for x in top["predicted_points"]],
            "total_points": [int(x) for x in top["total_points"]],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/news")
def api_news():
    try:
        bootstrap = fpl_api.get_bootstrap_data()
        items = data_processor.build_player_news(bootstrap)
        return jsonify({"ok": True, "news": items})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/history")
def api_history():
    """
    Past-season performance for players, sorted by this season's points
    (highest first). Paginated with offset/limit so the frontend can page
    through ALL players without one request trying to fetch 700+ player
    histories at once (which would time out on serverless). Each page's
    histories are fetched concurrently for speed.
    """
    offset = request.args.get("offset", default=0, type=int)
    limit = request.args.get("limit", default=50, type=int)
    limit = min(limit, 100)  # hard cap per request

    try:
        bootstrap = fpl_api.get_bootstrap_data()
        team_lookup = data_processor.build_team_lookup(bootstrap)

        all_elements = sorted(bootstrap["elements"], key=lambda p: p["total_points"], reverse=True)
        page = all_elements[offset:offset + limit]

        def fetch_one(p):
            history = fpl_api.get_player_history(p["id"])
            past = history.get("history_past", [])[-3:]  # last up to 3 completed seasons
            return {
                "name": p["web_name"],
                "team": team_lookup.get(p["team"], "UNK"),
                "position": data_processor.POSITION_MAP.get(p["element_type"], "UNK"),
                "current_points": p["total_points"],
                "seasons": [
                    {"season": s["season_name"], "points": s["total_points"]}
                    for s in past
                ],
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            result = list(pool.map(fetch_one, page))

        return jsonify({
            "ok": True,
            "players": result,
            "offset": offset,
            "limit": limit,
            "total": len(all_elements),
            "has_more": offset + limit < len(all_elements),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _current_gw_date_range():
    """
    'YYYYMMDD' start/end covering every fixture in the current FPL
    gameweek — so the Live Scores page shows all of this gameweek's
    matches (already played, live, or still to come) rather than just
    whatever happens to kick off today.
    """
    bootstrap = fpl_api.get_bootstrap_data()
    fixtures = fpl_api.get_fixtures()
    current_gw = fpl_api.get_current_gameweek(bootstrap)

    kickoffs = [
        f["kickoff_time"] for f in fixtures
        if f.get("event") == current_gw and f.get("kickoff_time")
    ]
    if not kickoffs:
        today = datetime.utcnow().strftime("%Y%m%d")
        return today, today

    dates = [datetime.fromisoformat(k.replace("Z", "+00:00")) for k in kickoffs]
    return min(dates).strftime("%Y%m%d"), max(dates).strftime("%Y%m%d")


@app.route("/api/live-scores")
def api_live_scores():
    try:
        date_from, date_to = _current_gw_date_range()
    except Exception:
        date_from, date_to = None, None
    games = external_data.get_live_scores(date_from, date_to)
    return jsonify({"ok": True, "games": games})


@app.route("/api/standings")
def api_standings():
    table = external_data.get_league_table()
    return jsonify({"ok": True, "table": table})


@app.route("/api/transfer-news")
def api_transfer_news():
    news = external_data.get_transfer_news(limit=25)
    return jsonify({"ok": True, "news": news})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
