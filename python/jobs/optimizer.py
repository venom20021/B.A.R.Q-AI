"""
Resume Optimizer — rewrites a resume to tailor it for a specific job description.

Uses Ollama to:
- Rewrite the summary section
- Reorder bullet points by relevance
- Inject missing keywords naturally
- Adjust tone
- Never fabricate experience
"""

from typing import Any

from config import get_settings


class ResumeOptimizer:
    """Tailors a resume for a specific job description using a local LLM."""

    def __init__(self):
        self.settings = get_settings()

    async def optimize(
        self,
        resume_md: str,
        job: dict[str, Any],
        match_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Optimize a resume for a specific job.

        Args:
            resume_md: The original resume in markdown format
            job: Job listing dict with title, company, description
            match_analysis: Optional output from JobMatcher

        Returns:
            Dict with optimized_md, keywords_injected, changes_made
        """
        prompt = self._build_prompt(resume_md, job, match_analysis)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert ATS resume optimizer. Your task is to rewrite "
                            "a resume to better match a specific job description. "
                            "CRITICAL RULES:\n"
                            "1. NEVER add skills or experience the candidate doesn't have\n"
                            "2. Only rephrase existing experience to highlight relevant aspects\n"
                            "3. Reorder bullet points so most relevant come first\n"
                            "4. Inject key terms from the job description naturally into bullet points\n"
                            "5. Keep all dates, company names, and factual information exactly\n"
                            "6. Output in clear markdown format"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.4},
            )

            content = response["message"]["content"]
            return self._parse_result(content)

        except Exception as e:
            print(f"[Optimizer] LLM optimization failed: {e}")
            return {
                "optimized_md": resume_md,
                "keywords_injected": [],
                "changes_made": ["Optimization unavailable — returned original resume"],
                "_error": str(e),
            }

    def _build_prompt(
        self,
        resume_md: str,
        job: dict[str, Any],
        match_analysis: dict[str, Any] | None,
    ) -> str:
        missing = ""
        if match_analysis:
            ms = match_analysis.get("missing_skills", [])
            if ms:
                missing = f"\nMissing Skills to weave in (if relevant): {', '.join(ms[:5])}"

        return f"""
Job Title: {job.get('title', 'Unknown')}
Company: {job.get('company', 'Unknown')}
Job Description:
{job.get('description', '')[:1500]}
{missing}

Original Resume:
{resume_md}

Please create an optimized version of this resume that:

1. Rewrites the summary/profile section to emphasize experience relevant to this role
2. Reorders bullet points in each role so the most relevant ones come first
3. Naturally incorporates relevant keywords from the job description into existing bullet points
4. Adjusts the tone to match the company style (startup vs enterprise)
5. Adds a "Relevant Skills" section highlighting exact matches

Format your response as:

## Keywords Injected
- keyword1
- keyword2

## Changes Made
- change1
- change2

## Optimized Resume
[Full resume markdown here]
"""

    def _parse_result(self, content: str) -> dict[str, Any]:
        """Parse the LLM response into structured data."""
        keywords = []
        changes = []
        optimized_md = content

        # Extract keywords section
        kw_section = self._extract_section(content, "Keywords Injected", "Changes Made")
        if kw_section:
            keywords = [
                line.strip("-* ").strip()
                for line in kw_section.strip().split("\n")
                if line.strip().startswith("-")
            ]

        # Extract changes section
        ch_section = self._extract_section(content, "Changes Made", "Optimized Resume")
        if ch_section:
            changes = [
                line.strip("-* ").strip()
                for line in ch_section.strip().split("\n")
                if line.strip().startswith("-")
            ]

        # Extract optimized resume
        opt_marker = "## Optimized Resume"
        if opt_marker in content:
            optimized_md = content[content.index(opt_marker) + len(opt_marker):].strip()
            # Remove leading/trailing code fences
            optimized_md = optimized_md.strip("`").strip()

        return {
            "optimized_md": optimized_md,
            "keywords_injected": keywords,
            "changes_made": changes if changes else ["Resume optimized for target job"],
        }

    @staticmethod
    def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
        """Extract text between two section markers."""
        start = text.find(f"## {start_marker}")
        if start == -1:
            start = text.find(f"# {start_marker}")
        if start == -1:
            return ""

        end = text.find(f"## {end_marker}", start + 1)
        if end == -1:
            end = text.find(f"# {end_marker}", start + 1)
        if end == -1:
            end = len(text)

        return text[start:end].strip()
