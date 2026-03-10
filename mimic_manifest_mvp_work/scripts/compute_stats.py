"""Recompute basic manifest statistics from a built CSV manifest."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from data.stats import compute_manifest_stats, write_stats_json


def parse_args() -> argparse.Namespace:
    """Parse CLI args for stats recomputation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to usable_samples.csv")
    parser.add_argument("--output", required=True, help="Path to stats.json")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    manifest_path = Path(args.manifest)
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    stats = compute_manifest_stats(rows)
    write_stats_json(stats, args.output)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
