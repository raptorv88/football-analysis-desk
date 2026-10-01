"""Probability calibration utilities for multiclass match predictions."""

import numpy as np
from sklearn.metrics import log_loss


def apply_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    """Sharpen or soften multiclass probabilities without changing their order."""
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0)
    logits = np.log(clipped) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    scaled = np.exp(logits)
    return scaled / scaled.sum(axis=1, keepdims=True)


def fit_temperature(probabilities: np.ndarray, targets: np.ndarray, labels: list[int]) -> float:
    """Select a temperature using a chronologically held-out calibration set."""
    candidates = np.linspace(0.5, 3.0, 251)
    return float(
        min(
            candidates,
            key=lambda value: log_loss(targets, apply_temperature(probabilities, value), labels=labels),
        )
    )
