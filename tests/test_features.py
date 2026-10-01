import unittest

import pandas as pd

from app.features import (
    ELO_INITIAL_RATING,
    build_pre_match_features,
    elo_ratings,
    fixture_features,
    season_form,
    venue_form,
)


MATCHES = pd.DataFrame(
    [
        {
            "date": "2026-08-01T12:00:00Z", "home_team": "Alpha", "away_team": "Bravo",
            "home_goals": 2, "away_goals": 0, "home_xg": 1.5, "away_xg": 0.5,
            "home_ppda": 8, "away_ppda": 14, "home_ppda_allowed": 14, "away_ppda_allowed": 8,
            "home_deep": 10, "away_deep": 4, "home_deep_allowed": 3, "away_deep_allowed": 7,
            "season": "2026/27",
        },
        {
            "date": "2026-08-08T12:00:00Z", "home_team": "Bravo", "away_team": "Alpha",
            "home_goals": 0, "away_goals": 1, "home_xg": 0.4, "away_xg": 1.2, "season": "2026/27",
        },
    ]
)
MATCHES["date"] = pd.to_datetime(MATCHES["date"], utc=True)


class EloFeatureTests(unittest.TestCase):
    def test_elo_updates_after_a_result(self):
        ratings = elo_ratings(MATCHES.iloc[:1])
        self.assertGreater(ratings["Alpha"], ELO_INITIAL_RATING)
        self.assertLess(ratings["Bravo"], ELO_INITIAL_RATING)

    def test_future_results_are_excluded(self):
        ratings = elo_ratings(MATCHES, before_date=MATCHES.iloc[0]["date"])
        self.assertEqual(ratings, {})

    def test_fixture_includes_elo_features(self):
        features = fixture_features(MATCHES, "Alpha", "Bravo", before_date=MATCHES.iloc[1]["date"])
        self.assertIn("home_elo", features)
        self.assertEqual(features["elo_difference"], round(features["home_elo"] - features["away_elo"], 2))

    def test_venue_and_season_form_exclude_future_matches(self):
        cutoff = MATCHES.iloc[1]["date"]
        home_form = venue_form(MATCHES, "Alpha", "home", before_date=cutoff)
        alpha_season = season_form(MATCHES, "Alpha", "2026/27", before_date=cutoff)
        self.assertEqual(home_form["points"], 3)
        self.assertEqual(alpha_season["points_per_game"], 3.0)

    def test_batch_builder_matches_fixture_features(self):
        batch_features = build_pre_match_features(MATCHES)
        fixture = fixture_features(
            MATCHES, "Bravo", "Alpha", before_date=MATCHES.iloc[1]["date"], season="2026/27"
        )
        for column in batch_features.columns:
            self.assertEqual(batch_features.iloc[1][column], fixture[column])

    def test_schedule_context_uses_only_prior_matches(self):
        fixture = fixture_features(
            MATCHES, "Bravo", "Alpha", before_date=MATCHES.iloc[1]["date"], season="2026/27"
        )
        self.assertEqual(fixture["home_rest_days"], 7.0)
        self.assertEqual(fixture["away_matches_last14_days"], 1)

    def test_xg_features_are_pre_match_and_venue_specific(self):
        features = fixture_features(
            MATCHES, "Bravo", "Alpha", before_date=MATCHES.iloc[1]["date"], season="2026/27"
        )
        self.assertEqual(features["home_xg_last5"], 0.5)
        self.assertEqual(features["away_xg_last5"], 1.5)
        self.assertEqual(features["home_home_xg_last5"], 0.0)
        self.assertEqual(features["away_away_xg_last5"], 0.0)
        self.assertEqual(features["home_finishing_last5"], -0.5)

    def test_style_features_include_pre_match_matchup_proxies(self):
        features = fixture_features(
            MATCHES, "Bravo", "Alpha", before_date=MATCHES.iloc[1]["date"], season="2026/27"
        )
        self.assertEqual(features["home_ppda_last5"], 14.0)
        self.assertEqual(features["away_ppda_last5"], 8.0)
        self.assertEqual(features["home_deep_last5"], 4.0)
        self.assertEqual(features["home_pressing_matchup"], 0.0)
        self.assertEqual(features["home_territory_matchup"], 1.0)
