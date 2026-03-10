"""CLI entrypoint for building a patient-safe MIMIC-CXR manifest."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from .asset_copy import copy_subset_assets
from .config import get_required, load_config, require_keys
from .io_utils import (
    load_annotation_id_set,
    load_metadata,
    write_csv,
    write_jsonl,
    write_lines,
)
from .report_utils import load_report_lookup, load_report_text, select_rationale_sentence
from .sampling import (
    assert_no_subject_leakage,
    assign_row_splits,
    select_subset_rows,
    split_subjects,
    summarize_split_counts,
)
from .stats import compute_manifest_stats, write_stats_json


LOGGER = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "subject_id",
    "study_id",
    "dicom_id",
    "image_path",
    "view_position",
    "report_used",
    "report_text_used",
    "rationale_sentence",
    "has_imagenome_anchor",
    "has_mscxr_lesion",
    "split",
    "usable_flag",
    "labels_chexpert",
    "anatomy",
    "claims_gold",
]


def build_manifest(config_path: str | Path) -> dict[str, str]:
    """Build manifest files, patient-level subject splits, and summary stats."""
    config = load_config(config_path)
    validate_config(config)
    setup_logging(config)

    LOGGER.info("Starting manifest build with config: %s", config_path)
    metadata_rows = load_metadata(config)
    frontal_rows = filter_frontal_rows(metadata_rows, config)
    imagenome_ids = load_annotation_id_set(
        config["io"]["chest_imagenome_annotations"], "Chest ImaGenome"
    )
    mscxr_ids = load_annotation_id_set(config["io"]["mscxr_annotations"], "MS-CXR")

    candidate_rows = [row for row in frontal_rows if row["dicom_id"] in imagenome_ids]
    LOGGER.info(
        "Candidate rows after frontal + MIMIC-ImaGenome intersection filtering: %s",
        len(candidate_rows),
    )
    if not candidate_rows:
        raise ValueError("No candidate rows remain after frontal + ImaGenome intersection.")

    report_lookup = load_report_lookup(config)
    usable_rows = materialize_rows(candidate_rows, imagenome_ids, mscxr_ids, report_lookup, config)
    LOGGER.info("Usable rows after image/report validation: %s", len(usable_rows))
    if not usable_rows:
        raise ValueError("No usable rows remain after validation.")
    LOGGER.info(
        "No Finding target (20-30%) is not enforced yet because labels_chexpert is a placeholder."
    )

    sampled_rows = select_subset_rows(usable_rows, config)
    LOGGER.info("Selected %s rows for the final subset.", len(sampled_rows))

    subject_to_split = split_subjects([row["subject_id"] for row in sampled_rows], config)
    assert_no_subject_leakage(subject_to_split)
    LOGGER.info("Leakage check passed: train/val/test subject sets are disjoint.")

    split_rows = assign_row_splits(sampled_rows, subject_to_split)
    split_rows = sorted(
        split_rows,
        key=lambda row: (
            {"train": 0, "val": 1, "test": 2}[row["split"]],
            row["subject_id"],
            row["study_id"],
            row["dicom_id"],
        ),
    )

    output_paths = write_outputs(split_rows, subject_to_split, config)
    output_paths.update(copy_subset_assets(split_rows, config))
    stats = compute_manifest_stats(split_rows)
    write_stats_json(stats, output_paths["stats_json"])

    split_summary = summarize_split_counts(split_rows)
    for split, summary in split_summary.items():
        LOGGER.info(
            "Split=%s | samples=%s | subjects=%s",
            split,
            summary["samples"],
            summary["subjects"],
        )
    LOGGER.info("Stats written to %s", output_paths["stats_json"])
    return output_paths


def validate_config(config: dict[str, Any]) -> None:
    """Validate the minimum config surface needed by the builder."""
    require_keys(
        config,
        [
            "random_seed",
            "io.metadata_csv",
            "io.mimic_jpg_root",
            "io.reports.mode",
            "io.chest_imagenome_annotations.path",
            "io.chest_imagenome_annotations.format",
            "io.chest_imagenome_annotations.dicom_id_column",
            "io.mscxr_annotations.path",
            "io.mscxr_annotations.format",
            "io.mscxr_annotations.dicom_id_column",
            "columns.metadata.subject_id",
            "columns.metadata.study_id",
            "columns.metadata.dicom_id",
            "columns.metadata.view_position",
            "paths.image_path_template",
            "sampling.allowed_view_positions",
            "sampling.target_images",
            "sampling.subject_split.train",
            "sampling.subject_split.val",
            "sampling.subject_split.test",
            "sampling.min_mscxr_images",
            "reports.prefer_sections",
            "reports.rationale_keywords",
            "validation.require_image_exists",
            "validation.require_non_empty_report",
            "outputs.output_dir",
            "outputs.usable_samples_csv",
            "outputs.usable_samples_jsonl",
            "outputs.claims_gold_jsonl",
            "outputs.stats_json",
            "outputs.subject_split_dir",
        ],
    )

    reports_mode = get_required(config, "io.reports.mode").lower()
    if reports_mode == "directory":
        require_keys(config, ["io.reports.root", "io.reports.path_template"])
    elif reports_mode == "csv":
        require_keys(
            config,
            [
                "io.reports.path",
                "io.reports.study_id_column",
                "io.reports.findings_column",
                "io.reports.impression_column",
            ],
        )
    else:
        raise ValueError("io.reports.mode must be 'directory' or 'csv'")

    if config.get("asset_copy", {}).get("enabled", False):
        require_keys(config, ["asset_copy.output_dir"])


def setup_logging(config: dict[str, Any]) -> None:
    """Initialize INFO logging once for CLI and test runs."""
    level_name = str(config.get("logging", {}).get("level", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
    )


def filter_frontal_rows(rows: list[dict[str, str]], config: dict[str, Any]) -> list[dict[str, str]]:
    """Keep PA/AP rows only."""
    allowed_views = {value.upper() for value in config["sampling"]["allowed_view_positions"]}
    frontal_rows = [row for row in rows if row["view_position"].upper() in allowed_views]
    LOGGER.info(
        "Filtered frontal rows: kept %s / %s using allowed views %s",
        len(frontal_rows),
        len(rows),
        sorted(allowed_views),
    )
    return frontal_rows


def materialize_rows(
    candidate_rows: list[dict[str, str]],
    imagenome_ids: set[str],
    mscxr_ids: set[str],
    report_lookup: dict[str, dict[str, str]] | None,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve file paths, reports, and final row payloads for eligible samples."""
    mimic_root = Path(config["io"]["mimic_jpg_root"])
    image_template = config["paths"]["image_path_template"]
    require_image_exists = bool(config["validation"]["require_image_exists"])
    require_non_empty_report = bool(config["validation"]["require_non_empty_report"])

    usable_rows: list[dict[str, Any]] = []
    skipped_missing_image = 0
    skipped_missing_report = 0
    skipped_empty_report = 0

    for row in candidate_rows:
        image_path = mimic_root / image_template.format(
            subject_id=row["subject_id"],
            subject_id_prefix=str(row["subject_id"])[:2],
            study_id=row["study_id"],
            dicom_id=row["dicom_id"],
        )
        if require_image_exists and not image_path.exists():
            skipped_missing_image += 1
            continue

        try:
            report_used, report_text = load_report_text(config, row, report_lookup)
        except FileNotFoundError:
            skipped_missing_report += 1
            continue

        if require_non_empty_report and not report_text:
            skipped_empty_report += 1
            continue

        rationale_sentence = select_rationale_sentence(report_text, config)
        usable_rows.append(
            {
                "subject_id": row["subject_id"],
                "study_id": row["study_id"],
                "dicom_id": row["dicom_id"],
                "image_path": str(image_path),
                "view_position": row["view_position"].upper(),
                "report_used": report_used,
                "report_text_used": report_text,
                "rationale_sentence": rationale_sentence,
                "has_imagenome_anchor": 1 if row["dicom_id"] in imagenome_ids else 0,
                "has_mscxr_lesion": 1 if row["dicom_id"] in mscxr_ids else 0,
                "split": "",
                "usable_flag": 1,
                "labels_chexpert": "{}",
                "anatomy": "[]",
                "claims_gold": "[]",
            }
        )

    LOGGER.info("Skipped %s rows because image file was missing.", skipped_missing_image)
    LOGGER.info("Skipped %s rows because report file was missing.", skipped_missing_report)
    LOGGER.info("Skipped %s rows because report text was empty.", skipped_empty_report)
    return usable_rows


def write_outputs(
    rows: list[dict[str, Any]],
    subject_to_split: dict[str, str],
    config: dict[str, Any],
) -> dict[str, str]:
    """Write CSV/JSONL manifests, claims stubs, and subject split files."""
    output_dir = Path(config["outputs"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    subject_split_dir = output_dir / config["outputs"]["subject_split_dir"]
    subject_split_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / config["outputs"]["usable_samples_csv"]
    jsonl_path = output_dir / config["outputs"]["usable_samples_jsonl"]
    claims_path = output_dir / config["outputs"]["claims_gold_jsonl"]
    stats_path = output_dir / config["outputs"]["stats_json"]

    write_csv(csv_path, rows, OUTPUT_COLUMNS)
    write_jsonl(jsonl_path, rows)

    claim_rows = [
        {
            "subject_id": row["subject_id"],
            "study_id": row["study_id"],
            "dicom_id": row["dicom_id"],
            "split": row["split"],
            "claims": [],
        }
        for row in rows
    ]
    write_jsonl(claims_path, claim_rows)

    split_to_subjects = {"train": [], "val": [], "test": []}
    for subject_id, split in sorted(subject_to_split.items()):
        split_to_subjects[split].append(subject_id)

    write_lines(subject_split_dir / "train_subjects.txt", split_to_subjects["train"])
    write_lines(subject_split_dir / "val_subjects.txt", split_to_subjects["val"])
    write_lines(subject_split_dir / "test_subjects.txt", split_to_subjects["test"])

    return {
        "usable_samples_csv": str(csv_path),
        "usable_samples_jsonl": str(jsonl_path),
        "claims_gold_jsonl": str(claims_path),
        "stats_json": str(stats_path),
        "train_subjects": str(subject_split_dir / "train_subjects.txt"),
        "val_subjects": str(subject_split_dir / "val_subjects.txt"),
        "test_subjects": str(subject_split_dir / "test_subjects.txt"),
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to configs/config.yaml")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    output_paths = build_manifest(args.config)
    print(json.dumps(output_paths, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
