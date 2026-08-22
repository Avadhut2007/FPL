"""
Offline sanity test — builds a synthetic but realistically-shaped dataset
(same schema as the real FPL API) so the pipeline can be verified without
needing live internet access. Run: python tests/test_offline.py
"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_processor
import optimizer
import predictor

random.seed(42)

TEAMS = [{"id": i, "short_name": name} for i, name in enumerate(
    ["ARS", "MCI", "LIV", "CHE", "MUN", "TOT", "NEW", "AVL", "BHA", "WHU",
     "WOL", "EVE", "FUL", "BRE", "CRY", "NFO", "BOU", "LUT", "BUR", "SHU"], start=1)]

POSITIONS = {1: ("GKP", 3), 2: ("DEF", 8), 3: ("MID", 8), 4: ("FWD", 4)}  # pos_id: (name, count per team)


def fake_bootstrap():
    elements = []
    pid = 1
    for team in TEAMS:
        for pos_id, (pos_name, count) in POSITIONS.items():
            for _ in range(count):
                price = round(random.uniform(4.0, 13.0), 1)
                form = round(random.uniform(0, 9), 1)
                elements.append({
                    "id": pid,
                    "first_name": f"Player{pid}",
                    "second_name": "Test",
                    "web_name": f"P{pid}",
                    "team": team["id"],
                    "element_type": pos_id,
                    "now_cost": int(price * 10),
                    "selected_by_percent": str(round(random.uniform(0, 40), 1)),
                    "form": str(form),
                    "points_per_game": str(round(random.uniform(0, 8), 1)),
                    "total_points": random.randint(0, 200),
                    "ict_index": str(round(random.uniform(0, 250), 1)),
                    "minutes": random.randint(0, 2500),
                    "status": random.choice(["a", "a", "a", "a", "i", "d"]),
                    "chance_of_playing_next_round": random.choice([None, 100, 75, 50, 25]),
                })
                pid += 1
    events = [{"id": i, "is_next": i == 10, "finished": i < 10} for i in range(1, 39)]
    return {"elements": elements, "teams": TEAMS, "events": events}


def fake_fixtures(current_gw=10):
    fixtures = []
    fid = 1
    team_ids = [t["id"] for t in TEAMS]
    for gw in range(current_gw, current_gw + 6):
        shuffled = team_ids[:]
        random.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            fixtures.append({
                "id": fid,
                "event": gw,
                "finished": False,
                "team_h": shuffled[i],
                "team_a": shuffled[i + 1],
                "team_h_difficulty": random.randint(1, 5),
                "team_a_difficulty": random.randint(1, 5),
            })
            fid += 1
    return fixtures


def run():
    print("Building synthetic dataset...")
    bootstrap = fake_bootstrap()
    fixtures = fake_fixtures(current_gw=10)

    df = data_processor.build_player_dataframe(bootstrap, fixtures, current_gw=10)
    print(f"Raw players: {len(df)}")

    df = data_processor.filter_available_players(df)
    print(f"After availability filter: {len(df)}")

    df = predictor.compute_predicted_points(df)
    assert "predicted_points" in df.columns
    assert df["predicted_points"].between(0, 10).all(), "predicted_points out of expected range"
    print("Predicted points computed OK. Top 5:")
    print(df[["web_name", "team", "position", "price", "predicted_points"]].head(5).to_string(index=False))

    print("\nRunning optimizer...")
    squad = optimizer.pick_best_squad(df)
    assert len(squad) == 15, f"Expected 15 players, got {len(squad)}"
    assert squad["price"].sum() <= 100.0 + 1e-6, "Budget exceeded!"
    for pos, count in {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}.items():
        actual = (squad["position"] == pos).sum()
        assert actual == count, f"Position {pos}: expected {count}, got {actual}"
    for team, count in squad["team"].value_counts().items():
        assert count <= 3, f"Team {team} has {count} players (>3 limit)"
    print(f"Squad valid: 15 players, £{squad['price'].sum():.1f}m, max-per-club OK")

    starting_xi, bench, captain, vice_captain, formation = optimizer.pick_best_starting_xi(squad)
    assert len(starting_xi) == 11
    assert len(bench) == 4
    print(f"Starting XI valid: formation {formation}, captain={captain['web_name']}")

    # Test transfer suggestions
    current_ids = squad["id"].tolist()
    suggestions = optimizer.suggest_transfers(current_ids, df, free_transfers=2, budget_bank=0.5)
    print(f"\nTransfer suggestions generated: {len(suggestions)}")
    for s in suggestions:
        print(f"  OUT {s['out']} -> IN {s['in']} | gain {s['gain']}")

    print("\n✅ ALL TESTS PASSED")


if __name__ == "__main__":
    run()
