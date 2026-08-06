"""
BARQ EvaluatorAgent — Reflection / Evaluator-Optimizer pattern.

Wraps the job-application and resume pipeline with a quality gate:

    generate → evaluate (secondary LLM, against the Job Description)
           → below threshold? → revise → re-evaluate (up to N iterations)
           → pass → continue to PDF / Telegram

Critical guardrails preserved from the existing pipeline:
- NEVER fabricate skills, experience, or projects.
- Keep all dates, company names, and factual information exactly.
- Preserve the candidate's established profile framing (Fullstack
  Development with a strong backend focus in .NET and Python).
- All LLM calls go through ``OllamaClient`` (local Ollama with the
  existing cloud fallback) — identical to the rest of the pipeline.

Usage:
    evaluator = EvaluatorAgent(threshold=80, max_iterations=2)
    result = await evaluator.ensure_resume_markdown(optimized_md, resume_md, job, optimizer, match_analysis)
    result = await evaluator.ensure_cover_letter(cover_letter, job, resume)
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from utils.ollama_client import OllamaClient

# ─── Profile framing rules — MUST survive every revision ────────────────────

PROFILE_RULES = (
    "CRITICAL PROFILE RULES (never violate):\n"
    "1. The candidate is a Fullstack Developer with a strong BACKEND focus in "
    ".NET (Core) and Python. Frame experience accordingly when the job allows.\n"
    "2. NEVER add skills, experience, projects, or achievements that are not "
    "present in the original resume.\n"
    "3. Keep all dates, company names, job titles, and factual information "
    "EXACTLY as they appear in the original resume.\n"
    "4. Rephrase and reorder existing bullets to emphasize relevance — never invent."
)

EVALUATOR_SYSTEM_PROMPT = """You are a senior ATS resume reviewer. Your job is to evaluate
how well a tailored document matches a target job description and produce a
STRICT, honest quality score.

Rules:
- Score 0-100 based on: keyword/skill coverage, relevance of bullets, ATS
  parsability, and factual integrity (never reward fabricated content).
- Penalize fabrication, generic filler, and missing critical keywords.
- Never suggest adding experience the candidate does not have.

Output ONLY valid JSON with this exact schema:
{
  "score": 85,
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "missing_keywords": ["...", "..."],
  "feedback": ["concrete, actionable revision instruction 1", "..."]
}
Feedback must be specific enough for a revision pass (e.g. 'Add a summary
sentence covering .NET Core + AWS + Python' or 'Reorder bullets so backend
microservices work is listed first')."""

REVISOR_SYSTEM_PROMPT = f"""You are an expert ATS resume optimizer performing a REVISION pass.
Apply the evaluator's feedback to improve the document's match score.

{PROFILE_RULES}

Output ONLY the revised document text (markdown for resumes, plain text
for cover letters). No commentary, no code fences."""


class EvaluatorAgent:
    """Reflection / evaluator-optimizer loop for job documents."""

    def __init__(
        self,
        threshold: int = 80,
        max_iterations: int = 2,
        client: Optional[OllamaClient] = None,
    ):
        self.threshold = int(threshold)
        self.max_iterations = max(int(max_iterations), 1)
        self._client = client

    def _get_client(self) -> OllamaClient:
        if self._client is None:
            self._client = OllamaClient(temperature=0.2)
        return self._client

    # ── Evaluation ────────────────────────────────────────────────────

    async def evaluate(
        self,
        document: str,
        job: dict[str, Any],
        doc_type: str = "resume",
    ) -> dict[str, Any]:
        """Evaluate a document against the job description with a secondary LLM.

        Returns:
            dict with score, passed, strengths, weaknesses, missing_keywords, feedback
        """
        job_title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        job_description = job.get("description", "")

        prompt = f"""Job Title: {job_title}
Company: {company}
Document type: {doc_type}

Job Description:
{job_description[:2500]}

Document to evaluate:
{document[:4000]}

Evaluate the match quality. Output ONLY the JSON object."""

        try:
            messages = [
                {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await self._get_client().chat(messages)
            data = self._parse_json(response)
        except Exception as e:
            print(f"[EvaluatorAgent] Evaluation failed: {e}")
            data = {}

        score = float(data.get("score", 0) or 0)
        feedback = data.get("feedback") or data.get("weaknesses") or []
        if isinstance(feedback, str):
            feedback = [feedback]

        return {
            "score": round(score, 1),
            "passed": score >= self.threshold,
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "missing_keywords": data.get("missing_keywords", []),
            "feedback": [str(f) for f in feedback][:6],
            "doc_type": doc_type,
        }

    # ── Revision ──────────────────────────────────────────────────────

    async def revise(
        self,
        current: str,
        original: str,
        job: dict[str, Any],
        feedback: list[str],
        doc_type: str = "resume",
    ) -> str:
        """Revise a document based on evaluator feedback (preserving profile rules)."""
        job_title = job.get("title", "Unknown")
        job_description = job.get("description", "")

        feedback_text = "\n".join(f"- {f}" for f in feedback)
        prompt = f"""Job Title: {job_title}
Job Description:
{job_description[:2500]}

Evaluator feedback to address:
{feedback_text}

Original resume (facts — do not fabricate beyond this):
{original[:4000] if original else '(not provided)'}

Current document to revise:
{current[:4000]}

Revise the current document to address ALL feedback items. Output ONLY the
revised document."""

        try:
            messages = [
                {"role": "system", "content": REVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await self._get_client().chat(messages)
            revised = response.strip()
            # Strip code fences if the LLM wrapped output
            if revised.startswith("```"):
                revised = re.sub(r"```[a-zA-Z]*", "", revised).strip().strip("`").strip()
            return revised if len(revised) > 50 else current
        except Exception as e:
            print(f"[EvaluatorAgent] Revision failed: {e}")
            return current

    # ── Orchestrated loops ────────────────────────────────────────────

    async def ensure_resume_markdown(
        self,
        optimized_md: str,
        resume_md: str,
        job: dict[str, Any],
        optimizer: Any,
        match_analysis: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Evaluate + revise a markdown resume until it passes or iterations exhaust.

        Uses the provided ``optimizer`` (ResumeOptimizer) to regenerate with
        feedback so the revision stays inside the existing optimization path.
        """
        history: list[dict[str, Any]] = []
        current = optimized_md

        for iteration in range(1, self.max_iterations + 1):
            evaluation = await self.evaluate(current, job, doc_type="resume")
            history.append(evaluation)
            if evaluation["passed"]:
                break
            if not evaluation["feedback"]:
                break

            print(f"[EvaluatorAgent] Resume below {self.threshold}% "
                  f"(score {evaluation['score']}) — revising (iter {iteration})")
            try:
                result = await optimizer.optimize(
                    resume_md,
                    job,
                    match_analysis,
                    feedback="\n".join(f"- {f}" for f in evaluation["feedback"]),
                )
                revised = result.get("optimized_md", current)
                current = revised if revised and len(revised) > 50 else current
            except Exception as e:
                print(f"[EvaluatorAgent] Optimizer revise failed: {e}")
                break

        return {
            "final_document": current,
            "passed": evaluation["passed"],
            "final_score": evaluation["score"],
            "iterations": len(history),
            "history": history,
            "revised": current != optimized_md,
        }

    async def ensure_resume_json(
        self,
        json_data: Optional[dict],
        resume_md: str,
        job: dict[str, Any],
        optimizer: Any,
        match_analysis: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Evaluate + regenerate structured JSON resumes (LaTeX/PDF path)."""
        if not json_data:
            return {"final_json": None, "passed": True, "iterations": 0,
                    "history": [], "revised": False}

        current_json = json_data
        history: list[dict[str, Any]] = []

        for iteration in range(1, self.max_iterations + 1):
            # Serialize JSON to readable text for the evaluator
            doc_text = json.dumps(current_json, indent=1, ensure_ascii=False)
            evaluation = await self.evaluate(doc_text, job, doc_type="resume_json")
            history.append(evaluation)
            if evaluation["passed"]:
                break
            if not evaluation["feedback"]:
                break

            print(f"[EvaluatorAgent] JSON resume below {self.threshold}% "
                  f"(score {evaluation['score']}) — re-mapping (iter {iteration})")
            try:
                result = await optimizer.optimize_latex(
                    resume_md,
                    job,
                    match_analysis,
                    feedback="\n".join(f"- {f}" for f in evaluation["feedback"]),
                )
                if result.get("_mode") == "latex_json" and result.get("json_data"):
                    current_json = result["json_data"]
                else:
                    break
            except Exception as e:
                print(f"[EvaluatorAgent] JSON revise failed: {e}")
                break

        return {
            "final_json": current_json,
            "passed": evaluation["passed"],
            "final_score": evaluation["score"],
            "iterations": len(history),
            "history": history,
            "revised": current_json != json_data,
        }

    async def ensure_cover_letter(
        self,
        cover_letter: str,
        job: dict[str, Any],
        resume: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Evaluate + revise a cover letter until it passes or iterations exhaust."""
        history: list[dict[str, Any]] = []
        current = cover_letter
        resume_text = self._resume_to_text(resume) if resume else ""

        for iteration in range(1, self.max_iterations + 1):
            evaluation = await self.evaluate(current, job, doc_type="cover_letter")
            history.append(evaluation)
            if evaluation["passed"]:
                break
            if not evaluation["feedback"]:
                break

            print(f"[EvaluatorAgent] Cover letter below {self.threshold}% "
                  f"(score {evaluation['score']}) — revising (iter {iteration})")
            revised = await self.revise(
                current, resume_text, job, evaluation["feedback"], doc_type="cover_letter"
            )
            current = revised if revised and len(revised) > 50 else current

        return {
            "final_document": current,
            "passed": evaluation["passed"],
            "final_score": evaluation["score"],
            "iterations": len(history),
            "history": history,
            "revised": current != cover_letter,
        }

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        return json.loads(text)

    @staticmethod
    def _resume_to_text(resume: dict[str, Any]) -> str:
        """Flatten parsed resume dict into readable text for revision prompts."""
        lines: list[str] = []
        for key in ("full_name", "headline", "summary"):
            if resume.get(key):
                lines.append(f"{key.replace('_', ' ').title()}: {resume[key]}")
        if resume.get("skills"):
            skills = resume["skills"]
            lines.append("Skills: " + (", ".join(skills) if isinstance(skills, list) else str(skills)))
        for section, label in (("experience", "Experience"), ("projects", "Projects"),
                               ("education", "Education")):
            items = resume.get(section) or []
            if items:
                lines.append(f"\n{label}:")
                for item in items[:5]:
                    if isinstance(item, dict):
                        title = item.get("role") or item.get("job_title") or item.get("degree") or item.get("name", "")
                        company = item.get("company", "")
                        dates = item.get("date_range") or item.get("start_date", "")
                        line = f"  {title}"
                        if company:
                            line += f" @ {company}"
                        if dates:
                            line += f" ({dates})"
                        lines.append(line)
                        for b in (item.get("bullets") or [])[:4]:
                            lines.append(f"    * {b}")
        return "\n".join(lines)
