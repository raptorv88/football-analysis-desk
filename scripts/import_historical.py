"""Import completed Premier League seasons from a public football-data cache.

By default this adds 2016/17 through 2022/23 to the project's historical CSV,
which already begins at 2023/24. It is safe to re-run: existing fixtures are
identified by season, date, home team, and away team and are not duplicated.

Run from the project root:
    python -m scripts.import_historical
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from app.data import validate_matches
from app.metadata import build_data_metadata, write_json

DATA_PATH = Path(__file__).parent.parent / "data" / "premier_league_historical.csv"
SEASONS = range(2016, 2023)
URL_TEMPLATE = "https://raw.githubusercontent.com/footballcsv/cache.footballdata/master/{season}/eng.1.csv"

# football-data.co.uk uses shorter names than the current fixture provider.
TEAM_NAMES = {
    "Arsenal": "Arsenal FC", "Aston Villa": "Aston Villa FC", "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford FC", "Brighton": "Brighton & Hove Albion FC", "Burnley": "Burnley FC",
    "Cardiff": "Cardiff City FC", "Chelsea": "Chelsea FC", "Crystal Palace": "Crystal Palace FC",
    "Everton": "Everton FC", "Fulham": "Fulham FC", "Huddersfield": "Huddersfield Town AFC",
    "Hull": "Hull City AFC", "Leeds": "Leeds United FC", "Leicester": "Leicester City FC",
    "Liverpool": "Liverpool FC", "Luton": "Luton Town FC", "Man City": "Manchester City FC",
    "Man United": "Manchester United FC", "Newcastle": "Newcastle United FC",
    "Middlesbrough": "Middlesbrough FC",
    "Norwich": "Norwich City FC", "Nott'm Forest": "Nottingham Forest FC",
    "Sheffield United": "Sheffield United FC", "Southampton": "Southampton FC", "Stoke": "Stoke City FC",
    "Sunderland": "Sunderland AFC", "Swansea": "Swansea City AFC", "Tottenham": "Tottenham Hotspur FC",
    "Watford": "Watford FC", "West Brom": "West Bromwich Albion FC", "West Ham": "West Ham United FC",
    "Wolves": "Wolverhampton Wanderers FC",
}


def import_season(start_year: int) -> pd.DataFrame:
    season = f"{start_year}/{str(start_year + 1)[-2:]}"
    source_season = f"{start_year}-{str(start_year + 1)[-2:]}"
    response = requests.get(URL_TEMPLATE.format(season=source_season), timeout=30)
    response.raise_for_status()
    raw = pd.read_csv(pd.io.common.StringIO(response.text))
    required = {"Date", "Team 1", "FT", "Team 2"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{season} source is missing columns: {sorted(missing)}")

    matches = raw.dropna(subset=["FT"]).copy()
    scores = matches["FT"].str.extract(r"^(?P<home>\d+)-(?P<away>\d+)$")
    matches = matches[scores.notna().all(axis=1)].copy()
    scores = scores.loc[matches.index]
    return pd.DataFrame(
        {
            "season": season,
            "date": pd.to_datetime(matches["Date"], utc=True, errors="raise"),
            "matchday": None,
            "home_team": matches["Team 1"].replace(TEAM_NAMES),
            "away_team": matches["Team 2"].replace(TEAM_NAMES),
            "home_goals": scores["home"],
            "away_goals": scores["away"],
        }
    )


def main() -> None:
    existing = pd.read_csv(DATA_PATH)
    imported = []
    for start_year in SEASONS:
        season = f"{start_year}/{str(start_year + 1)[-2:]}"
        if season in set(existing["season"]):
            print(f"Skipping {season}: already present")
            continue
        print(f"Downloading {season}...", flush=True)
        imported.append(import_season(start_year))

    if not imported:
        print("No seasons needed importing.")
        return

    combined = pd.concat([existing, *imported], ignore_index=True)
    validated = validate_matches(combined)
    validated = validated.sort_values("date")
    validated.to_csv(DATA_PATH, index=False)
    write_json(DATA_PATH.parent / "data_metadata.json", build_data_metadata(validated))
    print(f"Saved {len(validated)} historical matches to {DATA_PATH}")


if __name__ == "__main__":
    main()
