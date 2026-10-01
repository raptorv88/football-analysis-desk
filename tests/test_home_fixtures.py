import unittest

from app.main import featured_champions_league_fixtures


class FeaturedChampionsLeagueFixturesTests(unittest.TestCase):
    def test_prominent_matchups_rank_ahead_of_unknown_pairings(self):
        fixtures = [
            {"date": "2026-10-13T16:45:00+00:00", "home_team": "Sabah FK", "away_team": "SK Slavia Praha"},
            {"date": "2026-10-13T19:00:00+00:00", "home_team": "Club Atlético de Madrid", "away_team": "Manchester United FC"},
            {"date": "2026-10-14T19:00:00+00:00", "home_team": "Manchester City FC", "away_team": "Paris Saint-Germain FC"},
            {"date": "2026-10-13T19:00:00+00:00", "home_team": "Arsenal FC", "away_team": "Lille OSC"},
        ]

        selected = featured_champions_league_fixtures(fixtures, 3)

        self.assertEqual(
            [(fixture["home_team"], fixture["away_team"]) for fixture in selected],
            [
                ("Club Atlético de Madrid", "Manchester United FC"),
                ("Arsenal FC", "Lille OSC"),
                ("Manchester City FC", "Paris Saint-Germain FC"),
            ],
        )

    def test_unknown_fixtures_remain_as_fallback(self):
        fixtures = [
            {"date": "2026-10-14T19:00:00+00:00", "home_team": "Team C", "away_team": "Team D"},
            {"date": "2026-10-13T19:00:00+00:00", "home_team": "Team A", "away_team": "Team B"},
        ]

        selected = featured_champions_league_fixtures(fixtures, 1)

        self.assertEqual(selected[0]["home_team"], "Team A")


if __name__ == "__main__":
    unittest.main()