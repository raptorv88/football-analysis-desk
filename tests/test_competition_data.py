import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from app.competition_data import (
    ISOLATED_COMPETITIONS,
    league_table,
    matches_from_provider,
    matches_path,
    scorers_from_provider,
    load_team_assets,
    save_team_assets,
    team_assets_from_provider,
)


class CompetitionDataTests(unittest.TestCase):
    def test_provider_matches_keep_finished_and_scheduled_rows(self):
        frame = matches_from_provider([
            {
                "id": 1, "status": "FINISHED", "utcDate": "2024-08-01T12:00:00Z",
                "stage": "LEAGUE_STAGE", "matchday": 1,
                "homeTeam": {"name": "Home FC"}, "awayTeam": {"name": "Away FC"},
                "score": {"fullTime": {"home": 2, "away": 1}},
            },
            {
                "id": 2, "status": "SCHEDULED", "utcDate": "2024-08-08T12:00:00Z",
                "stage": "LEAGUE_STAGE", "matchday": 2,
                "homeTeam": {"name": "Away FC"}, "awayTeam": {"name": "Home FC"},
                "score": {"fullTime": {"home": None, "away": None}},
            },
        ], 2024)

        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["season"], "2024/25")
        self.assertEqual(frame.iloc[0]["home_goals"], 2)
        self.assertTrue(pd.isna(frame.iloc[1]["home_goals"]))

    def test_live_provider_scores_fall_back_to_current_score(self):
        frame = matches_from_provider([{
            "id": 3, "status": "IN_PLAY", "utcDate": "2026-10-01T12:00:00Z",
            "homeTeam": {"name": "Home FC"}, "awayTeam": {"name": "Away FC"},
            "score": {"fullTime": {"home": None, "away": None}, "current": {"home": 1, "away": 0}},
        }], 2026)
        self.assertEqual(frame.iloc[0]["home_goals"], 1)
        self.assertEqual(frame.iloc[0]["away_goals"], 0)

    def test_competition_files_are_separate_from_premier_league(self):
        self.assertEqual(matches_path("BL1").name, "bl1_matches.csv")
        self.assertNotEqual(matches_path("BL1"), matches_path("CL"))
        self.assertNotIn("PL", ISOLATED_COMPETITIONS)

    def test_scorer_records_are_flattened_without_match_claims(self):
        scorers = scorers_from_provider([{
            "player": {"id": 10, "name": "Forward One"},
            "team": {"id": 20, "name": "Home FC"},
            "goals": 8, "assists": 3, "penalties": 1, "playedMatches": 12,
        }])
        self.assertEqual(scorers.iloc[0]["player"], "Forward One")
        self.assertEqual(scorers.iloc[0]["goals"], 8)
        self.assertNotIn("match_id", scorers.columns)

    def test_provider_crests_are_extracted_outside_prediction_match_columns(self):
        payload = [{
            "homeTeam": {"id": 10, "name": "Home FC", "shortName": "Home", "tla": "HOM", "crest": "https://example.test/home.svg"},
            "awayTeam": {"id": 20, "name": "Away FC", "shortName": "Away", "tla": "AWY", "crest": "https://example.test/away.svg"},
        }]

        assets = team_assets_from_provider("CL", payload)

        self.assertEqual(assets["competition"].unique().tolist(), ["CL"])
        self.assertEqual(assets.set_index("team").loc["Home FC", "logo"], "https://example.test/home.svg")
        self.assertNotIn("crest", matches_from_provider([], 2026).columns)

    def test_logo_refresh_preserves_other_competition_assets(self):
        with TemporaryDirectory() as temporary:
            asset_path = Path(temporary) / "team_assets.csv"
            with patch("app.competition_data.TEAM_ASSETS_PATH", asset_path):
                save_team_assets("CL", pd.DataFrame([{
                    "team": "Club One", "team_id": 1, "short_name": "One",
                    "tla": "ONE", "logo": "https://example.test/one.svg",
                }]))
                save_team_assets("BL1", pd.DataFrame([{
                    "team": "Club Two", "team_id": 2, "short_name": "Two",
                    "tla": "TWO", "logo": "https://example.test/two.svg",
                }]))

                self.assertEqual(load_team_assets("CL"), {"Club One": "https://example.test/one.svg"})
                self.assertEqual(load_team_assets("BL1"), {"Club Two": "https://example.test/two.svg"})

    def test_champions_league_table_uses_league_phase_only(self):
        matches = pd.DataFrame([
            {"season": "2024/25", "stage": "LEAGUE_STAGE", "group": None,
             "status": "FINISHED", "home_team": "A", "away_team": "B",
             "home_goals": 2, "away_goals": 0},
            {"season": "2024/25", "stage": "FINAL", "group": None,
             "status": "FINISHED", "home_team": "C", "away_team": "D",
             "home_goals": 3, "away_goals": 0},
        ])
        from unittest.mock import patch
        with patch("app.competition_data.load_matches", return_value=matches):
            table = league_table("CL", "2024/25")
        self.assertEqual({row["team"] for row in table}, {"A", "B"})

    def test_upcoming_fixtures_convert_missing_provider_fields_to_null(self):
        from app.competition_data import upcoming_fixtures
        from unittest.mock import patch

        matches = pd.DataFrame([{
            "fixture_id": pd.NA, "season": "2026/27", "date": pd.Timestamp("2026-10-10", tz="UTC"),
            "stage": "LEAGUE_STAGE", "group": pd.NA, "matchday": pd.NA,
            "home_team": "Home FC", "away_team": "Away FC", "home_goals": pd.NA,
            "away_goals": pd.NA, "status": "TIMED",
        }])
        with patch("app.competition_data.load_matches", return_value=matches):
            fixture = upcoming_fixtures("CL")[0]
        self.assertIsNone(fixture["fixture_id"])
        self.assertIsNone(fixture["group"])
        self.assertIsNone(fixture["matchday"])


if __name__ == "__main__":
    unittest.main()