"""I/O helpers for reading metadata and annotations."""

from __future__ import annotations

import csv
import gzip
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from .config import ConfigError, get_required


LOGGER = logging.getLogger(__name__)


def open_text(path: Path):
    """Open a plain text or gzip-compressed text file."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Read a CSV or CSV.GZ file into a list of dictionaries."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")
    with open_text(csv_path) as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def load_metadata(config: dict[str, Any]) -> list[dict[str, str]]:
    """Load MIMIC metadata and normalize required columns."""
    metadata_path = Path(get_required(config, "io.metadata_csv"))
    column_config = get_required(config, "columns.metadata")
    rows = read_csv_rows(metadata_path)
    if not rows:
        raise ValueError(f"Metadata file is empty: {metadata_path}")

    required_source_columns = {
        "subject_id": column_config["subject_id"],
        "study_id": column_config["study_id"],
        "dicom_id": column_config["dicom_id"],
        "view_position": column_config["view_position"],
    }
    missing = [source for source in required_source_columns.values() if source not in rows[0]]
    if missing:
        raise ConfigError(
            "Metadata file is missing required columns. "
            f"Expected columns from config {required_source_columns}, missing {missing}."
        )

    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        normalized_rows.append(
            {
                "subject_id": str(row[required_source_columns["subject_id"]]).strip(),
                "study_id": str(row[required_source_columns["study_id"]]).strip(),
                "dicom_id": str(row[required_source_columns["dicom_id"]]).strip(),
                "view_position": str(row[required_source_columns["view_position"]]).strip(),
            }
        )
    LOGGER.info("Loaded %s metadata rows from %s", len(normalized_rows), metadata_path)
    return normalized_rows


def load_annotation_id_set(section_config: dict[str, Any], section_name: str) -> set[str]:
    """Load a dicom_id set from a supported annotation source."""
    path = Path(section_config["path"])
    if not path.exists():
        raise FileNotFoundError(f"{section_name} annotation file does not exist: {path}")

    fmt = section_config.get("format", "").lower()
    dicom_id_column = section_config.get("dicom_id_column")
    if not dicom_id_column:
        raise ConfigError(f"{section_name} config must define dicom_id_column")

    if fmt == "csv":
        rows = read_csv_rows(path)
        if rows and dicom_id_column not in rows[0]:
            raise ConfigError(
                f"{section_name} CSV is missing dicom column '{dicom_id_column}': {path}"
            )
        dicom_ids = {str(row[dicom_id_column]).strip() for row in rows if row.get(dicom_id_column)}
    elif fmt == "jsonl":
        dicom_ids = set()
        with open_text(path) as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                value = record.get(dicom_id_column)
                if value is None:
                    raise ConfigError(
                        f"{section_name} JSONL line {line_number} missing '{dicom_id_column}': {path}"
                    )
                dicom_ids.add(str(value).strip())
    elif fmt == "json":
        with open_text(path) as handle:
            payload = json.load(handle)
        dicom_ids = extract_dicom_ids_from_json(payload, dicom_id_column, section_name, path)
    elif fmt == "scene_graph_dir":
        dicom_ids = load_scene_graph_dir_ids(path, dicom_id_column, section_name)
    else:
        raise ConfigError(
            f"{section_name} format must be one of csv/json/jsonl/scene_graph_dir, got '{fmt}' for {path}"
        )

    LOGGER.info("Loaded %s unique dicom_ids from %s", len(dicom_ids), path)
    return dicom_ids


def load_scene_graph_dir_ids(path: Path, dicom_id_column: str, section_name: str) -> set[str]:
    """Scan a directory of per-image scene graph JSON files and collect image IDs."""
    if not path.is_dir():
        raise ConfigError(
            f"{section_name} with format='scene_graph_dir' must point to a directory: {path}"
        )

    scene_graph_files = sorted(path.glob("*_SceneGraph.json"))
    if not scene_graph_files:
        raise ConfigError(f"No *_SceneGraph.json files found in {path}")

    dicom_ids: set[str] = set()
    for scene_graph_path in scene_graph_files:
        with open_text(scene_graph_path) as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ConfigError(
                f"{section_name} scene graph must be a JSON object: {scene_graph_path}"
            )
        value = payload.get(dicom_id_column)
        if value is None:
            raise ConfigError(
                f"{section_name} scene graph missing '{dicom_id_column}': {scene_graph_path}"
            )
        dicom_ids.add(str(value).strip())
    return dicom_ids


def extract_dicom_ids_from_json(
    payload: Any, dicom_id_column: str, section_name: str, path: Path
) -> set[str]:
    """Extract dicom_ids from a JSON object or list."""
    dicom_ids: set[str] = set()
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            if not isinstance(item, dict) or dicom_id_column not in item:
                raise ConfigError(
                    f"{section_name} JSON list item {index} missing '{dicom_id_column}': {path}"
                )
            dicom_ids.add(str(item[dicom_id_column]).strip())
        return dicom_ids

    if isinstance(payload, dict):
        if dicom_id_column in payload and isinstance(payload[dicom_id_column], list):
            return {str(value).strip() for value in payload[dicom_id_column]}
        for key in payload:
            dicom_ids.add(str(key).strip())
        if dicom_ids:
            return dicom_ids

    raise ConfigError(
        f"{section_name} JSON structure is unsupported for dicom extraction: {path}"
    )


def ensure_parent_dir(path: str | Path) -> Path:
    """Create the parent directory of a file path if needed."""
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    """Write a CSV file with deterministic column ordering."""
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Write a JSONL file with one JSON object per line."""
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_lines(path: str | Path, values: Iterable[str]) -> None:
    """Write a plain text file with one value per line."""
    output_path = ensure_parent_dir(path)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(f"{value}\n")
