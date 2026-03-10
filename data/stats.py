"""Statistics helpers for manifest inspection."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


def compute_manifest_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute high-signal summary statistics for the current manifest."""
    total = len(rows)
    if total == 0:
        return {
            "total_samples": 0,
            "category_distribution_placeholder": {},
            "no_finding_ratio": None,
            "has_imagenome_anchor_ratio": 0.0,
            "has_mscxr_lesion_ratio": 0.0,
            "frontal_ratio": 0.0,
            "split_counts": {},
        }

    no_finding_ratio = None
    if any(str(row.get("labels_chexpert", "")).strip() not in ("", "{}", "[]") for row in rows):
        no_finding_values = []
        for row in rows:
            value = str(row.get("labels_chexpert", ""))
            no_finding_values.append('"No Finding": 1' in value or '"No Finding": true' in value.lower())
        no_finding_ratio = sum(no_finding_values) / total
    else:
        LOGGER.info(
            "No Finding ratio is a placeholder because labels_chexpert is empty for all rows."
        )

    split_counts: dict[str, int] = {}
    for split in ("train", "val", "test"):
        split_counts[split] = sum(1 for row in rows if row["split"] == split)

    return {
        "total_samples": total,
        "category_distribution_placeholder": {},
        "no_finding_ratio": no_finding_ratio,
        "has_imagenome_anchor_ratio": sum(int(row["has_imagenome_anchor"]) for row in rows) / total,
        "has_mscxr_lesion_ratio": sum(int(row["has_mscxr_lesion"]) for row in rows) / total,
        "frontal_ratio": sum(1 for row in rows if row["view_position"] in {"PA", "AP"}) / total,
        "split_counts": split_counts,
    }


def write_stats_json(stats: dict[str, Any], output_path: str | Path) -> Path:
    """Persist computed manifest statistics as JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
