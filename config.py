"""
Application configuration management.

Loads non-sensitive configuration from JSON and sensitive values
(e.g. Gemini API key) from environment variables or secret files.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("job_matcher_config.json")
DEFAULT_LOG_DIR = Path("logs")
DEFAULT_SUMMARY_DIR = Path("summaries")
DEFAULT_COVER_LETTER_DIR = Path("cover_letters")
SUMMARY_FILENAME = "job_summary.html"


@dataclass(frozen=True)
class Settings:
    """Container for application configuration."""

    csv_url: str
    score_threshold: float
    max_jobs: int
    resume_path: Path
    log_file: Optional[Path]
    summary_file: Optional[Path]
    cover_letter_dir: Path
    # TODO: Check if this is used - currently log level is determined by debug flag
    log_level: Optional[str]
    log_format: Optional[str]
    log_date_format: Optional[str]
    debug: bool
    save_html: bool
    use_llm: bool
    cover_letters: bool
    gemini_api_key: str
    gemini_model: str
    rescan_all_jobs: bool
    target_location: Optional[str]
    max_distance_km: Optional[float]
    llm_scoring_guide: Optional[str]


def _read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON file into a dictionary."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in configuration file: {path}") from exc


def _resolve_path(base: Path, value: Optional[str]) -> Optional[Path]:
    """Resolve a possibly relative path against a base directory."""
    if not value:
        return None
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def _load_secret(base: Path, key_path: Optional[str]) -> Optional[str]:
    """Load a secret value from a text file."""
    if not key_path:
        return None
    secret_file = _resolve_path(base, key_path)
    if secret_file and secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    LOGGER.warning("Secret file %s not found; skipping", secret_file)
    return None


def load_settings(config_path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    """
    Load application settings from config file and environment variables.

    Args:
        config_path: Path to the JSON configuration file.

    Returns:
        Settings dataclass populated with configuration values.
    """
    config_path = config_path.resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    config = _read_json(config_path)
    base_dir = config_path.parent

    csv_url = config.get("csv")
    if not csv_url:
        raise ValueError("Config must define 'csv' (job source).")

    score_threshold = float(config.get("score_threshold", 75.0))
    if score_threshold <= 0:
        raise ValueError("Config 'score_threshold' must be > 0.")

    max_jobs = int(config.get("max_jobs", 0))
    if max_jobs <= 0:
        raise ValueError("Config 'max_jobs' must be > 0.")

    resume_path = _resolve_path(base_dir, config.get("resume"))
    if not resume_path or not resume_path.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_path}")

    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_dir = DEFAULT_SUMMARY_DIR
    summary_dir.mkdir(parents=True, exist_ok=True)

    cover_letter_dir = _resolve_path(
        base_dir, config.get("cover_letter_dir")
    ) or DEFAULT_COVER_LETTER_DIR.resolve()
    cover_letter_dir.mkdir(parents=True, exist_ok=True)

    log_file_str = config.get("log_file")
    if log_file_str:
        # Replace timestamp placeholder if present
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file_str = log_file_str.replace("YYYYMMDD_HHMMSS", timestamp)
        log_file = _resolve_path(base_dir, log_file_str)
    else:
        log_file = None

    summary_file = _resolve_path(base_dir, config.get("summary_file"))
    if summary_file is None:
        summary_file = (summary_dir / SUMMARY_FILENAME).resolve()

    secret_key = _load_secret(base_dir, config.get("google_api_key_file"))
    api_key = secret_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "Gemini API key missing. Set GEMINI_API_KEY env or provide google_api_key_file."
        )

    gemini_model = config.get("gemini_model", "gemini-1.5-flash-latest")
    
    rescan_all_jobs = bool(config.get("rescan_all_jobs", False))
    target_location = config.get("target_location")
    max_distance_km = config.get("max_distance_km")
    if max_distance_km is not None:
        max_distance_km = float(max_distance_km)
    
    # Load LLM scoring guide from file or inline text
    llm_scoring_guide = None
    guide_file_path = config.get("llm_scoring_guide_file")
    if guide_file_path:
        # Load from file (similar to API key)
        llm_scoring_guide = _load_secret(base_dir, guide_file_path)
    else:
        # Fallback to inline text for backward compatibility
        llm_scoring_guide = config.get("llm_scoring_guide")
        if llm_scoring_guide and isinstance(llm_scoring_guide, str):
            llm_scoring_guide = llm_scoring_guide.strip()

    return Settings(
        csv_url=csv_url,
        score_threshold=score_threshold,
        max_jobs=max_jobs,
        resume_path=resume_path,
        log_file=log_file,
        summary_file=summary_file,
        cover_letter_dir=cover_letter_dir,
        log_level=config.get("log_level"),
        log_format=config.get("log_format"),
        log_date_format=config.get("log_date_format"),
        debug=bool(config.get("debug", False)),
        save_html=bool(config.get("save_html", False)),
        use_llm=bool(config.get("use_llm", True)),
        cover_letters=bool(config.get("cover_letters", True)),
        gemini_api_key=api_key,
        gemini_model=gemini_model,
        rescan_all_jobs=rescan_all_jobs,
        target_location=target_location,
        max_distance_km=max_distance_km,
        llm_scoring_guide=llm_scoring_guide,
    )

