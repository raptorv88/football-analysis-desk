import os
import unittest
from unittest.mock import patch

from app.refresh_service import (
    DEFAULT_COMPETITION_REFRESH_INTERVAL_SECONDS,
    DEFAULT_PL_REFRESH_INTERVAL_SECONDS,
    _interval,
    start_refresh_tasks,
)


class RefreshServiceTests(unittest.TestCase):
    def test_default_refresh_intervals_are_two_and_six_days(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_interval("PL_REFRESH_INTERVAL_SECONDS", DEFAULT_PL_REFRESH_INTERVAL_SECONDS), 172800)
            self.assertEqual(
                _interval("COMPETITION_REFRESH_INTERVAL_SECONDS", DEFAULT_COMPETITION_REFRESH_INTERVAL_SECONDS),
                518400,
            )

    def test_refresh_jobs_are_disabled_unless_explicitly_enabled(self):
        with patch.dict(os.environ, {"ENABLE_DATA_REFRESH": "false"}, clear=False):
            tasks = start_refresh_tasks()
        self.assertEqual(tasks, [])

    def test_enabled_refresh_without_provider_key_starts_no_jobs(self):
        environment = {"ENABLE_DATA_REFRESH": "true"}
        with patch.dict(os.environ, environment, clear=False):
            os.environ.pop("FOOTBALL_DATA_API_KEY", None)
            tasks = start_refresh_tasks()
        self.assertEqual(tasks, [])


if __name__ == "__main__":
    unittest.main()