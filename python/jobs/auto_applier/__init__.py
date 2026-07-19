"""
BARQ Auto Applier — Production-grade job automation engine.

Headful Playwright orchestration with zero-selector AI element discovery,
two-way interactive Telegram control, and EvoMap failure protocol.

Architecture:
  telegram/          ← aiogram bot with inline Apply/Skip buttons
  browser/           ← Stealth Playwright launcher with session persistence
  dom/               ← Hybrid accessibility-tree + filtered-DOM extraction
  llm/               ← Ollama wrapper for element selection + Q&A generation
  applier/           ← Zero-selector form filler + resume uploader
  boards/            ← Strategy pattern (LinkedIn, Indeed, Wellfound, etc.)
  discovery/         ← Job URL ingestion (TinyFish + LinkedIn + BARQ boards)
  failure/           ← EvoMap error logging with DOM snapshots
  pipeline/          ← End-to-end orchestrator + scheduler

Usage:
    from jobs.auto_applier.pipeline import AutoApplyPipeline
    pipeline = AutoApplyPipeline()
    await pipeline.run()
"""

from .pipeline.orchestrator import AutoApplyPipeline
from .telegram.bot import AutoApplyBot
from .applier.engine import ApplicationEngine
from .boards.base import JobBoardStrategy
from .config import ApplierConfig
from .resume.dynamic_builder import DynamicResumeBuilder, build_tailored_resume
from .resume.ai_resume_bridge import AIResumeBridge

__all__ = [
    "AutoApplyPipeline",
    "AutoApplyBot",
    "ApplicationEngine",
    "JobBoardStrategy",
    "ApplierConfig",
    "DynamicResumeBuilder",
    "build_tailored_resume",
    "AIResumeBridge",
]
