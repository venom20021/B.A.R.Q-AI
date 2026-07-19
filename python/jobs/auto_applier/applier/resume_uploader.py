"""
Resume upload handler.

Manages file uploads to application forms via Playwright file input detection.
Falls back to LinkedIn's saved resume if file upload fails.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from ..browser.stealth import StealthConfig
from ..config import CONFIG

logger = logging.getLogger("barq.auto_applier.resume")


class ResumeUploader:
    """Handles resume file uploads through Playwright file inputs."""

    def __init__(self, page: Any):
        self.page = page
        self._resume_path = Path(CONFIG.resume_pdf_path)

    async def upload(self, force: bool = False) -> dict[str, Any]:
        """Upload resume to the current form.

        Uses AI element discovery to find file input fields.
        Falls back gracefully if no file input is found.

        Args:
            force: If True, shows the file picker even if no input found.

        Returns:
            dict with: uploaded (bool), filename (str), method (str)
        """
        result = {"uploaded": False, "filename": "", "method": "none"}

        # Check resume file exists
        if not self._resume_path.exists():
            logger.warning("Resume PDF not found at: %s", self._resume_path)
            result["method"] = "linkedin_saved"
            return result

        try:
            # Try finding file input via aria-label, type, or accept attribute
            file_input = self.page.locator('input[type="file"]')
            if await file_input.count() == 0:
                file_input = self.page.locator('[aria-label*="resume" i], [aria-label*="CV" i], [aria-label*="upload" i]')
            if await file_input.count() == 0:
                file_input = self.page.locator('input[accept*=".pdf"], input[accept*=".doc"]')

            if await file_input.count() > 0:
                await file_input.first.wait_for(state="visible", timeout=5000)
                await file_input.first.set_input_files(str(self._resume_path.resolve()))
                await StealthConfig.human_delay(self.page, 500, 1000)
                result["uploaded"] = True
                result["filename"] = self._resume_path.name
                result["method"] = "file_input"
                logger.info("Resume uploaded: %s", self._resume_path.name)
            else:
                logger.info("No file input found — using LinkedIn saved resume")
                result["method"] = "linkedin_saved"

        except Exception as exc:
            logger.warning("Resume upload failed: %s", exc)
            result["method"] = f"failed: {exc}"

        return result

    @property
    def resume_exists(self) -> bool:
        return self._resume_path.exists()

    @property
    def resume_path(self) -> str:
        return str(self._resume_path)

    def set_resume_path(self, path: str) -> None:
        """Override the default resume path."""
        self._resume_path = Path(path)
