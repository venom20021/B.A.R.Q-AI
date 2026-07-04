"""
BARQ Job Search Automation Module

Scans 35+ job boards, evaluates matches using local LLM,
and generates tailored applications, cover letters, and cold emails.
"""

from .scanner import JobScanner
from .evaluator import JobEvaluator
from .applier import JobApplier
from .resume_parser import parse_resume, clear_parse_cache
from .matcher import JobMatcher
from .optimizer import ResumeOptimizer
from .cover_letter import CoverLetterGenerator
from .cold_mail import ColdEmailWriter

__all__ = [
    "JobScanner", "JobEvaluator", "JobApplier",
    "JobMatcher", "ResumeOptimizer", "CoverLetterGenerator", "ColdEmailWriter",
    "parse_resume", "clear_parse_cache",
]
