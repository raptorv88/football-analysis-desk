import unittest

from scripts.import_historical_api import matches_to_frame, season_label


class ApiHistoricalImportTests(unittest.TestCase):
    def test_season_label(self):
        self.assertEqual(season_label(2022), "2022/23")

    def test_keeps_finished_scored_matches_only(self):
        matches = [
            {
                "status": "FINISHED", "utcDate": "2022-08-01T12:00:00Z", "matchday": 1,
                "homeTeam": {"name": "Home FC"}, "awayTeam": {"name": "Away FC"},
                "score": {"fullTime": {"home": 2, "away": 1}},
            },
            {"status": "SCHEDULED", "score": {"fullTime": {"home": None, "away": None}}},
        ]
        frame = matches_to_frame(matches, 2022)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["season"], "2022/23")
        self.assertEqual(frame.iloc[0]["matchday"], 1)
