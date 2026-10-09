import glob
import json
import os
from pathlib import Path
import time
import unicodedata
import pandas as pd
import requests

def norm(s):
    if not s or not isinstance(s, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "player_photos_cache.json"

cache = {}
if CACHE_FILE.exists():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}

# Gather all top scorers across all CSVs
all_players = set()
for path in glob.glob(str(DATA_DIR / "competitions" / "*_scorers_*.csv")):
    try:
        df = pd.read_csv(path)
        if "player" in df.columns:
            # Take top 35 from each competition
            names = df["player"].dropna().head(35).tolist()
            all_players.update(names)
    except Exception as e:
        print(f"Error reading {path}: {e}")

print(f"Total top scorers to ensure cached: {len(all_players)}")

headers = {"User-Agent": "Mozilla/5.0"}
resolved_count = 0

for name in sorted(all_players):
    clean_name = norm(name)
    if clean_name in cache and cache[clean_name]:
        continue
    
    # Try searching via FotMob
    try:
        search_query = unicodedata.normalize("NFKD", name)
        search_query = "".join(c for c in search_query if not unicodedata.combining(c)).strip()
        r = requests.get(f"https://apigw.fotmob.com/searchapi/suggest?term={search_query}", headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            squad = data.get("squadMemberSuggest") or []
            found_img = None
            if squad and squad[0].get("options"):
                for opt in squad[0]["options"][:3]:
                    payload = opt.get("payload") or {}
                    pid = payload.get("id")
                    if pid:
                        found_img = f"https://images.fotmob.com/image_resources/playerimages/{pid}.png"
                        break
            if found_img:
                cache[clean_name] = found_img
                cache[name.lower().strip()] = found_img
                cache[name.strip()] = found_img
                resolved_count += 1
                safe_name = name.encode("ascii", "replace").decode("ascii")
                print(f"Cached: {safe_name} -> {found_img}")
        time.sleep(0.04)
    except Exception as e:
        safe_name = name.encode("ascii", "replace").decode("ascii")
        print(f"Error {safe_name}: {e}")

    if resolved_count % 10 == 0:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache, f, indent=2, ensure_ascii=False)

print(f"Done! Newly resolved: {resolved_count}, total cached: {len(cache)}")

