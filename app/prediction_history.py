"""Persistent snapshots of pre-match forecasts for later live/result display."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HISTORY_PATH = Path(__file__).parent.parent / "data" / "prediction_history.json"


def fixture_key(date, home_team: str, away_team: str) -> str:
    timestamp = pd.to_datetime(date, utc=True).isoformat()
    return f"{timestamp}|{home_team}|{away_team}"


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def snapshot_predictions(fixtures: list[dict], matches_df: pd.DataFrame) -> int:
    """Save forecasts for fixtures before a provider snapshot is replaced."""
    from app.predict import predict_fixture

    history = load_history()
    saved = 0
    archive_until = datetime.now(timezone.utc) + timedelta(days=14)
    for fixture in fixtures:
        if str(fixture.get("status", "")).upper() == "FINISHED":
            continue
        date = pd.to_datetime(fixture["date"], utc=True)
        status = str(fixture.get("status", "")).upper()
        if date.to_pydatetime() > archive_until and status not in {"IN_PLAY", "PAUSED", "LIVE", "INPLAY"}:
            continue
        key = fixture_key(date, fixture["home_team"], fixture["away_team"])
        if key in history:
            continue
        try:
            prediction = predict_fixture(
                matches_df,
                fixture["home_team"],
                fixture["away_team"],
                fixture_date=date,
                include_explanation=False,
            )
        except Exception:
            continue
        history[key] = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "fixture_date": date.isoformat(),
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
            "predicted_result": prediction["predicted_result"],
            "probabilities": prediction["probabilities"],
            "model": prediction["model"],
        }
        saved += 1

    if saved:
        HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return saved


def prediction_for(date, home_team: str, away_team: str) -> dict | None:
    return load_history().get(fixture_key(date, home_team, away_team))
