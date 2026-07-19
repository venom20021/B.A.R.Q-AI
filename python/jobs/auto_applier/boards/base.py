"""
Abstract Job Board Strategy (Strategy Pattern).

Each job board platform implements this interface. The high-level flow
(login, navigate, form-fill, submit) is defined per-platform, while the
underlying AI element discovery layer handles actual DOM interaction.

To add a new board: subclass JobBoardStrategy and override prepare() + apply().
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class JobBoardStrategy(ABC):
    """Base class for platform-specific application strategies.

    Subclasses must implement:
      - prepare(page, job_url): Platform-specific setup (login, navigation).
      - apply(page, job_url, context): Platform-specific form filling logic.

    The AI element discovery layer is available via self.selector and self.qa.
    """

    def __init__(self):
        self.ollama: Any = None
        self.selector: Any = None
        self.qa: Any = None

    @abstractmethod
    async def prepare(self, page: Any, job_url: str) -> dict[str, Any]:
        """Perform platform-specific setup before applying.

        This may include:
        - Logging in (if storage state is stale)
        - Navigating to the correct application page
        - Dismissing cookie/modals

        Args:
            page: Playwright page object.
            job_url: The job posting URL.

        Returns:
            dict with 'success' (bool) and optional 'error' (str).
        """
        ...

    @abstractmethod
    async def apply(
        self,
        page: Any,
        job_url: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the application for this platform.

        Args:
            page: Playwright page object.
            job_url: The job posting URL.
            context: Dict with keys:
                - ollama: OllamaClient instance
                - selector: ElementSelector instance
                - qa: QAGenerator instance
                - profile: CandidateProfile
                - job_context: Job description text

        Returns:
            dict with 'submitted' (bool) and optional errors, pages_completed, etc.
        """
        ...
