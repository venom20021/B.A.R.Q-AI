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
from .response_tracker import ResponseTracker, FollowUpAutomation

__all__ = [
    "JobScanner", "JobEvaluator", "JobApplier",
    "JobMatcher", "ResumeOptimizer", "CoverLetterGenerator", "ColdEmailWriter",
    "ResponseTracker", "FollowUpAutomation",
    "parse_resume", "clear_parse_cache",
]
