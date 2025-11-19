"""
CLI entry point for the AI Job Application Assistant.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from config import DEFAULT_CONFIG_PATH, load_settings
from matcher import JobMatcher
from reporting import write_html_summary, write_matches_json

MATCHES_JSON = Path("matched_jobs.json")


class TruncatingFormatter(logging.Formatter):
    """Formatter that truncates log messages to a maximum length."""
    
    def __init__(self, max_length: int = 200, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_length = max_length
    
    def format(self, record):
        # Format the message first
        formatted = super().format(record)
        # Truncate if too long
        if len(formatted) > self.max_length:
            formatted = formatted[:self.max_length] + "... (truncated)"
        return formatted


def configure_logging(settings) -> None:
    """
    Configure logging according to settings.

    Args:
        settings: Application settings dataclass.
    """
    log_format = settings.log_format or "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = settings.log_date_format or "%Y-%m-%d %H:%M:%S"
    
    # Create formatter with truncation for console output
    console_formatter = TruncatingFormatter(max_length=200, fmt=log_format, datefmt=datefmt)
    file_formatter = logging.Formatter(fmt=log_format, datefmt=datefmt)
    
    handlers = []
    if settings.log_file:
        file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)

    log_level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(level=log_level, handlers=handlers)
    
    # Suppress verbose HTTP logging from various libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("selenium.webdriver").setLevel(logging.WARNING)
    logging.getLogger("selenium.webdriver.remote").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    """Execute the AI job application assistant workflow."""
    try:
        settings = load_settings(DEFAULT_CONFIG_PATH)
    except (FileNotFoundError, ValueError) as exc:
        logging.error("Configuration error: %s", exc)
        sys.exit(1)

    configure_logging(settings)

    logging.info("Starting AI job application assistant")
    logging.info(
        "Configuration: csv=%s, score_threshold=%.1f, max_jobs=%d",
        settings.csv_url,
        settings.score_threshold,
        settings.max_jobs,
    )

    if not settings.use_llm:
        logging.error("LLM evaluation is required. Set 'use_llm': true in config.")
        sys.exit(1)

    try:
        matcher = JobMatcher(settings)
        all_jobs = matcher.run()
        
        # Filter jobs above threshold for JSON export
        matches_above_threshold = [job for job in all_jobs if job.score >= settings.score_threshold]

        write_matches_json(matches_above_threshold, MATCHES_JSON)
        write_html_summary(all_jobs, settings.summary_file, settings.score_threshold)

        logging.info("Processed %d jobs total, %d above threshold %.1f. Summary: %s", 
                    len(all_jobs), len(matches_above_threshold), settings.score_threshold, settings.summary_file)
        if settings.cover_letters:
            logging.info("Cover letters directory: %s", settings.cover_letter_dir)
        logging.info("Finished run successfully.")
    except Exception as exc:
        logging.exception("Fatal error occurred: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

