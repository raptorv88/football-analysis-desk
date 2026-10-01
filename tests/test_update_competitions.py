import unittest
from datetime import datetime, timezone

import pandas as pd
from pathlib import Path
from unittest.mock import patch

from scripts.update_competitions import current_season_start_year, infer_start_year, update_pl_scorers
from training.train_competition_models import build_elo_features


class CompetitionUpdateTests(unittest.TestCase):
    def test_current_season_start_year_respects_summer_boundary(self):
        july = datetime(2026, 7, 1, tzinfo=timezone.utc)
        june = datetime(2026, 6, 30, tzinfo=timezone.utc)
        self.assertEqual(current_season_start_year(july), 2026)
        self.assertEqual(current_season_start_year(june), 2025)

    def test_infer_start_year_uses_provider_season_date(self):
        payload = {"matches": [{"season": {"startDate": "2024-08-01"}}]}
        self.assertEqual(infer_start_year(payload, 2026), 2024)

    def test_infer_start_year_uses_fallback_for_empty_competition(self):
        self.assertEqual(infer_start_year({"matches": []}, 2026), 2026)

    def test_simultaneous_fixtures_share_pre_match_elo(self):
        matches = pd.DataFrame([
            {"date": "2024-08-01T12:00:00Z", "home_team": "A", "away_team": "B", "home_goals": 2, "away_goals": 0},
            {"date": "2024-08-01T12:00:00Z", "home_team": "C", "away_team": "A", "home_goals": 1, "away_goals": 0},
        ])
        matches["date"] = pd.to_datetime(matches["date"], utc=True)
        features, _, _ = build_elo_features(matches)
        self.assertEqual(features[:, 0].tolist(), [0.0, 0.0])

    def test_pl_scorer_refresh_only_writes_pl_scorer_summary(self):
        with patch("scripts.update_competitions._get_json", return_value={"scorers": []}), patch(
            "scripts.update_competitions.save_scorers", return_value=Path("pl_scorers.csv")
        ) as save:
            result = update_pl_scorers("test-token")
        self.assertEqual(result, Path("pl_scorers.csv"))
        self.assertEqual(save.call_args.args[0], "PL")
        self.assertEqual(len(save.call_args.args), 3)


if __name__ == "__main__":
    unittest.main()