"""
Cover Letter Generator — creates tailored cover letters for specific jobs.

Uses Ollama to generate 250-350 word cover letters with:
- Specific company hook (not generic)
- 2-3 paragraphs connecting resume highlights to JD requirements
- Confident call to action
- Professional but personable tone
"""

from typing import Any

from config import get_settings


class CoverLetterGenerator:
    """Generates tailored cover letters using local LLM."""

    def __init__(self):
        self.settings = get_settings()

    async def generate(
        self,
        job: dict[str, Any],
        resume: dict[str, Any],
        optimized_resume: str | None = None,
    ) -> str:
        """
        Generate a tailored cover letter.

        Args:
            job: Job listing details (title, company, description)
            resume: Parsed resume data
            optimized_resume: Optional optimized resume markdown for extra context

        Returns:
            Cover letter text (250-350 words)
        """
        resume_text = optimized_resume or resume.get("raw_md", "")
        prompt = self._build_prompt(job, resume_text)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert cover letter writer. Write compelling, "
                            "professional cover letters that are specific (never generic). "
                            "Each letter should:\n"
                            "1. Open with a specific hook about the company or role\n"
                            "2. Connect 2-3 specific resume highlights to JD requirements\n"
                            "3. Close with a confident call to action\n"
                            "4. Be 250-350 words\n"
                            "5. Never use 'I am writing to express my interest'\n"
                            "6. Sound human, not robotic"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.5},
            )

            return response["message"]["content"].strip()

        except Exception as e:
            print(f"[CoverLetter] Generation failed: {e}")
            return self._fallback(job)

    def _build_prompt(self, job: dict[str, Any], resume_text: str) -> str:
        return f"""
Job: {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}
Description: {job.get('description', '')[:1000]}

Resume:
{resume_text[:2000]}

Write a cover letter for this position.
"""

    def _fallback(self, job: dict[str, Any]) -> str:
        return f"""Dear Hiring Manager at {job.get('company', 'the company')},

I am excited to apply for the {job.get('title', 'open')} position. My background and skills align well with what you are looking for, and I am eager to contribute to your team.

Throughout my career, I have developed relevant experience that would allow me to hit the ground running in this role. I am particularly drawn to {job.get('company', 'your company')}'s mission and would be honored to contribute.

I would welcome the opportunity to discuss how my background aligns with your needs. Thank you for your consideration.

Best regards,
[Your Name]"""
