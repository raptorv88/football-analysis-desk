import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data import load_matches

matches = load_matches()

print("Total finished matches:", len(matches))
print("\nMatches per season:")
print(matches["season"].value_counts().sort_index())

print("\nMissing values:")
print(matches.isna().sum())

print("\nDuplicate rows:", matches.duplicated().sum())

print("\nDate range:")
print(matches["date"].min(), "to", matches["date"].max())

print("\nResult distribution:")
print(matches["result"].value_counts())

print("\nTeams:")
print(sorted(set(matches["home_team"]) | set(matches["away_team"])))
