"""
Loads match data once at startup and provides functions to compute
league tables and team stats on demand.
"""

import pandas as pd
from pathlib import Path
import os

from app.features import fixture_features

PROJECT_DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(PROJECT_DATA_DIR)))
XG_PATH = DATA_DIR / "premier_league_xg.csv"

REQUIRED_MATCH_COLUMNS = {
    "season", "date", "home_team", "away_team", "home_goals", "away_goals"
}


def _result(row):
    if row["home_goals"] > row["away_goals"]:
        return "HOME_WIN"
    elif row["home_goals"] < row["away_goals"]:
        return "AWAY_WIN"
    return "DRAW"


def validate_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize completed-match data before it is used anywhere."""
    missing = REQUIRED_MATCH_COLUMNS - set(matches.columns)
    if missing:
        raise ValueError(f"Match data is missing required columns: {sorted(missing)}")

    validated = matches.copy()
    if validated[["season", "date", "home_team", "away_team"]].isna().any(axis=1).any():
        raise ValueError("Match data contains missing season, date, or team values")

    try:
        # Historical imports serialize UTC as ``+00:00`` while the live API
        # emits ``Z``. Accept both valid ISO-8601 representations.
        validated["date"] = pd.to_datetime(
            validated["date"], utc=True, errors="raise", format="mixed"
        )
        for column in ("home_goals", "away_goals"):
            goals = pd.to_numeric(validated[column], errors="raise")
            if goals.isna().any() or (goals < 0).any() or (goals % 1 != 0).any():
                raise ValueError(f"{column} must contain non-negative whole numbers")
            validated[column] = goals.astype(int)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid match date or score: {exc}") from exc

    if (validated["home_team"] == validated["away_team"]).any():
        raise ValueError("A match cannot have the same home and away team")

    fixture_keys = ["season", "date", "home_team", "away_team"]
    if validated.duplicated(subset=fixture_keys).any():
        raise ValueError("Match data contains duplicate fixtures")

    return validated


def load_matches() -> pd.DataFrame:
    """Combine completed historical seasons with finished current-season matches."""

    historical = pd.read_csv(
    DATA_DIR / "premier_league_historical.csv"
)

    if "matchday" not in historical.columns:
        historical["matchday"] = None

    current = pd.read_csv(
        DATA_DIR / "premier_league_matches.csv"
    )

    current = current[current["status"] == "FINISHED"].copy()

    current["home_goals"] = current["home_goals"].astype(int)
    current["away_goals"] = current["away_goals"].astype(int)

    current["season"] = "2026/27"

    # The updater may not provide matchday.
    if "matchday" not in current.columns:
        current["matchday"] = None

    current = current[
        [
            "season",
            "date",
            "matchday",
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
        ]
    ]

    df = validate_matches(pd.concat([historical, current], ignore_index=True))
    if XG_PATH.exists():
        xg = pd.read_csv(XG_PATH)
        xg["season"] = xg["season"].astype(str)
        style_columns = [
            "home_ppda", "away_ppda", "home_ppda_allowed", "away_ppda_allowed",
            "home_deep", "away_deep", "home_deep_allowed", "away_deep_allowed",
        ]
        for column in style_columns:
            if column not in xg:
                xg[column] = 0.0
        xg = xg[["season", "home_team", "away_team", "home_xg", "away_xg", *style_columns]]
        df = df.merge(
            xg,
            on=["season", "home_team", "away_team"],
            how="left",
            validate="many_to_one",
        )
    else:
        df["home_xg"] = 0.0
        df["away_xg"] = 0.0
    numeric_columns = [
        "home_xg", "away_xg", "home_ppda", "away_ppda", "home_ppda_allowed", "away_ppda_allowed",
        "home_deep", "away_deep", "home_deep_allowed", "away_deep_allowed",
    ]
    df[numeric_columns] = df[numeric_columns].fillna(0.0)
    df["result"] = df.apply(_result, axis=1)

    return df.sort_values("date").reset_index(drop=True)


# Loaded once when the app starts
MATCHES = load_matches()


def list_seasons() -> list[str]:
    return sorted(MATCHES["season"].unique())


def league_table(season: str) -> list[dict]:
    df = dashboard_matches()
    df = df[df["season"] == season]
    if df.empty:
        return []

    home = df.groupby("home_team").agg(
        matches=("home_team", "count"),
        wins=("result", lambda x: (x == "HOME_WIN").sum()),
        draws=("result", lambda x: (x == "DRAW").sum()),
        losses=("result", lambda x: (x == "AWAY_WIN").sum()),
        goals_for=("home_goals", "sum"),
        goals_against=("away_goals", "sum"),
    )
    away = df.groupby("away_team").agg(
        matches=("away_team", "count"),
        wins=("result", lambda x: (x == "AWAY_WIN").sum()),
        draws=("result", lambda x: (x == "DRAW").sum()),
        losses=("result", lambda x: (x == "HOME_WIN").sum()),
        goals_for=("away_goals", "sum"),
        goals_against=("home_goals", "sum"),
    )

    table = home.add(away, fill_value=0)
    table.index.name = "team"
    table["goal_difference"] = table["goals_for"] - table["goals_against"]
    table["points"] = table["wins"] * 3 + table["draws"]
    table = table.sort_values(
        ["points", "goal_difference"], ascending=False
    ).reset_index()
    for col in ["matches", "wins", "draws", "losses", "goals_for", "goals_against", "goal_difference", "points"]:
        table[col] = table[col].astype(int)

    table.insert(0, "position", range(1, len(table) + 1))
    return table.to_dict(orient="records")


def dashboard_matches() -> pd.DataFrame:
    """Load finished and live current-season matches for provisional tables.

    This is intentionally separate from ``MATCHES`` so live scores can update
    dashboard standings without changing the prediction engine's training data.
    """
    historical = pd.read_csv(DATA_DIR / "premier_league_historical.csv")
    current = pd.read_csv(DATA_DIR / "premier_league_matches.csv")
    current["status"] = current["status"].astype(str).str.upper()
    current = current[current["status"].isin(["FINISHED", "IN_PLAY", "PAUSED", "LIVE", "INPLAY"])].copy()
    current["season"] = "2026/27"
    for column in ("home_goals", "away_goals"):
        current[column] = pd.to_numeric(current[column], errors="coerce").fillna(0).astype(int)
    columns = ["season", "date", "matchday", "home_team", "away_team", "home_goals", "away_goals"]
    combined = pd.concat([historical[columns], current[columns]], ignore_index=True)
    combined = validate_matches(combined)
    combined["result"] = combined.apply(_result, axis=1)
    return combined


def team_stats(team: str, season: str | None = None) -> dict | None:
    df = MATCHES if season is None else MATCHES[MATCHES["season"] == season]
    df = df[(df["home_team"] == team) | (df["away_team"] == team)]
    if df.empty:
        return None

    matches, wins, draws, losses = 0, 0, 0, 0
    goals_for, goals_against = 0, 0

    for _, row in df.iterrows():
        is_home = row["home_team"] == team
        gf = row["home_goals"] if is_home else row["away_goals"]
        ga = row["away_goals"] if is_home else row["home_goals"]
        goals_for += gf
        goals_against += ga
        matches += 1
        if gf > ga:
            wins += 1
        elif gf < ga:
            losses += 1
        else:
            draws += 1

    return {
        "team": team,
        "season": season or "all",
        "matches": matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": int(goals_for),
        "goals_against": int(goals_against),
        "goal_difference": int(goals_for - goals_against),
        "points": wins * 3 + draws,
    }


def team_profile(team: str, season: str | None = None) -> dict | None:
    """Return current rolling model inputs for a team, without a match result."""
    matches = MATCHES if season is None else MATCHES[MATCHES["season"] == season]
    if team not in set(matches["home_team"]) | set(matches["away_team"]):
        return None

    features = fixture_features(matches, team, "__profile_opponent__", season=season)
    return {
        "team": team,
        "season": season or "all",
        "elo": features["home_elo"],
        "xg_last5": features["home_xg_last5"],
        "xga_last5": features["home_xga_last5"],
        "xg_last10": features["home_xg_last10"],
        "xga_last10": features["home_xga_last10"],
        "finishing_last5": features["home_finishing_last5"],
        "defensive_overperformance_last5": features["home_defensive_overperformance_last5"],
        "ppda_last5": features["home_ppda_last5"],
        "ppda_allowed_last5": features["home_ppda_allowed_last5"],
        "deep_last5": features["home_deep_last5"],
        "deep_allowed_last5": features["home_deep_allowed_last5"],
        "rest_days": features["home_rest_days"],
        "matches_last14_days": features["home_matches_last14_days"],
        "matches_available": features["home_matches_available"],
    }


def list_teams() -> list[str]:
    return sorted(set(MATCHES["home_team"]) | set(MATCHES["away_team"]))


def upcoming_fixtures(limit: int = 10) -> list[dict]:
    """Scheduled (not yet played) fixtures from the current-season file."""
    current = pd.read_csv(DATA_DIR / "premier_league_matches.csv")
    upcoming = current[~current["status"].isin(["FINISHED", "IN_PLAY", "PAUSED", "LIVE"])].copy()
    if "matchday" not in upcoming.columns:
        upcoming["matchday"] = None
    upcoming["date"] = pd.to_datetime(upcoming["date"], utc=True)
    upcoming = upcoming.sort_values("date").head(limit)
    return upcoming[["date", "matchday", "home_team", "away_team"]].to_dict(orient="records")


def live_fixtures() -> list[dict]:
    """Return current fixtures marked live by the football data provider."""
    current = pd.read_csv(DATA_DIR / "premier_league_matches.csv")
    current["status"] = current["status"].astype(str).str.upper()
    live = current[current["status"].isin(["IN_PLAY", "PAUSED", "LIVE", "INPLAY"])].copy()
    if live.empty:
        return []
    live["home_goals"] = pd.to_numeric(live["home_goals"], errors="coerce").fillna(0).astype(int)
    live["away_goals"] = pd.to_numeric(live["away_goals"], errors="coerce").fillna(0).astype(int)
    live["date"] = pd.to_datetime(live["date"], utc=True)
    return live.sort_values("date")[[
        "date", "matchday", "home_team", "away_team", "home_goals", "away_goals", "status"
    ]].to_dict(orient="records")


def current_feed_status() -> dict:
    """Describe freshness and provider statuses in the saved current feed."""
    current = pd.read_csv(DATA_DIR / "premier_league_matches.csv")
    current["status"] = current["status"].astype(str).str.upper()
    dates = pd.to_datetime(current["date"], utc=True, errors="coerce")
    live_count = int(current["status"].isin(["IN_PLAY", "PAUSED", "LIVE", "INPLAY"]).sum())
    return {
        "file": str(DATA_DIR / "premier_league_matches.csv"),
        "last_fixture_date": dates.max().isoformat() if dates.notna().any() else None,
        "statuses": {str(key): int(value) for key, value in current["status"].value_counts().items()},
        "live_matches": live_count,
        "refresh_command": "python update_current.py",
        "requires_api_key": True,
    }
