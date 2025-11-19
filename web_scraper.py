"""
Fetching and parsing job listings and descriptions.
"""

from __future__ import annotations

import csv
import logging
import re
import time
from pathlib import Path
from typing import List, Optional

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from data_models import JobListing

LOGGER = logging.getLogger(__name__)


def fetch_job_listings(csv_url: str, max_jobs: int) -> List[JobListing]:
    """
    Download and parse the CSV job listings feed.

    Args:
        csv_url: URL to the CSV feed.
        max_jobs: Maximum number of jobs to return.

    Returns:
        List of JobListing records.
    """
    try:
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.error("Failed to fetch job listings: %s", exc)
        raise

    reader = csv.DictReader(response.text.splitlines())
    listings: List[JobListing] = []
    
    # Log available column names for debugging
    if reader.fieldnames:
        LOGGER.debug("CSV columns found: %s", list(reader.fieldnames))

    for idx, row in enumerate(reader, start=1):
        if idx > max_jobs:
            break
        
        # Create a normalized row dictionary for case-insensitive access
        # This handles variations like "Company", "COMPANY", "company ", etc.
        normalized_row = {k.strip().lower(): (v.strip() if isinstance(v, str) else str(v)) if v else "" for k, v in row.items()}
        
        # Extract company - try multiple approaches since it's the first column (index 0)
        # First try normalized lowercase key
        company = normalized_row.get("company", "")
        
        # If not found, try original case (preserve original column names)
        if not company:
            company = row.get("company", "") or row.get("Company", "") or row.get("COMPANY", "")
            if isinstance(company, str):
                company = company.strip()
        
        # Fallback to other common column name variations
        if not company:
            company = (
                normalized_row.get("company_name", "") or
                normalized_row.get("employer", "") or
                ""
            )
        
        # If still not found, try accessing by position (first column)
        if not company and reader.fieldnames:
            first_col_name = reader.fieldnames[0].strip()
            company = row.get(first_col_name, "")
            if isinstance(company, str):
                company = company.strip()
        
        # Log if company is missing for debugging
        if not company:
            LOGGER.warning("Company name missing for job at row %d. Available columns: %s. URL: %s", 
                          idx, list(row.keys()), normalized_row.get("url", "unknown URL"))
        else:
            LOGGER.debug("Row %d: Company='%s', Title='%s'", idx, company, normalized_row.get("title", ""))
        
        job_listing = JobListing(
            title=normalized_row.get("title", ""),
            company=company,
            category=normalized_row.get("category", ""),
            size=normalized_row.get("size", ""),
            level=normalized_row.get("level", ""),
            city=normalized_row.get("city", ""),
            url=normalized_row.get("url", ""),
            updated=normalized_row.get("updated", ""),
        )
        
        # Verify company was stored correctly
        if not job_listing.company:
            LOGGER.error("CRITICAL: Company field is empty in JobListing object for row %d. URL: %s", 
                        idx, job_listing.url)
        else:
            LOGGER.debug("Successfully stored company '%s' for job: %s", job_listing.company, job_listing.title)
        
        listings.append(job_listing)

    LOGGER.info("Fetched %d job listings", len(listings))
    # Log sample to verify company is present
    if listings:
        sample = listings[0]
        LOGGER.info("Sample listing - Company: '%s', Title: '%s', URL: '%s'", 
                   sample.company, sample.title, sample.url)
    return listings


def _create_driver() -> webdriver.Chrome:
    """
    Create and configure a headless Chrome WebDriver.

    Returns:
        Configured Chrome WebDriver instance.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except WebDriverException as exc:
        LOGGER.error("Failed to initialize Chrome WebDriver: %s", exc)
        raise


def fetch_job_description(url: str, save_html: bool = False) -> tuple[str, list[str]]:
    """
    Fetch the job description by scraping the given URL using Selenium.

    Args:
        url: Job posting URL.
        save_html: Whether to save raw HTML for debugging.

    Returns:
        Tuple of (extracted textual job description, list of individual requirements).
    """
    driver: Optional[webdriver.Chrome] = None
    try:
        driver = _create_driver()
        LOGGER.debug("Navigating to %s", url)
        driver.get(url)
        
        description = ""
        wait = WebDriverWait(driver, timeout=15)
        
        # First, try to find requirements in userDesignedContent company-description
        primary_selectors = [
            ".userDesignedContent.company-description li",
            ".userDesignedContent .company-description li",
        ]
        
        requirement_texts = []
        for selector in primary_selectors:
            try:
                # Wait for li elements to be present
                LOGGER.debug("Waiting for li elements with selector: %s", selector)
                li_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                )
                
                if li_elements:
                    LOGGER.debug("Found %d li elements in primary container", len(li_elements))
                    for li in li_elements:
                        li_text = li.text.strip()
                        li_text = re.sub(r"\s+", " ", li_text).strip()
                        if li_text:
                            requirement_texts.append(li_text)
                    
                    if requirement_texts:
                        description = " | ".join(requirement_texts)
                        LOGGER.debug("Extracted %d requirement items from primary selector (%d chars)", 
                                    len(requirement_texts), len(description))
                        if len(description) > 200:
                            if save_html:
                                _save_html_snapshot(driver, url)
                            return (description[:5000], requirement_texts)
            except TimeoutException:
                LOGGER.debug("Timeout waiting for primary selector: %s", selector)
                continue
        
        # Second option: look for jobs-description__content classes
        secondary_selectors = [
            ".jobs-description__content.jobs-description-content",
            ".jobs-description__content--condensed",
        ]
        
        for container_selector in secondary_selectors:
            try:
                # Wait for the container to be present
                container = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, container_selector))
                )
                LOGGER.debug("Found secondary requirements container: %s", container_selector)
                
                # Look for "Requirements" heading and extract ul list after it
                # Find all headings that might contain "Requirements"
                headings = container.find_elements(By.XPATH, ".//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6 | .//p | .//strong | .//b")
                requirements_text = []
                
                for heading in headings:
                    heading_text = heading.text.strip()
                    if re.search(r'\brequirements?\b', heading_text, re.IGNORECASE):
                        LOGGER.debug("Found Requirements heading: %s", heading_text[:100])
                        # Find the next ul after this heading
                        try:
                            # Try to find ul as a sibling
                            ul = heading.find_element(By.XPATH, "./following-sibling::ul[1]")
                            list_items = ul.find_elements(By.TAG_NAME, "li")
                            if list_items:
                                requirements_text.extend([li.text.strip() for li in list_items if li.text.strip()])
                                LOGGER.debug("Found requirements list with %d items", len(list_items))
                        except Exception:
                            # Try parent's next sibling
                            try:
                                parent = heading.find_element(By.XPATH, "./..")
                                ul = parent.find_element(By.XPATH, "./following-sibling::ul[1]")
                                list_items = ul.find_elements(By.TAG_NAME, "li")
                                if list_items:
                                    requirements_text.extend([li.text.strip() for li in list_items if li.text.strip()])
                                    LOGGER.debug("Found requirements list in parent sibling with %d items", len(list_items))
                            except Exception:
                                LOGGER.debug("Could not find ul list after Requirements heading")
                
                if requirements_text:
                    description = " | ".join(requirements_text)
                    description = re.sub(r"\s+", " ", description).strip()
                    LOGGER.debug("Extracted %d requirement items from secondary selector (%d chars)", 
                                len(requirements_text), len(description))
                    if len(description) > 100:
                        if save_html:
                            _save_html_snapshot(driver, url)
                        return (description[:5000], requirements_text)
                
                # If no requirements list found, get all text from this container
                if not description or len(description) < 100:
                    container_text = container.text.strip()
                    container_text = re.sub(r"\s+", " ", container_text).strip()
                    if len(container_text) > len(description):
                        description = container_text
                        LOGGER.debug("Using full container text: %d chars", len(description))
                        
            except TimeoutException:
                LOGGER.debug("Timeout waiting for secondary selector: %s", container_selector)
                continue
        
        # Fallback: try generic selectors
        if len(description) < 200:
            LOGGER.debug("Using fallback selectors")
            fallback_selectors = [
                "[class*='description' i]",
                "[class*='job-description' i]",
                "[class*='posting-description' i]",
                "article",
                "main",
                "section",
            ]
            
            for selector in fallback_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        text = " ".join([elem.text.strip() for elem in elements if elem.text.strip()])
                        text = re.sub(r"\s+", " ", text).strip()
                        if len(text) > len(description):
                            description = text
                    if len(description) > 400:
                        break
                except Exception:
                    continue

        # Last resort: get all text from body
        if len(description) < 200:
            LOGGER.debug("Using full page text as last resort")
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                description = body.text.strip()
            except Exception:
                description = driver.page_source[:5000]

        if save_html:
            _save_html_snapshot(driver, url)
        
        description = re.sub(r"\s+", " ", description).strip()
        # Return description with empty requirements list if we couldn't extract individual requirements
        return (description[:5000], [])
        
    except WebDriverException as exc:
        LOGGER.error("Selenium error while fetching job description from %s: %s", url, exc)
        raise
    except Exception as exc:
        LOGGER.error("Unexpected error while fetching job description from %s: %s", url, exc)
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _save_html_snapshot(driver: webdriver.Chrome, url: str) -> None:
    """
    Save the current page HTML for debugging.

    Args:
        driver: Selenium WebDriver instance.
        url: Original URL for naming the file.
    """
    try:
        snapshot_dir = Path("debug_pages")
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{int(time.time())}.html"
        snapshot_path.write_text(driver.page_source, encoding="utf-8")
        LOGGER.debug("Saved HTML snapshot to %s", snapshot_path)
    except Exception as exc:
        LOGGER.debug("Failed to save HTML snapshot: %s", str(exc)[:100])

