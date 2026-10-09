# Football Analysis Desk

Run these commands **in order, from inside the `pl_app` folder** (the one
this README is in — not the `app` subfolder). Every command uses
`python -m ...` instead of a bare command name — this sidesteps the
"'uvicorn' is not recognized" error some setups hit, since it always
runs through the same Python interpreter you installed packages into.

## 1. Install dependencies

```
python -m pip install -r requirements.txt
```

## 2. Train the model (creates the `models/` folder)

```
python -m scripts.train_model
```

(Named `training/`, not `scripts/` — Windows treats `scripts` and a venv's
own `Scripts` folder as the same name, which causes exactly this error if
your venv lives in the project root.)

This prints real accuracy/log-loss numbers from a held-out test split,
then saves the production model (trained on all available data) to
`models/model.pkl`. Current baseline: ~36-42% accuracy depending on
the exact split — this is a first working version, not a finished
product (draws are genuinely hard to predict; see chat for why).

### Optional: expand historical data

```
python -m scripts.import_historical
```

For the same provider used by the live updater, prefer:

```
python -m scripts.import_historical_api --start 2016 --end 2022
```

It uses your football-data.org token, retains the provider's matchday and team
names, and only imports seasons your API plan allows. Re-run the audit,
backtest, and training commands after importing.

## 3. Evaluate with rolling backtests

Before training with xG features, import the historical Understat match data:

```
python -m scripts.import_understat
```

This writes `data/premier_league_xg.csv`; it is joined automatically when the
application loads matches. Re-run training and backtesting after importing.

The same file also contains Understat tactical proxies: PPDA, PPDA allowed,
deep actions, and deep actions allowed. The model turns these into rolling
team profiles and matchup interactions. Possession, passing, crossing, and
set-piece fields are not available in the current source and are not inferred
from unrelated result data.

```
python -m scripts.evaluate_model
```

This evaluates each season using only matches from earlier seasons and compares
the model against a historical result-frequency baseline. It writes reproducible
metrics to `reports/`.

The current serving probabilities use a conservative blend: 75% Elo and 25%
calibrated xG/style features. This blend was selected from the expanding-season
backtest and remains compared against Elo and the standalone feature model in
`reports/backtest_metrics.csv`.

## 4. Run the server

```
python -m uvicorn app.main:app --reload
```

### Configure automatic data updates

Copy `.env.example` to `.env` and set `FOOTBALL_DATA_API_KEY` to your
football-data.org token. The updater reads it automatically and no longer
prompts for the key:

```
Copy-Item .env.example .env
notepad .env
python update_current.py
```

Keep `.env` private; it is excluded from version control.

## 5. Open it

Go to **http://127.0.0.1:8000** in your browser. The dashboard includes
Home, League Table, Team Stats, Predictions, and a Competition Centre for the
Premier League, Champions League, Bundesliga, La Liga, Serie A, and Ligue 1.

### Update other competitions

The Competition Centre reads Premier League tables and predictions from the
existing Premier League data/model. The five other competitions use isolated
match files and model folders. Import recent history and refresh current
fixtures and scorer summaries with:

```
python -m scripts.update_competitions --history-start-year 2023 --history-end-year 2024 --include-current
python -m training.train_competition_models --competition all
```

The updater writes non-PL match feeds and season scorer summaries under
`data/competitions/`; the trainer writes non-PL models under
`models/competitions/<code>/`. The existing Premier League match files and
model artifacts are not written by these commands. Refresh competition feeds
and the separate current-season Premier League scorer summary later with:

```
python -m scripts.update_competitions
```

To refresh only Premier League player totals without touching its match data or
model, run:

```
python -m scripts.update_competitions --pl-scorers-only
```

The provider supplies season-level goals, assists, penalties, and appearances
for scorer summaries, but not historical per-match player records. These
totals are displayed in the Competition Centre and are deliberately excluded
from model features to avoid future-information leakage. Player-informed
training needs a source with historical match-level player statistics and
lineup/availability snapshots.

### Deploy a self-updating service on Render

The repository includes a `render.yaml` Blueprint for a single-instance web
service with a persistent disk. The build installs dependencies and trains the
PL and competition models. At startup, `app.bootstrap` seeds only missing data
files onto the disk, then starts Uvicorn with one worker. This is intentional:
the scheduled refresh jobs run inside the web process and must not be duplicated
across multiple workers.

`APP_DATA_DIR` selects the persistent data directory. The Blueprint sets it to
`/var/data`; local development defaults to the repository's `data/` directory.
The bootstrap copies baseline CSV and metadata files only when they are missing,
never overwriting data already refreshed on the disk. Prediction history is
created there at runtime and is not seeded from the repository.

1. In Render, create a **Blueprint** from this GitHub repository.
2. Set `FOOTBALL_DATA_API_KEY` in the service environment. Never put the real
  value in this repository.
3. Deploy and wait for the initial build/training to complete.
4. Confirm the service health at `/health` and refresh state at
  `/api/system/status`.

When `ENABLE_DATA_REFRESH=true`, PL fixtures refresh every 2 days and the
other competitions refresh every 6 days by default. These intervals can be
changed with `PL_REFRESH_INTERVAL_SECONDS` and
`COMPETITION_REFRESH_INTERVAL_SECONDS`; do not set them below the provider's
rate limits. Local runs leave the scheduler disabled unless explicitly enabled.
The service needs a paid Render plan for its persistent disk. Keep it at one
instance; for horizontal scaling, move scheduled updates to a separate worker
and shared persistent storage such as PostgreSQL. Scheduled refreshes update
data and scorer summaries only; they do not retrain or replace model artifacts.
Model changes remain an explicit build/retraining step and should be evaluated
with the chronological backtest before promotion.

---

### Project structure

```
pl_app/
  app/
    main.py       FastAPI app + all routes
    data.py       Loads CSVs, computes league tables & team stats
    features.py   Shared "last 5 matches" form features (training + serving use the same code)
    predict.py    Loads the trained model, predicts a fixture
  training/
    train_model.py   Run once (or re-run anytime) to (re)train the model
  frontend/
    index.html, styles.css, app.js   Plain HTML/JS, no build step
  data/
    premier_league_historical.csv   2023/24 - 2025/26 (finished)
    premier_league_matches.csv      2026/27 (in progress + upcoming fixtures)
  models/          created by scripts/train_model.py (not in this zip)
```

### If something still doesn't start

Run `python --version` and `python -m pip --version` first — if either
command itself fails, there are likely multiple Python installs on your
machine and PATH is pointing somewhere unexpected. Paste the exact error
and we'll sort it out.
