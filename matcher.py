"""
Core pipeline coordinating job fetching, LLM scoring, and cover-letter creation.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Tuple

import requests
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

from data_models import JobListing, JobMatch
from llm_handler import GeminiClient
from resume_loader import load_resume, resume_to_text
from web_scraper import fetch_job_description, fetch_job_listings

LOGGER = logging.getLogger(__name__)

SCANNED_URLS_FILE = Path("scanned_urls.json")


class JobMatcher:
    """Coordinates job retrieval, LLM scoring, and report data assembly."""

    def __init__(self, settings) -> None:
        """
        Initialize the job matcher.

        Args:
            settings: Application settings dataclass.
        """
        self.settings = settings
        self.resume = load_resume(settings.resume_path)
        self.resume_text = resume_to_text(self.resume)
        self.llm = GeminiClient(
            settings.gemini_api_key, 
            settings.gemini_model,
            scoring_guide=settings.llm_scoring_guide
        )
        self.seen_urls: Set[str] = self._load_scanned_urls()
        self.target_coords: Optional[Tuple[float, float]] = None
        self._initialize_location_filtering()

    def _load_scanned_urls(self) -> Set[str]:
        """Load previously scanned URLs from JSON file."""
        if SCANNED_URLS_FILE.exists():
            try:
                with SCANNED_URLS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("urls", []))
            except (json.JSONDecodeError, Exception) as exc:
                LOGGER.warning("Failed to load scanned URLs: %s", exc)
                return set()
        return set()

    def _save_scanned_urls(self) -> None:
        """Save scanned URLs to JSON file."""
        try:
            with SCANNED_URLS_FILE.open("w", encoding="utf-8") as f:
                json.dump({"urls": list(self.seen_urls)}, f, indent=2)
            LOGGER.info("Saved %d scanned URLs to %s", len(self.seen_urls), SCANNED_URLS_FILE)
        except Exception as exc:
            LOGGER.error("Failed to save scanned URLs: %s", exc)

    def _initialize_location_filtering(self) -> None:
        """Initialize location filtering by geocoding the target location."""
        if not self.settings.target_location or not self.settings.max_distance_km:
            return
        
        try:
            geolocator = Nominatim(user_agent="job_matcher")
            location = geolocator.geocode(self.settings.target_location)
            if location:
                self.target_coords = (location.latitude, location.longitude)
                LOGGER.info("Geocoded target location: %s -> (%.4f, %.4f)", 
                           self.settings.target_location, 
                           self.target_coords[0], 
                           self.target_coords[1])
            else:
                LOGGER.warning("Failed to geocode target location: %s", self.settings.target_location)
        except Exception as exc:
            LOGGER.error("Error initializing location filtering: %s", exc)

    def _get_location_distance(self, job_location: str) -> Optional[float]:
        """
        Get the distance from target location to job location.

        Args:
            job_location: Job location string.

        Returns:
            Distance in kilometers, or None if geocoding fails.
        """
        if not self.target_coords:
            return None
        
        try:
            geolocator = Nominatim(user_agent="job_matcher")
            job_loc = geolocator.geocode(job_location)
            if not job_loc:
                LOGGER.warning("Failed to geocode job location: %s", job_location)
                return None
            
            job_coords = (job_loc.latitude, job_loc.longitude)
            distance = geodesic(self.target_coords, job_coords).kilometers
            return distance
        except Exception as exc:
            LOGGER.warning("Error calculating location distance for %s: %s", job_location, exc)
            return None

    def run(self) -> List[JobMatch]:
        """
        Execute the matching pipeline.

        Returns:
            List of all processed JobMatch records (regardless of threshold).
        """
        listings = fetch_job_listings(self.settings.csv_url, self.settings.max_jobs)
        all_jobs: List[JobMatch] = []
        matches: List[JobMatch] = []  # Jobs above threshold for cover letters

        for index, listing in enumerate(listings, start=1):
            LOGGER.info(
                "Evaluating job %d/%d: %s at %s",
                index,
                len(listings),
                listing.title,
                listing.company,
            )
            
            # Check if URL was already processed
            if not self.settings.rescan_all_jobs and listing.url in self.seen_urls:
                LOGGER.info("Skipping already processed job: %s", listing.url)
                continue
            
            # Check location distance and get distance value
            distance_km = None
            if self.target_coords and self.settings.max_distance_km:
                distance_km = self._get_location_distance(listing.city)
                if distance_km is None or distance_km > self.settings.max_distance_km:
                    continue
            
            try:
                description, requirements = fetch_job_description(listing.url, self.settings.save_html)
            except requests.RequestException:
                LOGGER.warning("Failed to fetch description for %s", listing.url)
                continue

            score_payload = self.llm.score_job(self.resume_text, description)
            if not score_payload:
                LOGGER.warning("LLM scoring failed for %s at %s", listing.title, listing.company)
                continue

            score = score_payload.get("score", 0)
            
            # Analyze requirements if available
            if requirements:
                core_skills = self.resume.get("skills", [])
                if not core_skills:
                    # Fallback to user-specified skills
                    core_skills = ['Python', 'Selenium', 'Web Scraping', 'Data Analysis']
                
                requirement_analysis = self.llm.analyze_requirements(requirements, core_skills)
                if requirement_analysis:
                    self._print_requirement_analysis_table(requirement_analysis, listing)
            
            # Extract explanation from score_payload
            explanation = score_payload.get("summary", "")
            if not explanation:
                # Fallback: try to get rationale or create a simple explanation
                explanation = score_payload.get("rationale", f"Match score: {score:.1f}")

            # Generate cover letter only for jobs above threshold
            cover_path = None
            if score >= self.settings.score_threshold:
                if self.settings.cover_letters:
                    cover_path = self._generate_cover_letter_pdf(listing, description)
                matches.append(
                    JobMatch(
                        listing=listing,
                        score=score,
                        rationale=explanation,
                        description=description,
                        cover_letter_path=cover_path,
                        distance_km=distance_km,
                    )
                )
                LOGGER.info("Job above threshold (score %.1f >= %.1f)", score, self.settings.score_threshold)
            else:
                LOGGER.info("Job below threshold (score %.1f < %.1f)", score, self.settings.score_threshold)
            
            # Add ALL processed jobs to all_jobs list (for dashboard display)
            all_jobs.append(
                JobMatch(
                    listing=listing,
                    score=score,
                    rationale=explanation,
                    description=description,
                    cover_letter_path=cover_path,
                    distance_km=distance_km,
                )
            )
            
            # Mark URL as processed
            self.seen_urls.add(listing.url)

            time.sleep(0.5)  # Polite rate limiting

        # Save scanned URLs at the end
        self._save_scanned_urls()

        LOGGER.info(
            "Processed %d jobs total, %d above threshold %.1f",
            len(all_jobs),
            len(matches),
            self.settings.score_threshold,
        )
        return all_jobs

    def _generate_cover_letter_pdf(
        self, listing: JobListing, description: str
    ) -> Optional[Path]:
        """
        Generate and save a tailored cover letter as a text file.

        Args:
            listing: Job listing metadata.
            description: Job description text.

        Returns:
            Path to the generated text file or None on failure.
        """
        contact = self.resume.get("contact", {})
        skills = self.resume.get("skills", [])
        letter_text = self.llm.generate_cover_letter(
            resume_text=self.resume_text,
            contact=contact,
            job_title=listing.title,
            company=listing.company,
            job_description=description,
            location=listing.city,
            skills=skills,
        )
        if not letter_text:
            return None

        safe_title = "_".join(listing.title.split()) or "job"
        safe_company = "_".join(listing.company.split()) or "company"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{safe_company}_{timestamp}.txt"
        output_path = self.settings.cover_letter_dir / filename

        try:
            # Get candidate name from resume
            candidate_name = self.resume.get("name", "")
            
            # Get current date in a readable format
            current_date = datetime.now().strftime("%B %d, %Y")
            
            # Build header
            header_lines = [
                current_date,
                listing.company,
                candidate_name,
                "",  # Empty line after header
            ]
            
            # Add contact information to the letter
            contact_lines = []
            email = contact.get("email")
            phone = contact.get("phone")
            if email:
                contact_lines.append(f"Email: {email}")
            if phone:
                contact_lines.append(f"Phone: {phone}")
            
            # Write text file with header, letter, and contact info
            full_text = "\n".join(header_lines) + letter_text
            if contact_lines:
                full_text += "\n\n" + "\n".join(contact_lines)
            
            output_path.write_text(full_text, encoding="utf-8")
            LOGGER.info("Cover letter saved: %s", output_path)
            return output_path
        except Exception as exc:
            LOGGER.error("Failed to write cover letter text file for %s: %s", listing.title, exc)
            return None

    def _print_requirement_analysis_table(self, analysis: list[dict], listing: JobListing) -> None:
        """
        Print a formatted table of requirement analysis results.

        Args:
            analysis: List of analysis dictionaries with 'requirement', 'score', and 'reason'.
            listing: Job listing for context.
        """
        print(f"\n{'='*80}")
        print(f"Requirement Analysis for: {listing.title} at {listing.company}")
        print(f"{'='*80}")
        print(f"{'Requirement':<50} {'Score':<10} {'Reason'}")
        print(f"{'-'*80}")
        
        for item in analysis:
            requirement = item.get("requirement", "")[:47] + "..." if len(item.get("requirement", "")) > 50 else item.get("requirement", "")
            score = item.get("score", 0)
            reason = item.get("reason", "")[:47] + "..." if len(item.get("reason", "")) > 50 else item.get("reason", "")
            print(f"{requirement:<50} {score:<10} {reason}")
        
        print(f"{'='*80}\n")

