"""Refresh the committed data provenance summary.

Run after importing or updating match data:
    python -m scripts.write_data_metadata
"""

from pathlib import Path

from app.data import load_matches
from app.metadata import build_data_metadata, write_json


def main() -> None:
    output = Path(__file__).parent.parent / "data" / "data_metadata.json"
    metadata = build_data_metadata(load_matches())
    write_json(output, metadata)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
