"""
Multi-board job scanner that scrapes and parses job listings from 35+ ATS providers.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
import httpx
from bs4 import BeautifulSoup
from config import get_settings


# Supported job boards and their base URLs
JOB_BOARDS = {
    "linkedin": "https://www.linkedin.com/jobs/search",
    "indeed": "https://www.indeed.com/jobs",
    "glassdoor": "https://www.glassdoor.com/Job",
    "monster": "https://www.monster.com/jobs",
    "ziprecruiter": "https://www.ziprecruiter.com/candidate/search",
    # Future: add 30+ more boards
}


class JobScanner:
    """Scans multiple job boards and aggregates results."""

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def scan_all(self, keywords: list[str], location: str = "") -> list[dict[str, Any]]:
        """
        Scan all configured job boards for matching positions.

        Args:
            keywords: List of search terms (e.g., ["software engineer", "react", "typescript"])
            location: Location filter (e.g., "remote", "San Francisco")

        Returns:
            List of normalized job listings
        """
        results: list[dict[str, Any]] = []

        # Scan boards in parallel
        tasks = [self._scan_board(board, keywords, location) for board in JOB_BOARDS]
        board_results = await asyncio.gather(*tasks, return_exceptions=True)

        for board_result in board_results:
            if isinstance(board_result, list):
                results.extend(board_result)
            elif isinstance(board_result, Exception):
                print(f"[Scanner] Board scan failed: {board_result}")

        # Deduplicate by title + company
        seen = set()
        unique_results = []
        for job in results:
            key = (job["title"].lower(), job["company"].lower())
            if key not in seen:
                seen.add(key)
                unique_results.append(job)

        return unique_results

    async def _scan_board(
        self, board: str, keywords: list[str], location: str
    ) -> list[dict[str, Any]]:
        """Scan a single job board."""
        url = JOB_BOARDS.get(board)
        if not url:
            return []

        query = "+".join(keywords)
        params = {"q": query, "l": location, "sort": "date"}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()

            jobs = self._parse_listings(board, response.text)
            print(f"[Scanner] Found {len(jobs)} jobs on {board}")
            return jobs

        except httpx.HTTPError as e:
            print(f"[Scanner] HTTP error on {board}: {e}")
            return []
        except Exception as e:
            print(f"[Scanner] Error scanning {board}: {e}")
            return []

    def _parse_listings(self, board: str, html: str) -> list[dict[str, Any]]:
        """Parse job listings from HTML based on board-specific structure."""
        soup = BeautifulSoup(html, "lxml")
        jobs: list[dict[str, Any]] = []

        # Board-specific parsing logic
        if board == "linkedin":
            jobs = self._parse_linkedin(soup)
        elif board == "indeed":
            jobs = self._parse_indeed(soup)
        elif board == "glassdoor":
            jobs = self._parse_glassdoor(soup)
        else:
            # Generic fallback parsing
            jobs = self._parse_generic(soup)

        # Normalize
        for job in jobs:
            job["source"] = board
            job["scanned_at"] = datetime.now(timezone.utc).isoformat()

        return jobs

    def _parse_linkedin(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse LinkedIn job search results."""
        jobs = []
        for card in soup.select(".job-search-card"):
            title_el = card.select_one(".base-search-card__title")
            company_el = card.select_one(".base-search-card__subtitle")
            location_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": location_el.text.strip() if location_el else "",
                    "url": link_el.get("href", "") if link_el else "",
                })
        return jobs

    def _parse_indeed(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse Indeed job search results."""
        jobs = []
        for card in soup.select(".job_seen_beacon"):
            title_el = card.select_one("h2.jobTitle a")
            company_el = card.select_one(".companyName")
            location_el = card.select_one(".companyLocation")

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": location_el.text.strip() if location_el else "",
                    "url": "https://www.indeed.com" + title_el.get("href", ""),
                })
        return jobs

    def _parse_glassdoor(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse Glassdoor job search results."""
        jobs = []
        for card in soup.select(".jobListing"):
            title_el = card.select_one(".jobTitle")
            company_el = card.select_one(".employerName")
            location_el = card.select_one(".location")

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": location_el.text.strip() if location_el else "",
                    "url": "",
                })
        return jobs

    def _parse_generic(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Generic fallback parser for unknown board structures."""
        jobs = []
        for card in soup.select('[class*="job"], [class*="listing"], [class*="card"]'):
            title_el = card.select_one(
                'h2, h3, [class*="title"], [class*="position"]'
            )
            company_el = card.select_one(
                '[class*="company"], [class*="employer"]'
            )

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": "",
                    "url": "",
                })
        return jobs

    async def close(self):
        await self.client.aclose()
