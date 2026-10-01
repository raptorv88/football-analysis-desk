"""Evaluate the predictor using expanding, season-by-season backtests.

Run from the project root:
    python -m scripts.evaluate_model

Each test season is predicted by a model trained only on earlier seasons.
This measures the model against information that would have been available at
the time, and compares it with a historical-result-frequency baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, log_loss
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from app.data import load_matches
from app.calibration import apply_temperature, fit_temperature
from app.features import FEATURE_COLUMNS, build_pre_match_features

REPORTS_DIR = Path(__file__).parent.parent / "reports"


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


def evaluate() -> pd.DataFrame:
    matches = load_matches()
    print(f"Building leakage-safe features for {len(matches)} matches...", flush=True)
    X, target = build_training_table(matches)
    encoder = LabelEncoder()
    y = encoder.fit_transform(target)
    labels = list(range(len(encoder.classes_)))
    seasons = sorted(matches["season"].unique())
    results = []

    for season in seasons[1:]:
        print(f"Evaluating {season}...", flush=True)
        train_mask = matches["season"] < season
        test_mask = matches["season"] == season
        X_train, X_test = X.loc[train_mask], X.loc[test_mask]
        y_train, y_test = y[train_mask], y[test_mask]

        model = make_model()
        model.fit(X_train, y_train, sample_weight=compute_sample_weight("balanced", y_train))
        probabilities = model.predict_proba(X_test)

        # Fit calibration on the most recent portion of the training period,
        # never on the season used for evaluation.
        calibration_split = int(len(X_train) * 0.8)
        calibration_model = make_model()
        calibration_model.fit(
            X_train.iloc[:calibration_split],
            y_train[:calibration_split],
            sample_weight=compute_sample_weight("balanced", y_train[:calibration_split]),
        )
        calibration_probabilities = calibration_model.predict_proba(X_train.iloc[calibration_split:])
        temperature = fit_temperature(
            calibration_probabilities, y_train[calibration_split:], labels
        )
        calibrated_probabilities = apply_temperature(
            calibration_model.predict_proba(X_test), temperature
        )

        elo_model = LogisticRegression(max_iter=1_000, random_state=42)
        elo_model.fit(X_train[["elo_difference"]].to_numpy(), y_train)
        elo_probabilities = elo_model.predict_proba(X_test[["elo_difference"]].to_numpy())

        # Blend the calibrated feature model with Elo. The weight is evaluated
        # out of sample so the report can distinguish a stable ensemble from a
        # feature model that only wins on one historical period.
        blend_probabilities = 0.25 * calibrated_probabilities + 0.75 * elo_probabilities

        class_frequency = pd.Series(y_train).value_counts(normalize=True)
        baseline_probabilities = [class_frequency.get(label, 0.0) for label in labels]
        baseline_predictions = [max(labels, key=lambda label: baseline_probabilities[label])] * len(y_test)
        results.append(
            {
                "test_season": season,
                "train_matches": len(X_train),
                "test_matches": len(X_test),
                "model_accuracy": accuracy_score(y_test, model.predict(X_test)),
                "model_log_loss": log_loss(y_test, probabilities, labels=labels),
                "calibrated_accuracy": accuracy_score(y_test, calibrated_probabilities.argmax(axis=1)),
                "calibrated_log_loss": log_loss(y_test, calibrated_probabilities, labels=labels),
                "elo_accuracy": accuracy_score(y_test, elo_model.predict(X_test[["elo_difference"]].to_numpy())),
                "elo_log_loss": log_loss(y_test, elo_probabilities, labels=labels),
                "blend_accuracy": accuracy_score(y_test, blend_probabilities.argmax(axis=1)),
                "blend_log_loss": log_loss(y_test, blend_probabilities, labels=labels),
                "baseline_accuracy": accuracy_score(y_test, baseline_predictions),
                "baseline_log_loss": log_loss(
                    y_test, [baseline_probabilities] * len(y_test), labels=labels
                ),
            }
        )

    return pd.DataFrame(results)


def main() -> None:
    results = evaluate()
    REPORTS_DIR.mkdir(exist_ok=True)
    results.to_csv(REPORTS_DIR / "backtest_metrics.csv", index=False)

    print("=== EXPANDING SEASON BACKTEST ===")
    print(results.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    print("\nMean metrics:")
    print(
        results[[
            "model_accuracy", "model_log_loss", "calibrated_accuracy", "calibrated_log_loss",
            "elo_accuracy", "elo_log_loss", "blend_accuracy", "blend_log_loss",
            "baseline_accuracy", "baseline_log_loss",
        ]]
        .mean()
        .to_string(float_format=lambda value: f"{value:.3f}")
    )

    summary = {
        "method": "Expanding-season backtest; each season is evaluated using only prior seasons.",
        "metrics": results.to_dict(orient="records"),
    }
    (REPORTS_DIR / "backtest_summary.json").write_text(json.dumps(summary, indent=2))
    print("\nSaved reports/backtest_metrics.csv and reports/backtest_summary.json")


if __name__ == "__main__":
    main()
