"""
BARQ Writer Agent — Generates ATS-optimized resumes and cover letters.

Takes the match analysis from MatcherAgent and:
1. Rewrites the resume summary to highlight matching skills
2. Reorders and rephrases bullet points for ATS relevance
3. Injects missing keywords naturally (without fabricating experience)
4. Generates a tailored cover letter with specific company hooks
"""

import json
import re
from typing import Any, Optional

from utils.ollama_client import OllamaClient
from .extractor import ExtractionResult
from .matcher import MatchResult


# ─── Output Schema ─────────────────────────────────────────────────────────

class WriterResult:
    """Generated documents from the WriterAgent."""

    def __init__(self, raw: dict[str, Any]):
        self.optimized_resume: str = raw.get("optimized_resume", "")
        self.cover_letter: str = raw.get("cover_letter", "")
        self.keywords_injected: list[str] = raw.get("keywords_injected", [])
        self.changes_summary: str = raw.get("changes_summary", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "optimized_resume": self.optimized_resume,
            "cover_letter": self.cover_letter,
            "keywords_injected": self.keywords_injected,
            "changes_summary": self.changes_summary,
        }


# ─── System Prompts ────────────────────────────────────────────────────────

RESUME_WRITER_PROMPT = """You are an expert ATS Resume Optimizer Agent.

Your task: Rewrite a candidate's resume to maximize ATS compatibility for a
specific job. CRITICAL RULES:
1. NEVER fabricate skills, experience, or qualifications
2. Only rephrase existing content to highlight relevance
3. Reorder bullet points so most relevant come first
4. Inject key terms from the job description naturally into existing bullets
5. Keep all dates, company names, and factual information exactly as-is
6. Output in clean markdown format

Return your response as valid JSON:
{
  "optimized_resume": "full markdown resume text",
  "keywords_injected": ["keyword1", "keyword2"],
  "changes_summary": "brief summary of what was changed"
}
"""

COVER_LETTER_WRITER_PROMPT = """You are an expert Cover Letter Writer Agent.

Write a compelling, specific cover letter (250-350 words) that:
1. Opens with a specific hook about the company or role (never "I am writing to express my interest")
2. Connects 2-3 specific resume highlights to job requirements
3. References the match analysis to address potential gaps confidently
4. Closes with a confident call to action
5. Sounds human, not robotic

Return your response as valid JSON:
{
  "cover_letter": "full cover letter text",
}
"""


# ─── Writer Agent ──────────────────────────────────────────────────────────

class WriterAgent:
    """Generates ATS-optimized resumes and cover letters using LLM."""

    def __init__(self):
        self.llm = OllamaClient()

    async def write_resume(
        self,
        extraction: ExtractionResult,
        match: MatchResult,
        resume_md: str,
    ) -> WriterResult:
        """Generate an ATS-optimized resume.

        Args:
            extraction: Structured job requirements.
            match: Match analysis from MatcherAgent.
            resume_md: Original resume in markdown format.

        Returns:
            WriterResult with optimized resume.
        """
        missing_skills_text = ", ".join(
            s.get("skill", "") for s in match.missing_skills
        ) if match.missing_skills else "None identified"

        prompt = f"""
Job: {extraction.job_title} at {extraction.company}
Must-Have Skills: {', '.join(extraction.must_have_skills)}
Missing Skills to address: {missing_skills_text}
Match Score: {match.overall_score}/100

Original Resume:
{resume_md[:3000]}

Create an ATS-optimized version of this resume tailored for the job above.
"""

        messages = [
            {"role": "system", "content": RESUME_WRITER_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.llm.chat(messages)
            text = response.strip()
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            data = json.loads(text)
            result = WriterResult({
                "optimized_resume": data.get("optimized_resume", resume_md),
                "cover_letter": "",
                "keywords_injected": data.get("keywords_injected", []),
                "changes_summary": data.get("changes_summary", "Resume optimized for target role"),
            })
            print(f"[WriterAgent] Resume optimized — {len(result.keywords_injected)} keywords injected")
            return result

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WriterAgent] Resume generation failed: {e}")
            return WriterResult({
                "optimized_resume": resume_md,
                "cover_letter": "",
                "keywords_injected": [],
                "changes_summary": "Optimization unavailable — returned original resume",
            })

        except Exception as e:
            print(f"[WriterAgent] Unexpected error: {e}")
            return WriterResult({
                "optimized_resume": resume_md,
                "cover_letter": "",
                "keywords_injected": [],
                "changes_summary": f"Error: {e}",
            })

    async def write_cover_letter(
        self,
        extraction: ExtractionResult,
        match: MatchResult,
        resume_md: str,
        optimized_resume_md: Optional[str] = None,
    ) -> str:
        """Generate a tailored cover letter.

        Args:
            extraction: Structured job requirements.
            match: Match analysis from MatcherAgent.
            resume_md: Original resume markdown.
            optimized_resume_md: Optional optimized resume for extra context.

        Returns:
            Cover letter text.
        """
        context_resume = optimized_resume_md or resume_md
        top_skills = ", ".join(extraction.must_have_skills[:5])
        matching = ", ".join(match.matching_skills[:5])
        actions = "; ".join(match.recommended_actions[:3])

        prompt = f"""
Company: {extraction.company}
Role: {extraction.job_title}
Key Skills Required: {top_skills}
Matching Skills: {matching}
Key Actions Needed: {actions}
Match Score: {match.overall_score}/100
Fit Summary: {match.fit_summary}

Resume Context:
{context_resume[:2000]}

Write a compelling cover letter for this position.
"""

        messages = [
            {"role": "system", "content": COVER_LETTER_WRITER_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.llm.chat(messages)
            text = response.strip()
            text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
            data = json.loads(text)
            letter = data.get("cover_letter", text)
            print(f"[WriterAgent] Cover letter written ({len(letter)} chars)")
            return letter

        except (json.JSONDecodeError, KeyError):
            # Response might be plain text, not JSON — use as-is
            cleaned = response.strip() if response else ""
            cleaned = re.sub(r"```(?:json)?", "", cleaned).strip().rstrip("`").strip()
            if cleaned and len(cleaned) > 50:
                return cleaned
            return self._fallback_letter(extraction)

        except Exception as e:
            print(f"[WriterAgent] Cover letter error: {e}")
            return self._fallback_letter(extraction)

    def _fallback_letter(self, extraction: ExtractionResult) -> str:
        return f"""Dear Hiring Manager at {extraction.company or 'the company'},

I am excited to apply for the {extraction.job_title or 'open'} position. My background and skills align well with the requirements outlined in the job description, and I am eager to contribute to your team.

Throughout my career, I have developed relevant experience in {', '.join(extraction.must_have_skills[:3]) or 'key areas'} that would allow me to hit the ground running in this role.

I would welcome the opportunity to discuss how my background aligns with your needs. Thank you for your consideration.

Best regards,
[Your Name]"""
