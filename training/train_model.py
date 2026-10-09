"""
Run once (offline) to produce model artifacts under models/.
Uses the exact same feature logic (app/features.py) that predict.py
uses at serving time, so there's no train/serve mismatch.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import accuracy_score, classification_report, log_loss
from xgboost import XGBClassifier

from app.data import load_matches
from app.features import fixture_features, FEATURE_COLUMNS

MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def build_training_table(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    rows = []
    for _, match in matches.iterrows():
        feats = fixture_features(
            matches, match["home_team"], match["away_team"], before_date=match["date"]
        )
        rows.append([feats[c] for c in FEATURE_COLUMNS])
    X = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    y = matches["result"].reset_index(drop=True)
    return X, y


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

    print("\n=== HELD-OUT EVALUATION ===")
    print("Accuracy:", accuracy_score(y_test, preds))
    print("Log-loss:", log_loss(y_test, proba, labels=[0, 1, 2]))
    print(classification_report(y_test, preds, target_names=encoder.classes_, zero_division=0))

    # Final model: retrain on ALL available data for serving.
    # (No more "future" data is being withheld once this is deployed.)
    final_weights = compute_sample_weight("balanced", y)
    final_model = make_model()
    final_model.fit(X, y, sample_weight=final_weights)

    joblib.dump(final_model, MODELS_DIR / "model.pkl")
    joblib.dump(encoder, MODELS_DIR / "label_encoder.pkl")
    with open(MODELS_DIR / "feature_columns.json", "w") as f:
        json.dump(FEATURE_COLUMNS, f)

    print(f"\nSaved model artifacts to {MODELS_DIR}/")


if __name__ == "__main__":
    main()
