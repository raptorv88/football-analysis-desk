"""
Shared "last 5 matches" form features, used both to build the
training dataset and to compute a team's current form for serving
live predictions on upcoming fixtures.
"""

from collections import defaultdict, deque

import pandas as pd

FEATURE_COLUMNS = [
    "home_form_last5",
    "away_form_last5",
    "home_goals_last5",
    "away_goals_last5",
    "home_goals_conceded_last5",
    "away_goals_conceded_last5",
    "home_elo",
    "away_elo",
    "elo_difference",
    "home_home_form_last5",
    "away_away_form_last5",
    "home_season_points_per_game",
    "away_season_points_per_game",
    "home_season_goal_difference_per_game",
    "away_season_goal_difference_per_game",
    "home_rest_days",
    "away_rest_days",
    "home_matches_last14_days",
    "away_matches_last14_days",
    "home_xg_last5",
    "away_xg_last5",
    "home_xg_last10",
    "away_xg_last10",
    "home_xga_last5",
    "away_xga_last5",
    "home_xga_last10",
    "away_xga_last10",
    "home_home_xg_last5",
    "home_home_xga_last5",
    "away_away_xg_last5",
    "away_away_xga_last5",
    "home_season_xg_difference_per_game",
    "away_season_xg_difference_per_game",
    "home_finishing_last5",
    "away_finishing_last5",
    "home_defensive_overperformance_last5",
    "away_defensive_overperformance_last5",
    "home_ppda_last5",
    "away_ppda_last5",
    "home_ppda_allowed_last5",
    "away_ppda_allowed_last5",
    "home_deep_last5",
    "away_deep_last5",
    "home_deep_allowed_last5",
    "away_deep_allowed_last5",
    "home_pressing_matchup",
    "away_pressing_matchup",
    "home_territory_matchup",
    "away_territory_matchup",
]

ELO_INITIAL_RATING = 1500.0
ELO_HOME_ADVANTAGE = 60.0
ELO_K_FACTOR = 20.0


def _team_last_n_matches(matches_df: pd.DataFrame, team: str, before_date=None, n: int = 5) -> pd.DataFrame:
    df = matches_df[(matches_df["home_team"] == team) | (matches_df["away_team"] == team)]
    if before_date is not None:
        df = df[df["date"] < before_date]
    return df.sort_values("date").tail(n)


def team_form(matches_df: pd.DataFrame, team: str, before_date=None, n: int = 5) -> dict:
    """Points, goals for, goals conceded over a team's last n matches."""
    recent = _team_last_n_matches(matches_df, team, before_date, n)

    points = 0
    goals_for = 0
    goals_conceded = 0

    for _, row in recent.iterrows():
        is_home = row["home_team"] == team
        gf = row["home_goals"] if is_home else row["away_goals"]
        ga = row["away_goals"] if is_home else row["home_goals"]
        goals_for += gf
        goals_conceded += ga
        if gf > ga:
            points += 3
        elif gf == ga:
            points += 1

    return {
        "points": int(points),
        "goals_for": int(goals_for),
        "goals_conceded": int(goals_conceded),
        "matches_available": len(recent),
    }


def venue_form(matches_df: pd.DataFrame, team: str, venue: str, before_date=None, n: int = 5) -> dict:
    """Return a team's points and goal difference over recent home or away games."""
    team_column = "home_team" if venue == "home" else "away_team"
    recent = matches_df[matches_df[team_column] == team]
    if before_date is not None:
        recent = recent[recent["date"] < before_date]
    recent = recent.sort_values("date").tail(n)

    points = 0
    goal_difference = 0
    for _, match in recent.iterrows():
        goals_for = match["home_goals"] if venue == "home" else match["away_goals"]
        goals_against = match["away_goals"] if venue == "home" else match["home_goals"]
        goal_difference += goals_for - goals_against
        if goals_for > goals_against:
            points += 3
        elif goals_for == goals_against:
            points += 1

    return {"points": int(points), "goal_difference": int(goal_difference), "matches_available": len(recent)}


def season_form(matches_df: pd.DataFrame, team: str, season: str, before_date=None) -> dict:
    """Return a team's same-season record before a fixture's kickoff."""
    season_matches = matches_df[matches_df["season"] == season]
    form = team_form(season_matches, team, before_date, n=len(season_matches))
    matches_played = form["matches_available"]
    goal_difference = form["goals_for"] - form["goals_conceded"]
    return {
        "points_per_game": form["points"] / matches_played if matches_played else 0.0,
        "goal_difference_per_game": goal_difference / matches_played if matches_played else 0.0,
        "matches_available": matches_played,
    }


def schedule_context(matches_df: pd.DataFrame, team: str, fixture_date=None) -> dict:
    """Return rest and fixture congestion known before a scheduled kickoff."""
    if fixture_date is None:
        return {"rest_days": 7.0, "matches_last14_days": 0}
    prior = _team_last_n_matches(matches_df, team, fixture_date, n=len(matches_df))
    if prior.empty:
        return {"rest_days": 7.0, "matches_last14_days": 0}
    rest_days = min(max((fixture_date - prior["date"].max()).total_seconds() / 86_400, 0), 21)
    return {
        "rest_days": round(rest_days, 2),
        "matches_last14_days": int((prior["date"] >= fixture_date - pd.Timedelta(days=14)).sum()),
    }


def elo_ratings(matches_df: pd.DataFrame, before_date=None) -> dict[str, float]:
    """Return team Elo ratings using only matches strictly before ``before_date``.

    Elo gives the model a long-term strength signal while the form features
    capture short-term performance. The home advantage is part of the expected
    result calculation, not permanently added to a team's rating.
    """
    matches = matches_df
    if before_date is not None:
        matches = matches[matches["date"] < before_date]

    ratings: dict[str, float] = {}
    for _, match in matches.sort_values("date").iterrows():
        home, away = match["home_team"], match["away_team"]
        home_rating = ratings.get(home, ELO_INITIAL_RATING)
        away_rating = ratings.get(away, ELO_INITIAL_RATING)
        home_expected = 1 / (1 + 10 ** ((away_rating - home_rating - ELO_HOME_ADVANTAGE) / 400))

        if match["home_goals"] > match["away_goals"]:
            home_actual = 1.0
        elif match["home_goals"] < match["away_goals"]:
            home_actual = 0.0
        else:
            home_actual = 0.5

        adjustment = ELO_K_FACTOR * (home_actual - home_expected)
        ratings[home] = home_rating + adjustment
        ratings[away] = away_rating - adjustment

    return ratings


def build_pre_match_features(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Build leakage-safe features for historical matches in one time-ordered pass.

    All matches sharing a kickoff timestamp receive features before any result
    from that timestamp updates form, Elo, or season statistics.
    """
    ordered = matches_df.sort_values(["date", "home_team", "away_team"], kind="stable")
    overall = defaultdict(lambda: deque(maxlen=5))
    home_venue = defaultdict(lambda: deque(maxlen=5))
    away_venue = defaultdict(lambda: deque(maxlen=5))
    season_stats = defaultdict(lambda: {"points": 0, "goal_difference": 0, "matches": 0})
    ratings: dict[str, float] = {}
    appearances = defaultdict(deque)
    overall_xg = defaultdict(lambda: deque(maxlen=10))
    home_xg = defaultdict(lambda: deque(maxlen=5))
    away_xg = defaultdict(lambda: deque(maxlen=5))
    xg_season_stats = defaultdict(lambda: {"difference": 0.0, "matches": 0})
    style_history = defaultdict(lambda: deque(maxlen=5))
    rows = []
    indices = []

    for _, simultaneous in ordered.groupby("date", sort=False):
        for index, match in simultaneous.iterrows():
            home, away, season = match["home_team"], match["away_team"], match["season"]
            home_recent = overall[home]
            away_recent = overall[away]
            home_season = season_stats[(season, home)]
            away_season = season_stats[(season, away)]
            home_rating = ratings.get(home, ELO_INITIAL_RATING)
            away_rating = ratings.get(away, ELO_INITIAL_RATING)

            def schedule_features(team):
                dates = appearances[team]
                cutoff = match["date"] - pd.Timedelta(days=14)
                while dates and dates[0] < cutoff:
                    dates.popleft()
                if not dates:
                    return 7.0, 0
                rest = min(max((match["date"] - dates[-1]).total_seconds() / 86_400, 0), 21)
                return round(rest, 2), len(dates)

            home_rest, home_congestion = schedule_features(home)
            away_rest, away_congestion = schedule_features(away)

            def points(records):
                return sum(record[0] for record in records)

            def goals_for(records):
                return sum(record[1] for record in records)

            def goals_against(records):
                return sum(record[2] for record in records)

            def per_game(stats, key):
                return stats[key] / stats["matches"] if stats["matches"] else 0.0

            def average(records, index, n=None):
                values = list(records)[-n:] if n else list(records)
                return sum(record[index] for record in values) / len(values) if values else 0.0

            def xg_value(match, column):
                value = match.get(column, 0.0)
                return 0.0 if pd.isna(value) else float(value)

            home_xg_recent = overall_xg[home]
            away_xg_recent = overall_xg[away]
            home_season_xg = xg_season_stats[(season, home)]
            away_season_xg = xg_season_stats[(season, away)]

            def style_value(match, column):
                value = match.get(column, 0.0)
                return 0.0 if pd.isna(value) else float(value)

            def style_average(records, index):
                return sum(record[index] for record in records) / len(records) if records else 0.0

            home_style = style_history[home]
            away_style = style_history[away]

            rows.append(
                {
                    "home_form_last5": points(home_recent),
                    "away_form_last5": points(away_recent),
                    "home_goals_last5": goals_for(home_recent),
                    "away_goals_last5": goals_for(away_recent),
                    "home_goals_conceded_last5": goals_against(home_recent),
                    "away_goals_conceded_last5": goals_against(away_recent),
                    "home_elo": round(home_rating, 2),
                    "away_elo": round(away_rating, 2),
                    "elo_difference": round(home_rating - away_rating, 2),
                    "home_home_form_last5": points(home_venue[home]),
                    "away_away_form_last5": points(away_venue[away]),
                    "home_season_points_per_game": round(per_game(home_season, "points"), 3),
                    "away_season_points_per_game": round(per_game(away_season, "points"), 3),
                    "home_season_goal_difference_per_game": round(per_game(home_season, "goal_difference"), 3),
                    "away_season_goal_difference_per_game": round(per_game(away_season, "goal_difference"), 3),
                    "home_rest_days": home_rest,
                    "away_rest_days": away_rest,
                    "home_matches_last14_days": home_congestion,
                    "away_matches_last14_days": away_congestion,
                    "home_xg_last5": round(average(home_xg_recent, 0, 5), 3),
                    "away_xg_last5": round(average(away_xg_recent, 0, 5), 3),
                    "home_xg_last10": round(average(home_xg_recent, 0, 10), 3),
                    "away_xg_last10": round(average(away_xg_recent, 0, 10), 3),
                    "home_xga_last5": round(average(home_xg_recent, 1, 5), 3),
                    "away_xga_last5": round(average(away_xg_recent, 1, 5), 3),
                    "home_xga_last10": round(average(home_xg_recent, 1, 10), 3),
                    "away_xga_last10": round(average(away_xg_recent, 1, 10), 3),
                    "home_home_xg_last5": round(average(home_xg[home], 0), 3),
                    "home_home_xga_last5": round(average(home_xg[home], 1), 3),
                    "away_away_xg_last5": round(average(away_xg[away], 0), 3),
                    "away_away_xga_last5": round(average(away_xg[away], 1), 3),
                    "home_season_xg_difference_per_game": round(per_game(home_season_xg, "difference"), 3),
                    "away_season_xg_difference_per_game": round(per_game(away_season_xg, "difference"), 3),
                    "home_finishing_last5": round(average(home_xg_recent, 2, 5), 3),
                    "away_finishing_last5": round(average(away_xg_recent, 2, 5), 3),
                    "home_defensive_overperformance_last5": round(average(home_xg_recent, 3, 5), 3),
                    "away_defensive_overperformance_last5": round(average(away_xg_recent, 3, 5), 3),
                    "home_ppda_last5": round(style_average(home_style, 0), 3),
                    "away_ppda_last5": round(style_average(away_style, 0), 3),
                    "home_ppda_allowed_last5": round(style_average(home_style, 1), 3),
                    "away_ppda_allowed_last5": round(style_average(away_style, 1), 3),
                    "home_deep_last5": round(style_average(home_style, 2), 3),
                    "away_deep_last5": round(style_average(away_style, 2), 3),
                    "home_deep_allowed_last5": round(style_average(home_style, 3), 3),
                    "away_deep_allowed_last5": round(style_average(away_style, 3), 3),
                    "home_pressing_matchup": round(style_average(away_style, 1) - style_average(home_style, 0), 3),
                    "away_pressing_matchup": round(style_average(home_style, 1) - style_average(away_style, 0), 3),
                    "home_territory_matchup": round(style_average(home_style, 2) - style_average(away_style, 3), 3),
                    "away_territory_matchup": round(style_average(away_style, 2) - style_average(home_style, 3), 3),
                }
            )
            indices.append(index)

        for _, match in simultaneous.iterrows():
            home, away, season = match["home_team"], match["away_team"], match["season"]
            home_goals, away_goals = match["home_goals"], match["away_goals"]
            match_home_xg = xg_value(match, "home_xg")
            match_away_xg = xg_value(match, "away_xg")
            match_home_xga = xg_value(match, "away_xg")
            match_away_xga = xg_value(match, "home_xg")
            home_style_record = (
                style_value(match, "home_ppda"), style_value(match, "home_ppda_allowed"),
                style_value(match, "home_deep"), style_value(match, "home_deep_allowed"),
            )
            away_style_record = (
                style_value(match, "away_ppda"), style_value(match, "away_ppda_allowed"),
                style_value(match, "away_deep"), style_value(match, "away_deep_allowed"),
            )
            if home_goals > away_goals:
                home_points, away_points, home_actual = 3, 0, 1.0
            elif home_goals < away_goals:
                home_points, away_points, home_actual = 0, 3, 0.0
            else:
                home_points, away_points, home_actual = 1, 1, 0.5

            overall[home].append((home_points, home_goals, away_goals))
            overall[away].append((away_points, away_goals, home_goals))
            home_venue[home].append((home_points, home_goals, away_goals))
            away_venue[away].append((away_points, away_goals, home_goals))
            overall_xg[home].append((match_home_xg, match_home_xga, home_goals - match_home_xg, away_goals - match_home_xga))
            overall_xg[away].append((match_away_xg, match_away_xga, away_goals - match_away_xg, home_goals - match_away_xga))
            home_xg[home].append((match_home_xg, match_home_xga))
            away_xg[away].append((match_away_xg, match_away_xga))
            style_history[home].append(home_style_record)
            style_history[away].append(away_style_record)
            for team, points_earned, goals_for, goals_against in (
                (home, home_points, home_goals, away_goals),
                (away, away_points, away_goals, home_goals),
            ):
                stats = season_stats[(season, team)]
                stats["points"] += points_earned
                stats["goal_difference"] += goals_for - goals_against
                stats["matches"] += 1
                xg_stats = xg_season_stats[(season, team)]
                team_xg = match_home_xg if team == home else match_away_xg
                team_xga = match_home_xga if team == home else match_away_xga
                xg_stats["difference"] += team_xg - team_xga
                xg_stats["matches"] += 1

            home_rating = ratings.get(home, ELO_INITIAL_RATING)
            away_rating = ratings.get(away, ELO_INITIAL_RATING)
            expected = 1 / (1 + 10 ** ((away_rating - home_rating - ELO_HOME_ADVANTAGE) / 400))
            adjustment = ELO_K_FACTOR * (home_actual - expected)
            ratings[home] = home_rating + adjustment
            ratings[away] = away_rating - adjustment
            appearances[home].append(match["date"])
            appearances[away].append(match["date"])

    features = pd.DataFrame(rows, index=indices, columns=FEATURE_COLUMNS)
    return features.reindex(matches_df.index)


def fixture_features(matches_df: pd.DataFrame, home_team: str, away_team: str, before_date=None, season: str | None = None, fixture_date=None) -> dict:
    """The 6 model features for a home_team vs away_team fixture,
    based on form strictly before `before_date` (None = use all data,
    i.e. 'as of right now')."""

    home = team_form(matches_df, home_team, before_date)
    away = team_form(matches_df, away_team, before_date)
    home_at_home = venue_form(matches_df, home_team, "home", before_date)
    away_away = venue_form(matches_df, away_team, "away", before_date)
    target_season = season or max(matches_df["season"])
    home_season = season_form(matches_df, home_team, target_season, before_date)
    away_season = season_form(matches_df, away_team, target_season, before_date)
    context_date = fixture_date or before_date
    home_schedule = schedule_context(matches_df, home_team, context_date)
    away_schedule = schedule_context(matches_df, away_team, context_date)
    ratings = elo_ratings(matches_df, before_date)
    home_elo = ratings.get(home_team, ELO_INITIAL_RATING)
    away_elo = ratings.get(away_team, ELO_INITIAL_RATING)

    cutoff = fixture_date or before_date
    if cutoff is None:
        cutoff = matches_df["date"].max() + pd.Timedelta(nanoseconds=1)
    prior = matches_df[matches_df["date"] < cutoff].copy()
    fixture_row = {
        "date": cutoff,
        "home_team": home_team,
        "away_team": away_team,
        "home_goals": 0,
        "away_goals": 0,
        "season": target_season,
    }
    serving_frame = pd.concat([prior, pd.DataFrame([fixture_row])], ignore_index=True)
    serving_features = build_pre_match_features(serving_frame).iloc[-1]
    xg_columns = FEATURE_COLUMNS[19:]
    values = {
        "home_form_last5": home["points"],
        "away_form_last5": away["points"],
        "home_goals_last5": home["goals_for"],
        "away_goals_last5": away["goals_for"],
        "home_goals_conceded_last5": home["goals_conceded"],
        "away_goals_conceded_last5": away["goals_conceded"],
        "home_elo": round(home_elo, 2),
        "away_elo": round(away_elo, 2),
        "elo_difference": round(home_elo - away_elo, 2),
        "home_home_form_last5": home_at_home["points"],
        "away_away_form_last5": away_away["points"],
        "home_season_points_per_game": round(home_season["points_per_game"], 3),
        "away_season_points_per_game": round(away_season["points_per_game"], 3),
        "home_season_goal_difference_per_game": round(home_season["goal_difference_per_game"], 3),
        "away_season_goal_difference_per_game": round(away_season["goal_difference_per_game"], 3),
        "home_rest_days": home_schedule["rest_days"],
        "away_rest_days": away_schedule["rest_days"],
        "home_matches_last14_days": home_schedule["matches_last14_days"],
        "away_matches_last14_days": away_schedule["matches_last14_days"],
        "home_matches_available": home["matches_available"],
        "away_matches_available": away["matches_available"],
    }
    values.update({column: float(serving_features[column]) for column in xg_columns})
    return values
