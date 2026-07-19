"""
Dynamic resume generation — tailored PDF builder with AI_Resume_Generator bridge.

Architecture (3-tier fallback):
  1. Primary: BARQ's native ResumePDFGenerator + ResumeOptimizer + Ollama
  2. Fallback: AI_Resume_Generator Next.js server via /api/generate-pdf HTTP
  3. Static:   ./data/base_resume.pdf (guaranteed fallback)
"""

from .dynamic_builder import DynamicResumeBuilder, ResumeBuildResult
from .ai_resume_bridge import AIResumeBridge

__all__ = ["DynamicResumeBuilder", "ResumeBuildResult", "AIResumeBridge"]
