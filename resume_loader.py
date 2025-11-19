"""
Utilities for loading and formatting the user's resume profile.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_resume(path: Path) -> Dict[str, Any]:
    """
    Load resume information from a JSON file.

    Args:
        path: Location of the resume JSON file.

    Returns:
        Parsed dictionary representing the resume.
    """
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resume_to_text(resume: Dict[str, Any]) -> str:
    """
    Convert resume content into a single text block for LLM consumption.

    Args:
        resume: Resume dictionary.

    Returns:
        Concatenated textual representation.
    """
    sections = []

    summary = resume.get("summary")
    if summary:
        sections.append(f"Summary: {summary}")

    for key in ("skills", "tools"):
        values = resume.get(key)
        if isinstance(values, list) and values:
            sections.append(f"{key.capitalize()}: {', '.join(values)}")

    experience = resume.get("experience", [])
    exp_lines = []
    for exp in experience:
        title = exp.get("title", "")
        company = exp.get("company", "")
        desc = exp.get("description", "")
        years = exp.get("years") or exp.get("period", "")
        exp_lines.append(f"{title} at {company} ({years}): {desc}")
    if exp_lines:
        sections.append("Experience: " + " | ".join(exp_lines))

    education = resume.get("education", [])
    edu_lines = []
    for edu in education:
        degree = edu.get("degree", "")
        institution = edu.get("university", "")
        edu_lines.append(f"{degree} - {institution}")
    if edu_lines:
        sections.append("Education: " + " | ".join(edu_lines))

    return "\n".join(sections).strip()

