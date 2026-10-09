"""In-process scheduled refresh jobs for a single-instance hosted deployment."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import subprocess
import sys

from app import data, predict


LOGGER = logging.getLogger("app.refresh")
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PL_REFRESH_INTERVAL_SECONDS = 2 * 24 * 60 * 60
DEFAULT_COMPETITION_REFRESH_INTERVAL_SECONDS = 6 * 24 * 60 * 60
_refresh_lock = asyncio.Lock()
_refresh_state = {
    "enabled": False,
    "pl": {"state": "disabled", "last_attempt": None, "last_success": None, "last_error": None},
    "competitions": {"state": "disabled", "last_attempt": None, "last_success": None, "last_error": None},
}


def _interval(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        LOGGER.warning("Invalid %s; using %s seconds", name, default)
        return default
    if value < 300:
        LOGGER.warning("%s must be at least 300 seconds; using %s", name, default)
        return default
    return value


def _run_update(command: list[str], job_name: str) -> None:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if result.stdout:
        LOGGER.info("%s output:\n%s", job_name, result.stdout[-6000:])
    if result.returncode != 0:
        error = result.stderr[-3000:] or f"Updater exited with code {result.returncode}"
        raise RuntimeError(error)


def _refresh_pl() -> None:
    _run_update([sys.executable, str(PROJECT_ROOT / "update_current.py")], "Premier League update")
    data.MATCHES = data.load_matches()
    predict._elo_cache.clear()


def _refresh_competitions() -> None:
    _run_update(
        [sys.executable, "-m", "scripts.update_competitions", "--competition", "all"],
        "Competition update",
    )


async def _periodic_job(name: str, callback, interval: int, initial_delay: int) -> None:
    state = _refresh_state[name]
    await asyncio.sleep(initial_delay)
    while True:
        state["state"] = "running"
        state["last_attempt"] = datetime.now(timezone.utc).isoformat()
        try:
            async with _refresh_lock:
                await asyncio.to_thread(callback)
        except Exception as exc:
            state["state"] = "error"
            state["last_error"] = f"{type(exc).__name__}: {exc}"[-1200:]
            LOGGER.exception("Scheduled %s refresh failed", name)
        else:
            state["state"] = "ok"
            state["last_success"] = datetime.now(timezone.utc).isoformat()
            state["last_error"] = None
        await asyncio.sleep(interval)


def start_refresh_tasks() -> list[asyncio.Task]:
    enabled = os.getenv("ENABLE_DATA_REFRESH", "false").strip().lower() in {"1", "true", "yes", "on"}
    _refresh_state["enabled"] = enabled
    if not enabled:
        return []
    if not os.getenv("FOOTBALL_DATA_API_KEY"):
        _refresh_state["pl"]["state"] = "blocked: API key missing"
        _refresh_state["competitions"]["state"] = "blocked: API key missing"
        LOGGER.error("ENABLE_DATA_REFRESH is on, but FOOTBALL_DATA_API_KEY is not configured")
        return []

    pl_interval = _interval("PL_REFRESH_INTERVAL_SECONDS", DEFAULT_PL_REFRESH_INTERVAL_SECONDS)
    competition_interval = _interval(
        "COMPETITION_REFRESH_INTERVAL_SECONDS", DEFAULT_COMPETITION_REFRESH_INTERVAL_SECONDS
    )
    LOGGER.info(
        "Scheduled data refresh enabled (PL every %ss, competitions every %ss)",
        pl_interval,
        competition_interval,
    )
    return [
        asyncio.create_task(_periodic_job("pl", _refresh_pl, pl_interval, 30)),
        asyncio.create_task(_periodic_job("competitions", _refresh_competitions, competition_interval, 240)),
    ]


async def stop_refresh_tasks(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def refresh_status() -> dict:
    return {
        "enabled": _refresh_state["enabled"],
        "jobs": {
            name: dict(state)
            for name, state in _refresh_state.items()
            if name != "enabled"
        },
    }