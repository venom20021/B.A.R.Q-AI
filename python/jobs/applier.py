"""
Generative job applications - creates ATS-friendly resumes and cover letters.
Supports Playwright-based auto-fill for common ATS platforms.
"""

import json
import os
from pathlib import Path
from typing import Any

from config import get_settings

from .pdf_generator import ResumePDFGenerator

# ATS platform signatures for form detection
ATS_SIGNATURES = {
    "greenhouse": ["greenhouse.io", "boards.greenhouse.io", "grnh.se"],
    "lever": ["lever.co", "jobs.lever.co"],
    "workday": ["myworkdayjobs.com", "workday.com"],
    "ashby": ["ashbyhq.com", "jobs.ashbyhq.com"],
    "bamboo": ["bamboohr.com"],
    "smartrecruiters": ["smartrecruiters.com"],
}


class JobApplier:
    """Generates tailored applications for matched jobs."""

    def __init__(self):
        self.settings = get_settings()

    async def generate_resume(
        self, job: dict[str, Any], user_profile: dict[str, Any]
    ) -> str:
        """Generate an ATS-optimized resume tailored to a specific job."""
        prompt = self._build_resume_prompt(job, user_profile)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert resume writer specializing in ATS-optimized "
                            "resumes. Create a tailored resume that highlights the most relevant "
                            "experience and skills for the specific job. Use markdown format."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.4},
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"[Applier] Resume generation failed: {e}")
            return self._fallback_resume(user_profile)

    async def generate_cover_letter(
        self, job: dict[str, Any], user_profile: dict[str, Any]
    ) -> str:
        """Generate a tailored cover letter for a specific job."""
        prompt = self._build_cover_letter_prompt(job, user_profile)
        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {"role": "system", "content": "You are an expert cover letter writer."},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.5},
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"[Applier] Cover letter generation failed: {e}")
            return self._fallback_cover_letter(job)

    # ─── Playwright ATS Auto-Fill ───────────────────────────────────────

    async def auto_fill_application(
        self,
        job_url: str,
        user_profile: dict[str, Any],
        resume_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Use Playwright to navigate to a job URL, detect the ATS platform,
        auto-fill the form, and take a screenshot WITHOUT submitting.

        Args:
            job_url: URL of the job posting or application page
            user_profile: User's personal and professional information
            resume_path: Optional path to resume file for upload fields

        Returns:
            Dict with filled_fields, detected_platform, screenshot_path, form_data
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "status": "unavailable",
                "message": "Playwright not installed. Run: pip install playwright && playwright install chromium",
                "filled_fields": {},
                "detected_platform": "unknown",
                "screenshot_path": "",
            }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Detect ATS platform
                current_url = page.url.lower()
                platform = self._detect_platform(current_url)

                # Find and fill form fields
                filled = await self._fill_form_fields(page, user_profile, platform)

                # Upload resume if there's a file field
                if resume_path and os.path.exists(resume_path):
                    await self._upload_resume(page, resume_path)

                # Screenshot for user review
                screenshot_dir = Path(os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "generated", "screenshots"
                ))
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = str(screenshot_dir / f"application_{hash(job_url)}.png")
                await page.screenshot(path=screenshot_path, full_page=True)

                await browser.close()

                return {
                    "status": "completed",
                    "message": "Form filled. Review screenshot before manual submission.",
                    "detected_platform": platform,
                    "filled_fields": filled,
                    "screenshot_path": screenshot_path,
                    "job_url": current_url,
                }

            except Exception as e:
                await browser.close()
                return {
                    "status": "error",
                    "message": f"Playwright auto-fill failed: {e}",
                    "filled_fields": {},
                    "detected_platform": "unknown",
                    "screenshot_path": "",
                }

    def _detect_platform(self, url: str) -> str:
        """Detect the ATS platform from the URL."""
        for platform, signatures in ATS_SIGNATURES.items():
            for sig in signatures:
                if sig in url:
                    return platform
        return "unknown"

    async def _fill_form_fields(
        self, page, user_profile: dict[str, Any], platform: str
    ) -> dict[str, str]:
        """Auto-detect and fill form fields on the page."""
        filled = {}

        # Common field selectors across ATS platforms
        field_selectors = {
            "name": ["input#name", "input#full_name", "input[name='name']", "input[aria-label*='name' i]",
                     "[data-qa*='name'] input", ".application-field input[name*='name']"],
            "email": ["input#email", "input[type='email']", "input[name='email']",
                      "input[aria-label*='email' i]", "[data-qa*='email'] input"],
            "phone": ["input#phone", "input[type='tel']", "input[name='phone']",
                      "input[name='phoneNumber']", "input[aria-label*='phone' i]"],
            "linkedin": ["input[name='linkedin']", "input[aria-label*='linkedin' i]",
                         "input[placeholder*='linkedin' i]"],
            "portfolio": ["input[name='portfolio']", "input[name='website']",
                          "input[aria-label*='portfolio' i]", "input[aria-label*='website' i]"],
        }

        field_values = {
            "name": user_profile.get("full_name", ""),
            "email": user_profile.get("email", ""),
            "phone": user_profile.get("phone", ""),
            "linkedin": user_profile.get("linkedin_url", ""),
            "portfolio": user_profile.get("portfolio_url", ""),
        }

        for field_type, selectors in field_selectors.items():
            value = field_values.get(field_type, "")
            if not value:
                continue

            for selector in selectors:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        await el.fill(value)
                        filled[field_type] = value
                        print(f"[Applier] Filled {field_type}: {value}")
                        break
                except Exception:
                    continue

        return filled

    async def _upload_resume(self, page, resume_path: str):
        """Upload resume file to file input fields."""
        file_selectors = [
            "input[type='file']",
            "input[name='resume']",
            "input[accept*='pdf']",
            "input[accept*='doc']",
            "[data-qa*='resume'] input[type='file']",
        ]
        for selector in file_selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    await el.set_input_files(resume_path)
                    print(f"[Applier] Uploaded resume to {selector}")
                    return
            except Exception:
                continue

    async def fill_application_form(
        self, form_fields: list[dict[str, Any]], user_profile: dict[str, Any]
    ) -> dict[str, str]:
        """
        Auto-fill application form fields based on user profile (legacy method).

        Args:
            form_fields: List of form field definitions
            user_profile: User's personal and professional information

        Returns:
            Dict mapping field names to values
        """
        filled = {}
        for field in form_fields:
            field_name = field.get("name", "").lower()

            if "name" in field_name and "full" in field_name:
                filled[field["name"]] = user_profile.get("full_name", "")
            elif "email" in field_name:
                filled[field["name"]] = user_profile.get("email", "")
            elif "phone" in field_name:
                filled[field["name"]] = user_profile.get("phone", "")
            elif "linkedin" in field_name:
                filled[field["name"]] = user_profile.get("linkedin_url", "")
            elif "portfolio" in field_name or "website" in field_name:
                filled[field["name"]] = user_profile.get("portfolio_url", "")
            elif "resume" in field_name or "cv" in field_name:
                filled[field["name"]] = "Uploaded automatically"
            elif "cover" in field_name:
                filled[field["name"]] = "Generated automatically"
            else:
                filled[field["name"]] = ""

        return filled

    def _build_resume_prompt(self, job: dict[str, Any], profile: dict[str, Any]) -> str:
        return f"""
Job: {job.get('title')} at {job.get('company')}
Description: {job.get('description', '')[:500]}
Skills: {', '.join(profile.get('skills', []))}
Experience: {json.dumps(profile.get('experience', []), indent=2)}
Education: {json.dumps(profile.get('education', []), indent=2)}

Create an ATS-optimized resume that:
1. Uses relevant keywords from the job description
2. Highlights matching experience first
3. Uses a clean, parsable format
4. Keeps to one page
"""

    def _build_cover_letter_prompt(self, job: dict[str, Any], profile: dict[str, Any]) -> str:
        return f"""
Job: {job.get('title')} at {job.get('company')}
Description: {job.get('description', '')[:500]}

Write a professional cover letter that:
1. Opens with enthusiasm for the role
2. Highlights 2-3 key relevant achievements
3. Explains why the user is a great fit
4. Closes with a call to action
Keep it to 3-4 paragraphs.
"""

    async def generate_resume_pdf(
        self,
        job: dict[str, Any],
        user_profile: dict[str, Any],
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a tailored resume AND compile it to PDF.

        Args:
            job: Job listing details (title, company, description)
            user_profile: User's resume/profile data
            output_dir: Optional output directory for the PDF

        Returns:
            Dict with pdf_path, backend_used, and the resume text
        """
        # Generate the resume text via LLM
        resume_md = await self.generate_resume(job, user_profile)

        # Add the generated resume text to user_profile for PDF compilation
        pdf_profile = {**user_profile, "raw_md": resume_md}

        # Generate PDF
        generator = ResumePDFGenerator()
        result = await generator.generate(pdf_profile, output_dir)
        result["resume_text"] = resume_md
        return result

    def _fallback_resume(self, profile: dict[str, Any]) -> str:
        skills = "\n".join(f"- {s}" for s in profile.get("skills", []))
        return f"""# {profile.get('full_name', 'Unknown')}

## Skills
{skills}

## Experience
{profile.get('experience', 'Experience details not available')}
"""

    def _fallback_cover_letter(self, job: dict[str, Any]) -> str:
        return f"""Dear Hiring Manager,

I am writing to express my strong interest in the {job.get('title')} position at {job.get('company')}.

I am confident that my skills and experience make me an excellent candidate for this role.

Thank you for your consideration.

Best regards,
[Your Name]
"""
