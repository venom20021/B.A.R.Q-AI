"""
BARQ Job Search Automation Module

Scans 35+ job boards, evaluates matches using local LLM,
and generates tailored applications, cover letters, and cold emails.
"""

from .applier import JobApplier
from .cold_mail import ColdEmailWriter
from .cover_letter import CoverLetterGenerator
from .evaluator import JobEvaluator
from .matcher import JobMatcher
from .optimizer import ResumeOptimizer
from .pdf_generator import ResumePDFGenerator, generate_resume_pdf
from .response_tracker import FollowUpAutomation, ResponseTracker
from .resume_parser import clear_parse_cache, parse_resume
from .scanner import JobScanner

__all__ = [
    "JobScanner", "JobEvaluator", "JobApplier",
    "JobMatcher", "ResumeOptimizer", "CoverLetterGenerator", "ColdEmailWriter",
    "ResponseTracker", "FollowUpAutomation",
    "ResumePDFGenerator", "generate_resume_pdf",
    "parse_resume", "clear_parse_cache",
]
