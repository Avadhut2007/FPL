"""
FPL Squad Lab — Flask web app.
Wraps the existing optimizer pipeline (fpl_api, data_processor, predictor,
optimizer) behind a small JSON API, served with a dark-themed dashboard UI.
"""
from flask import Flask, jsonify, render_template, request

import config
import data_processor
import fpl_api
import optimizer
import predictor

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


@app.route("/")
def index():
    return render_template("index.html")


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
        bootstrap = fpl_api.get_bootstrap_data()
        picks_data = fpl_api.get_entry_picks(team_id, max(gw - 1, 1))
        current_ids = [p["element"] for p in picks_data["picks"]]

        suggestions = optimizer.suggest_transfers(
            current_ids, df, free_transfers=free_transfers, budget_bank=budget_bank
        )
        return jsonify({"ok": True, "gameweek": gw, "suggestions": suggestions})
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
