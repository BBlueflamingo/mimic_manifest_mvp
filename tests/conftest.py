"""Synthetic dataset fixtures for manifest builder tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


@pytest.fixture()
def synthetic_config(tmp_path: Path) -> Path:
    """Create a small synthetic MIMIC-style dataset and return a config path."""
    images_root = tmp_path / "mimic_jpg"
    reports_root = tmp_path / "reports"
    images_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    metadata_rows = []
    imagenome_rows = []
    mscxr_rows = []

    dicom_counter = 1
    for subject_index in range(10):
        subject_id = f"{12000000 + subject_index}"
        study_id = f"{53000000 + subject_index}"
        for _ in range(2):
            dicom_id = f"d{dicom_counter:04d}"
            dicom_counter += 1
            image_relative = Path(
                f"p{subject_id[:2]}/p{subject_id}/s{study_id}/{dicom_id}.jpg"
            )
            report_relative = Path(f"p{subject_id[:2]}/p{subject_id}/s{study_id}.txt")
            (images_root / image_relative).parent.mkdir(parents=True, exist_ok=True)
            (images_root / image_relative).write_bytes(b"fakejpg")
            (reports_root / report_relative).parent.mkdir(parents=True, exist_ok=True)
            report_text = (
                "FINDINGS: Mild bibasal atelectasis. No pleural effusion. "
                "IMPRESSION: Stable chest radiograph."
            )
            (reports_root / report_relative).write_text(report_text, encoding="utf-8")
            metadata_rows.append(
                {
                    "subject_id": subject_id,
                    "study_id": study_id,
                    "dicom_id": dicom_id,
                    "ViewPosition": "PA",
                }
            )
            imagenome_rows.append({"dicom_id": dicom_id})
            if subject_index < 4:
                mscxr_rows.append({"dicom_id": dicom_id})

    metadata_path = tmp_path / "metadata.csv"
    imagenome_path = tmp_path / "imagenome.csv"
    mscxr_path = tmp_path / "mscxr.csv"

    for path, rows in (
        (metadata_path, metadata_rows),
        (imagenome_path, imagenome_rows),
        (mscxr_path, mscxr_rows),
    ):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    config = {
        "random_seed": 20260310,
        "io": {
            "metadata_csv": str(metadata_path),
            "mimic_jpg_root": str(images_root),
            "reports": {
                "mode": "directory",
                "root": str(reports_root),
                "path_template": "p{subject_id_prefix}/p{subject_id}/s{study_id}.txt",
            },
            "chest_imagenome_annotations": {
                "path": str(imagenome_path),
                "format": "csv",
                "dicom_id_column": "dicom_id",
            },
            "mscxr_annotations": {
                "path": str(mscxr_path),
                "format": "csv",
                "dicom_id_column": "dicom_id",
            },
        },
        "columns": {
            "metadata": {
                "subject_id": "subject_id",
                "study_id": "study_id",
                "dicom_id": "dicom_id",
                "view_position": "ViewPosition",
            }
        },
        "paths": {
            "image_path_template": "p{subject_id_prefix}/p{subject_id}/s{study_id}/{dicom_id}.jpg"
        },
        "sampling": {
            "allowed_view_positions": ["PA", "AP"],
            "target_images": 10,
            "subject_split": {"train": 0.8, "val": 0.1, "test": 0.1},
            "min_mscxr_images": 4,
        },
        "reports": {
            "prefer_sections": ["impression", "findings"],
            "rationale_keywords": ["atelectasis", "effusion", "opacity"],
        },
        "validation": {
            "require_image_exists": True,
            "require_non_empty_report": True,
        },
        "outputs": {
            "output_dir": str(tmp_path / "outputs"),
            "usable_samples_csv": "usable_samples.csv",
            "usable_samples_jsonl": "usable_samples.jsonl",
            "claims_gold_jsonl": "claims_gold.jsonl",
            "stats_json": "stats.json",
            "subject_split_dir": "subject_splits",
        },
        "asset_copy": {
            "enabled": True,
            "output_dir": str(tmp_path / "outputs" / "copied_subset"),
            "copy_images": True,
            "copy_reports": True,
        },
        "logging": {"level": "INFO"},
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path


@pytest.fixture()
def synthetic_scene_graph_config(tmp_path: Path) -> Path:
    """Create a synthetic dataset where ImaGenome annotations are stored as scene graph JSON files."""
    images_root = tmp_path / "mimic_jpg"
    reports_root = tmp_path / "reports"
    scene_graph_root = tmp_path / "scene_graph"
    images_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)
    scene_graph_root.mkdir(parents=True, exist_ok=True)

    metadata_rows = []
    mscxr_rows = []
    dicom_counter = 1
    for subject_index in range(5):
        subject_id = f"{22000000 + subject_index}"
        study_id = f"{63000000 + subject_index}"
        for _ in range(2):
            dicom_id = f"sg{dicom_counter:04d}"
            dicom_counter += 1
            image_relative = Path(
                f"p{subject_id[:2]}/p{subject_id}/s{study_id}/{dicom_id}.jpg"
            )
            report_relative = Path(f"p{subject_id[:2]}/p{subject_id}/s{study_id}.txt")
            (images_root / image_relative).parent.mkdir(parents=True, exist_ok=True)
            (images_root / image_relative).write_bytes(b"fakejpg")
            (reports_root / report_relative).parent.mkdir(parents=True, exist_ok=True)
            (reports_root / report_relative).write_text(
                "FINDINGS: Mild bibasal atelectasis. IMPRESSION: Stable chest radiograph.",
                encoding="utf-8",
            )
            metadata_rows.append(
                {
                    "subject_id": subject_id,
                    "study_id": study_id,
                    "dicom_id": dicom_id,
                    "ViewPosition": "PA",
                }
            )
            scene_graph_payload = {
                "image_id": dicom_id,
                "patient_id": int(subject_id),
                "study_id": int(study_id),
                "viewpoint": "AP",
                "objects": [],
            }
            scene_graph_path = scene_graph_root / f"{dicom_id}_SceneGraph.json"
            scene_graph_path.write_text(json.dumps(scene_graph_payload), encoding="utf-8")
            if subject_index < 3:
                mscxr_rows.append({"dicom_id": dicom_id})

    metadata_path = tmp_path / "metadata.csv"
    mscxr_path = tmp_path / "mscxr.csv"
    for path, rows in ((metadata_path, metadata_rows), (mscxr_path, mscxr_rows)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    config = {
        "random_seed": 20260311,
        "io": {
            "metadata_csv": str(metadata_path),
            "mimic_jpg_root": str(images_root),
            "reports": {
                "mode": "directory",
                "root": str(reports_root),
                "path_template": "p{subject_id_prefix}/p{subject_id}/s{study_id}.txt",
            },
            "chest_imagenome_annotations": {
                "path": str(scene_graph_root),
                "format": "scene_graph_dir",
                "dicom_id_column": "image_id",
            },
            "mscxr_annotations": {
                "path": str(mscxr_path),
                "format": "csv",
                "dicom_id_column": "dicom_id",
            },
        },
        "columns": {
            "metadata": {
                "subject_id": "subject_id",
                "study_id": "study_id",
                "dicom_id": "dicom_id",
                "view_position": "ViewPosition",
            }
        },
        "paths": {
            "image_path_template": "p{subject_id_prefix}/p{subject_id}/s{study_id}/{dicom_id}.jpg"
        },
        "sampling": {
            "allowed_view_positions": ["PA", "AP"],
            "target_images": 8,
            "subject_split": {"train": 0.8, "val": 0.1, "test": 0.1},
            "min_mscxr_images": 2,
        },
        "reports": {
            "prefer_sections": ["impression", "findings"],
            "rationale_keywords": ["atelectasis", "effusion", "opacity"],
        },
        "validation": {
            "require_image_exists": True,
            "require_non_empty_report": True,
        },
        "outputs": {
            "output_dir": str(tmp_path / "outputs"),
            "usable_samples_csv": "usable_samples.csv",
            "usable_samples_jsonl": "usable_samples.jsonl",
            "claims_gold_jsonl": "claims_gold.jsonl",
            "stats_json": "stats.json",
            "subject_split_dir": "subject_splits",
        },
        "asset_copy": {
            "enabled": True,
            "output_dir": str(tmp_path / "outputs" / "copied_subset"),
            "copy_images": True,
            "copy_reports": True,
        },
        "logging": {"level": "INFO"},
    }

    config_path = tmp_path / "scene_graph_config.yaml"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path
