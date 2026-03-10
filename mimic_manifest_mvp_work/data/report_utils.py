"""Report parsing and rationale extraction helpers."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .config import ConfigError, get_required
from .io_utils import open_text, read_csv_rows


LOGGER = logging.getLogger(__name__)

SECTION_HEADER_PATTERN = re.compile(r"(?i)\b(impression|findings)\s*:")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def load_report_lookup(config: dict[str, Any]) -> dict[str, dict[str, str]] | None:
    """Load report content when config points to a report CSV file."""
    report_config = get_required(config, "io.reports")
    mode = report_config.get("mode", "directory").lower()
    if mode == "directory":
        return None
    if mode != "csv":
        raise ConfigError(f"io.reports.mode must be 'directory' or 'csv', got '{mode}'")

    report_path = Path(get_required(config, "io.reports.path"))
    rows = read_csv_rows(report_path)
    if not rows:
        raise ValueError(f"Report CSV is empty: {report_path}")

    study_id_column = get_required(config, "io.reports.study_id_column")
    findings_column = get_required(config, "io.reports.findings_column")
    impression_column = get_required(config, "io.reports.impression_column")
    required = [study_id_column, findings_column, impression_column]
    missing = [column for column in required if column not in rows[0]]
    if missing:
        raise ConfigError(
            f"Report CSV is missing required columns {missing}: {report_path}"
        )

    lookup: dict[str, dict[str, str]] = {}
    for row in rows:
        lookup[str(row[study_id_column]).strip()] = {
            "findings": str(row.get(findings_column, "") or "").strip(),
            "impression": str(row.get(impression_column, "") or "").strip(),
        }
    LOGGER.info("Loaded %s reports from %s", len(lookup), report_path)
    return lookup


def load_report_text(
    config: dict[str, Any],
    row: dict[str, str],
    report_lookup: dict[str, dict[str, str]] | None,
) -> tuple[str, str]:
    """Return the preferred report section name and text for a metadata row."""
    report_config = get_required(config, "io.reports")
    mode = report_config.get("mode", "directory").lower()
    if mode == "csv":
        report_sections = report_lookup.get(row["study_id"], {}) if report_lookup else {}
        return select_report_section(config, report_sections)

    report_path = resolve_report_path(config, row)
    if report_path is None:
        return "", ""
    if not report_path.exists():
        raise FileNotFoundError(
            f"Report file does not exist for study {row['study_id']}: {report_path}"
        )

    with open_text(report_path) as handle:
        full_text = handle.read().strip()

    if not full_text:
        raise ValueError(f"Report file is empty for study {row['study_id']}: {report_path}")

    report_sections = parse_report_sections(full_text)
    if not report_sections:
        report_sections = {"findings": full_text}
    return select_report_section(config, report_sections)


def resolve_report_path(config: dict[str, Any], row: dict[str, str]) -> Path | None:
    """Resolve the source txt report path when reports are stored on disk."""
    report_config = get_required(config, "io.reports")
    if report_config.get("mode", "directory").lower() != "directory":
        return None

    report_root = Path(get_required(config, "io.reports.root"))
    template = get_required(config, "io.reports.path_template")
    relative_path = template.format(
        subject_id=row["subject_id"],
        subject_id_prefix=str(row["subject_id"])[:2],
        study_id=row["study_id"],
        dicom_id=row["dicom_id"],
    )
    return report_root / relative_path


def parse_report_sections(report_text: str) -> dict[str, str]:
    """Parse IMPRESSION/FINDINGS sections from free-text MIMIC reports."""
    sections: dict[str, str] = {}
    matches = list(SECTION_HEADER_PATTERN.finditer(report_text))
    for index, match in enumerate(matches):
        name = match.group(1).strip().lower()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(report_text)
        body = " ".join(report_text[body_start:body_end].split())
        if body:
            sections[name] = body
    return sections


def select_report_section(
    config: dict[str, Any], report_sections: dict[str, str]
) -> tuple[str, str]:
    """Choose impression first, then findings, according to config priority."""
    for section_name in get_required(config, "reports.prefer_sections"):
        text = report_sections.get(section_name, "").strip()
        if text:
            return section_name, text
    return "", ""


def select_rationale_sentence(report_text: str, config: dict[str, Any]) -> str:
    """Select one extractive rationale sentence using keyword matching."""
    sentences = split_sentences(report_text)
    if not sentences:
        return ""

    keywords = [keyword.lower() for keyword in get_required(config, "reports.rationale_keywords")]
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in keywords):
            return sentence
    return sentences[0]


def split_sentences(report_text: str) -> list[str]:
    """Split report text into simple sentence candidates."""
    collapsed = " ".join(report_text.split())
    if not collapsed:
        return []
    parts = [part.strip() for part in SENTENCE_SPLIT_PATTERN.split(collapsed) if part.strip()]
    return parts or [collapsed]
