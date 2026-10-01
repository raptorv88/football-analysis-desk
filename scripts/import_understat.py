"""Download match-level Premier League xG from Understat.

Run from the project root with ``python -m scripts.import_understat``.
The output is kept separate from score data and is joined by season and teams
when the application loads matches.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

from app.data import DATA_DIR, load_matches

URL = "https://understat.com/getLeagueData/EPL/{season}"
OUTPUT = DATA_DIR / "premier_league_xg.csv"
STYLE_COLUMNS = [
    "home_ppda", "away_ppda", "home_ppda_allowed", "away_ppda_allowed",
    "home_deep", "away_deep", "home_deep_allowed", "away_deep_allowed",
]


def season_label(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def normalize_team(name: str) -> str:
    aliases = {
        "Arsenal": "Arsenal FC", "Aston Villa": "Aston Villa FC", "Bournemouth": "AFC Bournemouth",
        "Brighton": "Brighton & Hove Albion FC", "Brentford": "Brentford FC", "Burnley": "Burnley FC", "Cardiff": "Cardiff City FC",
        "Cardiff City": "Cardiff City FC", "Coventry": "Coventry City FC",
        "Chelsea": "Chelsea FC", "Crystal Palace": "Crystal Palace FC", "Everton": "Everton FC",
        "Fulham": "Fulham FC", "Huddersfield": "Huddersfield Town AFC", "Hull": "Hull City AFC",
        "Leeds": "Leeds United FC", "Leicester": "Leicester City FC", "Liverpool": "Liverpool FC",
        "Luton": "Luton Town FC", "Man City": "Manchester City FC", "Man United": "Manchester United FC",
        "Manchester City": "Manchester City FC", "Manchester United": "Manchester United FC", "Middlesbrough": "Middlesbrough FC",
        "Newcastle": "Newcastle United FC", "Newcastle United": "Newcastle United FC",
        "Norwich": "Norwich City FC", "Nott'm Forest": "Nottingham Forest FC",
        "Nottingham Forest": "Nottingham Forest FC", "Sheffield United": "Sheffield United FC", "Southampton": "Southampton FC",
        "Stoke": "Stoke City FC", "Stoke City": "Stoke City FC", "Sunderland": "Sunderland AFC", "Swansea": "Swansea City AFC",
        "Tottenham": "Tottenham Hotspur FC", "Watford": "Watford FC", "West Brom": "West Bromwich Albion FC",
        "West Bromwich Albion": "West Bromwich Albion FC", "West Ham": "West Ham United FC", "Wolves": "Wolverhampton Wanderers FC",
        "Wolverhampton": "Wolverhampton Wanderers FC",
        "Wolverhampton Wanderers": "Wolverhampton Wanderers FC",
        "Ipswich": "Ipswich Town FC",
    }
    return aliases.get(name, name)


def fetch_season(start_year: int) -> pd.DataFrame:
    response = requests.get(
        URL.format(season=start_year),
        headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    history = {}
    for team in payload.get("teams", {}).values():
        for record in team.get("history", []):
            ppda = record.get("ppda") or {}
            ppda_allowed = record.get("ppda_allowed") or {}
            key = (normalize_team(team["title"]), record.get("date"), record.get("h_a"))
            history[key] = {
                "ppda": float(ppda.get("att", 0)) / max(float(ppda.get("def", 0)), 1.0),
                "ppda_allowed": float(ppda_allowed.get("att", 0)) / max(float(ppda_allowed.get("def", 0)), 1.0),
                "deep": float(record.get("deep", 0)),
                "deep_allowed": float(record.get("deep_allowed", 0)),
            }
    rows = []
    for match in payload.get("dates", []):
        if not match.get("isResult"):
            continue
        match_date = match["datetime"]
        home_style = history.get((normalize_team(match["h"]["title"]), match_date, "h"), {})
        away_style = history.get((normalize_team(match["a"]["title"]), match_date, "a"), {})
        rows.append({
                "season": season_label(start_year),
                "date": match["datetime"],
                "home_team": normalize_team(match["h"]["title"]),
                "away_team": normalize_team(match["a"]["title"]),
                "home_xg": float(match["xG"]["h"]),
                "away_xg": float(match["xG"]["a"]),
                "home_ppda": home_style.get("ppda", 0.0),
                "away_ppda": away_style.get("ppda", 0.0),
                "home_ppda_allowed": home_style.get("ppda_allowed", 0.0),
                "away_ppda_allowed": away_style.get("ppda_allowed", 0.0),
                "home_deep": home_style.get("deep", 0.0),
                "away_deep": away_style.get("deep", 0.0),
                "home_deep_allowed": home_style.get("deep_allowed", 0.0),
                "away_deep_allowed": away_style.get("deep_allowed", 0.0),
            })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Understat Premier League match xG")
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=2026)
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must not be after --end")

    frames = []
    for year in range(args.start, args.end + 1):
        print(f"Downloading Understat {season_label(year)}...", flush=True)
        frame = fetch_season(year)
        print(f"  Found {len(frame)} matches", flush=True)
        frames.append(frame)
    xg = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["season", "home_team", "away_team"]
    )
    matches = load_matches().drop(columns=["home_xg", "away_xg"], errors="ignore")
    keys = ["season", "home_team", "away_team"]
    missing = matches.merge(xg[keys], on=keys, how="left", indicator=True)
    unmatched = missing[missing["_merge"] == "left_only"]
    if len(unmatched) > 0:
        print(f"Warning: {len(unmatched)} project fixtures have no Understat match")
    OUTPUT.parent.mkdir(exist_ok=True)
    xg.to_csv(OUTPUT, index=False)
    print(f"Saved {len(xg)} xG/style matches to {OUTPUT}")


if __name__ == "__main__":
    main()