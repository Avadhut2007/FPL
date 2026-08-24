"""
FPL Squad Lab — Flask web app.
Wraps the existing optimizer pipeline (fpl_api, data_processor, predictor,
optimizer) behind a small JSON API, served as a multi-page dark-themed site.
"""
import os
import stat

from flask import Flask, jsonify, render_template, request
import concurrent.futures

import config
import data_processor
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

# Simple in-process cache of the scored player dataframe so repeated
# requests (e.g. changing budget) don't re-fetch from the FPL API every time.
_df_cache = {"df": None, "gw": None}


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


def player_to_dict(row):
    return {
        "id": int(row["id"]),
        "name": row["web_name"],
        "team": row["team"],
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


@app.route("/transfers")
def transfers_page():
    return render_template("transfers.html", active="transfers")


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
    n = request.args.get("n", default=20, type=int)
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

        # Auto-pick up "money in the bank" from the entry's own history so the
        # user doesn't have to enter it manually, unless they explicitly did.
        if not budget_bank:
            budget_bank = picks_data.get("entry_history", {}).get("bank", 0) / 10.0

        suggestions = optimizer.suggest_transfers(
            current_ids, df, free_transfers=free_transfers, budget_bank=budget_bank,
            history_fetcher=fpl_api.get_player_history,
        )
        return jsonify({"ok": True, "gameweek": gw, "suggestions": suggestions})
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


@app.route("/api/fixtures")
def api_fixtures():
    try:
        bootstrap = fpl_api.get_bootstrap_data()
        fixtures = fpl_api.get_fixtures()
        current_gw = fpl_api.get_current_gameweek(bootstrap)
        items = data_processor.build_fixtures_list(bootstrap, fixtures, current_gw)
        return jsonify({"ok": True, "gameweek": current_gw, "fixtures": items})
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
