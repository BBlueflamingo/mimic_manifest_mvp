"""Sampling, patient-level split, and leakage checks."""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from typing import Any


LOGGER = logging.getLogger(__name__)


class LeakageError(RuntimeError):
    """Raised when subject leakage is detected between splits."""


def group_rows_by_subject(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group sample rows by subject_id."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["subject_id"])].append(row)
    return dict(grouped)


def select_subset_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Select a deterministic target-sized subset while preferring MS-CXR-aligned rows."""
    target_images = int(config["sampling"]["target_images"])
    min_mscxr_images = int(config["sampling"]["min_mscxr_images"])
    rng = random.Random(int(config["random_seed"]))

    if len(rows) <= target_images:
        LOGGER.info(
            "Candidate set has %s rows, below target %s. Using all rows.",
            len(rows),
            target_images,
        )
        return sorted_rows(rows)

    positive_rows = [row for row in rows if int(row["has_mscxr_lesion"]) == 1]
    negative_rows = [row for row in rows if int(row["has_mscxr_lesion"]) == 0]
    rng.shuffle(positive_rows)
    rng.shuffle(negative_rows)

    selected: list[dict[str, Any]] = []
    positive_target = min(min_mscxr_images, len(positive_rows), target_images)
    selected.extend(positive_rows[:positive_target])
    remaining_slots = target_images - len(selected)

    if len(positive_rows) < min_mscxr_images:
        LOGGER.info(
            "MS-CXR aligned rows available: %s, below requested minimum %s. "
            "Using all available positives.",
            len(positive_rows),
            min_mscxr_images,
        )
    else:
        LOGGER.info("Reserved %s MS-CXR aligned rows before filling remaining slots.", positive_target)

    pool = positive_rows[positive_target:] + negative_rows
    rng.shuffle(pool)
    selected.extend(pool[:remaining_slots])
    return sorted_rows(selected)


def sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows sorted deterministically by identifiers."""
    return sorted(
        rows,
        key=lambda row: (
            str(row["subject_id"]),
            str(row["study_id"]),
            str(row["dicom_id"]),
        ),
    )


def split_subjects(subject_ids: list[str], config: dict[str, Any]) -> dict[str, str]:
    """Create reproducible patient-level train/val/test assignments."""
    rng = random.Random(int(config["random_seed"]))
    ordered_subjects = sorted({str(subject_id) for subject_id in subject_ids})
    rng.shuffle(ordered_subjects)
    total_subjects = len(ordered_subjects)
    if total_subjects == 0:
        raise ValueError("No subjects available for splitting.")

    train_ratio = float(config["sampling"]["subject_split"]["train"])
    val_ratio = float(config["sampling"]["subject_split"]["val"])
    test_ratio = float(config["sampling"]["subject_split"]["test"])
    if round(train_ratio + val_ratio + test_ratio, 6) != 1.0:
        raise ValueError("Subject split ratios must sum to 1.0")

    train_count = int(total_subjects * train_ratio)
    val_count = int(total_subjects * val_ratio)
    test_count = total_subjects - train_count - val_count

    if total_subjects >= 3:
        if val_count == 0:
            val_count = 1
            train_count = max(train_count - 1, 1)
            test_count = total_subjects - train_count - val_count
        if test_count == 0:
            test_count = 1
            train_count = max(train_count - 1, 1)
            val_count = total_subjects - train_count - test_count

    train_subjects = ordered_subjects[:train_count]
    val_subjects = ordered_subjects[train_count : train_count + val_count]
    test_subjects = ordered_subjects[train_count + val_count :]

    subject_to_split = {subject_id: "train" for subject_id in train_subjects}
    subject_to_split.update({subject_id: "val" for subject_id in val_subjects})
    subject_to_split.update({subject_id: "test" for subject_id in test_subjects})
    return subject_to_split


def assert_no_subject_leakage(subject_to_split: dict[str, str]) -> None:
    """Ensure each split owns a disjoint set of subject_ids."""
    split_to_subjects: dict[str, set[str]] = defaultdict(set)
    for subject_id, split in subject_to_split.items():
        split_to_subjects[split].add(subject_id)

    train_subjects = split_to_subjects.get("train", set())
    val_subjects = split_to_subjects.get("val", set())
    test_subjects = split_to_subjects.get("test", set())

    intersections = {
        "train_val": train_subjects & val_subjects,
        "train_test": train_subjects & test_subjects,
        "val_test": val_subjects & test_subjects,
    }
    leaked = {name: values for name, values in intersections.items() if values}
    if leaked:
        raise LeakageError(f"Subject leakage detected across splits: {leaked}")


def assign_row_splits(
    rows: list[dict[str, Any]], subject_to_split: dict[str, str]
) -> list[dict[str, Any]]:
    """Attach split labels to each row using subject-level assignments."""
    assigned_rows: list[dict[str, Any]] = []
    for row in rows:
        subject_id = str(row["subject_id"])
        if subject_id not in subject_to_split:
            raise KeyError(f"Missing split assignment for subject_id={subject_id}")
        enriched = dict(row)
        enriched["split"] = subject_to_split[subject_id]
        assigned_rows.append(enriched)
    return assigned_rows


def summarize_split_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Return sample and subject counts per split for logging and stats."""
    summary: dict[str, dict[str, int]] = {}
    grouped = group_rows_by_subject(rows)
    for split in ("train", "val", "test"):
        split_rows = [row for row in rows if row["split"] == split]
        split_subjects = {subject_id for subject_id, items in grouped.items() if items[0]["split"] == split}
        summary[split] = {
            "samples": len(split_rows),
            "subjects": len(split_subjects),
        }
    return summary
