"""
AIResumeBridge — HTTP client for AI_Resume_Generator's /api/generate-pdf endpoint.

Converts BARQ's candidate profile into the AI_Resume_Generator's ResumeData JSON
schema and POSTs to the Next.js server's PDF generation API.

Requirements:
  - AI_Resume_Generator Next.js server running (default: http://127.0.0.1:3000)
  - The server must have GOOGLE_GENERATIVE_AI_API_KEY set (for /api/generate),
    but /api/generate-pdf only needs the PDF runtime, not the AI key.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from ..config import CONFIG, PROFILE

logger = logging.getLogger("barq.auto_applier.resume.bridge")

DEFAULT_AI_RESUME_PORT = 3000
DEFAULT_TIMEOUT_SECONDS = 30

# ─── Schema Mapper ──────────────────────────────────────────────────────────


def _to_resume_data_schema(
    job_description: str = "",
    template: str = "modern",
) -> dict[str, Any]:
    """Convert BARQ's profile + job context to AI_Resume_Generator's ResumeData JSON schema.

    The AI_Resume_Generator expects:
    {
      personalInfo: { fullName, email, phone, location, linkedIn, website, summary },
      education: [{ id, institution, degree, field, startDate, endDate, gpa, description }],
      experience: [{ id, company, position, location, startDate, endDate, current, bulletPoints }],
      skills: [{ id, name, level: "beginner"|"intermediate"|"advanced"|"expert", category }],
      template: "modern"|"classic"|"minimal"
    }
    """
    import random
    import string

    def _gen_id() -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=9))

    # ── Personal Info ──────────────────────────────────────────────────
    personal_info = {
        "fullName": PROFILE.full_name,
        "email": PROFILE.email,
        "phone": PROFILE.phone or "",
        "location": "",
        "linkedIn": PROFILE.linkedin_url,
        "website": PROFILE.github_url,
        "summary": PROFILE.summary,
    }

    # ── Education ──────────────────────────────────────────────────────
    education = []
    edu_text = PROFILE.education  # "Bachelor of Computer Science, University of Windsor (2024)"
    parts = edu_text.split(", ")
    degree_text = parts[0] if len(parts) > 0 else ""
    institution_text = parts[1] if len(parts) > 1 else ""

    education.append({
        "id": _gen_id(),
        "institution": institution_text,
        "degree": degree_text,
        "field": "Computer Science",
        "startDate": "2020",
        "endDate": "2024",
        "gpa": "",
        "description": "Bachelor of Computer Science graduate",
    })

    # ── Experience ─────────────────────────────────────────────────────
    experience = []
    for exp in PROFILE.experiences:
        bullet_points = exp.get("highlights", exp.get("bullets", []))
        # Parse period into start/end dates
        period = exp.get("period", "")
        dates = period.split(" – ")
        start = dates[0] if len(dates) > 0 else ""
        end = dates[1] if len(dates) > 1 else ""
        is_current = "Present" in end or "present" in end

        experience.append({
            "id": _gen_id(),
            "company": exp.get("company", ""),
            "position": exp.get("role", ""),
            "location": "",
            "startDate": start,
            "endDate": end if not is_current else "",
            "current": is_current,
            "bulletPoints": bullet_points,
        })

    # ── Skills ──────────────────────────────────────────────────────────
    # Map skills to categories based on keywords
    category_map: dict[str, list[str]] = {
        "Languages": [".NET", "C#", "Python", "TypeScript", "JavaScript", "HTML5", "CSS3", "SQL"],
        "Frameworks & Libraries": ["React.js", "Angular", "Node.js"],
        "Databases": ["PostgreSQL", "MongoDB"],
        "Tools & Platforms": ["AWS", "Docker", "Kubernetes", "CI/CD"],
        "Soft Skills": ["System Design", "Agile/Scrum", "OOP"],
    }

    skills = []
    for skill in PROFILE.skills:
        assigned_category = "Other"
        for cat, candidates in category_map.items():
            if any(c.lower() in skill.lower() for c in candidates):
                assigned_category = cat
                break

        skills.append({
            "id": _gen_id(),
            "name": skill,
            "level": "advanced",
            "category": assigned_category,
        })

    # Include job description in the data for context
    data: dict[str, Any] = {
        "personalInfo": personal_info,
        "education": education,
        "experience": experience,
        "skills": skills,
        "template": template,
    }

    if job_description:
        data["jobDescriptions"] = [job_description]

    return data


# ─── HTTP Bridge ────────────────────────────────────────────────────────────


class AIResumeBridge:
    """HTTP client for AI_Resume_Generator's PDF generation endpoint.

    Usage:
        bridge = AIResumeBridge(host="127.0.0.1", port=3000)
        pdf_bytes = await bridge.generate_pdf(job_description="...", template="modern")
        if pdf_bytes:
            path = await bridge.save_pdf(pdf_bytes, output_dir=...)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_AI_RESUME_PORT,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def is_server_running(self) -> bool:
        """Check if the AI_Resume_Generator Next.js server is reachable."""
        try:
            resp = await self._http.get(f"{self._base_url}/api/check-key", timeout=5)
            return resp.status_code < 500  # 200, 503 (key missing) both mean server is up
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return False

    async def generate_pdf(
        self,
        job_description: str = "",
        template: str = "modern",
    ) -> Optional[bytes]:
        """Generate a PDF via AI_Resume_Generator's /api/generate-pdf.

        Args:
            job_description: Raw job description text for context (optional).
            template: One of "modern", "classic", "minimal".

        Returns:
            Raw PDF bytes, or None if the server is unreachable or errors.
        """
        try:
            # Check server availability first
            if not await self.is_server_running():
                logger.info("AI_Resume_Generator server not reachable at %s", self._base_url)
                return None

            # Convert BARQ profile to AI_Resume_Generator schema
            payload = _to_resume_data_schema(
                job_description=job_description,
                template=template,
            )

            logger.info(
                "Calling AI_Resume_Generator /api/generate-pdf (template=%s, %d skills, %d exp entries)",
                template,
                len(payload.get("skills", [])),
                len(payload.get("experience", [])),
            )

            resp = await self._http.post(
                f"{self._base_url}/api/generate-pdf",
                json=payload,
                timeout=self._timeout,
            )

            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if "application/pdf" in content_type or len(resp.content) > 200:
                    logger.info("PDF generated successfully (%d bytes)", len(resp.content))
                    return resp.content
                else:
                    logger.warning(
                        "AI_Resume_Generator returned non-PDF response (status=%d, type=%s)",
                        resp.status_code,
                        content_type,
                    )
                    return None
            else:
                logger.warning(
                    "AI_Resume_Generator PDF endpoint failed (status=%d): %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None

        except httpx.TimeoutException:
            logger.warning("AI_Resume_Generator PDF endpoint timed out")
            return None
        except Exception as exc:
            logger.warning("AI_Resume_Generator bridge error: %s", exc)
            return None

    async def save_pdf(
        self,
        pdf_bytes: bytes,
        output_dir: str | Path,
        filename: str = "tailored_resume.pdf",
    ) -> Optional[str]:
        """Save generated PDF bytes to disk.

        Args:
            pdf_bytes: Raw PDF bytes from generate_pdf().
            output_dir: Directory to save the PDF.
            filename: Output filename.

        Returns:
            Absolute path to saved PDF, or None on failure.
        """
        try:
            output_path = Path(output_dir) / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(pdf_bytes)
            logger.info("Saved AI_Resume_Generator PDF: %s", output_path)
            return str(output_path.resolve())
        except Exception as exc:
            logger.warning("Failed to save AI_Resume_Generator PDF: %s", exc)
            return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
