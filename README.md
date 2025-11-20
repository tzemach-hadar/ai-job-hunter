# AI Job Application Assistant

An intelligent, automated job matching and application tool that streamlines your job search by scraping job listings, evaluating them against your resume using AI, and generating personalized cover letters.

## Project Description

This is an **AI-powered job application assistant** that automates the entire job search workflow—from discovering opportunities to generating tailored application materials. The tool reads job listings from CSV feeds, uses **Selenium WebDriver** to scrape detailed job descriptions from dynamic websites, and leverages **Google Gemini LLM** to intelligently score each job's fit based on your skills, experience, and preferences.

### Key Features

- **Intelligent Web Scraping**: Uses Selenium to dynamically scrape job descriptions from modern job boards (Comeet, Greenhouse, Lever, etc.), handling JavaScript-rendered content and extracting structured requirements from HTML.

- **AI-Powered Job Scoring**: Employs Google Gemini LLM to analyze job descriptions against your resume, providing a relevancy score (0-100) with detailed rationale explaining the match.

- **Personalized Scoring Logic**: Supports user-defined scoring heuristics via a configurable guide (e.g., "PENALIZE jobs requiring Master's degree", "BOOST AI Engineer roles", "IGNORE years of experience for non-Senior roles") that adjusts the LLM's evaluation to match your priorities.

- **Smart Filtering System**: 
  - **Location-based filtering**: Calculates distance from a target location using geopy and filters jobs within a specified radius
  - **De-duplication**: Tracks processed job URLs in `scanned_urls.json` to avoid re-scanning, with an option to rescan all jobs

- **Interactive HTML Dashboard**: Generates a sophisticated, interactive DataTables-powered dashboard with:
  - Client-side sorting and filtering on all columns
  - Visual highlighting for jobs above the score threshold
  - Professional color scheme with gradient headers
  - Direct links to job postings and generated cover letters
  - Distance calculations displayed for each job

- **Automated Cover Letter Generation**: Creates personalized, professional cover letters for high-scoring jobs, matching your experience to specific job requirements using the LLM.

- **Requirement Analysis**: Performs semantic analysis of individual job requirements against your core skills, generating a detailed match score table (1-10) with explanations for each requirement.

- **Comprehensive Reporting**: Produces both JSON exports (`matched_jobs.json`) and interactive HTML summaries, with all jobs displayed in the dashboard regardless of score, while highlighting and generating materials only for jobs above the threshold.

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Setup

1. **Copy example files**:
   ```bash
   cp resume.json.example resume.json
   cp job_matcher_config.json.example job_matcher_config.json
   cp llm_scoring_guide.txt.example llm_scoring_guide.txt
   ```

2. **Edit your resume**: Open `resume.json` and fill in your information (skills, experience, education, contact details, etc.).

3. **Configure the application**: Edit `job_matcher_config.json` with your desired settings (see Configuration section below).

4. **Set up API keys**: Create a `secrets/` directory and add your Google Gemini API key:
   ```bash
   mkdir -p secrets
   echo "your-api-key-here" > secrets/google_api_key.txt
   ```
   Alternatively, you can set the `GEMINI_API_KEY` environment variable.

5. **Select CSV file based on your field/experience**: 
   
   Browse available job CSV files from the [Techmap repository](https://github.com/mluggy/techmap/tree/main/jobs) and select the one that matches your professional field. Each CSV file contains jobs with various experience levels (Junior, Mid, Senior, Manager, etc.) that will be evaluated against your resume.
   
   Available CSV files by category:
   - `data-science.csv` - Data Science roles
   - `software.csv` - Software Engineering roles
   - `frontend.csv` - Frontend Development roles
   - `devops.csv` - DevOps/Infrastructure roles
   - `qa.csv` - Quality Assurance roles
   - `product.csv` - Product Management roles
   - `design.csv` - Design roles
   - `security.csv` - Security roles
   - `hardware.csv` - Hardware Engineering roles
   - `admin.csv` - Administrative roles
   - `business.csv` - Business roles
   - `finance.csv` - Finance roles
   - `hr.csv` - Human Resources roles
   - `legal.csv` - Legal roles
   - `marketing.csv` - Marketing roles
   - `sales.csv` - Sales roles
   - `support.csv` - Support roles
   - And more... (see [full list](https://github.com/mluggy/techmap/tree/main/jobs))
   
   **How to select**: Choose the CSV file that matches your primary field. The AI will then evaluate all jobs in that file (across all experience levels) and match them to your resume based on your skills and experience.
   
   Once you've selected your CSV file, update `job_matcher_config.json` with the corresponding URL:
   ```json
   {
     "csv": "https://raw.githubusercontent.com/mluggy/techmap/main/jobs/YOUR-SELECTED-FILE.csv",
     ...
   }
   ```
   
   **Example**: If you're a Data Scientist looking for roles in data science, use:
   ```json
   {
     "csv": "https://raw.githubusercontent.com/mluggy/techmap/main/jobs/data-science.csv",
     ...
   }
   ```
   
   **Note**: The CSV files contain jobs with different experience levels (Junior, Mid, Senior, Manager, Scientist, etc.). The AI will score each job based on how well it matches your resume, regardless of the listed experience level. You can adjust the `score_threshold` in the config to filter for higher-scoring matches.

6. **Run the script**:
   ```bash
   python3 main.py
   ```

## Configuration

All settings are read from the JSON config file (defaults to `job_matcher_config.json`). Edit that file to change behaviour. The following keys are required:

- `csv` - URL to the CSV feed containing job listings
- `score_threshold` - Minimum match score (0-100) for generating cover letters
- `max_jobs` - Maximum number of jobs to process
- `resume` - Path to your resume JSON file

Additional keys (logging, LLM, cover letters, file paths, location filtering) are optional but recommended.

### Config Example

```json
{
  "csv": "https://example.com/my-jobs.csv",
  "score_threshold": 80,
  "max_jobs": 30,
  "resume": "resume.json",
  "debug": false,
  "save_html": true,
  "use_llm": true,
  "cover_letters": true,
  "log_file": "logs/job_matcher_YYYYMMDD_HHMMSS.log",
  "summary_file": "summaries/job_summary.html",
  "google_api_key_file": "secrets/google_api_key.txt",
  "gemini_model": "gemini-1.5-flash-latest",
  "rescan_all_jobs": false,
  "target_location": "Your City, Your Country",
  "max_distance_km": 60,
  "llm_scoring_guide_file": "llm_scoring_guide.txt"
}
```

**Note**: The config file is the single source of truth. All settings are controlled through `job_matcher_config.json`.

### API Keys

Store your API keys outside version control. Create a `secrets/` directory (ignored by git) and place the key in a plain text file, e.g. `secrets/google_api_key.txt`. Reference that file from the config using `google_api_key_file`.

Alternatively, you can set the `GEMINI_API_KEY` environment variable before running:

```bash
export GEMINI_API_KEY="your_gemini_key"
```

## Usage

### Basic Usage

Simply run:
```bash
python3 main.py
```

The application will read all settings from `job_matcher_config.json`. Make sure you've:
- Created and filled in `resume.json`
- Set up your API key in `secrets/google_api_key.txt` or as `GEMINI_API_KEY` environment variable
- Configured `job_matcher_config.json` with your preferences

### LLM Scoring Guide

You can customize how the AI evaluates jobs by editing `llm_scoring_guide.txt`. This file allows you to define personal preferences using rules like:

- `PENALIZE: "Lower the score if..."` - Reduces score for certain conditions
- `BOOST: "Give a higher score for..."` - Increases score for certain conditions  
- `IGNORE: "Pay less attention to..."` - Tells the AI to de-emphasize certain factors

See `llm_scoring_guide.txt.example` for examples.

### Output Files

After each run you will see paths to the generated artefacts:

- `logs/job_matcher_YYYYMMDD_HHMMSS.log` – Full execution log
- `matched_jobs.json` – JSON array of match records
- `summaries/YYYYMMDD_HHMMSS_job_matches_summary.html` – HTML summary table sorted by LLM score
- `cover_letters_YYYYMMDD_HHMMSS/*.txt` – Generated cover letters (if enabled)

The HTML summary presents columns in this order: **Match Score, Job Title, Company, Category, Size, Level, City, Distance, Job URL, Match Explanation, Cover Letter**. Each row links directly to the job posting and the generated cover letter text file (where available).

### Sample Console Output

```
Match: 85.3% | LLM: 88.5%
Title: AI Engineer
Company: SolarEdge Technologies
City: הרצליה
URL: https://www.comeet.com/jobs/...
  Generating cover letter... ✓
```

## Logging

Logs are stored in the `logs/` directory:

- Default log file: `logs/job_matcher_YYYYMMDD_HHMMSS.log` (timestamp is automatically inserted)
- Customize the log file path in `job_matcher_config.json` using the `log_file` key
- Logs include HTTP activity, scoring details, LLM feedback, and summary generation events
- Set `debug: true` in config for verbose logging

View logs with:
```bash
tail -f logs/job_matcher_*.log
```

## How It Works

1. **Job Listing Retrieval**: Fetches job listings from a CSV feed (default: Techmap data-science feed).
2. **Web Scraping**: Uses Selenium WebDriver to scrape detailed job descriptions from job board websites.
3. **LLM Scoring**: Uses Google Gemini LLM to analyze each job description against your resume, providing a relevancy score (0-100) with detailed rationale.
4. **Location Filtering**: Optionally filters jobs by distance from a target location using geocoding.
5. **Cover Letter Generation**: For jobs above the score threshold, generates personalized cover letters using the LLM.
6. **Reporting**: Creates an interactive HTML dashboard and JSON export of all processed jobs.

## File Structure

```
.
├── main.py                      # Main entry point
├── config.py                    # Configuration management
├── matcher.py                   # Core job matching logic
├── web_scraper.py               # Job description scraping
├── llm_handler.py               # Google Gemini API wrapper
├── reporting.py                 # HTML/JSON report generation
├── resume_loader.py             # Resume data loading
├── data_models.py               # Data structures
├── job_matcher_config.json      # Your configuration (not in git)
├── resume.json                  # Your resume data (not in git)
├── llm_scoring_guide.txt        # Your scoring preferences (not in git)
├── requirements.txt             # Python dependencies
├── .gitignore                  # Git ignore rules
├── README.md                    # This file
└── *.example                    # Example/template files
```

**Important**: Files marked as "not in git" are excluded from version control for privacy. Copy the `.example` files to create your own versions.

## Requirements

- Python 3.8+
- Chrome/Chromium browser (for Selenium WebDriver)
- Internet access for CSV retrieval and job description scraping
- Google Gemini API key (get one at https://makersuite.google.com/app/apikey)
- See `requirements.txt` for all Python dependencies

## Troubleshooting

- **Missing Gemini models**: Upgrade `google-generativeai` and re-run.
- **LLM scoring fails**: Ensure API key is set correctly in `secrets/google_api_key.txt` or as `GEMINI_API_KEY` environment variable.
- **Sparse matches**: Enrich `resume.json` with relevant skills/tools and adjust `score_threshold` in config.
- **Web scraping issues**: Enable `save_html: true` in config and inspect files under `debug_pages/` directory.
- **Chrome/WebDriver errors**: Ensure Chrome browser is installed. Selenium will use the system Chrome installation.
- **Location filtering not working**: Check that `target_location` is a valid address that can be geocoded.

## License

This project is provided as-is for personal use.

