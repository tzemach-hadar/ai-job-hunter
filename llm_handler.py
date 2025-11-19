"""
LLM client wrapper for scoring and cover-letter generation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import google.generativeai as genai

LOGGER = logging.getLogger(__name__)

# Try to import safety settings, but make them optional
try:
    from google.generativeai.types import HarmBlockThreshold, HarmCategory
    SAFETY_SETTINGS_AVAILABLE = True
except (ImportError, AttributeError):
    SAFETY_SETTINGS_AVAILABLE = False
    HarmCategory = None
    HarmBlockThreshold = None


class GeminiClient:
    """Wrapper around the Google Gemini API for scoring jobs and generating letters."""

    def __init__(self, api_key: str, model_name: str, scoring_guide: Optional[str] = None) -> None:
        """
        Initialize the Gemini client.

        Args:
            api_key: Google Gemini API key.
            model_name: Name of the Gemini model to use.
            scoring_guide: Optional personal scoring guide for LLM evaluation.
        """
        genai.configure(api_key=api_key)
        self._model_name = model_name
        self._model = None
        self._use_new_api = self._check_api_version()
        self._initialize_model()
        self._generation_config = {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 32,
            "candidate_count": 1,
        }
        self._safety_settings = self._build_safety_settings()
        self._scoring_guide = scoring_guide
        LOGGER.info("Gemini client initialized with model %s (API: %s)", self._model_name, "new" if self._use_new_api else "legacy")

    def _check_api_version(self) -> bool:
        """
        Check if the new GenerativeModel API is available.

        Returns:
            True if new API is available, False for legacy generate_text API.
        """
        return hasattr(genai, "GenerativeModel")

    def _build_safety_settings(self) -> Optional[dict]:
        """
        Build safety settings if available, otherwise return None.

        Returns:
            Dictionary of safety settings or None if not available.
        """
        if not SAFETY_SETTINGS_AVAILABLE:
            LOGGER.debug("Safety settings not available in this version of google-generativeai")
            return None

        try:
            settings = {}
            # Try to set common safety categories, handling missing attributes gracefully
            categories = {
                "HARM_CATEGORY_HARASSMENT": "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH": "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "HARM_CATEGORY_DANGEROUS_CONTENT",
            }
            
            for attr_name, category_name in categories.items():
                if hasattr(HarmCategory, category_name):
                    category = getattr(HarmCategory, category_name)
                    if hasattr(HarmBlockThreshold, "BLOCK_NONE"):
                        settings[category] = HarmBlockThreshold.BLOCK_NONE
            
            return settings if settings else None
        except Exception as exc:
            LOGGER.debug("Failed to build safety settings: %s", str(exc)[:100])
            return None

    def _initialize_model(self) -> None:
        """Initialize the Gemini model with fallback options."""
        preferred = [
            self._model_name,
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-pro",
        ]

        working_model = None
        try:
            models = list(genai.list_models())
            LOGGER.debug("Gemini list_models returned %d models", len(models))

            def supports_generate(model) -> bool:
                methods = getattr(model, "supported_generation_methods", None)
                if isinstance(methods, (list, tuple, set)):
                    for method in methods:
                        if str(method).lower() in {"generatecontent", "generate_content"}:
                            return True
                    return False
                return True

            candidates = [m for m in models if supports_generate(m)]
            by_name = {getattr(m, "name", ""): m for m in candidates}
            for choice in preferred:
                if choice in by_name:
                    working_model = choice
                    break
            if not working_model and candidates:
                ordered = sorted(
                    (getattr(m, "name", "") for m in candidates),
                    key=lambda n: (
                        0 if "flash-latest" in n else
                        1 if "flash" in n else
                        2 if "1.5-pro" in n else
                        3 if "pro" in n else
                        9
                    ),
                )
                working_model = ordered[0] if ordered else None
        except Exception as exc:
            LOGGER.debug("Gemini list_models unavailable: %s", str(exc)[:100])
            pass

        attempts = []
        if working_model:
            attempts.append(working_model)
        attempts.extend(preferred)
        attempts = [m for i, m in enumerate(attempts) if m and m not in attempts[:i]]

        for attempt in attempts:
            try:
                if self._use_new_api:
                    self._model = genai.GenerativeModel(attempt)
                else:
                    # For legacy API, just store the model name
                    self._model = attempt
                self._model_name = attempt
                LOGGER.info("LLM enabled (Gemini) with model %s", attempt)
                return
            except Exception as exc:
                LOGGER.debug("Gemini model %s failed: %s", attempt, str(exc)[:100])
                pass
        raise RuntimeError("No supported Gemini model found")

    def score_job(self, resume_text: str, job_description: str) -> Optional[dict]:
        """
        Request an LLM-based relevancy score.

        Args:
            resume_text: Resume content prepared for the model.
            job_description: Job description to evaluate.

        Returns:
            Dictionary containing score and rationale, or None if scoring failed.
        """
        # Build the prompt with optional personal scoring guide
        prompt_parts = [
            "You are a precise job-match evaluator. Given a resume and a job description, "
            "return a JSON with fields: score (0-100 integer), strengths (short list), gaps (short list), "
            "and summary (2-3 sentences). Focus on skills, experience, domain, seniority, and tech stack alignment.\n\n"
        ]
        
        # Add personal scoring guidelines if provided
        if self._scoring_guide:
            prompt_parts.append("--- PERSONAL SCORING GUIDELINES ---\n")
            prompt_parts.append(self._scoring_guide)
            prompt_parts.append("\n--- END OF GUIDELINES ---\n\n")
        
        prompt_parts.append(f"Resume:\n{resume_text}\n\n")
        prompt_parts.append(f"Job Description:\n{job_description}\n\n")
        
        # Add explicit instruction about using the guidelines
        if self._scoring_guide:
            prompt_parts.append(
                "Your primary task is to score the job based on my core skills. "
                "However, you must use the PERSONAL SCORING GUIDELINES provided above to adjust the final score and the reason. "
                "These are my personal priorities.\n\n"
            )
        
        prompt_parts.append("Respond with ONLY the JSON.")
        
        prompt = "".join(prompt_parts)

        try:
            if self._use_new_api:
                # New API: generate_content takes content as positional argument
                kwargs = {}
                if self._generation_config:
                    kwargs["generation_config"] = self._generation_config
                if self._safety_settings:
                    kwargs["safety_settings"] = self._safety_settings
                # Pass prompt as positional argument (first parameter)
                response = self._model.generate_content(prompt, **kwargs)
                # Handle different response formats
                if hasattr(response, 'text'):
                    text = (response.text or "").strip()
                elif hasattr(response, 'result'):
                    text = (response.result or "").strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    # New API might return candidates list
                    text = (response.candidates[0].content.parts[0].text or "").strip()
                else:
                    LOGGER.error("Unexpected response format from Gemini: %s", type(response))
                    text = ""
            else:
                # Legacy API using generate_text
                response = genai.generate_text(
                    model=self._model,
                    prompt=prompt,
                    temperature=self._generation_config.get("temperature", 0.2),
                    top_p=self._generation_config.get("top_p"),
                    top_k=self._generation_config.get("top_k"),
                    candidate_count=self._generation_config.get("candidate_count", 1),
                )
                text = (response.result or "").strip()
            if not text:
                LOGGER.warning("Empty response from Gemini")
                return None

            # Log raw response for debugging (truncated)
            LOGGER.debug("Raw LLM response (first 200 chars): %s", text[:200])
            
            if not text.startswith("{"):
                match = re.search(r"\{.*\}", text, re.S)
                if match:
                    text = match.group(0)
                    LOGGER.debug("Extracted JSON from response (first 200 chars): %s", text[:200])
                else:
                    LOGGER.warning("No JSON found in LLM response. Full response (first 200 chars): %s", text[:200])
                    return None

            try:
                data = json.loads(text)
                LOGGER.debug("Parsed JSON data (keys: %s)", list(data.keys())[:10])
            except json.JSONDecodeError as json_exc:
                LOGGER.error("Failed to parse JSON from LLM response: %s. Response text (first 200 chars): %s", json_exc, text[:200])
                return None

            # Check if score field exists
            if "score" not in data:
                LOGGER.error("'score' field missing in LLM response! Response keys: %s", list(data.keys())[:10])
                return None
            
            try:
                score = float(data.get("score", 0))
                LOGGER.info("LLM returned score: %.1f (raw value: %s)", score, data.get("score"))
            except (ValueError, TypeError) as score_exc:
                LOGGER.error("Failed to convert score to float: %s. Score value: %s (type: %s)", 
                           score_exc, data.get("score"), type(data.get("score")))
                return None
            
            if score == 0:
                LOGGER.warning("LLM returned score of 0.0 - this might indicate a problem")
            
            data["score"] = max(0.0, min(100.0, score))
            LOGGER.info("Final LLM score after validation: %.1f", data["score"])
            return data
        except Exception as exc:
            LOGGER.error("Gemini scoring failed: %s. Response text (first 200 chars): %s", 
                        exc, text[:200] if 'text' in locals() else "N/A")
            return None

    def generate_cover_letter(
        self,
        resume_text: str,
        contact: dict,
        job_title: str,
        company: str,
        job_description: str,
        location: str,
        skills: list[str],
    ) -> Optional[str]:
        """
        Generate a tailored cover letter.

        Args:
            resume_text: Resume content.
            contact: Contact info dictionary.
            job_title: Job title.
            company: Company name.
            job_description: Description for the role.
            location: Job location.
            skills: List of candidate's skills (to prevent hallucination).

        Returns:
            Cover letter string or None on failure.
        """
        email = contact.get("email", "")
        phone = contact.get("phone", "")
        skills_str = ", ".join(skills) if skills else "None specified"
        
        prompt = f"""You are a professional cover letter writer. Write a personalized cover letter for the following job application.

Job Title: {job_title}
Company: {company}
Location: {location if location else "Not specified"}

Job Description:
{job_description[:3000]}

Candidate Resume:
{resume_text}

Candidate Skills (ONLY mention these - do not invent skills):
{skills_str}

STRICT SYSTEM INSTRUCTIONS - FOLLOW EXACTLY:

1. LENGTH REQUIREMENT:
   - The cover letter body must be EXACTLY TWO PARAGRAPHS. No exceptions.
   - Be extremely concise. Every sentence must add value.
   - Do not include introductory paragraphs, closing paragraphs, or call-to-action paragraphs beyond the two required paragraphs.

2. TONE REQUIREMENT - MATTER-OF-FACT AND PROFESSIONAL:
   - Use a direct, professional, matter-of-fact tone.
   - FORBIDDEN WORDS/PHRASES (DO NOT USE):
     * "thrilled", "excited", "passionate", "eager", "enthusiastic"
     * "dream job", "perfect fit", "perfect candidate"
     * "I am very interested" (too enthusiastic)
     * Any exclamation marks or overly positive language
   - ALLOWED PHRASING (USE THESE):
     * "I am writing regarding the [Job Title] position..."
     * "My experience includes..."
     * "I am confident in my ability to..."
     * "My background in [skill] aligns with your requirements..."
     * Direct, factual statements about qualifications

3. ACCURACY REQUIREMENT - NO HALLUCINATIONS:
   - ONLY mention skills that are listed in "Candidate Skills" above or explicitly evident in the resume.
   - If the job requires a skill not in the candidate's skills list, DO NOT mention it.
   - DO NOT apologize for missing skills.
   - DO NOT invent or assume skills the candidate has.
   - Focus on skills the candidate actually possesses.

4. SELF-LEARNING EMPHASIS (REQUIRED IN SECOND PARAGRAPH):
   - The second paragraph MUST explicitly mention the candidate's proven ability for self-learning and adapting to new technologies quickly.
   - Frame this as a key asset that allows the candidate to bridge any gap in specific tool requirements.
   - Use matter-of-fact language, not enthusiastic language.
   - Example phrasing: "My track record demonstrates rapid adaptation to new technologies and tools, which enables me to quickly bridge any gaps in specific tool requirements."

STRUCTURE:
- Date (use current date format)
- Hiring Manager or Company Name
- Company Address (if location provided, otherwise omit)
- Subject line
- Salutation
- FIRST PARAGRAPH: Direct statement of interest and key qualifications matching the job
- SECOND PARAGRAPH: Self-learning ability and adaptability (as specified above)
- Closing (Sincerely,)
- Candidate name
- Email: {email}
- Phone: {phone}

Write ONLY the cover letter, no additional commentary."""

        try:
            if self._use_new_api:
                # New API: generate_content takes content as positional argument
                kwargs = {}
                gen_config = {
                    **self._generation_config,
                    "temperature": 0.7,
                }
                if gen_config:
                    kwargs["generation_config"] = gen_config
                if self._safety_settings:
                    kwargs["safety_settings"] = self._safety_settings
                # Pass prompt as positional argument (first parameter)
                response = self._model.generate_content(prompt, **kwargs)
                # Handle different response formats
                if hasattr(response, 'text'):
                    text = (response.text or "").strip()
                elif hasattr(response, 'result'):
                    text = (response.result or "").strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    # New API might return candidates list
                    text = (response.candidates[0].content.parts[0].text or "").strip()
                else:
                    LOGGER.error("Unexpected response format from Gemini: %s", type(response))
                    text = ""
            else:
                # Legacy API using generate_text
                response = genai.generate_text(
                    model=self._model,
                    prompt=prompt,
                    temperature=0.7,
                    top_p=self._generation_config.get("top_p"),
                    top_k=self._generation_config.get("top_k"),
                    candidate_count=self._generation_config.get("candidate_count", 1),
                )
                text = (response.result or "").strip()
            if not text:
                LOGGER.warning("Empty cover letter response from Gemini")
                return None
            return text
        except Exception as exc:
            LOGGER.error("Gemini cover letter generation failed: %s", exc)
            return None

    def analyze_requirements(
        self, requirements: list[str], core_skills: list[str]
    ) -> Optional[list[dict]]:
        """
        Analyze job requirements against core skills and provide match scores.

        Args:
            requirements: List of individual requirement strings.
            core_skills: List of core skills to match against.

        Returns:
            List of dictionaries with 'requirement', 'score', and 'reason' keys, or None on failure.
        """
        if not requirements:
            return []

        skills_str = ", ".join(core_skills)
        requirements_str = "\n".join(f"{i+1}. {req}" for i, req in enumerate(requirements))

        prompt = f"""You are an expert HR analyst. Analyze each job requirement against these core skills: {skills_str}

Job Requirements:
{requirements_str}

For each requirement, provide:
1. A Match Score from 1 (irrelevant) to 10 (perfect match) based on semantic alignment with the core skills
2. A brief reason explaining the score (e.g., "High score: Directly mentions Python and data analysis" or "Low score: Focuses on non-relevant marketing skills")

Return ONLY a JSON array where each element has:
- "requirement": the original requirement text
- "score": integer from 1-10
- "reason": short explanation sentence

Example format:
[
  {{"requirement": "Experience with Python programming", "score": 9, "reason": "High score: Directly mentions Python which is a core skill"}},
  {{"requirement": "Marketing experience required", "score": 2, "reason": "Low score: Focuses on marketing, not relevant to technical skills"}}
]

Respond with ONLY the JSON array, no additional text."""

        try:
            if self._use_new_api:
                kwargs = {}
                if self._generation_config:
                    kwargs["generation_config"] = self._generation_config
                if self._safety_settings:
                    kwargs["safety_settings"] = self._safety_settings
                response = self._model.generate_content(prompt, **kwargs)
                if hasattr(response, 'text'):
                    text = (response.text or "").strip()
                elif hasattr(response, 'result'):
                    text = (response.result or "").strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    text = (response.candidates[0].content.parts[0].text or "").strip()
                else:
                    LOGGER.error("Unexpected response format from Gemini")
                    return None
            else:
                response = genai.generate_text(
                    model=self._model,
                    prompt=prompt,
                    temperature=self._generation_config.get("temperature", 0.2),
                    top_p=self._generation_config.get("top_p"),
                    top_k=self._generation_config.get("top_k"),
                    candidate_count=self._generation_config.get("candidate_count", 1),
                )
                text = (response.result or "").strip()

            if not text:
                LOGGER.warning("Empty response from Gemini for requirement analysis")
                return None

            # Extract JSON from response
            if not text.startswith("["):
                match = re.search(r"\[.*\]", text, re.S)
                if match:
                    text = match.group(0)
                else:
                    LOGGER.warning("No JSON array found in LLM response")
                    return None

            try:
                data = json.loads(text)
                if not isinstance(data, list):
                    LOGGER.error("LLM response is not a list")
                    return None
                return data
            except json.JSONDecodeError as json_exc:
                LOGGER.error("Failed to parse JSON from requirement analysis: %s", json_exc)
                return None
        except Exception as exc:
            LOGGER.error("Gemini requirement analysis failed: %s", exc)
            return None

