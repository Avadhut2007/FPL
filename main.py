"""
FPL Optimizer — CLI entry point.

Usage:
    python main.py                          # build a fresh optimal 15-man squad
    python main.py --team-id 123456         # suggest transfers for your existing team
    python main.py --refresh                # force re-fetch from the FPL API (ignore cache)
    python main.py --budget 99.5            # use a custom budget
"""
import argparse

import pandas as pd

import config
import data_processor
import fpl_api
import optimizer
import predictor


def build_dataframe(force_refresh: bool = False) -> pd.DataFrame:
    print("Fetching FPL data...")
    bootstrap = fpl_api.get_bootstrap_data(force_refresh=force_refresh)
    fixtures = fpl_api.get_fixtures(force_refresh=force_refresh)
    current_gw = fpl_api.get_current_gameweek(bootstrap)
    print(f"Current gameweek: {current_gw}")

    df = data_processor.build_player_dataframe(bootstrap, fixtures, current_gw)
    df = data_processor.filter_available_players(df)
    df = predictor.compute_predicted_points(df)
    return df


def print_squad(starting_xi, bench, captain, vice_captain, formation, total_cost):
    print(f"\n{'='*50}")
    print(f"BEST XI — Formation {formation}  |  Squad cost: £{total_cost:.1f}m")
    print(f"{'='*50}")
    for pos in ["GKP", "DEF", "MID", "FWD"]:
        rows = starting_xi[starting_xi["position"] == pos]
        if rows.empty:
            continue
        print(f"\n{pos}:")
        for _, r in rows.iterrows():
            tag = " (C)" if r["id"] == captain["id"] else (" (VC)" if r["id"] == vice_captain["id"] else "")
            print(f"  {r['web_name']:<20} {r['team']:<4} £{r['price']:<5.1f} "
                  f"pred={r['predicted_points']:.2f}{tag}")

    print(f"\nBENCH:")
    for _, r in bench.iterrows():
        print(f"  {r['web_name']:<20} {r['team']:<4} £{r['price']:<5.1f} pred={r['predicted_points']:.2f}")

    print(f"\nCaptain: {captain['web_name']} | Vice-captain: {vice_captain['web_name']}")
    print(f"Projected starting-XI points (captain doubled): "
          f"{starting_xi['predicted_points'].sum() + captain['predicted_points']:.1f}")


def main():
    parser = argparse.ArgumentParser(description="FPL squad optimizer")
    parser.add_argument("--team-id", type=int, help="Your FPL team ID, to get transfer suggestions instead of a fresh squad")
    parser.add_argument("--refresh", action="store_true", help="Force refresh data from the FPL API (ignore cache)")
    parser.add_argument("--budget", type=float, default=config.BUDGET, help="Total budget in £m")
    parser.add_argument("--free-transfers", type=int, default=1, help="Number of free transfers available (transfer mode only)")
    parser.add_argument("--top", type=int, default=0, help="Just print top N players by predicted points and exit (no optimization)")
    args = parser.parse_args()

    df = build_dataframe(force_refresh=args.refresh)

    if args.top:
        print(f"\nTop {args.top} players by predicted points:\n")
        cols = ["web_name", "team", "position", "price", "predicted_points", "value"]
        print(df[cols].head(args.top).to_string(index=False))
        return

    if args.team_id:
        bootstrap = fpl_api.get_bootstrap_data()
        current_gw = fpl_api.get_current_gameweek(bootstrap)
        picks_data = fpl_api.get_entry_picks(args.team_id, max(current_gw - 1, 1))
        current_ids = [p["element"] for p in picks_data["picks"]]

        print(f"\nAnalyzing your current squad ({len(current_ids)} players)...")
        suggestions = optimizer.suggest_transfers(current_ids, df, free_transfers=args.free_transfers)

        if not suggestions:
            print("No beneficial transfers found within your free transfer limit — your squad looks solid!")
        else:
            print(f"\nSuggested transfers:")
            for s in suggestions:
                print(f"  OUT: {s['out']} ({s['out_points']}) -> IN: {s['in']} ({s['in_points']}) "
                      f"| gain: +{s['gain']} pts | price change: {s['price_delta']:+.1f}m")
        return

    # Default: build a brand new optimal squad from scratch
    squad = optimizer.pick_best_squad(df, budget=args.budget)
    starting_xi, bench, captain, vice_captain, formation = optimizer.pick_best_starting_xi(squad)
    print_squad(starting_xi, bench, captain, vice_captain, formation, squad["price"].sum())


if __name__ == "__main__":
    main()
