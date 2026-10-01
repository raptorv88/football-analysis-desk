from pathlib import Path
import json
import numpy as np

import joblib

from app.features import elo_ratings, fixture_features, team_form, FEATURE_COLUMNS
from app.calibration import apply_temperature

MODELS_DIR = Path(__file__).parent.parent / "models"

_encoder = joblib.load(MODELS_DIR / "label_encoder.pkl")
with open(MODELS_DIR / "feature_columns.json") as f:
    _feature_columns = json.load(f)
selection_path = MODELS_DIR / "model_selection.json"
if selection_path.exists():
    with open(selection_path) as f:
        _serving_model = json.load(f)["serving_model"]
else:
    _serving_model = "xgboost"

_elo_model = joblib.load(MODELS_DIR / "elo_model.pkl")
_blend_weight = 0.25
if selection_path.exists():
    with open(selection_path) as f:
        _blend_weight = json.load(f).get("blend_feature_weight", 0.25)

if _serving_model == "elo_logistic":
    _model = _elo_model
    _temperature = 1.0
else:
    _model = joblib.load(MODELS_DIR / "model.pkl")
    calibration_path = MODELS_DIR / "calibration.json"
    _temperature = json.loads(calibration_path.read_text())["temperature"] if calibration_path.exists() else 1.0

assert _feature_columns == FEATURE_COLUMNS, "Model was trained with a different feature set"
_elo_cache = {}


def _cached_elo_ratings(matches_df, before_date=None):
    cutoff = before_date
    if cutoff is not None and cutoff > matches_df["date"].max():
        cutoff = None
    key = (id(matches_df), str(cutoff))
    if key not in _elo_cache:
        _elo_cache[key] = elo_ratings(matches_df, before_date=cutoff)
    return _elo_cache[key]


def predict_fixture(matches_df, home_team: str, away_team: str, fixture_date=None, include_explanation=True) -> dict:
    """Predict outcome probabilities for home_team vs away_team,
    using each team's most recent form as of right now."""

    if include_explanation or _serving_model != "elo_logistic":
        feats = fixture_features(matches_df, home_team, away_team, fixture_date=fixture_date)
    else:
        ratings = _cached_elo_ratings(matches_df, before_date=fixture_date)
        home_form = team_form(matches_df, home_team, before_date=fixture_date)
        away_form = team_form(matches_df, away_team, before_date=fixture_date)
        feats = {
            "elo_difference": round(
                ratings.get(home_team, 1500.0) - ratings.get(away_team, 1500.0), 2
            ),
            "home_matches_available": home_form["matches_available"],
            "away_matches_available": away_form["matches_available"],
        }
    if _serving_model == "elo_logistic":
        proba = _elo_model.predict_proba([[feats["elo_difference"]]])[0]
    elif _serving_model == "blend":
        X = [[feats[col] for col in FEATURE_COLUMNS]]
        feature_proba = apply_temperature(_model.predict_proba(X), _temperature)[0]
        elo_proba = _elo_model.predict_proba([[feats["elo_difference"]]])[0]
        proba = (1 - _blend_weight) * elo_proba + _blend_weight * feature_proba
    else:
        X = [[feats[col] for col in FEATURE_COLUMNS]]
        proba = apply_temperature(_model.predict_proba(X), _temperature)[0]
    probabilities = {cls: round(float(p), 3) for cls, p in zip(_encoder.classes_, proba)}
    predicted = _encoder.classes_[proba.argmax()]

    if not include_explanation:
        return {
            "home_team": home_team,
            "away_team": away_team,
            "predicted_result": predicted,
            "model": _serving_model,
            "probabilities": probabilities,
            "home_recent_matches_used": feats["home_matches_available"],
            "away_recent_matches_used": feats["away_matches_available"],
        }

    def rounded(name):
        return round(float(feats[name]), 3)

    explanation = {
        "home": {
            "elo": rounded("home_elo"),
            "xg_last5": rounded("home_xg_last5"),
            "xga_last5": rounded("home_xga_last5"),
            "xg_last10": rounded("home_xg_last10"),
            "xga_last10": rounded("home_xga_last10"),
            "finishing_last5": rounded("home_finishing_last5"),
            "defensive_overperformance_last5": rounded("home_defensive_overperformance_last5"),
            "ppda_last5": rounded("home_ppda_last5"),
            "ppda_allowed_last5": rounded("home_ppda_allowed_last5"),
            "deep_last5": rounded("home_deep_last5"),
            "deep_allowed_last5": rounded("home_deep_allowed_last5"),
        },
        "away": {
            "elo": rounded("away_elo"),
            "xg_last5": rounded("away_xg_last5"),
            "xga_last5": rounded("away_xga_last5"),
            "xg_last10": rounded("away_xg_last10"),
            "xga_last10": rounded("away_xga_last10"),
            "finishing_last5": rounded("away_finishing_last5"),
            "defensive_overperformance_last5": rounded("away_defensive_overperformance_last5"),
            "ppda_last5": rounded("away_ppda_last5"),
            "ppda_allowed_last5": rounded("away_ppda_allowed_last5"),
            "deep_last5": rounded("away_deep_last5"),
            "deep_allowed_last5": rounded("away_deep_allowed_last5"),
        },
        "matchup": {
            "elo_difference": rounded("elo_difference"),
            "home_pressing_edge": rounded("home_pressing_matchup"),
            "away_pressing_edge": rounded("away_pressing_matchup"),
            "home_territory_edge": rounded("home_territory_matchup"),
            "away_territory_edge": rounded("away_territory_matchup"),
        },
    }

    return {
        "home_team": home_team,
        "away_team": away_team,
        "predicted_result": predicted,
        "model": _serving_model,
        "probabilities": probabilities,
        "home_recent_matches_used": feats["home_matches_available"],
        "away_recent_matches_used": feats["away_matches_available"],
        "prediction_scope": "pre_match",
        "disclaimer": "This forecast uses information available before kickoff and does not update from live match events.",
        "explanation": explanation,
    }
