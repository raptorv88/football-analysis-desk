"""Refresh isolated non-Premier-League competition feeds from football-data.org.

Run from the project root with FOOTBALL_DATA_API_KEY set in .env:
    python -m scripts.update_competitions
    python -m scripts.update_competitions --competition BL1 --season-start-year 2024
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

import requests
from dotenv import load_dotenv
import os

from app.competition_data import (
    COMPETITIONS,
    ISOLATED_COMPETITIONS,
    matches_from_provider,
    save_matches,
    save_scorers,
    season_label,
    scorers_from_provider,
    save_team_assets,
    team_assets_from_provider,
)


API_ROOT = "https://api.football-data.org/v4"
PROJECT_ROOT = Path(__file__).parent.parent
_last_request_at = 0.0


def current_season_start_year(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    return current.year if current.month >= 7 else current.year - 1


def infer_start_year(payload: dict, fallback: int) -> int:
    matches = payload.get("matches") or []
    for match in matches:
        start_date = (match.get("season") or {}).get("startDate")
        if start_date:
            return int(start_date[:4])
    return fallback


def _get_json(url: str, api_key: str, params: dict | None = None) -> dict:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if _last_request_at and elapsed < 6.1:
        time.sleep(6.1 - elapsed)
    response = requests.get(
        url,
        headers={"X-Auth-Token": api_key},
        params=params,
        timeout=(5, 30),
    )
    _last_request_at = time.monotonic()
    response.raise_for_status()
    return response.json()


def update_competition(
    code: str,
    api_key: str,
    season_start_year: int | None = None,
    include_scorers: bool = True,
) -> tuple[Path, Path | None]:
    if code not in ISOLATED_COMPETITIONS:
        raise ValueError(f"Unsupported competition '{code}'")
    provider_code = COMPETITIONS[code]["provider_code"]
    params = {"season": season_start_year} if season_start_year is not None else None
    matches_payload = _get_json(f"{API_ROOT}/competitions/{provider_code}/matches", api_key, params)
    fallback_year = season_start_year or current_season_start_year()
    start_year = infer_start_year(matches_payload, fallback_year)
    match_rows = matches_from_provider(matches_payload.get("matches", []), start_year)
    match_path = save_matches(code, match_rows)
    if season_start_year is None:
        assets = team_assets_from_provider(code, matches_payload.get("matches", []))
        save_team_assets(code, assets)
        print(f"{code}: saved {len(assets)} club crests")

    scorer_path = None
    if include_scorers:
        scorer_params = {"season": start_year, "limit": 100}
        try:
            scorers_payload = _get_json(
                f"{API_ROOT}/competitions/{provider_code}/scorers", api_key, scorer_params
            )
        except requests.RequestException as exc:
            print(f"{code}: scorer summary unavailable ({exc})")
        else:
            scorer_rows = scorers_from_provider(scorers_payload.get("scorers", []))
            scorer_path = save_scorers(code, scorer_rows, season_label(start_year))
    print(f"{code}: saved {len(match_rows)} fixtures to {match_path}")
    if scorer_path:
        print(f"{code}: saved {len(scorer_rows)} season scorer rows to {scorer_path}")
    return match_path, scorer_path


def update_pl_scorers(api_key: str) -> Path:
    start_year = current_season_start_year()
    payload = _get_json(
        f"{API_ROOT}/competitions/PL/scorers",
        api_key,
        {"season": start_year, "limit": 100},
    )
    rows = scorers_from_provider(payload.get("scorers", []))
    path = save_scorers("PL", rows, season_label(start_year))
    print(f"PL: saved {len(rows)} season scorer rows to {path}")
    return path


def update_pl_team_assets(api_key: str) -> Path:
    payload = _get_json(
        f"{API_ROOT}/competitions/PL/matches",
        api_key,
        {"season": current_season_start_year()},
    )
    assets = team_assets_from_provider("PL", payload.get("matches", []))
    path = save_team_assets("PL", assets)
    print(f"PL: saved {len(assets)} club crests")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Update isolated football competition data")
    parser.add_argument(
        "--competition", choices=["all", *ISOLATED_COMPETITIONS], default="all",
        help="Competition code to update (default: all supported competitions)",
    )
    parser.add_argument(
        "--season-start-year", type=int,
        help="Import one historical season only (scorer totals are current-season only)",
    )
    parser.add_argument("--history-start-year", type=int, help="First historical season to import")
    parser.add_argument("--history-end-year", type=int, help="Last historical season to import")
    parser.add_argument("--include-current", action="store_true", help="Also refresh the current season")
    parser.add_argument(
        "--pl-scorers-only", action="store_true",
        help="Refresh Premier League scorer summaries only; does not touch PL match or model files",
    )
    args = parser.parse_args()
    if (args.history_start_year is None) != (args.history_end_year is None):
        parser.error("--history-start-year and --history-end-year must be used together")
    if args.history_start_year is not None and args.history_start_year > args.history_end_year:
        parser.error("--history-start-year must not be after --history-end-year")
    if args.season_start_year is not None and args.history_start_year is not None:
        parser.error("use either --season-start-year or the --history-start-year/--history-end-year range")
    if args.pl_scorers_only and (args.season_start_year is not None or args.history_start_year is not None):
        parser.error("--pl-scorers-only cannot be combined with historical season options")

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not api_key:
        parser.error("FOOTBALL_DATA_API_KEY is missing from .env")

    if args.pl_scorers_only:
        try:
            update_pl_scorers(api_key)
        except requests.RequestException as exc:
            parser.error(f"PL scorer update failed: {exc}")
        return

    codes = list(ISOLATED_COMPETITIONS) if args.competition == "all" else [args.competition]
    if args.season_start_year is not None:
        for code in codes:
            try:
                update_competition(code, api_key, args.season_start_year, include_scorers=False)
            except requests.RequestException as exc:
                print(f"{code}: update failed ({exc})")
        return

    if args.history_start_year is not None:
        for start_year in range(args.history_start_year, args.history_end_year + 1):
            for code in codes:
                try:
                    update_competition(code, api_key, start_year, include_scorers=False)
                except requests.RequestException as exc:
                    print(f"{code} {season_label(start_year)}: history unavailable ({exc})")

    if args.history_start_year is None or args.include_current:
        for code in codes:
            try:
                update_competition(code, api_key)
            except requests.RequestException as exc:
                print(f"{code}: update failed ({exc})")
        if args.competition == "all":
            try:
                update_pl_scorers(api_key)
            except requests.RequestException as exc:
                print(f"PL scorer summary update failed ({exc})")
            try:
                update_pl_team_assets(api_key)
            except requests.RequestException as exc:
                print(f"PL crest update failed ({exc})")


if __name__ == "__main__":
    main()