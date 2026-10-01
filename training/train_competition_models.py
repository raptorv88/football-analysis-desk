"""Train isolated Elo-logistic outcome models for non-PL competitions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss

from app.competition_data import COMPETITIONS, ISOLATED_COMPETITIONS, load_matches
from app.features import ELO_INITIAL_RATING


MODEL_DIR = Path(__file__).parent.parent / "models" / "competitions"
MIN_TRAIN_MATCHES = 80


def result_for(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "HOME_WIN"
    if home_goals < away_goals:
        return "AWAY_WIN"
    return "DRAW"


def build_elo_features(matches):
    ordered = matches.sort_values("date").reset_index(drop=True)
    ratings = {}
    rows = []
    labels = []
    for _, simultaneous in ordered.groupby("date", sort=False):
        for _, match in simultaneous.iterrows():
            home, away = match["home_team"], match["away_team"]
            rows.append([ratings.get(home, ELO_INITIAL_RATING) - ratings.get(away, ELO_INITIAL_RATING)])
            labels.append(result_for(int(match["home_goals"]), int(match["away_goals"])))
        for _, match in simultaneous.iterrows():
            home, away = match["home_team"], match["away_team"]
            result = result_for(int(match["home_goals"]), int(match["away_goals"]))
            home_rating = ratings.get(home, ELO_INITIAL_RATING)
            away_rating = ratings.get(away, ELO_INITIAL_RATING)
            expected_home = 1 / (1 + 10 ** ((away_rating - home_rating - 60.0) / 400))
            actual_home = 1.0 if result == "HOME_WIN" else 0.0 if result == "AWAY_WIN" else 0.5
            adjustment = 20.0 * (actual_home - expected_home)
            ratings[home] = home_rating + adjustment
            ratings[away] = away_rating - adjustment
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=str), ordered


def train_competition(code: str) -> dict:
    matches = load_matches(code, finished_only=True)
    if len(matches) < MIN_TRAIN_MATCHES:
        raise ValueError(f"{code} has {len(matches)} finished matches; at least {MIN_TRAIN_MATCHES} are required")

    features, labels, ordered = build_elo_features(matches)
    unique_dates = ordered["date"].drop_duplicates().sort_values().tolist()
    if len(unique_dates) < 2:
        raise ValueError(f"{code} needs at least two kickoff dates for chronological validation")
    split_date = unique_dates[max(1, int(len(unique_dates) * 0.8))]
    train_mask = ordered["date"].to_numpy() < split_date
    test_mask = ~train_mask
    train_labels = labels[train_mask]
    test_labels = labels[test_mask]
    if len(set(train_labels)) < 3 or len(test_labels) == 0:
        raise ValueError(f"{code} does not have all result classes in its chronological training split")

    evaluation_model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    evaluation_model.fit(features[train_mask], train_labels)
    test_probabilities = evaluation_model.predict_proba(features[test_mask])
    test_predictions = evaluation_model.classes_[test_probabilities.argmax(axis=1)]
    metrics = {
        "accuracy": float(accuracy_score(test_labels, test_predictions)),
        "log_loss": float(log_loss(test_labels, test_probabilities, labels=evaluation_model.classes_)),
        "test_matches": int(test_mask.sum()),
    }

    final_model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    final_model.fit(features, labels)
    output_dir = MODEL_DIR / code
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, output_dir / "outcome_model.pkl")
    metadata = {
        "competition": code,
        "competition_name": COMPETITIONS[code]["name"],
        "model": "competition_elo_logistic",
        "features": ["elo_difference"],
        "matches": len(matches),
        "seasons": sorted(matches["season"].unique().tolist()),
        "validation": metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train isolated non-PL outcome models")
    parser.add_argument("--competition", choices=["all", *ISOLATED_COMPETITIONS], default="all")
    args = parser.parse_args()
    codes = list(ISOLATED_COMPETITIONS) if args.competition == "all" else [args.competition]
    for code in codes:
        try:
            result = train_competition(code)
        except (ValueError, FileNotFoundError) as exc:
            print(f"{code}: skipped ({exc})")
            continue
        print(
            f"{code}: trained on {result['matches']} matches; "
            f"walk-forward accuracy={result['validation']['accuracy']:.3f}, "
            f"log-loss={result['validation']['log_loss']:.3f}"
        )
    print("Restart the app server to load newly trained competition models.")


if __name__ == "__main__":
    main()