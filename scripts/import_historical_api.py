"""Import finished Premier League seasons from football-data.org.

Examples, from the project root:
    python -m scripts.import_historical_api
    python -m scripts.import_historical_api --start 2016 --end 2022

The API token is prompted securely and is never written to disk. Seasons that
your subscription cannot access are reported and skipped; downloaded data is
validated before the historical CSV is replaced.
"""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

import pandas as pd
import requests

from app.data import validate_matches
from app.metadata import build_data_metadata, write_json

API_URL = "https://api.football-data.org/v4/competitions/PL/matches"
DATA_PATH = Path(__file__).parent.parent / "data" / "premier_league_historical.csv"


def season_label(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def matches_to_frame(matches: list[dict], start_year: int) -> pd.DataFrame:
    rows = []
    for match in matches:
        if match.get("status") != "FINISHED":
            continue
        score = match.get("score", {}).get("fullTime", {})
        if score.get("home") is None or score.get("away") is None:
            continue
        rows.append(
            {
                "season": season_label(start_year),
                "date": match["utcDate"],
                "matchday": match.get("matchday"),
                "home_team": match["homeTeam"]["name"],
                "away_team": match["awayTeam"]["name"],
                "home_goals": score["home"],
                "away_goals": score["away"],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Premier League history from football-data.org")
    parser.add_argument("--start", type=int, default=2016, help="First season's start year (default: 2016)")
    parser.add_argument("--end", type=int, default=2022, help="Last season's start year (default: 2022)")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must not be after --end")

    api_key = getpass("Enter your football-data.org API key: ")
    existing = pd.read_csv(DATA_PATH)
    existing_seasons = set(existing["season"])
    downloaded = []

    for year in range(args.start, args.end + 1):
        season = season_label(year)
        if season in existing_seasons:
            print(f"Skipping {season}: already present")
            continue
        print(f"Downloading {season}...", flush=True)
        response = requests.get(
            API_URL,
            headers={"X-Auth-Token": api_key},
            params={"season": year, "status": "FINISHED"},
            timeout=30,
        )
        if response.status_code != 200:
            print(f"Skipping {season}: API returned {response.status_code}")
            continue
        frame = matches_to_frame(response.json().get("matches", []), year)
        if frame.empty:
            print(f"Skipping {season}: no finished matches returned")
            continue
        downloaded.append(frame)
        print(f"  Found {len(frame)} finished matches")

    if not downloaded:
        print("No new seasons were imported. Check your API plan and selected year range.")
        return

    combined = pd.concat([existing, *downloaded], ignore_index=True)
    validated = validate_matches(combined).sort_values("date")
    validated.to_csv(DATA_PATH, index=False)
    write_json(DATA_PATH.parent / "data_metadata.json", build_data_metadata(validated))
    print(f"Saved {len(validated)} historical matches to {DATA_PATH}")


if __name__ == "__main__":
    main()
