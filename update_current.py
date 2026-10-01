import requests
import pandas as pd
from pathlib import Path
import os
from dotenv import load_dotenv

from app.data import load_matches
from app.metadata import build_data_metadata, write_json
from app.prediction_history import snapshot_predictions

API_URL = "https://api.football-data.org/v4/competitions/PL/matches"

load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
if not API_KEY:
    raise SystemExit(
        "Missing FOOTBALL_DATA_API_KEY. Copy .env.example to .env and add your football-data.org token."
    )

headers = {
    "X-Auth-Token": API_KEY
}

print("Downloading latest Premier League data...", flush=True)
previous_matches = load_matches()

try:
    response = requests.get(API_URL, headers=headers, timeout=(5, 30))
except requests.exceptions.Timeout as exc:
    raise SystemExit(
        "The football-data.org request timed out after 30 seconds. Check your internet connection and try again."
    ) from exc
except requests.exceptions.RequestException as exc:
    raise SystemExit(f"Could not reach football-data.org: {exc}") from exc

if response.status_code != 200:
    raise SystemExit(
        f"football-data.org returned HTTP {response.status_code}. "
        "Check that FOOTBALL_DATA_API_KEY is valid and available on your plan."
    )

data = response.json()

rows = []

for match in data["matches"]:
    score = match.get("score", {})
    current_score = score.get("current") or score.get("fullTime") or {}
    rows.append({
        "date": match["utcDate"],
        "matchday": match.get("matchday"),
        "home_team": match["homeTeam"]["name"],
        "away_team": match["awayTeam"]["name"],
        "home_goals": current_score.get("home"),
        "away_goals": current_score.get("away"),
        "status": str(match["status"]).upper()
    })

df = pd.DataFrame(rows)

output_path = Path("data") / "premier_league_matches.csv"
df.to_csv(output_path, index=False)
write_json(Path("data") / "data_metadata.json", build_data_metadata(load_matches()))

print(f"Updated file: {output_path}")
print(f"Total matches downloaded: {len(df)}")

# Archive after the data file is safely refreshed. If prediction archiving is
# interrupted, live scores are still available and the next run can retry it.
print("Archiving near-term pre-match predictions...", flush=True)
saved_predictions = snapshot_predictions(df.to_dict(orient="records"), previous_matches)
print(f"Archived {saved_predictions} new pre-match predictions")
print("\nStatus summary:")
print(df["status"].value_counts())

from datetime import datetime, timezone

now = datetime.now(timezone.utc)
today_str = now.strftime("%Y-%m-%d")

cols = ["date", "matchday", "home_team", "away_team", "home_goals", "away_goals", "status"]

live = df[df["status"].isin(["IN_PLAY", "PAUSED", "LIVE", "INPLAY"])]
if not live.empty:
    print("\n\U0001f7e2 Live now:")
    print(live[cols].to_string(index=False))
else:
    print("\nNo matches currently live.")

today_finished = df[
    (df["status"] == "FINISHED") &
    (df["date"].astype(str).str.startswith(today_str))
]
if not today_finished.empty:
    print(f"\n\U0001f3c6 Finished today ({today_str}):")
    print(today_finished[cols].to_string(index=False))

upcoming = df[df["status"] == "TIMED"].copy()
upcoming = upcoming.sort_values("date").head(10)
if not upcoming.empty:
    print("\n\U0001f4c5 Next fixtures (up to 10):")
    print(upcoming[cols].to_string(index=False))
