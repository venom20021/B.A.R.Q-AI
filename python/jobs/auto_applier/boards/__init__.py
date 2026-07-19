"""Strategy pattern for job board platforms."""

from .base import JobBoardStrategy
from .linkedin import LinkedInStrategy

__all__ = ["JobBoardStrategy", "LinkedInStrategy"]
