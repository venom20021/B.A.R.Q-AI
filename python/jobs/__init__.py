"""
BARQ Job Search Automation Module

Scans 35+ job boards, evaluates matches using local LLM,
and generates tailored applications.
"""

from .scanner import JobScanner
from .evaluator import JobEvaluator
from .applier import JobApplier

__all__ = ["JobScanner", "JobEvaluator", "JobApplier"]
