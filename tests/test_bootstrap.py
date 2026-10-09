import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.bootstrap import seed_persistent_data


class PersistentDataBootstrapTests(unittest.TestCase):
    def test_seeds_baseline_once_and_preserves_runtime_history(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            target = Path(temporary) / "mounted"
            (source / "competitions").mkdir(parents=True)
            (source / "premier_league_matches.csv").write_text("baseline", encoding="utf-8")
            (source / "data_metadata.json").write_text("{}", encoding="utf-8")
            (source / "prediction_history.json").write_text("secret runtime history", encoding="utf-8")
            (source / "competitions" / "cl_matches.csv").write_text("baseline CL", encoding="utf-8")

            first_copy = seed_persistent_data(source, target)
            (target / "premier_league_matches.csv").write_text("updated live data", encoding="utf-8")
            second_copy = seed_persistent_data(source, target)

            self.assertEqual(len(first_copy), 3)
            self.assertEqual(second_copy, [])
            self.assertEqual(
                (target / "premier_league_matches.csv").read_text(encoding="utf-8"),
                "updated live data",
            )
            self.assertFalse((target / "prediction_history.json").exists())


if __name__ == "__main__":
    unittest.main()