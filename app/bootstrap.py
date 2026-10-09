"""Seed a persistent data volume before importing the FastAPI application."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_DATA_DIR = PROJECT_ROOT / "data"


def seed_persistent_data(source: Path, target: Path) -> list[Path]:
    """Copy baseline CSV/metadata files only when absent; never overwrite live data."""
    source = source.resolve()
    target = target.resolve()
    if source == target:
        return []

    copied = []
    target.mkdir(parents=True, exist_ok=True)
    source_files = [
        *source.glob("*.csv"),
        source / "data_metadata.json",
    ]
    source_competitions = source / "competitions"
    if source_competitions.exists():
        source_files.extend(source_competitions.glob("*.csv"))

    for source_file in source_files:
        if not source_file.exists():
            continue
        relative = source_file.relative_to(source)
        target_file = target / relative
        if target_file.exists():
            continue
        target_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = target_file.with_suffix(target_file.suffix + ".tmp")
        shutil.copy2(source_file, temporary)
        temporary.replace(target_file)
        copied.append(target_file)
    return copied


def main() -> None:
    data_dir = Path(os.getenv("APP_DATA_DIR", str(PROJECT_DATA_DIR)))
    copied = seed_persistent_data(PROJECT_DATA_DIR, data_dir)
    print(f"Persistent data directory ready: {data_dir} ({len(copied)} seed files copied)", flush=True)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        os.getenv("PORT", "8000"),
        "--workers",
        "1",
    ]
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()