import unittest

from scripts.import_historical import TEAM_NAMES


class HistoricalImportTests(unittest.TestCase):
    def test_common_source_names_are_normalized(self):
        self.assertEqual(TEAM_NAMES["Man City"], "Manchester City FC")
        self.assertEqual(TEAM_NAMES["Wolves"], "Wolverhampton Wanderers FC")
        self.assertEqual(TEAM_NAMES["Bournemouth"], "AFC Bournemouth")
