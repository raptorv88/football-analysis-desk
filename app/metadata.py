"""Small helpers for recording reproducible data and model metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_data_metadata(matches: pd.DataFrame) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_finished_matches": int(len(matches)),
        "seasons": sorted(matches["season"].unique().tolist()),
        "matches_per_season": {
            str(season): int(count)
            for season, count in matches["season"].value_counts().sort_index().items()
        },
        "date_range": {
            "start": matches["date"].min().isoformat(),
            "end": matches["date"].max().isoformat(),
        },
        "sources": {
            "historical": "footballcsv/cache.footballdata (derived from football-data.co.uk)",
            "current_season": "football-data.org API",
        },
    }
