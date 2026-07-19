"""
DynamicResumeBuilder — generates a tailored resume PDF for a specific job description.

3-tier fallback architecture:
  1. PRIMARY — BARQ's native pipeline
       ResumeOptimizer (Ollama) → ResumePDFGenerator (LaTeX/fpdf)
  2. FALLBACK — AI_Resume_Generator HTTP bridge
       POST to /api/generate-pdf (3 templates: modern/classic/minimal)
  3. STATIC — ./data/base_resume.pdf (always available)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG, PROFILE
from ..failure.evo_logger import EvoLogger

logger = logging.getLogger("barq.auto_applier.resume.builder")

# ─── Default paths ──────────────────────────────────────────────────────────

_STAGED_DIR = Path(CONFIG.project_root) / "data" / "staged_resumes"
_BASE_RESUME_PATH = Path(CONFIG.project_root) / "data" / "base_resume.pdf"
_GENERATION_TIMEOUT = 90  # seconds


@dataclass
class ResumeBuildResult:
    """Result from DynamicResumeBuilder.build()."""

    status: str                         # "generated" | "ai_resume_fallback" | "static_fallback" | "error"
    pdf_path: str                       # Absolute path to the generated PDF
    source: str                         # "barq_native" | "ai_resume_generator" | "static" | ""
    file_size_bytes: int = 0
    generated_at: str = ""
    template_used: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DynamicResumeBuilder:
    """Generates a job-tailored resume PDF with 3-tier fallback.

    Usage:
        builder = DynamicResumeBuilder()
        result = await builder.build(job_description="...", job_title="...", company="...")
        if result.status == "generated":
            print(f"Resume saved to: {result.pdf_path}")
    """

    def __init__(self):
        self._evo = EvoLogger()
        self._ai_bridge: Any = None  # Lazy import to avoid dependency when not used

    # ── Public API ──────────────────────────────────────────────────────

    async def build(
        self,
        job_description: str = "",
        job_title: str = "",
        company: str = "",
        template: str = "modern",
        timeout: int = _GENERATION_TIMEOUT,
    ) -> ResumeBuildResult:
        """Generate a tailored resume PDF for a specific job.

        Uses 3-tier fallback:
          1. BARQ native pipeline (Ollama + ResumePDFGenerator)
          2. AI_Resume_Generator HTTP bridge (Next.js /api/generate-pdf)
          3. Static base_resume.pdf

        Args:
            job_description: Raw job description text for tailoring.
            job_title: Job title for filename and context.
            company: Company name for filename and context.
            template: For AI_Resume_Generator fallback: "modern" | "classic" | "minimal".
            timeout: Total timeout in seconds for the generation attempt.

        Returns:
            ResumeBuildResult with status, pdf_path, source, etc.
        """
        # Ensure staged directory exists
        _STAGED_DIR.mkdir(parents=True, exist_ok=True)

        # Generate a unique filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in job_title)[:30]
        safe_company = "".join(c if c.isalnum() or c in " -_" else "_" for c in company)[:20]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"resume_{safe_company}_{safe_title}_{timestamp}.pdf"
        output_path = _STAGED_DIR / filename

        start_time = datetime.now(timezone.utc)

        # ── TIER 1: BARQ Native Pipeline ───────────────────────────────
        try:
            result = await asyncio.wait_for(
                self._build_via_barq(job_description, job_title, company, output_path),
                timeout=timeout,
            )
            if result.pdf_path and Path(result.pdf_path).exists():
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                result.generated_at = start_time.isoformat()
                result.metadata["elapsed_seconds"] = round(elapsed, 1)
                logger.info(
                    "Tier 1 (BARQ native) succeeded: %s (%.1fs)",
                    result.pdf_path,
                    elapsed,
                )
                return result

            logger.warning("Tier 1 (BARQ native) returned empty path, trying fallback...")
        except asyncio.TimeoutError:
            logger.warning("Tier 1 (BARQ native) timed out after %ds", timeout)
        except Exception as exc:
            logger.warning("Tier 1 (BARQ native) failed: %s", exc)
            await self._evo.log_failure(
                url="",
                error_type=type(exc).__name__,
                error_message=f"BARQ native resume generation failed: {exc}",
                context={"tier": 1, "job_title": job_title, "company": company},
            )

        # ── TIER 2: AI_Resume_Generator Bridge ──────────────────────────
        try:
            result = await asyncio.wait_for(
                self._build_via_ai_resume(job_description, output_path, template),
                timeout=max(30, timeout // 2),
            )
            if result.pdf_path and Path(result.pdf_path).exists():
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                result.generated_at = start_time.isoformat()
                result.metadata["elapsed_seconds"] = round(elapsed, 1)
                logger.info(
                    "Tier 2 (AI_Resume_Generator) succeeded: %s (%.1fs)",
                    result.pdf_path,
                    elapsed,
                )
                return result

            logger.warning("Tier 2 (AI_Resume_Generator) returned empty path, trying static fallback...")
        except asyncio.TimeoutError:
            logger.warning("Tier 2 (AI_Resume_Generator) timed out")
        except Exception as exc:
            logger.warning("Tier 2 (AI_Resume_Generator) failed: %s", exc)

        # ── TIER 3: Static Fallback ─────────────────────────────────────
        result = await self._build_static(job_title, company, output_path)
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        result.generated_at = start_time.isoformat()
        result.metadata["elapsed_seconds"] = round(elapsed, 1)
        return result

    # ── Tier 1: BARQ Native Pipeline ───────────────────────────────────

    async def _build_via_barq(
        self,
        job_description: str,
        job_title: str,
        company: str,
        output_path: Path,
    ) -> ResumeBuildResult:
        """Use BARQ's own ResumePDFGenerator + ResumeOptimizer + Ollama.

        This pipeline requires:
          - python/jobs/resume_parser.py (to load base resume)
          - python/jobs/optimizer.py (ResumeOptimizer)
          - python/jobs/pdf_generator.py (ResumePDFGenerator)
          - Ollama running locally
        """
        from ...resume_parser import parse_resume
        from ...optimizer import ResumeOptimizer
        from ...pdf_generator import ResumePDFGenerator

        # 1. Load base resume data
        resume = parse_resume()
        if resume.get("_error") or not resume.get("raw_md"):
            logger.warning("Base resume not found at default path: %s", resume.get("_error", "unknown"))
            return ResumeBuildResult(
                status="error",
                pdf_path="",
                source="",
                error="Base resume file not found",
            )

        resume_md = resume["raw_md"]

        # 2. Optimize for the specific job
        optimizer = ResumeOptimizer()
        job_dict = {
            "title": job_title or "Unknown",
            "company": company or "Unknown",
            "description": job_description or "",
        }
        optimized = await optimizer.optimize(resume_md, job_dict)
        optimized_md = optimized.get("optimized_md", resume_md)

        # 3. Merge optimized content back into resume data
        pdf_resume_data = {**resume, "raw_md": optimized_md}

        # 4. Generate PDF
        pdf_gen = ResumePDFGenerator()
        pdf_result = await pdf_gen.generate(
            pdf_resume_data,
            output_dir=str(_STAGED_DIR),
            filename=output_path.stem,  # Without extension
        )

        if pdf_result.get("status") == "completed" and pdf_result.get("pdf_path"):
            actual_path = pdf_result["pdf_path"]
            file_size = Path(actual_path).stat().st_size
            return ResumeBuildResult(
                status="generated",
                pdf_path=actual_path,
                source="barq_native",
                file_size_bytes=file_size,
                template_used=pdf_result.get("backend", "fpdf"),
                metadata={
                    "keywords_injected": optimized.get("keywords_injected", []),
                    "changes_made": optimized.get("changes_made", []),
                },
            )

        return ResumeBuildResult(
            status="error",
            pdf_path="",
            source="barq_native",
            error=pdf_result.get("message", "PDF generation returned incomplete status"),
        )

    # ── Tier 2: AI_Resume_Generator Bridge ─────────────────────────────

    async def _build_via_ai_resume(
        self,
        job_description: str,
        output_path: Path,
        template: str = "modern",
    ) -> ResumeBuildResult:
        """Use the AI_Resume_Generator's /api/generate-pdf endpoint as fallback.

        Requires:
          - AI_Resume_Generator Next.js server running (default port 3000)
        """
        from .ai_resume_bridge import AIResumeBridge

        bridge = AIResumeBridge()
        try:
            # Check server availability
            if not await bridge.is_server_running():
                logger.info("AI_Resume_Generator server not available — skipping tier 2")
                return ResumeBuildResult(
                    status="error",
                    pdf_path="",
                    source="",
                    error="AI_Resume_Generator server not reachable",
                )

            # Generate PDF bytes
            pdf_bytes = await bridge.generate_pdf(
                job_description=job_description,
                template=template,
            )

            if not pdf_bytes:
                return ResumeBuildResult(
                    status="error",
                    pdf_path="",
                    source="ai_resume_generator",
                    error="PDF generation returned no bytes",
                )

            # Save to staged directory
            output_path.write_bytes(pdf_bytes)
            file_size = output_path.stat().st_size

            return ResumeBuildResult(
                status="generated",
                pdf_path=str(output_path.resolve()),
                source="ai_resume_generator",
                file_size_bytes=file_size,
                template_used=template,
            )

        finally:
            await bridge.close()

    # ── Tier 3: Static Fallback ────────────────────────────────────────

    async def _build_static(
        self,
        job_title: str,
        company: str,
        output_path: Path,
    ) -> ResumeBuildResult:
        """Copy the static base_resume.pdf as the final fallback.

        If even the static file doesn't exist, generate a minimal one using fpdf.
        """
        static_path = Path(_BASE_RESUME_PATH)

        if static_path.exists():
            try:
                import shutil
                shutil.copy2(str(static_path), str(output_path))
                file_size = output_path.stat().st_size
                logger.info("Static fallback used: %s -> %s", static_path, output_path)
                return ResumeBuildResult(
                    status="static_fallback",
                    pdf_path=str(output_path.resolve()),
                    source="static",
                    file_size_bytes=file_size,
                    template_used="static",
                    metadata={"original_path": str(static_path)},
                )
            except Exception as exc:
                logger.warning("Static file copy failed: %s", exc)
                # Fall through to generate one
        else:
            logger.warning("Static base resume not found at %s — generating minimal PDF", static_path)

        # Generate a minimal PDF with fpdf as last resort
        try:
            return await self._generate_minimal_pdf(output_path, job_title, company)
        except Exception as exc:
            return ResumeBuildResult(
                status="error",
                pdf_path="",
                source="",
                error=f"All tiers failed. Last error: {exc}",
            )

    # ── Helper: Minimal PDF Generator ──────────────────────────────────

    async def _generate_minimal_pdf(
        self,
        output_path: Path,
        job_title: str,
        company: str,
    ) -> ResumeBuildResult:
        """Generate a minimal but professional PDF using fpdf as absolute last resort."""
        # Lazy import fpdf
        try:
            from fpdf import FPDF
        except ImportError:
            raise ImportError("fpdf is required for PDF generation. Install: pip install fpdf")

        def _build():
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 24)
            pdf.set_text_color(26, 54, 93)
            pdf.cell(0, 12, PROFILE.full_name, new_x="LMARGIN", new_y="NEXT", align="C")

            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(113, 128, 150)
            contact_parts = [p for p in [PROFILE.email, PROFILE.phone] if p]
            contact = " | ".join(contact_parts)
            if contact:
                pdf.cell(0, 6, contact, new_x="LMARGIN", new_y="NEXT", align="C")

            pdf.ln(8)

            # Summary
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(26, 54, 93)
            pdf.cell(0, 8, "Professional Summary", new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(26, 54, 93)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(30, 30, 30)
            summary = PROFILE.summary
            if job_title or company:
                summary += " Seeking " + f"{job_title or ''}".strip()
                if company:
                    summary += f" role at {company}"
            pdf.multi_cell(0, 5, summary)

            pdf.ln(4)

            # Skills
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(26, 54, 93)
            pdf.cell(0, 8, "Skills", new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(26, 54, 93)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(43, 108, 192)
            skill_text = ", ".join(PROFILE.skills[:25])
            pdf.multi_cell(0, 5, skill_text)

            # Experience
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(26, 54, 93)
            pdf.cell(0, 8, "Experience", new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(26, 54, 93)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

            for exp in PROFILE.experiences:
                role = exp.get("role", "")
                comp = exp.get("company", "")
                period = exp.get("period", "")
                highlights = exp.get("highlights", [])

                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(43, 108, 192)
                line = role
                if comp:
                    line += f" -- {comp}"
                pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")

                if period:
                    pdf.set_font("Helvetica", "I", 9)
                    pdf.set_text_color(113, 128, 150)
                    pdf.cell(0, 4, period, new_x="LMARGIN", new_y="NEXT")

                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.l_margin += 4
                for bullet in highlights[:5]:
                    pdf.cell(0, 4.5, f"  -  {bullet[:90]}", new_x="LMARGIN", new_y="NEXT")
                pdf.l_margin -= 4
                pdf.ln(2)

            # Education
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(26, 54, 93)
            pdf.cell(0, 8, "Education", new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(26, 54, 93)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(43, 108, 192)
            pdf.cell(0, 5, PROFILE.education, new_x="LMARGIN", new_y="NEXT")

            pdf.output(str(output_path))

        await asyncio.to_thread(_build)
        file_size = output_path.stat().st_size
        logger.info("Minimal fallback PDF generated: %s (%d bytes)", output_path, file_size)
        return ResumeBuildResult(
            status="static_fallback",
            pdf_path=str(output_path.resolve()),
            source="static",
            file_size_bytes=file_size,
            template_used="minimal_fallback",
            metadata={"note": "Generated as absolute last resort — no base_resume.pdf found"},
        )


# ─── Convenience function ───────────────────────────────────────────────────


async def build_tailored_resume(
    job_description: str = "",
    job_title: str = "",
    company: str = "",
) -> ResumeBuildResult:
    """Quick one-shot resume builder.

    Usage:
        result = await build_tailored_resume(
            job_description="...",
            job_title="Software Engineer",
            company="Acme Inc",
        )
        print(f"Resume: {result.pdf_path}")
    """
    builder = DynamicResumeBuilder()
    return await builder.build(
        job_description=job_description,
        job_title=job_title,
        company=company,
    )
