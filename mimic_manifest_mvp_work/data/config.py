
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class ConfigError(ValueError):
    """Raised when the config file is missing required values."""


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load a JSON-compatible YAML config file from disk."""
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ConfigError(f"Config file is empty: {path}")

    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except ImportError:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                "PyYAML is not installed, so the config must be JSON-compatible YAML. "
                f"Failed to parse {path}: {exc}"
            ) from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping: {path}")
    return data


def require_keys(mapping: dict[str, Any], dotted_keys: Iterable[str]) -> None:
    """Ensure the given dotted config keys are present."""
    for dotted_key in dotted_keys:
        get_required(mapping, dotted_key)


def get_required(mapping: dict[str, Any], dotted_key: str) -> Any:
    """Read a required value from a nested mapping using dotted notation."""
    current: Any = mapping
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ConfigError(f"Missing required config key: {dotted_key}")
        current = current[part]
    return current
