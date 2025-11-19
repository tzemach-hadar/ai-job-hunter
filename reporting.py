"""
Summary reporting utilities (HTML summary generation).
"""

from __future__ import annotations

import json
import logging
from html import escape
from pathlib import Path
from typing import Iterable

from data_models import JobMatch

LOGGER = logging.getLogger(__name__)


def write_matches_json(matches: Iterable[JobMatch], output_path: Path) -> None:
    """
    Persist match results to JSON.

    Args:
        matches: Sequence of JobMatch records.
        output_path: Destination file path.
    """
    payload = []
    for match in matches:
        payload.append(
            {
                "job": {
                    "title": match.listing.title,
                    "company": match.listing.company,
                    "category": match.listing.category,
                    "size": match.listing.size,
                    "level": match.listing.level,
                    "city": match.listing.city,
                    "url": match.listing.url,
                    "updated": match.listing.updated,
                },
                "score": match.score,
                "rationale": match.rationale,
                "description": match.description[:1000],
                "cover_letter_path": str(match.cover_letter_path) if match.cover_letter_path else "",
            }
        )

    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Wrote match JSON to %s", output_path)


def write_html_summary(matches: Iterable[JobMatch], output_path: Path, score_threshold: float = 75.0) -> None:
    """
    Generate an interactive HTML dashboard with DataTables for job matches.

    Args:
        matches: Sequence of JobMatch records.
        output_path: Destination HTML file path.
        score_threshold: Score threshold for highlighting rows.
    """
    sorted_matches = sorted(matches, key=lambda m: m.score, reverse=True)

    rows = []
    for match in sorted_matches:
        listing = match.listing
        
        # Verify company is present (debug check)
        if not listing.company:
            LOGGER.warning("Company missing for job: %s (URL: %s)", listing.title, listing.url)
        cover_link = ""
        if match.cover_letter_path:
            # Calculate relative path from summary file to cover letter
            summary_dir = output_path.parent
            cover_letter_path = match.cover_letter_path
            
            # Try to calculate relative path
            try:
                relative_path = cover_letter_path.relative_to(summary_dir)
            except ValueError:
                # If not in same directory tree, calculate from common parent
                try:
                    # Get common parent directory
                    summary_parts = summary_dir.parts
                    cover_parts = cover_letter_path.parent.parts
                    common_len = 0
                    for i in range(min(len(summary_parts), len(cover_parts))):
                        if summary_parts[i] == cover_parts[i]:
                            common_len += 1
                        else:
                            break
                    
                    # Build relative path: go up from summary, then down to cover letter
                    up_levels = len(summary_parts) - common_len
                    down_path = Path(*cover_parts[common_len:]) / cover_letter_path.name
                    relative_path = Path("../" * up_levels) / down_path
                except Exception:
                    # Fallback: just use the filename
                    relative_path = Path(cover_letter_path.name)
            
            cover_link = f'<a href="{escape(str(relative_path))}" target="_blank">Cover Letter</a>'

        # Show full rationale text without truncation
        rationale_display = escape(match.rationale)
        
        # Format distance
        distance_display = f"{match.distance_km:.1f}" if match.distance_km is not None else "N/A"
        
        # Apply highlight class if score is above threshold
        row_class = ' class="highlight"' if match.score >= score_threshold else ""
        
        rows.append(
            f'<tr{row_class}>'
            f"<td>{match.score:.2f}</td>"
            f"<td>{escape(listing.title)}</td>"
            f"<td>{escape(listing.company)}</td>"
            f"<td>{escape(listing.category)}</td>"
            f"<td>{escape(listing.size)}</td>"
            f"<td>{escape(listing.level)}</td>"
            f"<td>{escape(listing.city)}</td>"
            f"<td>{distance_display}</td>"
            f'<td><a href="{escape(listing.url)}" target="_blank">Job Posting</a></td>'
            f"<td>{rationale_display}</td>"
            f"<td>{cover_link}</td>"
            "</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Job Match Dashboard</title>
    
    <!-- jQuery -->
    <script src="https://code.jquery.com/jquery-3.7.1.min.js" integrity="sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo=" crossorigin="anonymous"></script>
    
    <!-- DataTables CSS -->
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
    
    <!-- DataTables JS -->
    <script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
    
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 2rem;
            background-color: #f7f1ec;
        }}
        h1 {{
            color: #677472;
            margin-bottom: 1rem;
        }}
        .info {{
            color: #677472;
            margin-bottom: 1.5rem;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            background-color: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        th, td {{
            border: 1px solid #e0e0e0;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-image: linear-gradient(to right, #677472, #91a29e);
            background-color: #677472;
            color: white;
            font-weight: bold;
            position: relative;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        tr:nth-child(odd) {{
            background-color: #f7f1ec;
            border-bottom: 1px solid #e0e0e0;
        }}
        tr:nth-child(even) {{
            background-color: rgba(218, 179, 155, 0.15);
            border-bottom: 1px solid #e0e0e0;
        }}
        tr:hover {{
            background-color: rgba(218, 179, 155, 0.3);
        }}
        .highlight {{
            background-color: #91a29e !important;
            box-shadow: 0 2px 4px rgba(103, 116, 114, 0.2);
            border-left: 3px solid #677472;
        }}
        .highlight:hover {{
            background-color: #c9a389 !important;
        }}
        td:nth-child(10) {{
            max-width: 400px;
            word-wrap: break-word;
        }}
        a {{
            color: #677472;
            text-decoration: none;
            font-weight: 500;
        }}
        a:hover {{
            text-decoration: underline;
            color: #91a29e;
        }}
        
        /* DataTables styling */
        .dataTables_wrapper {{
            margin-top: 1rem;
        }}
        .dataTables_filter input {{
            border: 2px solid #91a29e;
            border-radius: 4px;
            padding: 6px 10px;
            margin-left: 10px;
            color: #677472;
            background-color: #f7f1ec;
        }}
        .dataTables_filter input:focus {{
            outline: none;
            border-color: #677472;
            box-shadow: 0 0 5px rgba(103, 116, 114, 0.3);
            background-color: white;
        }}
        .dataTables_length select {{
            border: 2px solid #91a29e;
            border-radius: 4px;
            padding: 4px 8px;
            color: #677472;
            background-color: #f7f1ec;
        }}
        .dataTables_length select:focus {{
            outline: none;
            border-color: #677472;
            background-color: white;
        }}
        .dataTables_paginate .paginate_button {{
            border: 1px solid #91a29e;
            color: #677472 !important;
            padding: 6px 12px;
            margin: 0 2px;
            border-radius: 4px;
            background-color: #f7f1ec;
        }}
        .dataTables_paginate .paginate_button:hover {{
            background: #91a29e !important;
            border-color: #677472;
            color: white !important;
        }}
        .dataTables_paginate .paginate_button.current {{
            background: #91a29e !important;
            border-color: #677472;
            color: white !important;
        }}
        .dataTables_info {{
            color: #677472;
        }}
    </style>
</head>
<body>
    <h1>Job Match Dashboard</h1>
    <p class="info">Total matches: {len(rows)}</p>
    <table id="jobTable">
        <thead>
            <tr>
                <th>Match Score</th>
                <th>Job Title</th>
                <th>Company</th>
                <th>Category</th>
                <th>Size</th>
                <th>Level</th>
                <th>City</th>
                <th>Distance (km)</th>
                <th>Job URL</th>
                <th>Match Explanation</th>
                <th>Cover Letter</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    
    <script>
        $(document).ready(function() {{
            $('#jobTable').DataTable({{
                order: [[0, 'desc']],  // Sort by Match Score descending by default
                pageLength: 25,
                lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
                responsive: true,
                columnDefs: [
                    {{ targets: [0], type: 'num' }},  // Match Score - numeric
                    {{ targets: [7], type: 'num' }}     // Distance - numeric
                ]
            }});
        }});
    </script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    LOGGER.info("Wrote HTML summary to %s", output_path)

