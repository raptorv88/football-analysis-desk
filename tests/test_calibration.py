import unittest

import numpy as np

from app.calibration import apply_temperature


class CalibrationTests(unittest.TestCase):
    def test_temperature_one_preserves_probabilities(self):
        probabilities = np.array([[0.2, 0.3, 0.5]])
        np.testing.assert_allclose(apply_temperature(probabilities, 1.0), probabilities)

    def test_scaled_probabilities_sum_to_one(self):
        scaled = apply_temperature(np.array([[0.2, 0.3, 0.5]]), 2.0)
        self.assertAlmostEqual(float(scaled.sum()), 1.0)
