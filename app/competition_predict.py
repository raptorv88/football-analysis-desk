"""Prediction helpers for the isolated non-Premier-League models."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib

from app.competition_data import competition_code
from app.features import ELO_INITIAL_RATING, elo_ratings


MODEL_DIR = Path(__file__).parent.parent / "models" / "competitions"


@lru_cache(maxsize=5)
def _load_model(code: str):
    path = MODEL_DIR / code / "outcome_model.pkl"
    if not path.exists():
        raise FileNotFoundError(f"No trained {code} model; run training.train_competition_models")
    return joblib.load(path)


def model_available(code: str) -> bool:
    normalized = competition_code(code)
    return (MODEL_DIR / normalized / "outcome_model.pkl").exists()


def predict_fixture(code: str, matches, home_team: str, away_team: str, fixture_date=None) -> dict:
    normalized = competition_code(code)
    teams = set(matches["home_team"]) | set(matches["away_team"])
    if home_team not in teams or away_team not in teams:
        raise ValueError("Unknown team name(s) for this competition")
    model = _load_model(normalized)
    ratings = elo_ratings(matches, before_date=fixture_date)
    elo_difference = ratings.get(home_team, ELO_INITIAL_RATING) - ratings.get(away_team, ELO_INITIAL_RATING)
    probabilities = model.predict_proba([[elo_difference]])[0]
    probability_map = {
        str(result): round(float(probability), 4)
        for result, probability in zip(model.classes_, probabilities)
    }
    return {
        "competition": normalized,
        "home_team": home_team,
        "away_team": away_team,
        "predicted_result": max(probability_map, key=probability_map.get),
        "probabilities": probability_map,
        "elo_difference": round(float(elo_difference), 2),
        "model": "competition_elo_logistic",
    }