# FPL Squad Lab

A web app (+ CLI) that picks or improves your Fantasy Premier League squad
using real FPL data and a linear-programming optimizer, instead of guesswork.
Built as a SYBCA mini project.

## What it does

1. **Fetches live data** from the official FPL API — prices, form, points,
   ownership, injury status, and upcoming fixture difficulty.
2. **Scores every player** with a transparent weighted model (form, points-per-game,
   fixture ease, ICT index, minutes reliability) — see `predictor.py`.
3. **Optimizes your squad** with linear programming (PuLP) to find the
   mathematically best 15 players under the £100m budget and all FPL rules
   (2 GKP / 5 DEF / 5 MID / 3 FWD, max 3 per club).
4. **Picks your best XI + captain** from a valid formation, shown on a
   visual pitch.
5. **Suggests transfers** if you already have a team.

## Setup

```bash
pip install -r requirements.txt
```

## Running the web app (recommended for demo/presentation)

```bash
python app.py
```
Then open **http://127.0.0.1:5000** in your browser. You'll see:
- A dark, stadium-themed dashboard
- A "Generate Optimal Squad" button that builds your best XI on a live pitch view
- A top-rated players table, filterable by position
- A transfer-suggestions tool (enter your FPL Team ID)

## Running the CLI instead

### Build a brand-new optimal squad from scratch
```bash
python main.py
```

### Get transfer suggestions for your existing team
Find your team ID in the URL when you view your team on the FPL site
(`fantasy.premierleague.com/entry/XXXXXXX/...`):
```bash
python main.py --team-id 1234567 --free-transfers 1
```

### Just see the top-rated players (no optimization)
```bash
python main.py --top 20
```

### Other options
```bash
python main.py --refresh          # ignore cache, pull fresh data
python main.py --budget 99.5      # custom budget (e.g. if you've banked money)
```

## Project structure

```
fpl_optimizer/
├── config.py             # all tunable settings: budget, weights, formations
├── fpl_api.py            # API client with caching + retries
├── data_processor.py     # raw JSON -> clean player DataFrame + fixture scoring
├── predictor.py          # weighted scoring model -> predicted_points
├── optimizer.py          # PuLP linear programming: squad + starting XI + transfers
├── main.py               # CLI entry point
├── app.py                # Flask web app entry point (JSON API + dashboard)
├── templates/
│   └── index.html        # dashboard page
├── static/
│   ├── css/style.css     # dark stadium theme
│   └── js/main.js        # fetches API, renders pitch/table/transfers
├── tests/
│   └── test_offline.py   # synthetic-data test, runs without internet
└── data/                 # auto-created cache folder (gitignore this)
```

## Tuning the model

Open `config.py` and adjust `WEIGHTS`:

```python
WEIGHTS = {
    "form": 0.35,              # recent performance
    "points_per_game": 0.20,   # season-long consistency
    "fixture_score": 0.25,     # how easy their next 5 fixtures are
    "ict_index": 0.10,         # influence/creativity/threat
    "minutes_reliability": 0.10,  # do they actually play 60+ mins?
}
```
Increase `fixture_score` if you want to chase good fixture runs more
aggressively; increase `form` to chase in-form players more.

## Extending it further

Ideas if you want to keep building:
- **xG/xA data**: merge in Understat or FBref data for better attacking
  predictions than raw FPL stats (needs web scraping — no clean API).
- **Injury news scraping**: the FPL API's `chance_of_playing_next_round`
  is often outdated; PhysioRoom-style scraping gives fresher news.
- **Multi-gameweek planning**: current optimizer looks at one snapshot —
  you could extend `optimizer.py` to plan transfers 3-4 gameweeks ahead.
- **Web UI**: wrap `main.py`'s functions in a Streamlit or Flask app so you
  don't need the command line every week.

## Notes

- Data is cached in `data/` for 6 hours (see `CACHE_TTL_HOURS` in config.py)
  so you're not hammering the FPL API — delete the folder or use `--refresh`
  to force new data.
- The FPL API has no authentication needed for reading public data, but
  `get_entry_picks` needs your team ID to see *your* squad specifically.
