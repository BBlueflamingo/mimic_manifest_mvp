"""Acceptance tests for the manifest builder MVP."""

from __future__ import annotations

import csv
from pathlib import Path

from data.build_manifest import OUTPUT_COLUMNS, build_manifest


def read_subjects(path: str | Path) -> set[str]:
    """Read a subject split file into a set."""
    values = Path(path).read_text(encoding="utf-8").splitlines()
    return {value.strip() for value in values if value.strip()}


def read_manifest_rows(path: str | Path) -> list[dict[str, str]]:
    """Load the generated CSV manifest."""
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_no_subject_leakage(synthetic_config: Path) -> None:
    """train/val/test subject sets must be pairwise disjoint."""
    outputs = build_manifest(synthetic_config)
    train_subjects = read_subjects(outputs["train_subjects"])
    val_subjects = read_subjects(outputs["val_subjects"])
    test_subjects = read_subjects(outputs["test_subjects"])

    assert train_subjects.isdisjoint(val_subjects)
    assert train_subjects.isdisjoint(test_subjects)
    assert val_subjects.isdisjoint(test_subjects)


def test_split_reproducible(synthetic_config: Path) -> None:
    """The same config+seed must reproduce identical subject split files."""
    first_outputs = build_manifest(synthetic_config)
    first_train = Path(first_outputs["train_subjects"]).read_text(encoding="utf-8")
    first_val = Path(first_outputs["val_subjects"]).read_text(encoding="utf-8")
    first_test = Path(first_outputs["test_subjects"]).read_text(encoding="utf-8")

    second_outputs = build_manifest(synthetic_config)
    second_train = Path(second_outputs["train_subjects"]).read_text(encoding="utf-8")
    second_val = Path(second_outputs["val_subjects"]).read_text(encoding="utf-8")
    second_test = Path(second_outputs["test_subjects"]).read_text(encoding="utf-8")

    assert first_train == second_train
    assert first_val == second_val
    assert first_test == second_test


def test_row_split_matches_subject(synthetic_config: Path) -> None:
    """Each row split must match the split assigned to its subject_id."""
    outputs = build_manifest(synthetic_config)
    rows = read_manifest_rows(outputs["usable_samples_csv"])
    subject_to_split = {}
    for split_name, key in (
        ("train", "train_subjects"),
        ("val", "val_subjects"),
        ("test", "test_subjects"),
    ):
        for subject_id in read_subjects(outputs[key]):
            subject_to_split[subject_id] = split_name

    assert rows
    for row in rows:
        assert row["subject_id"] in subject_to_split
        assert row["split"] == subject_to_split[row["subject_id"]]


def test_required_columns_present(synthetic_config: Path) -> None:
    """The generated manifest must contain the full required schema."""
    outputs = build_manifest(synthetic_config)
    rows = read_manifest_rows(outputs["usable_samples_csv"])

    assert rows
    assert set(OUTPUT_COLUMNS).issubset(rows[0].keys())


def test_copied_subset_present(synthetic_config: Path) -> None:
    """Copied subset directories must be created when asset_copy is enabled."""
    outputs = build_manifest(synthetic_config)
    copied_subset_dir = Path(outputs["copied_subset_dir"])

    assert copied_subset_dir.exists()
    assert any((copied_subset_dir / split / "images").exists() for split in ("train", "val", "test"))
    assert any((copied_subset_dir / split / "reports").exists() for split in ("train", "val", "test"))
