"""
Uses linear programming (PuLP) to pick the mathematically-best 15-man squad
under FPL's real constraints, then the best starting XI + captain from it.
"""
import pandas as pd
import pulp
import concurrent.futures

import config


def pick_best_squad(df: pd.DataFrame, budget: float = None, locked_ids=None, excluded_ids=None) -> pd.DataFrame:
    """
    Select 15 players maximizing total predicted_points subject to:
      - total price <= budget
      - exact position counts (2 GKP, 5 DEF, 5 MID, 3 FWD)
      - max 3 players per club
      - locked_ids: players that MUST be included (e.g. keeping a player you own)
      - excluded_ids: players that must NOT be included (e.g. injured, banned)
    """
    budget = budget if budget is not None else config.BUDGET
    locked_ids = set(locked_ids or [])
    excluded_ids = set(excluded_ids or [])

    pool = df[~df["id"].isin(excluded_ids)].reset_index(drop=True)

    prob = pulp.LpProblem("FPL_Squad_Selection", pulp.LpMaximize)
    player_vars = {row.id: pulp.LpVariable(f"player_{row.id}", cat="Binary") for row in pool.itertuples()}

    # Objective: maximize total predicted points
    prob += pulp.lpSum(player_vars[row.id] * row.predicted_points for row in pool.itertuples())

    # Squad size
    prob += pulp.lpSum(player_vars.values()) == config.SQUAD_SIZE

    # Budget
    prob += pulp.lpSum(player_vars[row.id] * row.price for row in pool.itertuples()) <= budget

    # Position counts
    for pos, count in config.POSITION_LIMITS.items():
        prob += pulp.lpSum(player_vars[row.id] for row in pool.itertuples() if row.position == pos) == count

    # Max per club
    for team in pool["team"].unique():
        prob += pulp.lpSum(player_vars[row.id] for row in pool.itertuples() if row.team == team) <= config.MAX_PER_CLUB

    # Locked players (must include)
    for pid in locked_ids:
        if pid in player_vars:
            prob += player_vars[pid] == 1

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Optimizer could not find a valid squad: {pulp.LpStatus[prob.status]}")

    selected_ids = [pid for pid, var in player_vars.items() if var.value() == 1]
    return pool[pool["id"].isin(selected_ids)].reset_index(drop=True)


def pick_best_starting_xi(squad: pd.DataFrame):
    """
    From a 15-man squad, find the best valid starting XI (1 GKP + a valid
    DEF/MID/FWD formation) and pick the captain (highest predicted_points).
    Returns (starting_xi_df, bench_df, captain_row, vice_captain_row).
    """
    best_xi = None
    best_score = -1
    best_formation = None

    gkps = squad[squad["position"] == "GKP"].sort_values("predicted_points", ascending=False)
    defs = squad[squad["position"] == "DEF"].sort_values("predicted_points", ascending=False)
    mids = squad[squad["position"] == "MID"].sort_values("predicted_points", ascending=False)
    fwds = squad[squad["position"] == "FWD"].sort_values("predicted_points", ascending=False)

    best_gkp = gkps.iloc[[0]]

    for d_count, m_count, f_count in config.VALID_FORMATIONS:
        if len(defs) < d_count or len(mids) < m_count or len(fwds) < f_count:
            continue
        xi = pd.concat([
            best_gkp,
            defs.iloc[:d_count],
            mids.iloc[:m_count],
            fwds.iloc[:f_count],
        ])
        score = xi["predicted_points"].sum()
        if score > best_score:
            best_score = score
            best_xi = xi
            best_formation = f"{d_count}-{m_count}-{f_count}"

    bench = squad[~squad["id"].isin(best_xi["id"])].reset_index(drop=True)
    starting_xi = best_xi.sort_values("predicted_points", ascending=False).reset_index(drop=True)

    captain = starting_xi.iloc[0]
    vice_captain = starting_xi.iloc[1]

    return starting_xi, bench, captain, vice_captain, best_formation


def _historical_avg_points(player_id: int, history_fetcher) -> float:
    """Average total points across a player's last 2 completed seasons, or
    None if unavailable (e.g. brand new to the league)."""
    try:
        hist = history_fetcher(player_id)
        past = hist.get("history_past", [])[-2:]
        if not past:
            return None
        return sum(s["total_points"] for s in past) / len(past)
    except Exception:
        return None


def suggest_transfers(
    current_squad_ids: list,
    df: pd.DataFrame,
    free_transfers: int = 1,
    budget_bank: float = 0.0,
    history_fetcher=None,
    shortlist_size: int = 10,
    historical_weight: float = 0.2,
    target_ids: list = None,
):
    """
    Transfer suggestion engine. For each of your current players (worst first,
    or exactly the players in `target_ids` if given — e.g. only your injured
    ones, for the Injury Tracker), every affordable, position-matching,
    club-limit-respecting replacement in the pool is considered, then ranked
    by a blend of current predicted form AND real past-season performance
    when `history_fetcher` is supplied (pass fpl_api.get_player_history in
    production; leave None for pure current-form ranking, e.g. offline tests).

    blended_score = predicted_points*(1-w) + (avg_points_last_2_seasons/38)*w

    Squad-legality constraints enforced on every suggestion:
      - position-to-position only (a GKP can only be replaced by a GKP, etc.)
      - max 3 players per club in the resulting squad, tracked cumulatively.

    When `target_ids` is given, every targeted player gets a suggestion
    attempt (not capped by `free_transfers`) since the point is "what should
    replace each of these specific injured players", not "pick your best N
    swaps overall".

    Returns a list of dicts: {out, in, gain, price_delta}.
    """
    current = df[df["id"].isin(current_squad_ids)].copy()
    if target_ids is not None:
        current = current[current["id"].isin(target_ids)]
        free_transfers = len(current)  # don't cap — cover every targeted player

    suggestions = []
    squad_ids = set(current_squad_ids)
    team_counts = df[df["id"].isin(current_squad_ids)]["team"].value_counts().to_dict()

    def blended_score(player_id, predicted_points):
        if history_fetcher is None:
            return predicted_points
        hist_avg = _historical_avg_points(player_id, history_fetcher)
        if hist_avg is None:
            return predicted_points
        return predicted_points * (1 - historical_weight) + (hist_avg / 38.0) * historical_weight

    for _, out_player in current.sort_values("predicted_points").iterrows():
        if out_player["id"] not in squad_ids:
            continue  # already transferred out by an earlier suggestion this call

        pos = out_player["position"]
        out_team = out_player["team"]
        max_price = out_player["price"] + budget_bank

        team_counts_after_out = team_counts.copy()
        team_counts_after_out[out_team] = team_counts_after_out.get(out_team, 0) - 1

        # Every affordable, position-matching player is a candidate — past
        # performance (below) can justify a swap even if current predicted
        # points are close or momentarily lower.
        candidates = df[
            (df["position"] == pos)                          # <-- position-to-position, hard filter
            & (~df["id"].isin(squad_ids))
            & (df["price"] <= max_price)
        ].copy()

        candidates["team_count_after_in"] = candidates["team"].map(
            lambda t: team_counts_after_out.get(t, 0) + 1
        )
        candidates = candidates[candidates["team_count_after_in"] <= config.MAX_PER_CLUB]
        candidates = candidates.sort_values("predicted_points", ascending=False).head(shortlist_size)

        if candidates.empty:
            continue

        if history_fetcher is not None:
            ids_to_warm = list(candidates["id"]) + [out_player["id"]]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda pid: _historical_avg_points(pid, history_fetcher), ids_to_warm))

        out_score = blended_score(out_player["id"], out_player["predicted_points"])
        candidates["blended_score"] = candidates.apply(
            lambda r: blended_score(r["id"], r["predicted_points"]), axis=1
        )
        candidates = candidates.sort_values("blended_score", ascending=False)
        best_in = candidates.iloc[0]

        if best_in["blended_score"] <= out_score:
            continue  # not a real upgrade once past performance is weighed in

        assert best_in["position"] == pos, (
            f"Position mismatch: tried to replace {out_player['web_name']} "
            f"({pos}) with {best_in['web_name']} ({best_in['position']})"
        )

        suggestions.append({
            "out": out_player["web_name"],
            "out_id": int(out_player["id"]),
            "out_points": round(out_player["predicted_points"], 2),
            "in": best_in["web_name"],
            "in_points": round(best_in["predicted_points"], 2),
            "gain": round(best_in["predicted_points"] - out_player["predicted_points"], 2),
            "price_delta": round(best_in["price"] - out_player["price"], 1),
        })

        squad_ids.discard(out_player["id"])
        squad_ids.add(best_in["id"])
        team_counts[out_team] = team_counts.get(out_team, 0) - 1
        team_counts[best_in["team"]] = team_counts.get(best_in["team"], 0) + 1

        if len(suggestions) >= free_transfers:
            break

    return sorted(suggestions, key=lambda x: x["gain"], reverse=True)
