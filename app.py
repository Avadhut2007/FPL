"""
FPL Squad Lab — Flask web app.

Wraps the existing optimizer pipeline (fpl_api, data_processor,
predictor, optimizer) plus external_data (ESPN scores/standings,
BBC transfer news) behind a small JSON API, served as a multi-page
dark-themed site.
"""

import os
import stat
import concurrent.futures

from datetime import datetime

from flask import Flask, jsonify, render_template, request

import config
import data_processor
import external_data
import fpl_api
import optimizer
import predictor


# ============================================================
# PUlp / CBC PERMISSIONS
# ============================================================

def _fix_cbc_permissions():
    """
    Walk PuLP's install directory and chmod +x any solver binaries.

    On serverless platforms, files are sometimes re-packaged and lose
    their execute permission, which makes PuLP fail with a solver
    permission error even though the binary exists.

    This runs once at import time.
    """

    try:
        import pulp

        pulp_dir = os.path.dirname(
            pulp.__file__
        )

        for root, _dirs, files in os.walk(
            pulp_dir
        ):

            for fname in files:

                if (
                    "cbc" in fname.lower()
                    and not fname.endswith(
                        (
                            ".py",
                            ".pyc",
                            ".txt",
                            ".md",
                        )
                    )
                ):

                    fpath = os.path.join(
                        root,
                        fname,
                    )

                    try:
                        st = os.stat(
                            fpath
                        )

                        os.chmod(
                            fpath,
                            st.st_mode
                            | stat.S_IEXEC
                            | stat.S_IXGRP
                            | stat.S_IXOTH,
                        )

                    except OSError:
                        pass

    except Exception:
        pass


_fix_cbc_permissions()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)


# ============================================================
# IN-PROCESS DATA CACHE
# ============================================================

_df_cache = {
    "df": None,
    "gw": None,
}


def get_scored_dataframe(
    force_refresh=False,
):
    """
    Build and cache the scored player dataframe.

    This prevents repeated requests such as changing the squad
    budget from re-fetching the complete FPL dataset.
    """

    if (
        _df_cache["df"] is not None
        and not force_refresh
    ):
        return (
            _df_cache["df"],
            _df_cache["gw"],
        )

    bootstrap = fpl_api.get_bootstrap_data(
        force_refresh=force_refresh
    )

    fixtures = fpl_api.get_fixtures(
        force_refresh=force_refresh
    )

    current_gw = (
        fpl_api.get_current_gameweek(
            bootstrap
        )
    )

    df = (
        data_processor.build_player_dataframe(
            bootstrap,
            fixtures,
            current_gw,
        )
    )

    df = (
        data_processor.filter_available_players(
            df
        )
    )

    df = (
        predictor.compute_predicted_points(
            df
        )
    )

    _df_cache["df"] = df
    _df_cache["gw"] = current_gw

    return (
        df,
        current_gw,
    )


# ============================================================
# PLAYER SERIALIZER
# ============================================================

def player_to_dict(row):
    """
    Convert a dataframe row into JSON-safe player data.
    """

    return {
        "id": int(
            row["id"]
        ),

        "name": row[
            "web_name"
        ],

        "team": row[
            "team"
        ],

        "team_crest": row.get(
            "team_crest",
            "",
        ),

        "photo": row.get(
            "photo",
            "",
        ),

        "position": row[
            "position"
        ],

        "price": round(
            float(
                row["price"]
            ),
            1,
        ),

        "predicted_points": round(
            float(
                row["predicted_points"]
            ),
            2,
        ),

        "form": round(
            float(
                row["form"]
            ),
            1,
        ),

        "value": round(
            float(
                row["value"]
            ),
            2,
        ),
    }


# ============================================================
# PAGES
# ============================================================

@app.route("/")
def index():
    return render_template(
        "index.html",
        active="home",
    )


@app.route("/squad")
def squad_page():
    return render_template(
        "squad.html",
        active="squad",
    )


@app.route("/transfers")
def transfers_page():
    return render_template(
        "transfers.html",
        active="transfers",
    )


@app.route("/chart")
def chart_page():
    return render_template(
        "chart.html",
        active="chart",
    )


@app.route("/news")
def news_page():
    return render_template(
        "news.html",
        active="news",
    )


@app.route("/fixtures")
def fixtures_page():
    return render_template(
        "fixtures.html",
        active="fixtures",
    )


@app.route("/history")
def history_page():
    return render_template(
        "history.html",
        active="history",
    )


@app.route("/live-scores")
def live_scores_page():
    return render_template(
        "live_scores.html",
        active="live-scores",
    )


@app.route("/transfer-news")
def transfer_news_page():
    return render_template(
        "transfer_news.html",
        active="transfer-news",
    )


# ============================================================
# API — SQUAD
# ============================================================

@app.route("/api/squad")
def api_squad():

    budget = request.args.get(
        "budget",
        default=config.BUDGET,
        type=float,
    )

    force_refresh = (
        request.args.get(
            "refresh",
            default="0",
        )
        == "1"
    )

    try:

        df, gw = get_scored_dataframe(
            force_refresh=force_refresh
        )

        squad = optimizer.pick_best_squad(
            df,
            budget=budget,
        )

        (
            starting_xi,
            bench,
            captain,
            vice_captain,
            formation,
        ) = optimizer.pick_best_starting_xi(
            squad
        )

        total_points = float(
            starting_xi[
                "predicted_points"
            ].sum()
            + captain[
                "predicted_points"
            ]
        )

        return jsonify(
            {
                "ok": True,

                "gameweek": gw,

                "formation": formation,

                "budget_used": round(
                    float(
                        squad["price"].sum()
                    ),
                    1,
                ),

                "budget_total": budget,

                "projected_points": round(
                    total_points,
                    1,
                ),

                "captain": player_to_dict(
                    captain
                ),

                "vice_captain": player_to_dict(
                    vice_captain
                ),

                "starting_xi": [
                    player_to_dict(row)
                    for _, row
                    in starting_xi.iterrows()
                ],

                "bench": [
                    player_to_dict(row)
                    for _, row
                    in bench.iterrows()
                ],
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — TOP PLAYERS
# ============================================================

@app.route("/api/top")
def api_top():

    n = request.args.get(
        "n",
        default=30,
        type=int,
    )

    position = request.args.get(
        "position",
        default=None,
        type=str,
    )

    try:

        df, gw = get_scored_dataframe()

        if position and position != "ALL":
            df = df[
                df["position"] == position
            ]

        top = df.head(n)

        return jsonify(
            {
                "ok": True,

                "gameweek": gw,

                "players": [
                    player_to_dict(row)
                    for _, row
                    in top.iterrows()
                ],
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — PLAYER HISTORY
# ============================================================

@app.route(
    "/api/player-history/<int:player_id>"
)
def api_player_history(
    player_id,
):
    """
    This-season gameweek-by-gameweek points
    for one player.
    """

    try:

        history_data = (
            fpl_api.get_player_history(
                player_id
            )
        )

        gw_history = (
            data_processor.build_player_gw_history(
                history_data
            )
        )

        return jsonify(
            {
                "ok": True,
                "history": gw_history,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — TRANSFERS
# ============================================================

@app.route("/api/transfers")
def api_transfers():

    team_id = request.args.get(
        "team_id",
        type=int,
    )

    free_transfers = request.args.get(
        "free_transfers",
        default=1,
        type=int,
    )

    budget_bank = request.args.get(
        "budget_bank",
        default=0.0,
        type=float,
    )

    if not team_id:

        return jsonify(
            {
                "ok": False,
                "error": "team_id is required",
            }
        ), 400

    try:

        df, gw = get_scored_dataframe()

        picks_data = (
            fpl_api.get_entry_picks(
                team_id,
                max(
                    gw - 1,
                    1,
                ),
            )
        )

        current_ids = [
            player["element"]
            for player
            in picks_data["picks"]
        ]

        if not budget_bank:

            budget_bank = (
                picks_data
                .get(
                    "entry_history",
                    {},
                )
                .get(
                    "bank",
                    0,
                )
                / 10.0
            )

        suggestions = (
            optimizer.suggest_transfers(
                current_ids,
                df,
                free_transfers=free_transfers,
                budget_bank=budget_bank,
                history_fetcher=(
                    fpl_api.get_player_history
                ),
            )
        )

        return jsonify(
            {
                "ok": True,
                "gameweek": gw,
                "suggestions": suggestions,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — INJURY TRACKER
# ============================================================

@app.route(
    "/api/injury-tracker/<int:team_id>"
)
def api_injury_tracker(
    team_id,
):
    """
    Find injured/doubtful/suspended players
    in a manager's squad and suggest replacements.
    """

    try:

        df, gw = get_scored_dataframe()

        bootstrap = (
            fpl_api.get_bootstrap_data()
        )

        picks_data = (
            fpl_api.get_entry_picks(
                team_id,
                max(
                    gw - 1,
                    1,
                ),
            )
        )

        squad = (
            data_processor.build_team_squad(
                picks_data,
                bootstrap,
            )
        )

        flagged = [
            player
            for player in squad
            if player["status"] != "a"
        ]

        if not flagged:

            return jsonify(
                {
                    "ok": True,
                    "gameweek": gw,
                    "flagged_players": [],
                    "suggestions": [],
                }
            )

        current_ids = [
            player["id"]
            for player in squad
        ]

        target_ids = [
            player["id"]
            for player in flagged
        ]

        budget_bank = (
            picks_data
            .get(
                "entry_history",
                {},
            )
            .get(
                "bank",
                0,
            )
            / 10.0
        )

        suggestions = (
            optimizer.suggest_transfers(
                current_ids,
                df,
                budget_bank=budget_bank,
                history_fetcher=(
                    fpl_api.get_player_history
                ),
                target_ids=target_ids,
            )
        )

        return jsonify(
            {
                "ok": True,
                "gameweek": gw,
                "flagged_players": flagged,
                "suggestions": suggestions,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — TEAM
# ============================================================

@app.route("/api/team/<int:team_id>")
def api_team(
    team_id,
):

    try:

        bootstrap = (
            fpl_api.get_bootstrap_data()
        )

        gw = (
            fpl_api.get_current_gameweek(
                bootstrap
            )
        )

        entry_info = (
            fpl_api.get_entry_info(
                team_id
            )
        )

        picks_data = (
            fpl_api.get_entry_picks(
                team_id,
                max(
                    gw - 1,
                    1,
                ),
            )
        )

        squad = (
            data_processor.build_team_squad(
                picks_data,
                bootstrap,
            )
        )

        manager_name = (
            f"{entry_info.get('player_first_name', '')} "
            f"{entry_info.get('player_last_name', '')}"
        ).strip()

        return jsonify(
            {
                "ok": True,

                "gameweek": gw,

                "team_name": entry_info.get(
                    "name",
                    "Unknown FC",
                ),

                "manager_name": (
                    manager_name
                    or "Unknown Manager"
                ),

                "overall_points": (
                    entry_info.get(
                        "summary_overall_points"
                    )
                ),

                "overall_rank": (
                    entry_info.get(
                        "summary_overall_rank"
                    )
                ),

                "bank": (
                    picks_data
                    .get(
                        "entry_history",
                        {},
                    )
                    .get(
                        "bank",
                        0,
                    )
                    / 10.0
                ),

                "squad": squad,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — DEADLINE
# ============================================================

@app.route("/api/deadline")
def api_deadline():
    """
    Return the next FPL deadline.
    """

    try:

        bootstrap = (
            fpl_api.get_bootstrap_data()
        )

        deadline = (
            fpl_api.get_next_deadline(
                bootstrap
            )
        )

        return jsonify(
            {
                "ok": True,
                **deadline,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — FIXTURES
# ============================================================

@app.route("/api/fixtures")
def api_fixtures():

    lookahead = request.args.get(
        "lookahead",
        default=5,
        type=int,
    )

    try:

        bootstrap = (
            fpl_api.get_bootstrap_data()
        )

        fixtures = (
            fpl_api.get_fixtures()
        )

        current_gw = (
            fpl_api.get_current_gameweek(
                bootstrap
            )
        )

        grid = (
            data_processor.build_fdr_grid(
                bootstrap,
                fixtures,
                current_gw,
                lookahead=lookahead,
            )
        )

        return jsonify(
            {
                "ok": True,
                "current_gameweek": current_gw,
                **grid,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — CHART DATA
# ============================================================

@app.route("/api/chart-data")
def api_chart_data():

    n = request.args.get(
        "n",
        default=12,
        type=int,
    )

    position = request.args.get(
        "position",
        default="ALL",
        type=str,
    )

    metric = request.args.get(
        "metric",
        default="predicted_points",
        type=str,
    )

    try:

        df, gw = get_scored_dataframe()

        if position != "ALL":
            df = df[
                df["position"] == position
            ]

        sort_col = (
            "total_points"
            if metric == "total_points"
            else "predicted_points"
        )

        top = (
            df
            .sort_values(
                sort_col,
                ascending=False,
            )
            .head(n)
        )

        return jsonify(
            {
                "ok": True,

                "gameweek": gw,

                "labels": (
                    top["web_name"]
                    .tolist()
                ),

                "predicted_points": [
                    round(
                        float(value),
                        2,
                    )
                    for value
                    in top[
                        "predicted_points"
                    ]
                ],

                "total_points": [
                    int(value)
                    for value
                    in top[
                        "total_points"
                    ]
                ],
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — NEWS
# ============================================================

@app.route("/api/news")
def api_news():

    try:

        bootstrap = (
            fpl_api.get_bootstrap_data()
        )

        items = (
            data_processor.build_player_news(
                bootstrap
            )
        )

        return jsonify(
            {
                "ok": True,
                "news": items,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# API — HISTORY
# ============================================================

@app.route("/api/history")
def api_history():
    """
    Past-season performance for players.

    Results are paginated so the frontend does not try to fetch
    700+ player histories in one serverless request.
    """

    offset = request.args.get(
        "offset",
        default=0,
        type=int,
    )

    limit = request.args.get(
        "limit",
        default=50,
        type=int,
    )

    limit = min(
        limit,
        100,
    )

    try:

        bootstrap = (
            fpl_api.get_bootstrap_data()
        )

        team_lookup = (
            data_processor.build_team_lookup(
                bootstrap
            )
        )

        all_elements = sorted(
            bootstrap["elements"],
            key=lambda player:
                player["total_points"],
            reverse=True,
        )

        page = all_elements[
            offset:
            offset + limit
        ]

        def fetch_one(player):

            history = (
                fpl_api.get_player_history(
                    player["id"]
                )
            )

            past = (
                history
                .get(
                    "history_past",
                    [],
                )
                [-3:]
            )

            return {
                "name": player[
                    "web_name"
                ],

                "team": team_lookup.get(
                    player["team"],
                    "UNK",
                ),

                "position": (
                    data_processor.POSITION_MAP.get(
                        player["element_type"],
                        "UNK",
                    )
                ),

                "current_points": player[
                    "total_points"
                ],

                "seasons": [
                    {
                        "season": season[
                            "season_name"
                        ],

                        "points": season[
                            "total_points"
                        ],
                    }

                    for season in past
                ],
            }

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=15
        ) as pool:

            result = list(
                pool.map(
                    fetch_one,
                    page,
                )
            )

        return jsonify(
            {
                "ok": True,

                "players": result,

                "offset": offset,

                "limit": limit,

                "total": len(
                    all_elements
                ),

                "has_more": (
                    offset + limit
                    < len(all_elements)
                ),
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
            }
        ), 500


# ============================================================
# LIVE SCORES — GAMEWEEK DATE RANGE
# ============================================================

def _current_gw_date_range():
    """
    Return YYYYMMDD start/end dates covering the current FPL
    gameweek.

    IMPORTANT:
    This intentionally makes a direct short FPL request instead
    of using ThreadPoolExecutor. A ThreadPoolExecutor context
    manager waits for its worker when exiting, which can defeat
    the intended timeout inside a Vercel serverless function.
    """

    fixtures = fpl_api.get_fixtures(
        retries=1,
        timeout=4,
    )

    current_gw = (
        fpl_api.get_current_gameweek_from_fixtures(
            fixtures
        )
    )

    kickoffs = [
        fixture["kickoff_time"]
        for fixture in fixtures
        if (
            fixture.get("event")
            == current_gw
            and fixture.get(
                "kickoff_time"
            )
        )
    ]

    if not kickoffs:

        today = datetime.utcnow().strftime(
            "%Y%m%d"
        )

        return today, today

    dates = [
        datetime.fromisoformat(
            kickoff.replace(
                "Z",
                "+00:00",
            )
        )

        for kickoff in kickoffs
    ]

    return (
        min(dates).strftime(
            "%Y%m%d"
        ),

        max(dates).strftime(
            "%Y%m%d"
        ),
    )


# ============================================================
# DEBUG NETWORK
# ============================================================

@app.route("/api/debug-network")
def api_debug_network():
    """
    Diagnostic endpoint.

    Tests every ESPN fallback URL and the FPL fixtures endpoint.

    Open:

        /api/debug-network

    This makes it possible to see exactly which external source
    is reachable from the deployed server.
    """

    import requests as _requests

    targets = {}

    for index, url in enumerate(
        config.ESPN_SCOREBOARD_URLS
    ):

        targets[
            f"espn_scoreboard_{index + 1}"
        ] = url

    for index, url in enumerate(
        config.ESPN_STANDINGS_URLS
    ):

        targets[
            f"espn_standings_{index + 1}"
        ] = url

    targets[
        "fpl_fixtures"
    ] = config.FIXTURES_URL

    results = {}

    for name, url in targets.items():

        try:

            response = _requests.get(
                url,
                headers=external_data.HEADERS,
                timeout=6,
            )

            response.raise_for_status()

            try:

                data = response.json()

                if isinstance(
                    data,
                    dict,
                ):

                    preview = {
                        "keys": list(
                            data.keys()
                        )[:20]
                    }

                else:

                    preview = {
                        "type": type(
                            data
                        ).__name__
                    }

            except Exception:

                preview = {
                    "body_preview": (
                        response.text[:300]
                    )
                }

            results[name] = {
                "ok": True,

                "status_code": (
                    response.status_code
                ),

                "content_type": (
                    response.headers.get(
                        "content-type"
                    )
                ),

                "preview": preview,
            }

        except Exception as error:

            results[name] = {
                "ok": False,

                "error_type": (
                    type(error).__name__
                ),

                "error": str(error),
            }

    return jsonify(
        results
    )


# ============================================================
# LIVE SCORES
# ============================================================

@app.route("/api/live-scores")
def api_live_scores():
    """
    Return Premier League live/current-gameweek scores.

    Strategy:

    1. Try the FPL fixtures endpoint quickly to determine
       the current FPL gameweek date range.
    2. If FPL is slow/unavailable, immediately fall back to
       today's ESPN scoreboard.
    3. ESPN itself has multiple fallback hosts.
    4. Always return valid JSON to the frontend.
    """

    date_from = None
    date_to = None

    try:

        date_from, date_to = (
            _current_gw_date_range()
        )

    except Exception:

        # Do not let an unavailable FPL API
        # prevent ESPN live scores from loading.
        date_from = None
        date_to = None

    try:

        games = (
            external_data.get_live_scores(
                date_from,
                date_to,
            )
        )

        return jsonify(
            {
                "ok": True,
                "games": games,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
                "games": [],
            }
        ), 502


# ============================================================
# STANDINGS
# ============================================================

@app.route("/api/standings")
def api_standings():

    try:

        table = (
            external_data.get_league_table()
        )

        return jsonify(
            {
                "ok": True,
                "table": table,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
                "table": [],
            }
        ), 502


# ============================================================
# TRANSFER NEWS
# ============================================================

@app.route("/api/transfer-news")
def api_transfer_news():

    try:

        news = (
            external_data.get_transfer_news(
                limit=25
            )
        )

        return jsonify(
            {
                "ok": True,
                "news": news,
            }
        )

    except Exception as error:

        return jsonify(
            {
                "ok": False,
                "error": str(error),
                "news": [],
            }
        ), 502


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5000,
    )
