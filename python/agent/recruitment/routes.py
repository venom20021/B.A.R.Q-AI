"""
FastAPI routes for the BARQ Recruitment Multi-Agent Team.

Exposes endpoints for each agent individually and the full pipeline.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .orchestrator import RecruitmentOrchestrator

router = APIRouter()
orchestrator = RecruitmentOrchestrator()


# ─── Models ─────────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    job_description: str
    title_hint: str = ""
    company_hint: str = ""


class MatchRequest(BaseModel):
    job_description: str
    title_hint: str = ""
    company_hint: str = ""
    resume_path: Optional[str] = None


class WriteRequest(BaseModel):
    job_description: str
    title_hint: str = ""
    company_hint: str = ""
    resume_path: Optional[str] = None
    generate_cover_letter: bool = True


class PipelineRequest(BaseModel):
    job_description: str
    title_hint: str = ""
    company_hint: str = ""
    resume_path: Optional[str] = None
    generate_cover_letter: bool = True


# ─── Individual Agent Endpoints ────────────────────────────────────────────

@router.post("/extract", summary="Extract job requirements from description")
async def extract_job(request: ExtractRequest):
    """Run only the Extractor Agent — parse job description into structured data.

    Returns structured requirements including must-have/nice-to-have skills,
    experience level, education, responsibilities, and remote status.
    """
    try:
        result = await orchestrator.run_extract_only(
            job_description=request.job_description,
            title_hint=request.title_hint,
            company_hint=request.company_hint,
        )
        return {"status": "completed", "extraction": result.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match", summary="Match job requirements against resume")
async def match_job(request: MatchRequest):
    """Run the Matcher Agent — compare extracted requirements against resume.

    Returns scores, missing skills with severity, and recommendations.
    """
    try:
        extraction = await orchestrator.run_extract_only(
            job_description=request.job_description,
            title_hint=request.title_hint,
            company_hint=request.company_hint,
        )
        match = await orchestrator.run_match_only(
            extraction=extraction,
            resume_path=request.resume_path,
        )
        return {
            "status": "completed",
            "extraction": extraction.to_dict(),
            "match": match.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/write", summary="Generate ATS-optimized resume and cover letter")
async def write_documents(request: WriteRequest):
    """Run the full pipeline and generate optimized documents.

    Returns optimized resume markdown, cover letter, and changes summary.
    """
    try:
        progress = await orchestrator.run_full_pipeline(
            job_description=request.job_description,
            title_hint=request.title_hint,
            company_hint=request.company_hint,
            resume_path=request.resume_path,
            generate_cover_letter=request.generate_cover_letter,
        )
        if progress.status == "error":
            raise HTTPException(status_code=500, detail=progress.message)
        return {
            "status": "completed",
            "overall_score": progress.match.get("overall_score", 0) if progress.match else 0,
            "extraction": progress.extraction,
            "match": progress.match,
            "writer": progress.writer,
            "cover_letter": progress.cover_letter,
            "elapsed_seconds": progress.elapsed_seconds,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Full Pipeline Endpoint ───────────────────────────────────────────────

@router.post("/pipeline", summary="Run the full recruitment pipeline")
async def run_pipeline(request: PipelineRequest):
    """Execute the complete multi-agent recruitment pipeline.

    Stages:
    1. Extractor Agent — parses job description into structured data
    2. Matcher Agent — compares against resume for match analysis
    3. Writer Agent — generates ATS-optimized resume + optional cover letter

    Returns results from all stages with progress tracking.
    """
    try:
        progress = await orchestrator.run_full_pipeline(
            job_description=request.job_description,
            title_hint=request.title_hint,
            company_hint=request.company_hint,
            resume_path=request.resume_path,
            generate_cover_letter=request.generate_cover_letter,
        )
        if progress.status == "error":
            raise HTTPException(status_code=500, detail=progress.message)
        return progress.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/progress", summary="Get current pipeline progress")
async def get_pipeline_progress():
    """Get the current progress of the running pipeline."""
    progress = orchestrator.get_progress()
    return progress.to_dict()
