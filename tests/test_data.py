import unittest

import pandas as pd

from app.data import upcoming_fixtures, validate_matches


def valid_match(**overrides):
    match = {
        "season": "2026/27", "date": "2026-08-21T19:00:00Z",
        "home_team": "Arsenal FC", "away_team": "Chelsea FC",
        "home_goals": 2, "away_goals": 1,
    }
    match.update(overrides)
    return match


class ValidateMatchesTests(unittest.TestCase):
    def test_normalizes_date_and_goal_types(self):
        matches = validate_matches(pd.DataFrame([valid_match(home_goals="2")]))
        self.assertIsInstance(matches["date"].dtype, pd.DatetimeTZDtype)
        self.assertEqual(matches["home_goals"].dtype, "int64")

    def test_rejects_invalid_scores(self):
        with self.assertRaisesRegex(ValueError, "non-negative whole"):
            validate_matches(pd.DataFrame([valid_match(home_goals=-1)]))

    def test_rejects_duplicate_fixtures(self):
        with self.assertRaisesRegex(ValueError, "duplicate fixtures"):
            validate_matches(pd.DataFrame([valid_match(), valid_match()]))

    def test_rejects_same_team_fixture(self):
        with self.assertRaisesRegex(ValueError, "same home and away"):
            validate_matches(pd.DataFrame([valid_match(away_team="Arsenal FC")]))

    def test_upcoming_fixtures_have_matchday_key(self):
        fixtures = upcoming_fixtures()
        self.assertTrue(all("matchday" in fixture for fixture in fixtures))
