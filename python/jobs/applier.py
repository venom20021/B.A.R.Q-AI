"""
Generative job applications - creates ATS-friendly resumes and cover letters.
"""

import json
from typing import Any

from config import get_settings


class JobApplier:
    """Generates tailored applications for matched jobs."""

    def __init__(self):
        self.settings = get_settings()

    async def generate_resume(
        self, job: dict[str, Any], user_profile: dict[str, Any]
    ) -> str:
        """
        Generate an ATS-optimized resume tailored to a specific job.

        Args:
            job: Job listing details
            user_profile: User's skills, experience, education

        Returns:
            Markdown-formatted resume tailored to the job
        """
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
        """
        Generate a tailored cover letter for a specific job.

        Args:
            job: Job listing details
            user_profile: User's background and motivation

        Returns:
            Cover letter text
        """
        prompt = self._build_cover_letter_prompt(job, user_profile)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert cover letter writer. Write compelling, "
                            "professional cover letters that highlight relevant experience "
                            "and enthusiasm for the role."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.5},
            )

            return response["message"]["content"]

        except Exception as e:
            print(f"[Applier] Cover letter generation failed: {e}")
            return self._fallback_cover_letter(job)

    async def fill_application_form(
        self, form_fields: list[dict[str, Any]], user_profile: dict[str, Any]
    ) -> dict[str, str]:
        """
        Auto-fill application form fields based on user profile.

        Args:
            form_fields: List of form field definitions
            user_profile: User's personal and professional information

        Returns:
            Dict mapping field names to values
        """
        filled = {}
        for field in form_fields:
            field_name = field.get("name", "").lower()
            field_type = field.get("type", "text")

            # Map common fields
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
