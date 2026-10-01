"""Competition-scoped data storage kept separate from Premier League inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).parent.parent / "data" / "competitions"
MATCH_COLUMNS = [
    "fixture_id", "season", "date", "stage", "group", "matchday",
    "home_team", "away_team", "home_goals", "away_goals", "status",
]
SCORER_COLUMNS = [
    "player_id", "player", "team_id", "team", "goals", "assists",
    "penalties", "played_matches",
]
TEAM_ASSET_COLUMNS = ["competition", "team", "team_id", "short_name", "tla", "logo"]
TEAM_ASSETS_PATH = DATA_DIR / "team_assets.csv"

COMPETITIONS = {
    "CL": {"name": "UEFA Champions League", "provider_code": "CL", "format": "league_phase"},
    "BL1": {"name": "Bundesliga", "provider_code": "BL1", "format": "round_robin"},
    "PD": {"name": "La Liga", "provider_code": "PD", "format": "round_robin"},
    "SA": {"name": "Serie A", "provider_code": "SA", "format": "round_robin"},
    "FL1": {"name": "Ligue 1", "provider_code": "FL1", "format": "round_robin"},
}
ISOLATED_COMPETITIONS = tuple(COMPETITIONS)
COMPETITIONS = {
    "PL": {"name": "Premier League", "provider_code": "PL", "format": "round_robin"},
    **COMPETITIONS,
}


def competition_code(code: str) -> str:
    normalized = code.upper()
    if normalized not in COMPETITIONS:
        raise ValueError(f"Unsupported competition '{code}'")
    return normalized


def matches_path(code: str) -> Path:
    return DATA_DIR / f"{competition_code(code).lower()}_matches.csv"


def scorers_path(code: str, season: str | None = None) -> Path:
    suffix = f"_{season.replace('/', '-') }" if season else ""
    return DATA_DIR / f"{competition_code(code).lower()}_scorers{suffix}.csv"


def season_label(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def matches_from_provider(matches: list[dict], start_year: int) -> pd.DataFrame:
    """Normalize football-data.org match records without touching PL datasets."""
    rows = []
    for match in matches:
        score = match.get("score") or {}
        full_time = score.get("fullTime") or {}
        current = score.get("current") or {}
        home_goals = full_time.get("home")
        away_goals = full_time.get("away")
        if home_goals is None:
            home_goals = current.get("home")
        if away_goals is None:
            away_goals = current.get("away")
        rows.append({
            "fixture_id": match.get("id"),
            "season": season_label(start_year),
            "date": match.get("utcDate"),
            "stage": match.get("stage"),
            "group": match.get("group"),
            "matchday": match.get("matchday"),
            "home_team": (match.get("homeTeam") or {}).get("name"),
            "away_team": (match.get("awayTeam") or {}).get("name"),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": str(match.get("status") or "SCHEDULED").upper(),
        })
    return normalize_matches(pd.DataFrame(rows, columns=MATCH_COLUMNS))


def normalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    normalized = matches.reindex(columns=MATCH_COLUMNS).copy()
    if normalized.empty:
        return normalized
    for column in ("season", "home_team", "away_team"):
        if normalized[column].isna().any():
            raise ValueError(f"Competition matches contain missing {column}")
    normalized["date"] = pd.to_datetime(normalized["date"], utc=True, errors="coerce")
    if normalized["date"].isna().any():
        raise ValueError("Competition matches contain invalid kickoff dates")
    for column in ("home_goals", "away_goals"):
        goals = pd.to_numeric(normalized[column], errors="coerce")
        if ((goals.dropna() < 0) | (goals.dropna() % 1 != 0)).any():
            raise ValueError(f"{column} must contain non-negative whole numbers")
        normalized[column] = goals.astype("Int64")
    normalized["status"] = normalized["status"].fillna("SCHEDULED").astype(str).str.upper()
    return normalized.sort_values("date").reset_index(drop=True)


def scorers_from_provider(scorers: list[dict]) -> pd.DataFrame:
    rows = []
    for item in scorers:
        player = item.get("player") or {}
        team = item.get("team") or {}
        rows.append({
            "player_id": player.get("id"),
            "player": player.get("name"),
            "team_id": team.get("id"),
            "team": team.get("name"),
            "goals": item.get("goals", 0),
            "assists": item.get("assists", 0),
            "penalties": item.get("penalties", 0),
            "played_matches": item.get("playedMatches", 0),
        })
    return pd.DataFrame(rows, columns=SCORER_COLUMNS)


def team_assets_from_provider(code: str, matches: list[dict]) -> pd.DataFrame:
    """Extract crests separately so presentation metadata never enters model rows."""
    normalized_code = competition_code(code)
    assets = {}
    for match in matches:
        for side in ("homeTeam", "awayTeam"):
            team = match.get(side) or {}
            name = team.get("name")
            crest = team.get("crest")
            if name and crest:
                assets[name] = {
                    "competition": normalized_code,
                    "team": name,
                    "team_id": team.get("id"),
                    "short_name": team.get("shortName"),
                    "tla": team.get("tla"),
                    "logo": crest,
                }
    return pd.DataFrame(assets.values(), columns=TEAM_ASSET_COLUMNS)


def save_team_assets(code: str, assets: pd.DataFrame) -> Path:
    normalized_code = competition_code(code)
    path = TEAM_ASSETS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = assets.reindex(columns=TEAM_ASSET_COLUMNS).copy()
    if incoming.empty:
        return path
    incoming["competition"] = normalized_code
    if path.exists():
        existing = pd.read_csv(path).reindex(columns=TEAM_ASSET_COLUMNS)
        existing = existing[existing["competition"] != normalized_code]
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming
    combined = combined.drop_duplicates(["competition", "team"], keep="last")
    temporary = path.with_suffix(".csv.tmp")
    combined.to_csv(temporary, index=False)
    temporary.replace(path)
    return path


def load_team_assets(code: str | None = None) -> dict[str, str]:
    if not TEAM_ASSETS_PATH.exists():
        return {}
    assets = pd.read_csv(TEAM_ASSETS_PATH).reindex(columns=TEAM_ASSET_COLUMNS)
    if code is not None:
        assets = assets[assets["competition"] == competition_code(code)]
    assets = assets.dropna(subset=["team", "logo"]).drop_duplicates("team", keep="last")
    return dict(zip(assets["team"], assets["logo"]))


def save_matches(code: str, matches: pd.DataFrame) -> Path:
    path = matches_path(code)
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = normalize_matches(matches)
    if path.exists():
        existing = normalize_matches(pd.read_csv(path))
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming
    if combined["fixture_id"].notna().all():
        combined = combined.drop_duplicates("fixture_id", keep="last")
    else:
        combined = combined.drop_duplicates(
            ["season", "date", "home_team", "away_team"], keep="last"
        )
    combined = normalize_matches(combined)
    temporary = path.with_suffix(".csv.tmp")
    combined.to_csv(temporary, index=False)
    temporary.replace(path)
    return path


def save_scorers(code: str, scorers: pd.DataFrame, season: str | None = None) -> Path:
    path = scorers_path(code, season)
    path.parent.mkdir(parents=True, exist_ok=True)
    scorers.reindex(columns=SCORER_COLUMNS).to_csv(path, index=False)
    return path


def load_matches(code: str, finished_only: bool = False) -> pd.DataFrame:
    path = matches_path(code)
    if not path.exists():
        return pd.DataFrame(columns=MATCH_COLUMNS)
    matches = normalize_matches(pd.read_csv(path))
    if finished_only:
        matches = matches[
            (matches["status"] == "FINISHED")
            & matches["home_goals"].notna()
            & matches["away_goals"].notna()
        ].copy()
    return matches.reset_index(drop=True)


def list_seasons(code: str) -> list[str]:
    matches = load_matches(code)
    return sorted(matches["season"].dropna().unique().tolist())


def upcoming_fixtures(code: str, limit: int = 10) -> list[dict]:
    matches = load_matches(code)
    excluded = {"FINISHED", "IN_PLAY", "PAUSED", "LIVE", "INPLAY", "SUSPENDED", "POSTPONED", "CANCELLED"}
    upcoming = matches[~matches["status"].isin(excluded)].sort_values("date").head(limit)
    columns = ["fixture_id", "date", "stage", "group", "matchday", "home_team", "away_team"]
    records = upcoming[columns].to_dict("records")
    return [
        {key: None if pd.isna(value) else value for key, value in record.items()}
        for record in records
    ]


def _table_for_matches(matches: pd.DataFrame, group_name: str | None = None) -> list[dict]:
    records: dict[str, dict] = {}
    for _, match in matches.iterrows():
        home, away = match["home_team"], match["away_team"]
        home_goals, away_goals = int(match["home_goals"]), int(match["away_goals"])
        for team in (home, away):
            records.setdefault(team, {
                "team": team, "matches": 0, "wins": 0, "draws": 0,
                "losses": 0, "goals_for": 0, "goals_against": 0, "points": 0,
            })
        home_row, away_row = records[home], records[away]
        home_row["matches"] += 1
        away_row["matches"] += 1
        home_row["goals_for"] += home_goals
        home_row["goals_against"] += away_goals
        away_row["goals_for"] += away_goals
        away_row["goals_against"] += home_goals
        if home_goals > away_goals:
            home_row["wins"] += 1
            home_row["points"] += 3
            away_row["losses"] += 1
        elif home_goals < away_goals:
            away_row["wins"] += 1
            away_row["points"] += 3
            home_row["losses"] += 1
        else:
            home_row["draws"] += 1
            away_row["draws"] += 1
            home_row["points"] += 1
            away_row["points"] += 1
    rows = list(records.values())
    for row in rows:
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
        if group_name:
            row["group"] = group_name
    rows.sort(key=lambda row: (-row["points"], -row["goal_difference"], -row["goals_for"], row["team"]))
    for position, row in enumerate(rows, start=1):
        row["position"] = position
    return rows


def league_table(code: str, season: str) -> list[dict]:
    code = competition_code(code)
    matches = load_matches(code, finished_only=True)
    matches = matches[matches["season"] == season]
    if code == "CL":
        league_stages = matches[matches["stage"].isin(["LEAGUE_STAGE", "GROUP_STAGE"])]
        if not league_stages.empty:
            matches = league_stages
    if matches.empty:
        return []
    if code == "CL" and matches["group"].notna().any():
        tables = []
        for group_name, group_matches in matches.groupby("group", dropna=False, sort=True):
            label = str(group_name) if pd.notna(group_name) else None
            tables.extend(_table_for_matches(group_matches, label))
        return tables
    return _table_for_matches(matches)


def load_scorers(code: str, season: str | None = None) -> pd.DataFrame:
    path = scorers_path(code, season)
    if not path.exists():
        return pd.DataFrame(columns=SCORER_COLUMNS)
    return pd.read_csv(path).reindex(columns=SCORER_COLUMNS)