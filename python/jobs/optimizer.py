"""
Resume Optimizer — rewrites a resume to tailor it for a specific job description.

Uses OllamaClient (supports Ollama, LM Studio, and cloud fallback) to:
- Rewrite the summary section
- Reorder bullet points by relevance
- Inject missing keywords naturally
- Adjust tone
- Never fabricate experience
"""

from typing import Any

from config import get_settings
from utils.ollama_client import OllamaClient


class ResumeOptimizer:
    """Tailors a resume for a specific job description using a local LLM."""

    def __init__(self):
        self.settings = get_settings()
        self._client: OllamaClient | None = None

    def _get_client(self) -> OllamaClient:
        """Get or create the LLM client with low temperature for deterministic output."""
        if self._client is None:
            self._client = OllamaClient(temperature=0.4)
        return self._client

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
            client = self._get_client()
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert ATS resume optimizer. Use low temperature (0.3-0.4) "
                        "for deterministic output. Your task is to rewrite "
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
            ]
            content = await client.chat(messages)
            return self._parse_result(content)

        except Exception as e:
            print(f"[Optimizer] LLM optimization failed: {e}")
            return {
                "optimized_md": resume_md,
                "keywords_injected": [],
                "changes_made": ["Optimization unavailable — returned original resume"],
                "_error": str(e),
            }

    async def optimize_latex(
        self,
        resume_md: str,
        job: dict[str, Any],
        match_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Optimize a resume for a specific job, outputting structured JSON data.

        The LLM acts as a DATA-MAPPING ENGINE — it outputs ONLY a JSON object
        with structured resume fields (summary, skills, experience, education,
        projects). It does NOT write LaTeX, markdown, or any formatting.

        The JSON output is then injected into a hardcoded, pre-verified LaTeX
        template by the PDF generator. This prevents:
        - Malformed LaTeX from the LLM
        - Leaked markdown tags (###, **)
        - Stray characters or broken compilation

        Args:
            resume_md: The original resume in markdown format
            job: Job listing dict with title, company, description
            match_analysis: Optional output from JobMatcher

        Returns:
            Dict with json_data (structured JSON), keywords_injected, changes_made, _mode
        """
        prompt = self._build_latex_json_prompt(resume_md, job, match_analysis)

        try:
            client = self._get_client()
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a data-mapping engine. Your ONLY job is to extract, "
                        "rephrase, and structure resume data into a strict JSON schema.\n"
                        "CRITICAL RULES:\n"
                        "1. NEVER add skills or experience the candidate doesn't have.\n"
                        "2. Only rephrase existing experience to highlight relevant aspects.\n"
                        "3. Reorder bullet points so most relevant come first.\n"
                        "4. Inject key terms from the job description naturally into bullet points.\n"
                        "5. Keep all dates, company names, and factual information exactly.\n"
                        "6. Output ONLY a valid JSON object — no LaTeX, no markdown, "
                        "no code fences, no conversational text, no explanations.\n"
                        "7. Do NOT use \"###\", \"**\", \"*\", or any markdown formatting.\n"
                        "8. Every string value must be plain text only."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            content = await client.chat(messages)

            # Strip noise (code fences, leading/trailing whitespace)
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(lines).strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()

            import json as _json
            json_data = _json.loads(content)

            # Validate basic structure
            if not isinstance(json_data, dict):
                raise ValueError("LLM output is not a JSON object")

            return {
                "json_data": json_data,
                "keywords_injected": [],
                "changes_made": ["Resume optimized for target job via structured JSON"],
                "_mode": "latex_json",
            }

        except Exception as e:
            print(f"[Optimizer] JSON optimization failed: {e}")
            return {
                "json_data": {},
                "keywords_injected": [],
                "changes_made": ["JSON optimization unavailable, falling back to markdown"],
                "_error": str(e),
                "_mode": "latex_json_fallback",
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

    def _build_latex_json_prompt(
        self,
        resume_md: str,
        job: dict[str, Any],
        match_analysis: dict[str, Any] | None,
    ) -> str:
        """Build a prompt requesting ONLY a JSON object — no LaTeX, no markdown.

        The LLM acts as a data-mapping engine that outputs structured data
        which gets injected into a hardcoded LaTeX template by the PDF generator.
        """
        missing = ""
        if match_analysis:
            ms = match_analysis.get("missing_skills", [])
            if ms:
                missing = f"\nMissing Skills to weave in (if relevant): {', '.join(ms[:5])}"

        return f"""Job Title: {job.get('title', 'Unknown')}
Company: {job.get('company', 'Unknown')}
Job Description:
{job.get('description', '')[:1500]}
{missing}

Original Resume (markdown):
{resume_md}

---

You are a data-mapping engine. Output ONLY a JSON object with this exact schema.
Do NOT output any LaTeX, markdown, code fences, or conversational text.

{{
  "name": "Full name",
  "contact": {{
    "email": "email@example.com",
    "phone": "+1-234-567-8900",
    "linkedin": "https://linkedin.com/in/username",
    "github": "https://github.com/username"
  }},
  "summary": "A 2-3 sentence professional summary tailored to this specific job. Briefly highlight key experience, relevant technologies, and the unique value you bring.",
  "skills": ["Skill1", "Skill2", "Skill3"],
  "experience": [
    {{
      "job_title": "Fullstack Developer",
      "company": "Coinmint",
      "start_date": "Jan 2022",
      "end_date": "Present",
      "bullets": [
        "Achievement bullet rephrased to highlight relevance to this specific job. Use action verbs and include measurable impact where possible.",
        "Another bullet point focusing on the most relevant aspect of this role."
      ]
    }}
  ],
  "education": [
    {{
      "degree": "Bachelor of Computer Science",
      "institution": "University of Windsor",
      "start_date": "2018",
      "end_date": "2022"
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "description": "Brief description highlighting relevant technologies and impact."
    }}
  ]
}}

STRICT RULES:
1. NEVER add skills, experience, or projects the candidate doesn't have.
2. Rephrase existing bullet points to emphasize relevance to the target job.
3. Reorder experience/projects so the most relevant ones come first.
4. Inject job description keywords naturally into existing bullet points.
5. Keep all dates, company names, and factual information EXACTLY as in the original resume.
6. For my role at Coinmint, I was a Fullstack Developer with a heavily focused backend role.
7. Output ONLY the raw JSON object — no explanations, no markdown, no LaTeX, no code fences."""

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
