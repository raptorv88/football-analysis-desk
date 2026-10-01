from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import html
import re
import time
import xml.etree.ElementTree as ET

import requests

from app import data
from app import predict
from app import competition_data
from app.competition_predict import model_available, predict_fixture as predict_competition_fixture
from app.prediction_history import prediction_for

app = FastAPI(title="PL Match Predictor API")

NEWS_FEEDS = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/premier-league/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/football/premierleague/rss"),
    ("Sky Sports", "https://www.skysports.com/rss/12040"),
]
TEAM_LOGOS = {
    "Arsenal FC": "359", "Aston Villa FC": "362", "AFC Bournemouth": "8678",
    "Brentford FC": "337", "Brighton & Hove Albion FC": "397", "Burnley FC": "379",
    "Chelsea FC": "363", "Crystal Palace FC": "384", "Everton FC": "368",
    "Fulham FC": "370", "Leeds United FC": "357", "Liverpool FC": "364",
    "Manchester City FC": "382", "Manchester United FC": "360", "Newcastle United FC": "361",
    "Nottingham Forest FC": "393", "Sunderland AFC": "366", "Tottenham Hotspur FC": "367",
    "Ipswich Town FC": "373", "Hull City AFC": "306", "Coventry City FC": "388", "Cardiff City FC": "347",
    "West Ham United FC": "371", "Wolverhampton Wanderers FC": "380",
}
_news_cache = {"expires": 0.0, "items": []}
FEATURED_CHAMPIONS_LEAGUE_CLUBS = {
    "arsenal fc", "bayer 04 leverkusen", "borussia dortmund", "chelsea fc",
    "club atlético de madrid", "fc barcelona", "fc bayern münchen",
    "fc internazionale milano", "fc porto", "juventus fc", "liverpool fc",
    "manchester city fc", "manchester united fc", "paris saint-germain fc",
    "real madrid cf", "rb leipzig", "sl benfica", "sporting clube de portugal",
    "ssc napoli", "tottenham hotspur fc", "villarreal cf", "galatasaray sk",
}


def featured_champions_league_fixtures(fixtures: list[dict], limit: int) -> list[dict]:
    def prominence(fixture: dict) -> int:
        return sum(
            team.casefold() in FEATURED_CHAMPIONS_LEAGUE_CLUBS
            for team in (fixture["home_team"], fixture["away_team"])
        )

    ranked = sorted(
        fixtures,
        key=lambda fixture: (
            -prominence(fixture), fixture["date"], fixture["home_team"], fixture["away_team"]
        ),
    )
    selected = ranked[:limit]
    return sorted(selected, key=lambda fixture: fixture["date"])

# Allow the basic HTML/JS frontend (served from anywhere/file://) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "matches_loaded": len(data.MATCHES)}


@app.get("/api/seasons")
def seasons():
    return data.list_seasons()


def _competition_or_404(code: str) -> str:
    try:
        return competition_data.competition_code(code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/competitions")
def competitions():
    result = []
    for code, config in competition_data.COMPETITIONS.items():
        if code == "PL":
            seasons = data.list_seasons()
            result.append({
                "code": code,
                "name": config["name"],
                "format": config["format"],
                "seasons": seasons,
                "fixtures_loaded": len(data.MATCHES),
                "model_available": True,
            })
            continue
        matches = competition_data.load_matches(code)
        result.append({
            "code": code,
            "name": config["name"],
            "format": config["format"],
            "seasons": sorted(matches["season"].dropna().unique().tolist()),
            "fixtures_loaded": len(matches),
            "model_available": model_available(code),
        })
    return result


@app.get("/api/competitions/{code}/seasons")
def competition_seasons(code: str):
    code = _competition_or_404(code)
    return data.list_seasons() if code == "PL" else competition_data.list_seasons(code)


@app.get("/api/competitions/{code}/table")
def competition_table(code: str, season: str | None = None):
    code = _competition_or_404(code)
    seasons = data.list_seasons() if code == "PL" else competition_data.list_seasons(code)
    season = season or (seasons or [None])[-1]
    if season is None:
        return []
    return data.league_table(season) if code == "PL" else competition_data.league_table(code, season)


@app.get("/api/competitions/{code}/upcoming")
def competition_upcoming(code: str, limit: int = 10):
    code = _competition_or_404(code)
    if code == "PL":
        fixtures = data.upcoming_fixtures(max(1, min(limit, 50)))
        return [
            {**fixture, "fixture_id": None, "stage": "REGULAR_SEASON", "group": None,
             "date": fixture["date"].isoformat()}
            for fixture in fixtures
        ]
    fixtures = competition_data.upcoming_fixtures(code, max(1, min(limit, 50)))
    return [{**fixture, "date": fixture["date"].isoformat()} for fixture in fixtures]


@app.get("/api/competitions/{code}/scorers")
def competition_scorers(code: str, season: str | None = None, team: str | None = None, limit: int = 20):
    code = _competition_or_404(code)
    seasons = data.list_seasons() if code == "PL" else competition_data.list_seasons(code)
    season = season or (seasons or [None])[-1]
    scorers = competition_data.load_scorers(code, season)
    if team:
        scorers = scorers[scorers["team"] == team]
    scorers = scorers.sort_values(["goals", "assists", "player"], ascending=[False, False, True], na_position="last")
    records = scorers.head(max(1, min(limit, 100))).fillna("").to_dict("records")
    return {"competition": code, "season": season, "scope": "season_totals", "players": records}


@app.get("/api/competitions/{code}/predictions/upcoming")
def competition_predictions_upcoming(code: str, limit: int = 8):
    code = _competition_or_404(code)
    if code == "PL":
        fixtures = data.upcoming_fixtures(max(1, min(limit, 50)))
        predictions = []
        for fixture in fixtures:
            try:
                prediction = predict.predict_fixture(
                    data.MATCHES, fixture["home_team"], fixture["away_team"],
                    fixture_date=fixture["date"], include_explanation=False,
                )
            except Exception:
                continue
            predictions.append({
                **prediction,
                "fixture_id": None,
                "date": fixture["date"].isoformat(),
                "matchday": fixture["matchday"],
                "stage": "REGULAR_SEASON",
            })
        return predictions
    if not model_available(code):
        raise HTTPException(
            status_code=409,
            detail=f"No isolated model is trained for {code}; run python -m training.train_competition_models --competition {code}",
        )
    matches = competition_data.load_matches(code, finished_only=True)
    fixtures = competition_data.upcoming_fixtures(code, max(1, min(limit, 50)))
    predictions = []
    for fixture in fixtures:
        try:
            prediction = predict_competition_fixture(
                code, matches, fixture["home_team"], fixture["away_team"], fixture["date"]
            )
        except ValueError:
            continue
        predictions.append({
            **prediction,
            "fixture_id": fixture["fixture_id"],
            "date": fixture["date"].isoformat(),
            "matchday": fixture["matchday"],
            "stage": fixture["stage"],
        })
    return predictions


@app.get("/api/teams/{team}/scorers")
def premier_league_team_scorers(team: str, season: str | None = None, limit: int = 10):
    season = season or (data.list_seasons() or [None])[-1]
    scorers = competition_data.load_scorers("PL", season)
    scorers = scorers[scorers["team"] == team]
    scorers = scorers.sort_values(
        ["goals", "assists", "player"], ascending=[False, False, True], na_position="last"
    )
    players = scorers.head(max(1, min(limit, 50))).fillna("").to_dict("records")
    return {"team": team, "season": season, "scope": "season_totals", "players": players}


@app.get("/api/overview/upcoming")
def overview_upcoming(limit: int = 12):
    limit = max(1, min(limit, 50))
    fixtures = []
    featured_codes = ("PL", "CL")
    per_competition_limit = max(1, (limit + len(featured_codes) - 1) // len(featured_codes))
    for code in featured_codes:
        config = competition_data.COMPETITIONS[code]
        if code == "PL":
            upcoming = data.upcoming_fixtures(per_competition_limit)
        elif code == "CL":
            candidates = competition_data.upcoming_fixtures(code, 50)
            upcoming = featured_champions_league_fixtures(candidates, per_competition_limit)
        else:
            upcoming = competition_data.upcoming_fixtures(code, per_competition_limit)
        fixtures.extend({
            **fixture,
            "competition": code,
            "competition_name": config["name"],
            "date": fixture["date"].isoformat(),
        } for fixture in upcoming)
    fixtures.sort(key=lambda fixture: fixture["date"])
    return fixtures[:limit]


@app.get("/api/model-info")
def model_info():
    root = Path(__file__).parent.parent
    def load_json(path: Path):
        return json.loads(path.read_text()) if path.exists() else None

    return {
        "data": load_json(root / "data" / "data_metadata.json"),
        "model": load_json(root / "models" / "model_metadata.json"),
        "selection": load_json(root / "models" / "model_selection.json"),
    }


def _clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    return re.sub(r"<[^>]+>", "", text).strip()


def _image_from_item(item) -> str | None:
    for element in item.iter():
        tag = element.tag.lower()
        url = element.attrib.get("url") or element.text
        if url and ("thumbnail" in tag or "content" in tag or tag.endswith("enclosure")):
            if any(ext in url.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", "image")):
                return url
    return None


@app.get("/api/news")
def news(limit: int = 6):
    """Return cached latest Premier League headlines from public RSS feeds."""
    now = time.time()
    if _news_cache["expires"] > now:
        return _news_cache["items"][:limit]

    collected = []
    for source, url in NEWS_FEEDS:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "PL-Match-Predictor/1.0"},
                timeout=8,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            items = []
            for item in root.findall(".//item")[:10]:
                title = _clean_text(item.findtext("title"))
                link = item.findtext("link") or ""
                published = item.findtext("pubDate") or item.findtext("published") or ""
                description = _clean_text(item.findtext("description"))
                if title and link:
                    items.append({
                        "source": source,
                        "title": title,
                        "url": link,
                        "published": published,
                        "summary": description[:180],
                        "image": _image_from_item(item),
                        "x_search": "https://x.com/search?q=" + requests.utils.quote(title + " Premier League") + "&src=typed_query",
                    })
            collected.extend(items)
        except (requests.RequestException, ET.ParseError):
            continue
    unique = {}
    for item in collected:
        unique.setdefault(item["url"], item)
    items = list(unique.values())
    items.sort(key=lambda item: item["published"], reverse=True)
    if items:
        _news_cache.update({"expires": now + 600, "items": items})
    return items[:limit]


@app.get("/api/table/{season:path}")
def table(season: str, league: str = "PL"):
    result = data.league_table(season)
    if not result:
        raise HTTPException(status_code=404, detail=f"No data for season '{season}' in {league}")
    return result


@app.get("/api/teams")
def teams(league: str = "PL"):
    return data.list_teams()


@app.get("/api/team-assets")
def team_assets(league: str = "PL"):
    official = {"AFC Bournemouth": "https://resources.premierleague.com/premierleague/badges/50/t91.png"}
    assets = {
        team: {
            "logo": official.get(team) or (f"https://a.espncdn.com/i/teamlogos/soccer/500/{TEAM_LOGOS[team]}.png" if team in TEAM_LOGOS else None),
            "initials": "".join(part[0] for part in team.replace("&", "").split() if part)[:3].upper(),
        }
        for team in data.list_teams()
    }
    for code in competition_data.COMPETITIONS:
        for team, logo in competition_data.load_team_assets(code).items():
            if team not in assets:
                assets[team] = {
                    "logo": logo,
                    "initials": "".join(part[0] for part in team.replace("&", "").split() if part)[:3].upper(),
                }
            elif not assets[team]["logo"]:
                assets[team]["logo"] = logo
    return assets


@app.get("/api/teams/{team}/stats")
def stats_for_team(team: str, season: str | None = None, league: str = "PL"):
    result = data.team_stats(team, season)
    if result is None:
        detail = f"No data for team '{team}'" + (f" in season '{season}'" if season else "")
        raise HTTPException(status_code=404, detail=detail)
    return result


@app.get("/api/teams/{team}/profile")
def profile_for_team(team: str, season: str | None = None, league: str = "PL"):
    result = data.team_profile(team, season)
    if result is None:
        detail = f"No profile data for team '{team}'" + (f" in season '{season}'" if season else "")
        raise HTTPException(status_code=404, detail=detail)
    return result


@app.get("/api/predict")
def predict_matchup(home: str, away: str, league: str = "PL"):
    known_teams = data.list_teams()
    if home not in known_teams or away not in known_teams:
        raise HTTPException(status_code=404, detail="Unknown team name(s) — see /api/teams for valid names")
    return predict.predict_fixture(data.MATCHES, home, away)


@app.get("/api/predictions/upcoming")
def predictions_upcoming(limit: int = 10, league: str = "PL"):
    fixtures = data.upcoming_fixtures(limit)
    results = []
    for fx in fixtures:
        try:
            pred = predict.predict_fixture(
                data.MATCHES, fx["home_team"], fx["away_team"],
                fixture_date=fx["date"], include_explanation=False
            )
        except Exception:
            continue  # skip fixtures involving teams with no history (e.g. data gaps)
        pred["date"] = fx["date"].isoformat()
        pred["matchday"] = fx["matchday"]
        results.append(pred)
    return results


@app.get("/api/upcoming")
def upcoming(limit: int = 4, league: str = "PL"):
    return [
        {
            **fixture,
            "date": fixture["date"].isoformat(),
        }
        for fixture in data.upcoming_fixtures(limit)
    ]


@app.get("/api/live")
def live(league: str = "PL"):
    fixtures = data.live_fixtures()
    for fixture in fixtures:
        fixture["prediction"] = prediction_for(
            fixture["date"], fixture["home_team"], fixture["away_team"]
        )
    return fixtures


@app.get("/api/predictions/history")
def prediction_history(league: str = "PL"):
    from app.prediction_history import load_history
    return list(load_history().values())


@app.get("/api/live/status")
def live_status(league: str = "PL"):
    return data.current_feed_status()


@app.get("/api/results/recent")
def recent_results(days: int = 7, league: str = "PL"):
    """Return finished matches from the last `days` days with archived predictions."""
    import pandas as pd
    from datetime import datetime, timedelta, timezone
    from app.prediction_history import load_history, fixture_key
    from app.data import DATA_DIR

    current = pd.read_csv(DATA_DIR / "premier_league_matches.csv")
    current["status"] = current["status"].astype(str).str.upper()
    finished = current[current["status"] == "FINISHED"].copy()
    if finished.empty:
        return []

    finished["date"] = pd.to_datetime(finished["date"], utc=True, errors="coerce")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = finished[finished["date"] >= cutoff].sort_values("date", ascending=False)

    history = load_history()

    def _result(row):
        if row["home_goals"] > row["away_goals"]:
            return "HOME_WIN"
        elif row["home_goals"] < row["away_goals"]:
            return "AWAY_WIN"
        return "DRAW"

    results = []
    for _, row in recent.iterrows():
        home_goals = int(pd.to_numeric(row.get("home_goals"), errors="coerce") or 0)
        away_goals = int(pd.to_numeric(row.get("away_goals"), errors="coerce") or 0)
        actual = _result({"home_goals": home_goals, "away_goals": away_goals})
        key = fixture_key(row["date"], row["home_team"], row["away_team"])
        prediction = history.get(key)
        correct = prediction is not None and prediction["predicted_result"] == actual
        results.append({
            "date": row["date"].isoformat(),
            "matchday": row.get("matchday"),
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "home_goals": home_goals,
            "away_goals": away_goals,
            "actual_result": actual,
            "prediction": prediction,
            "correct": correct if prediction else None,
        })
    return results


# Serve the basic HTML/JS frontend from /frontend at the site root
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
from fastapi.responses import FileResponse

@app.get("/")
def serve_root():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

