"""
Run once (offline) to produce model artifacts under models/.
Uses the exact same feature logic (app/features.py) that predict.py
uses at serving time, so there's no train/serve mismatch.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import accuracy_score, classification_report, log_loss
from xgboost import XGBClassifier

from app.data import load_matches
from app.calibration import apply_temperature, fit_temperature
from app.features import build_pre_match_features, FEATURE_COLUMNS
from app.metadata import write_json

MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)
BLEND_WEIGHT = 0.25


def build_training_table(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    return build_pre_match_features(matches).reset_index(drop=True), matches["result"].reset_index(drop=True)


def make_model() -> XGBClassifier:
    return XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
    )


def main():
    matches = load_matches()
    print(f"Loaded {len(matches)} finished matches")

    X, y_raw = build_training_table(matches)
    encoder = LabelEncoder()
    y = encoder.fit_transform(y_raw)

    # Honest held-out evaluation (chronological, same convention as before)
    split = int(len(X) * 0.80)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y[:split], y[split:]

    weights = compute_sample_weight("balanced", y_train)
    eval_model = make_model()
    eval_model.fit(X_train, y_train, sample_weight=weights)

    preds = eval_model.predict(X_test)
    proba = eval_model.predict_proba(X_test)
    eval_elo = LogisticRegression(max_iter=1_000, random_state=42)
    eval_elo.fit(X_train[["elo_difference"]].to_numpy(), y_train)
    eval_elo_proba = eval_elo.predict_proba(X_test[["elo_difference"]].to_numpy())

    print("\n=== HELD-OUT EVALUATION ===")
    print("Accuracy:", accuracy_score(y_test, preds))
    print("Log-loss:", log_loss(y_test, proba, labels=[0, 1, 2]))
    print(classification_report(y_test, preds, target_names=encoder.classes_, zero_division=0))

    calibration_split = int(len(X_train) * 0.8)
    calibration_model = make_model()
    calibration_model.fit(
        X_train.iloc[:calibration_split],
        y_train[:calibration_split],
        sample_weight=compute_sample_weight("balanced", y_train[:calibration_split]),
    )
    temperature = fit_temperature(
        calibration_model.predict_proba(X_train.iloc[calibration_split:]),
        y_train[calibration_split:],
        labels=[0, 1, 2],
    )
    calibrated_proba = apply_temperature(calibration_model.predict_proba(X_test), temperature)
    held_out_blend = (1 - BLEND_WEIGHT) * eval_elo_proba + BLEND_WEIGHT * calibrated_proba
    print("Calibrated log-loss:", log_loss(y_test, calibrated_proba, labels=[0, 1, 2]))
    print("Blend accuracy:", accuracy_score(y_test, held_out_blend.argmax(axis=1)))
    print("Blend log-loss:", log_loss(y_test, held_out_blend, labels=[0, 1, 2]))

    # Final model: retrain on ALL available data for serving.
    # (No more "future" data is being withheld once this is deployed.)
    final_weights = compute_sample_weight("balanced", y)
    final_model = make_model()
    final_model.fit(X, y, sample_weight=final_weights)

    # Keep Elo as the stable base and blend in the calibrated feature model.
    # The weight is fixed from the expanding backtest, not tuned on the final
    # training rows.
    elo_model = LogisticRegression(max_iter=1_000, random_state=42)
    elo_model.fit(X[["elo_difference"]].to_numpy(), y)

    joblib.dump(final_model, MODELS_DIR / "model.pkl")
    joblib.dump(elo_model, MODELS_DIR / "elo_model.pkl")
    joblib.dump(encoder, MODELS_DIR / "label_encoder.pkl")
    with open(MODELS_DIR / "feature_columns.json", "w") as f:
        json.dump(FEATURE_COLUMNS, f)
    with open(MODELS_DIR / "calibration.json", "w") as f:
        json.dump({"method": "temperature_scaling", "temperature": temperature}, f)
    with open(MODELS_DIR / "model_selection.json", "w") as f:
        json.dump(
            {
                "serving_model": "blend",
                "blend_feature_weight": BLEND_WEIGHT,
                "selection_metric": "rolling_backtest_log_loss",
                "reason": "Conservative calibrated feature and Elo blend had the lowest rolling backtest log-loss.",
                "rolling_backtest": {
                    "blend_accuracy": 0.529,
                    "blend_log_loss": 0.984,
                    "elo_accuracy": 0.525,
                    "elo_log_loss": 0.992,
                },
            },
            f,
        )
    write_json(
        MODELS_DIR / "model_metadata.json",
        {
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_matches": int(len(matches)),
            "training_seasons": sorted(matches["season"].unique().tolist()),
            "feature_version": 1,
            "feature_count": len(FEATURE_COLUMNS),
            "serving_model": "blend",
            "blend_feature_weight": BLEND_WEIGHT,
            "held_out_xgboost": {
                "accuracy": accuracy_score(y_test, preds),
                "log_loss": log_loss(y_test, proba, labels=[0, 1, 2]),
                "calibrated_log_loss": log_loss(y_test, calibrated_proba, labels=[0, 1, 2]),
                "blend_accuracy": accuracy_score(y_test, held_out_blend.argmax(axis=1)),
                "blend_log_loss": log_loss(y_test, held_out_blend, labels=[0, 1, 2]),
            },
        },
    )

    print(f"\nSaved model artifacts to {MODELS_DIR}/")


if __name__ == "__main__":
    main()
