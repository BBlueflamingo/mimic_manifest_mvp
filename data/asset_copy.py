"""Helpers for copying the finalized subset assets to a new directory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from .config import get_required
from .report_utils import resolve_report_path


LOGGER = logging.getLogger(__name__)


def copy_subset_assets(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, str]:
    """Copy selected images and txt reports into a compact subset directory."""
    asset_copy_config = config.get("asset_copy", {})
    if not asset_copy_config.get("enabled", False):
        LOGGER.info("Subset asset copying is disabled.")
        return {}

    output_dir = Path(get_required(config, "asset_copy.output_dir"))
    copy_images = bool(asset_copy_config.get("copy_images", True))
    copy_reports = bool(asset_copy_config.get("copy_reports", True))
    mimic_root = Path(get_required(config, "io.mimic_jpg_root"))

    output_dir.mkdir(parents=True, exist_ok=True)
    copied_images = 0
    copied_reports = 0

    for row in rows:
        split = row["split"]
        if copy_images:
            source_image = Path(row["image_path"])
            image_relative = make_relative_path(source_image, mimic_root)
            target_image = output_dir / split / "images" / image_relative
            target_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_image, target_image)
            copied_images += 1

        if copy_reports:
            source_report = resolve_report_path(config, row)
            if source_report is None:
                raise ValueError(
                    "asset_copy.copy_reports=True requires io.reports.mode='directory' with txt files."
                )
            report_root = Path(get_required(config, "io.reports.root"))
            report_relative = make_relative_path(source_report, report_root)
            target_report = output_dir / split / "reports" / report_relative
            target_report.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_report, target_report)
            copied_reports += 1

    LOGGER.info("Copied %s images into %s", copied_images, output_dir)
    if copy_reports:
        LOGGER.info("Copied %s txt reports into %s", copied_reports, output_dir)

    return {
        "copied_subset_dir": str(output_dir),
    }


def make_relative_path(source_path: Path, root_path: Path) -> Path:
    """Return a stable relative path if possible, otherwise fall back to the filename."""
    try:
        return source_path.relative_to(root_path)
    except ValueError:
        return Path(source_path.name)
