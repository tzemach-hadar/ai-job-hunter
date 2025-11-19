"""
Shared data models used across the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class JobListing:
    """Job listing metadata parsed from the CSV feed."""

    title: str
    company: str
    category: str
    size: str
    level: str
    city: str
    url: str
    updated: str


@dataclass
class JobMatch:
    """Result of LLM evaluation for a single job."""

    listing: JobListing
    score: float
    rationale: str
    description: str
    cover_letter_path: Optional[Path]
    distance_km: Optional[float] = None

