"""
Multi-board job scanner that scrapes and parses job listings from 35+ ATS providers.
Supports real-time progress tracking for frontend status bar.
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

from config import get_settings

# Supported job boards and their base URLs
# ─── User-Agent rotation pool ──────────────────────────────────────────
# Rotate through different real browser UAs to avoid being blocked by
# anti-bot measures (Cloudflare, Akamai, etc.).  Each scraper picks a
# random UA from this pool on every request.
USER_AGENTS = [
    # Chrome 124 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox 125 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox 125 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Edge 124 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Safari 17.4 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Chrome 123 on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


import random as _random


def _random_ua() -> str:
    """Return a random User-Agent string from the rotation pool."""
    return USER_AGENTS[_random.randint(0, len(USER_AGENTS) - 1)]


def _rich_headers() -> dict[str, str]:
    """Return a dict of HTTP headers that mimic a real browser request.

    Includes Accept, Accept-Language, Cache-Control, Upgrade-Insecure-Requests,
    and a rotated User-Agent.  Boards that need extra headers (e.g. API tokens)
    can call this and add their own overrides.
    """
    return {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }


JOB_BOARDS = {
    "linkedin": "https://www.linkedin.com/jobs/search",
    "indeed": "https://www.indeed.com/jobs",
    "glassdoor": "https://www.glassdoor.com/Job",
    "monster": "https://www.monster.com/jobs",
    "ziprecruiter": "https://www.ziprecruiter.com/candidate/search",
    "google": "https://www.google.com/search",                  # Google for Jobs (via JobSpy)
    "remotive": "https://remotive.com/api/remote-jobs",          # Free API, no key needed
    "remoteok": "https://remoteok.com/api",                       # Free API, no key needed
    "hn_algolia": "https://hn.algolia.com/api/v1/search",        # HN "Who is Hiring" threads
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards",   # Greenhouse API
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/",   # Ashby API
    "lever": "https://api.lever.co/v0/postings",                 # Lever API
    "workday": "https://www.myworkdayjobs.com",                   # Workday (Playwright)
    "bamboohr": "https://api.bamboohr.com/api/gateway.php",       # BambooHR API

    # ─── New v3.0 Custom Job Boards ──────────────────────────────────
    "himalayas": "https://himalayas.app/jobs",                      # Himalayas — AI-matched remote jobs
    "wellfound": "https://wellfound.com/jobs",                     # Wellfound (AngelList) — startup jobs
    "weworkremotely": "https://weworkremotely.com",                 # WeWorkRemotely — curated remote jobs
    "workingnomads": "https://www.workingnomads.com/jobs",         # WorkingNomads — remote job board
    "instahyre": "https://www.instahyre.com/job-search",            # Instahyre — India tech hiring
    "protocol": "https://www.protocoljobs.ai/jobs",                # Protocol — AI-matched job search
    "welcometothejungle": "https://www.welcometothejungle.com/en/jobs",  # Welcome to the Jungle
    "cutshort": "https://cutshort.io/jobs",                        # Cutshort — India tech hiring
    "relocateme": "https://relocate.me/search",                     # Relocate.me — relocation jobs
    "hnhiring": "https://hnhiring.com",                            # HN "Who's Hiring" aggregator
}

# ─── JobSpy adapter ───────────────────────────────────────────────────────
# JobSpy (pip install python-jobspy) wraps Playwright with stealth settings
# and maintains up-to-date selectors for anti-bot-heavy boards (LinkedIn,
# Indeed, Glassdoor, ZipRecruiter, Google for Jobs).  These boards are routed
# through it in _scan_board; if the library is missing they fall back to the
# legacy Playwright/HTTP scrapers.  Resulting jobs feed the exact same
# evaluation + dedup pipeline as every other board.
JOBSPY_SITES = ("linkedin", "indeed", "glassdoor", "ziprecruiter", "google")

# JobSpy site identifiers differ slightly from our board keys
_JOBSPY_SITE_NAMES = {
    "linkedin": "linkedin",
    "indeed": "indeed",
    "glassdoor": "glassdoor",
    "ziprecruiter": "zip_recruiter",
    "google": "google",
}

JOBSPY_RESULTS_PER_SITE = 20      # jobs per board per scan (keeps requests light)
JOBSPY_HOURS_OLD = 72             # only jobs posted within this window
JOBSPY_SEARCH_TERM_MAX = 3        # max keywords sent as the search term
# Indeed/Glassdoor country (required by JobSpy). Override via JOBSPY_COUNTRY
# env var (e.g. USA, UK, Canada) — default matches the VM's India deployment.
JOBSPY_COUNTRY = os.getenv("JOBSPY_COUNTRY", "India")


def _jobspy_search_term(keywords: list[str]) -> str:
    """Build the JobSpy search term from the first few keywords.

    JobSpy sends the term to the board's own search box, so a long skill
    list would over-constrain the query.  We send a short primary term and
    let the keyword filter (_matches_any_keyword) do the rest.
    """
    kws = [k.strip() for k in keywords if k and k.strip()]
    return " ".join(kws[:JOBSPY_SEARCH_TERM_MAX])


def _matches_any_keyword(job: dict[str, Any], keywords: list[str]) -> bool:
    """True when the job title or description mentions any keyword."""
    kws = [k.lower() for k in keywords if k]
    if not kws:
        return True
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(k in haystack for k in kws)


def _clean_str(value: Any) -> str:
    """Coerce a JobSpy cell to a clean string (None/NaN → '')."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _jobspy_row_to_job(row: dict[str, Any], site: str) -> dict[str, Any] | None:
    """Map a JobSpy result row (pandas Series / dict) into BARQ's job dict."""
    title = _clean_str(row.get("title"))
    if not title:
        return None

    location_parts = [
        p for p in (_clean_str(row.get("city")), _clean_str(row.get("state"))) if p
    ]
    country = _clean_str(row.get("country"))
    if country and country not in location_parts:
        location_parts.append(country)

    def _to_int(value: Any) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    posted = row.get("date_posted")
    if isinstance(posted, datetime):
        posted_str = posted.strftime("%Y-%m-%d")
    elif posted is not None:
        posted_str = _clean_str(posted)[:10]
    else:
        posted_str = ""

    return {
        "title": title,
        "company": _clean_str(row.get("company")),
        "location": ", ".join(location_parts),
        "description": _clean_str(row.get("description"))[:2000],
        "url": _clean_str(row.get("job_url")),
        "salary_min": _to_int(row.get("min_amount")),
        "salary_max": _to_int(row.get("max_amount")),
        "source_board": site,
        "posted_date": posted_str,
        "employment_type": _clean_str(row.get("job_type")).lower() or "fulltime",
        "remote_status": "remote" if row.get("is_remote") else "unknown",
    }


# Progress tracking — module-level singleton so routes can share state
# Asyncio event for SSE real-time notifications
_scan_notify_event: asyncio.Event | None = None


def _get_event() -> asyncio.Event:
    """Get or create the scan notification event."""
    global _scan_notify_event
    if _scan_notify_event is None:
        _scan_notify_event = asyncio.Event()
    return _scan_notify_event


def notify_progress_changed() -> None:
    """Signal that scan progress has changed. Used by SSE stream.

    Does NOT clear the event — the SSE listener's finally block handles
    that after consuming the update, ensuring no race conditions.
    """
    _get_event().set()


_scan_progress: dict[str, Any] = {
    "status": "idle",           # idle | scanning | evaluating | complete | error
    "phase": "",
    "phase_index": 0,
    "total_phases": 4,
    "progress_pct": 0,
    "boards_total": len(JOB_BOARDS),
    "boards_scanned": 0,
    "boards_errors": 0,
    "jobs_found": 0,
    "jobs_evaluated": 0,
    "message": "",
    "started_at": None,
    "elapsed_seconds": 0,
    "boards_results": [],  # Per-board log: [{board, status, jobs_count, error}]
}


def get_scan_progress() -> dict[str, Any]:
    """Return a snapshot of scan progress."""
    p = _scan_progress
    if p["started_at"]:
        p["elapsed_seconds"] = round(time.time() - p["started_at"], 1)
    return dict(p)


def set_scan_error(message: str):
    """Set scan progress to error state."""
    _scan_progress["status"] = "error"
    _scan_progress["message"] = message
    notify_progress_changed()


def reset_scan_progress():
    _scan_progress["status"] = "idle"
    _scan_progress["phase"] = ""
    _scan_progress["phase_index"] = 0
    _scan_progress["progress_pct"] = 0
    _scan_progress["boards_scanned"] = 0
    _scan_progress["boards_errors"] = 0
    _scan_progress["jobs_found"] = 0
    _scan_progress["jobs_evaluated"] = 0
    _scan_progress["message"] = ""
    _scan_progress["started_at"] = None
    _scan_progress["elapsed_seconds"] = 0
    _scan_progress["boards_results"] = []
    notify_progress_changed()


PHASES = [
    "Connecting to job boards",
    "Searching listings",
    "Evaluating matches",
    "Finalizing results",
]


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
        reset_scan_progress()
        _scan_progress["status"] = "scanning"
        _scan_progress["started_at"] = time.time()
        notify_progress_changed()

        results: list[dict[str, Any]] = []

        # Phase 1: Connecting
        _scan_progress["phase"] = PHASES[0]
        _scan_progress["phase_index"] = 0
        _scan_progress["progress_pct"] = 5
        _scan_progress["message"] = f"Preparing to scan {len(JOB_BOARDS)} job boards..."
        notify_progress_changed()
        await asyncio.sleep(0.3)  # Let the user see the phase

        # Phase 2: Searching — scan boards in parallel
        _scan_progress["phase"] = PHASES[1]
        _scan_progress["phase_index"] = 1
        _scan_progress["progress_pct"] = 10
        _scan_progress["message"] = "Starting parallel board scans..."
        notify_progress_changed()

        # ── Concurrency-limited board scanning ────────────────────────
        # Running all 27 boards in parallel via asyncio.gather(*) hogs the
        # event loop and hangs the scan if even ONE board hangs (Playwright
        # timeout, slow HTTP response, etc.).  Use a semaphore to limit
        # concurrent scans to 5 at a time, with a per-board timeout wrapper.
        _sem = asyncio.Semaphore(5)

        board_names = list(JOB_BOARDS.keys())

        async def _scan_with_limits(board: str, _kw: list[str], _loc: str) -> tuple:
            """Wrapper: acquire semaphore + apply per-board timeout.

            Returns (board_name, jobs_list, error_message_or_None).
            """
            async with _sem:
                try:
                    # JobSpy boards launch a Playwright browser — give them
                    # more room (30s is too tight for LinkedIn/Glassdoor).
                    _timeout = 90.0 if board in JOBSPY_SITES else 30.0
                    jobs = await asyncio.wait_for(
                        self._scan_board(board, _kw, _loc),
                        timeout=_timeout,
                    )
                    return (board, jobs, None)
                except asyncio.TimeoutError:
                    print(f"[Scanner] Board '{board}' timed out after 30s")
                    return (board, [], "Timeout after 30s")
                except Exception as e:
                    err_msg = str(e)[:120]
                    print(f"[Scanner] Board '{board}' error: {e}")
                    return (board, [], err_msg)

        board_results = await asyncio.gather(
            *[_scan_with_limits(board, keywords, location) for board in board_names],
            return_exceptions=True,
        )

        for board_result in board_results:
            if isinstance(board_result, tuple) and len(board_result) == 3:
                board_name, jobs_list, error = board_result
                if jobs_list and len(jobs_list) > 0:
                    results.extend(jobs_list)
                    _scan_progress["boards_scanned"] += 1
                    _scan_progress["jobs_found"] += len(jobs_list)
                    _scan_progress["boards_results"].append({
                        "board": board_name,
                        "status": "success",
                        "jobs_count": len(jobs_list),
                        "error": None,
                    })
                    _scan_progress["message"] = f"Found {_scan_progress['jobs_found']} jobs across {_scan_progress['boards_scanned']} boards"
                else:
                    _scan_progress["boards_errors"] += 1
                    _scan_progress["boards_results"].append({
                        "board": board_name,
                        "status": "error",
                        "jobs_count": 0,
                        "error": error or "No results",
                    })
            else:
                # Unexpected return (shouldn't happen, but handle gracefully)
                _scan_progress["boards_errors"] += 1

            # Update progress: searching phase = 10% to 50%
            done = _scan_progress["boards_scanned"] + _scan_progress["boards_errors"]
            pct_done = done / max(_scan_progress["boards_total"], 1)
            _scan_progress["progress_pct"] = round(10 + pct_done * 40, 1)
            notify_progress_changed()

        # Deduplicate
        seen = set()
        unique_results = []
        for job in results:
            key = (job["title"].lower(), job["company"].lower())
            if key not in seen:
                seen.add(key)
                unique_results.append(job)

        deduped_count = len(unique_results)
        removed = len(results) - deduped_count
        _scan_progress["jobs_found"] = deduped_count
        _scan_progress["progress_pct"] = 55
        _scan_progress["message"] = f"Found {deduped_count} unique jobs (removed {removed} duplicates)"
        notify_progress_changed()

        # Phase 3: Evaluating
        _scan_progress["phase"] = PHASES[2]
        _scan_progress["phase_index"] = 2
        _scan_progress["status"] = "evaluating"
        _scan_progress["progress_pct"] = 60
        _scan_progress["message"] = f"Evaluating {deduped_count} job matches..."
        notify_progress_changed()

        # Evaluate top jobs (limit to avoid long eval times)
        # Uses actual parsed resume instead of hardcoded profile
        from . import JobEvaluator
        from .resume_parser import parse_resume
        evaluator = JobEvaluator()

        parsed_resume = parse_resume()

        # Default: try resume skills first, fallback to generic tech keywords
        resume_skills = parsed_resume.get("skills", []) or [
            "python", "typescript", "react", "fastapi", "javascript",
            "node.js", "sql", "aws", "docker", "git",
        ]
        resume_exp = parsed_resume.get("experience", []) or []
        resume_summary = (parsed_resume.get("summary", "") or parsed_resume.get("headline", "") or "")

        if parsed_resume.get("_error"):
            # No resume file found — log once but keep using defaults
            print("[Scanner] Resume not found — using generic skill profile for evaluation")

        # Build user profile from actual resume
        user_profile = {
            "skills": resume_skills,
            "tech_skills": resume_skills,
            "experience_level": self._infer_level_from_resume(resume_exp),
            "target_salary": "",
            "preferred_locations": ["remote", "hybrid", "us", "canada", "uk", "europe"],
            "remote_preference": "Remote",
            "industry": "Technology",
            "summary": resume_summary[:300] if resume_summary else "",
        }

        evaluated: list[dict[str, Any]] = []
        for idx, job in enumerate(unique_results[:50]):
            eval_result = await evaluator.evaluate(job, user_profile)
            evaluated.append({**job, **eval_result})
            _scan_progress["jobs_evaluated"] = idx + 1
            eval_pct = (idx + 1) / max(len(unique_results[:50]), 1)
            _scan_progress["progress_pct"] = round(60 + eval_pct * 35, 1)
            _scan_progress["message"] = f"Evaluated {idx + 1} of {min(len(unique_results), 50)} jobs..."
            notify_progress_changed()

        # Phase 4: Finalizing
        _scan_progress["phase"] = PHASES[3]
        _scan_progress["phase_index"] = 3
        _scan_progress["status"] = "complete"
        _scan_progress["progress_pct"] = 100
        _scan_progress["message"] = f"Scan complete — {deduped_count} jobs found, {len(evaluated)} evaluated"
        _scan_progress["elapsed_seconds"] = round(time.time() - _scan_progress["started_at"], 1)
        notify_progress_changed()

        # Reset after a brief delay so frontend can read "complete" state
        asyncio.create_task(self._auto_reset())

        return evaluated or unique_results

    @staticmethod
    def _infer_level_from_resume(experience: list) -> str:
        """Infer experience level from actual resume experience entries."""
        if not experience:
            return "Mid"
        total_years = 0
        import re as _re
        for exp in experience:
            date_str = exp.get("date_range", "")
            if not date_str:
                continue
            years = _re.findall(r"\b(20\d{2})\b", date_str)
            if len(years) >= 2:
                try:
                    total_years += int(years[-1]) - int(years[0])
                except (ValueError, IndexError):
                    total_years += 1
            elif len(years) == 1:
                total_years += 1
        if total_years < 2:
            return "Entry"
        elif total_years < 5:
            return "Mid"
        elif total_years < 10:
            return "Senior"
        return "Lead/Executive"

    async def _auto_reset(self):
        """Reset progress to idle after a delay."""
        await asyncio.sleep(10)
        if _scan_progress["status"] == "complete":
            _scan_progress["status"] = "idle"

    # ─── Free API-based scrapers ───────────────────────────────────────

    async def _scan_remotive(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Remotive.com free API for remote jobs."""
        try:
            resp = await self.client.get("https://remotive.com/api/remote-jobs")
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            keyword_str = " ".join(k.lower() for k in keywords)
            for job in data.get("jobs", [])[:30]:
                title = job.get("title", "").lower()
                desc = job.get("description", "").lower()
                if keyword_str and keyword_str not in title and not any(k in title for k in keywords):
                    # Still include if keyword appears in description
                    if not any(k in desc for k in keywords):
                        if keywords != [""]:
                            continue
                jobs.append({
                    "title": job.get("title", ""),
                    "company": job.get("company_name", ""),
                    "location": "Remote",
                    "description": job.get("description", "")[:2000],
                    "url": job.get("url", ""),
                    "salary_min": job.get("salary_min", 0) or 0,
                    "salary_max": job.get("salary_max", 0) or 0,
                    "source_board": "remotive",
                    "posted_date": job.get("publication_date", ""),
                    "employment_type": job.get("job_type", "full_time"),
                })
            return jobs
        except Exception as e:
            print(f"[Scanner] Remotive error: {e}")
            return []

    async def _scan_remoteok(self) -> list[dict[str, Any]]:
        """Scrape RemoteOK free API for remote jobs."""
        try:
            resp = await self.client.get("https://remoteok.com/api")
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for job in data[:30]:
                if isinstance(job, dict) and job.get("title"):
                    jobs.append({
                        "title": job.get("title", ""),
                        "company": job.get("company", ""),
                        "location": "Remote",
                        "description": job.get("description", "")[:2000],
                        "url": job.get("url", ""),
                        "salary_min": 0,
                        "salary_max": int(job.get("salary_max", 0) or 0),
                        "source_board": "remoteok",
                        "posted_date": job.get("date", ""),
                        "employment_type": "full_time",
                    })
            return jobs
        except Exception as e:
            print(f"[Scanner] RemoteOK error: {e}")
            return []

    # ─── New v2.0 Board Scrapers ───────────────────────────────────────

    async def _scan_greenhouse(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Greenhouse Open API for job listings.

        Uses the public boards API to discover companies, then fetches
        jobs per board. Falls back to known company boards + Google Jobs
        if the board discovery fails.
        """
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []
            seen_urls = set()

            def _add_job(job: dict, company_name: str) -> bool:
                """Add a job if it matches keywords and is not a duplicate."""
                nonlocal jobs
                title = job.get("title", "")
                if not title:
                    return False
                title_lower = title.lower()
                # Keyword matching: title must contain at least one keyword
                if not any(k.lower() in title_lower for k in keywords):
                    return False
                url = job.get("absolute_url", "") or job.get("url", "")
                if url and url in seen_urls:
                    return False
                if url:
                    seen_urls.add(url)
                location_obj = job.get("location", {})
                if isinstance(location_obj, dict):
                    location = location_obj.get("name", "")
                else:
                    location = str(location_obj)
                content = job.get("content", "") or job.get("description", "") or ""
                # Strip HTML tags for clean description
                import re as _re
                clean_desc = _re.sub(r"<[^>]+>", "", content)[:2000]
                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "description": clean_desc,
                    "url": url,
                    "salary_min": 0,
                    "salary_max": 0,
                    "source_board": "greenhouse",
                    "posted_date": job.get("updated_at", "") or job.get("created_at", ""),
                    "employment_type": "full_time",
                    "remote_status": "remote" if job.get("remote") else ("hybrid" if job.get("hybrid") else "unknown"),
                })
                return True

            # Try the boards API to discover companies
            try:
                board_resp = await self.client.get(
                    "https://boards-api.greenhouse.io/v1/boards",
                    params={"content": "true", "per_page": 40},
                    timeout=15,
                    headers=_rich_headers(),
                )
                if board_resp.status_code == 200:
                    boards_data = board_resp.json()
                    boards = boards_data.get("boards", [])
                    for board in boards[:15]:
                        board_id = board.get("id", "")
                        board_name = board.get("name", "") or board_id
                        if not board_id:
                            continue
                        try:
                            jobs_resp = await self.client.get(
                                f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs",
                                params={"content": "true", "per_page": 30},
                                timeout=15,
                                headers=_rich_headers(),
                            )
                            if jobs_resp.status_code == 200:
                                jobs_data = jobs_resp.json()
                                for job in jobs_data.get("jobs", []):
                                    _add_job(job, board_name)
                        except Exception as e:
                            print(f"[Scanner] Greenhouse board '{board_id}' error: {e}")
                            continue
                        if len(jobs) >= 50:
                            break
            except Exception as e:
                print(f"[Scanner] Greenhouse board discovery error: {e}")

            # If no jobs found from board discovery, try known companies
            if not jobs:
                known_companies = [
                    "airbnb", "dropbox", "stripe", "datadog", "gitlab",
                    "hashicorp", "cloudflare", "reddit", "pinterest",
                    "coinbase", "mongodb", "square", "doordash",
                    "instacart", "redfin", "zillow", "twilio",
                    "intercom", "notion", "figma",
                ]
                for company in known_companies[:10]:
                    try:
                        resp = await self.client.get(
                            f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs",
                            params={"content": "true", "per_page": 30},
                            timeout=15,
                            headers=_rich_headers(),
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for job in data.get("jobs", []):
                                _add_job(job, company.title())
                    except Exception:
                        continue
                    if len(jobs) >= 50:
                        break

            if jobs:
                print(f"[Scanner] Greenhouse: {len(jobs)} jobs")
                return jobs

            # Final fallback: Google Jobs
            google_jobs = await self._scan_via_google_jobs("greenhouse.io", keywords)
            if google_jobs:
                print(f"[Scanner] Greenhouse: {len(google_jobs)} jobs (Google Jobs)")
                return google_jobs
            return []
        except Exception as e:
            print(f"[Scanner] Greenhouse error: {e}")
            return []

    async def _scan_ashby(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape AshbyHQ jobs using known company board slugs + Google discovery.

        Ashby's public API is per-company:
          GET https://api.ashbyhq.com/posting-api/job-board/{board_name}
        There is no directory endpoint, so we maintain a list of known
        companies and also discover new ones via Google.
        """
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []

            # Known companies using Ashby for job postings
            known_boards = [
                "notion", "airbase", "commonapp", "brex", "deel",
                "webflow", "linear", "raycast", "descript", "heygen",
                "perplexity", "cursor", "clerk", "vercel", "supabase",
                "chainlink", "narval", "scaleai", "runpod", "modal",
            ]

            # Try known boards (limit to first 8 to save time)
            for board_slug in known_boards[:8]:
                try:
                    resp = await self.client.get(
                        f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}",
                        timeout=15,
                        headers=_rich_headers(),
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for job in (data.get("jobs", []) or data.get("postings", []))[:15]:
                            if isinstance(job, dict):
                                title = job.get("title", "") or job.get("text", "")
                                if not title:
                                    continue
                                title_lower = title.lower()
                                if not any(k.lower() in title_lower for k in keywords):
                                    continue
                                company_name = job.get("company", {}).get("name", "") if isinstance(job.get("company"), dict) else (job.get("companyName", "") or board_slug.title())
                                jobs.append({
                                    "title": title,
                                    "company": company_name,
                                    "location": job.get("location", "") or job.get("address", {}).get("addressLocality", "") if isinstance(job.get("address"), dict) else "",
                                    "description": (job.get("descriptionHtml") or job.get("description", "") or "")[:2000],
                                    "url": job.get("applyUrl", "") or f"https://jobs.ashbyhq.com/{board_slug}",
                                    "salary_min": job.get("salary", {}).get("min", 0) if isinstance(job.get("salary"), dict) else (job.get("salaryMin", 0) or 0),
                                    "salary_max": job.get("salary", {}).get("max", 0) if isinstance(job.get("salary"), dict) else (job.get("salaryMax", 0) or 0),
                                    "source_board": "ashby",
                                    "posted_date": job.get("publishedAt", "") or job.get("createdAt", ""),
                                    "employment_type": "full_time",
                                })
                except Exception:
                    continue

            # If we got jobs from known boards, return them
            if jobs:
                print(f"[Scanner] Ashby: {len(jobs)} jobs (known boards)")
                return jobs

            # No jobs found — try Google discovery + Jobs cache
            google_jobs = await self._scan_via_google_jobs("jobs.ashbyhq.com", keywords)
            if google_jobs:
                print(f"[Scanner] Ashby: {len(google_jobs)} jobs (Google Jobs fallback)")
                return google_jobs

            # Last resort: return fallback result
            return []
        except Exception as e:
            print(f"[Scanner] Ashby error: {e}")
            return []

    async def _scan_lever(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Lever API for job listings.

        Lever has a per-company public API:
          GET https://api.lever.co/v0/postings/{company}
        Returns JSON array of active postings.
        """
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []

            # Known companies using Lever for job postings
            known_companies = [
                "lever", "buffi", "buffer", "harvest", "wistia",
                "basecamp", "hey", "hashi", "travisci", "npm",
                "discourse", "ghost", "automattic", "kong",
                "grafana", "influxdata", "elastic", "fastly",
                "netlify", "vercel", "sentry", "datadog",
            ]

            seen_urls = set()
            for company_slug in known_companies[:12]:
                try:
                    resp = await self.client.get(
                        f"https://api.lever.co/v0/postings/{company_slug}",
                        timeout=15,
                        headers=_rich_headers(),
                    )
                    if resp.status_code != 200:
                        continue
                    postings = resp.json()
                    if not isinstance(postings, list):
                        continue
                    for posting in postings[:15]:
                        title = posting.get("text", "") or posting.get("title", "")
                        if not title:
                            continue
                        title_lower = title.lower()
                        if not any(k.lower() in title_lower for k in keywords):
                            continue
                        apply_url_obj = posting.get("applyUrl", {})
                        apply_url = apply_url_obj.get("url", "") if isinstance(apply_url_obj, dict) else str(apply_url_obj)
                        if apply_url in seen_urls:
                            continue
                        seen_urls.add(apply_url)
                        company_name = posting.get("company", "") or company_slug.title()
                        # Clean company name
                        if "-" in company_name:
                            company_name = company_name.replace("-", " ").title()
                        categories = posting.get("categories", {}) or {}
                        if isinstance(categories, dict):
                            location = categories.get("location", "")
                            commitment = categories.get("commitment", "full_time")
                        else:
                            location = ""
                            commitment = "full_time"
                        description_html = posting.get("description", "") or ""
                        import re as _re
                        description_clean = _re.sub(r"<[^>]+>", "", description_html)[:2000]
                        salary = posting.get("salary", {}) or {}
                        jobs.append({
                            "title": title,
                            "company": company_name,
                            "location": location,
                            "description": description_clean,
                            "url": apply_url,
                            "salary_min": salary.get("min", 0) if isinstance(salary, dict) else 0,
                            "salary_max": salary.get("max", 0) if isinstance(salary, dict) else 0,
                            "source_board": "lever",
                            "posted_date": posting.get("createdAt", "") or posting.get("updatedAt", ""),
                            "employment_type": commitment.lower() if commitment else "full_time",
                        })
                except Exception as e:
                    print(f"[Scanner] Lever '{company_slug}' error: {e}")
                    continue

            if jobs:
                print(f"[Scanner] Lever: {len(jobs)} jobs")
                return jobs

            # Fallback: Google Jobs
            google_jobs = await self._scan_via_google_jobs("jobs.lever.co", keywords)
            if google_jobs:
                print(f"[Scanner] Lever: {len(google_jobs)} jobs (Google Jobs)")
                return google_jobs
            return []
        except Exception as e:
            print(f"[Scanner] Lever error: {e}")
            return []

    async def _scan_bamboohr(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape BambooHR job listings using known company portals.

        BambooHR career portals are at:
          https://{company}.bamboohr.com/careers/list
        Returns JSON with a 'jobs' array.
        """
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []

            # Known companies using BambooHR
            known_companies = [
                "zapier", "mailchimp", "automattic", "blend",
                "segment", "expensify", "calendly", "hubspot",
                "godaddy", "newrelic", "databricks", "snowflake",
            ]

            seen_urls = set()
            for company in known_companies[:10]:
                try:
                    resp = await self.client.get(
                        f"https://{company}.bamboohr.com/careers/list",
                        timeout=15,
                        headers={"Accept": "application/json", **_rich_headers()},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for job in data.get("jobs", [])[:15]:
                        title = job.get("jobTitle", "") or job.get("title", "")
                        if not title:
                            continue
                        title_lower = title.lower()
                        if not any(k.lower() in title_lower for k in keywords):
                            continue
                        apply_url = job.get("applyUrl", "") or job.get("url", "")
                        if apply_url in seen_urls:
                            continue
                        seen_urls.add(apply_url)
                        jobs.append({
                            "title": title,
                            "company": job.get("companyName", "") or company.title(),
                            "location": job.get("location", "") or job.get("city", "") or "",
                            "description": (job.get("jobDescription", "") or "").replace("<[^>]*>", "")[:2000],
                            "url": apply_url,
                            "salary_min": 0,
                            "salary_max": 0,
                            "source_board": "bamboohr",
                            "posted_date": job.get("postedDate", "") or job.get("date", ""),
                            "employment_type": "full_time",
                        })
                except Exception as e:
                    print(f"[Scanner] BambooHR '{company}' error: {e}")
                    continue

            if jobs:
                print(f"[Scanner] BambooHR: {len(jobs)} jobs")
                return jobs

            # Fallback: Google Jobs
            google_jobs = await self._scan_via_google_jobs("bamboohr.com", keywords)
            if google_jobs:
                print(f"[Scanner] BambooHR: {len(google_jobs)} jobs (Google Jobs)")
                return google_jobs
            return []
        except Exception as e:
            print(f"[Scanner] BambooHR error: {e}")
            return []

    async def _scan_workday(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Workday job listings using Playwright + Google discovery."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return await self._scan_via_google_jobs("myworkdayjobs.com", keywords)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                keyword_str = " ".join(k.lower() for k in keywords)  # noqa: F841
                jobs = []

                # Search Google for Workday job listings

                search_query = "+".join(keywords) + "+site:myworkdayjobs.com"
                await page.goto(
                    f"https://www.google.com/search?q={search_query}&num=30",
                    wait_until="domcontentloaded",
                    timeout=20000,
                )
                await page.wait_for_timeout(1500)

                # Extract job links
                links = await page.evaluate("""
                    () => {
                        const results = [];
                        const links = document.querySelectorAll('a[href*="myworkdayjobs.com"]');
                        links.forEach(a => {
                            const href = a.href;
                            if (href && !results.includes(href)) {
                                results.push(href);
                            }
                        });
                        return results.slice(0, 30);
                    }
                """)

                for link in links[:20]:
                    try:
                        await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(1000)

                        # Extract job details using page content
                        title = await page.title()
                        body_text = await page.evaluate("() => document.body.innerText")

                        if title and len(title) > 5:
                            title_lower = title.lower()
                            if not any(k.lower() in title_lower for k in keywords):
                                if not any(k.lower() in body_text.lower() for k in keywords):
                                    continue

                            jobs.append({
                                "title": title.replace(" - Job Posting", "").replace(" | Workday", ""),
                                "company": "",
                                "location": "",
                                "description": body_text[:2000],
                                "url": link,
                                "salary_min": 0,
                                "salary_max": 0,
                                "source_board": "workday",
                                "posted_date": "",
                                "employment_type": "full_time",
                            })
                    except Exception as e:
                        print(f"[Scanner] Workday link error: {e}")
                        continue

                await browser.close()
                print(f"[Scanner] Found {len(jobs)} jobs on Workday")
                return jobs

        except Exception as e:
            print(f"[Scanner] Workday Playwright error: {e}")
            return []

    async def _scan_via_google_jobs(self, domain: str, keywords: list[str]) -> list[dict[str, Any]]:
        """Fallback: scan via Google Jobs cache. Used when native API fails."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            query = "+".join(keywords)
            resp = await self.client.get(
                "https://www.google.com/search",
                params={"q": f"{query} job site:{domain}", "num": 20},
                timeout=20,
                headers=_rich_headers(),
            )
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            seen = set()

            # Google SERP selectors (2024+): div.g > a[href] > h3
            # Also try newer Google Jobs widget format
            for result in soup.select("div.g, div[jsdata], div[data-hveid]"):
                link = result.select_one("a[href]")
                title_el = result.select_one("h3")
                snippet_el = result.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")

                # Try Google Jobs embedded cards
                if not title_el:
                    title_el = result.select_one('[class*="jobTitle"], [class*="title"] a')

                if link and title_el:
                    href = link.get("href", "")
                    title = title_el.text.strip()
                    if not title or len(title) < 5:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)

                    title_lower = title.lower()
                    if keyword_str and keyword_str not in title_lower and not any(k.lower() in title_lower for k in keywords):
                        continue

                    jobs.append({
                        "title": title,
                        "company": domain.replace("www.", "").replace(".com", "").title(),
                        "location": "",
                        "description": (snippet_el.text.strip() if snippet_el else "")[:1000],
                        "url": href,
                        "salary_min": 0,
                        "salary_max": 0,
                        "source_board": domain.split(".")[0] if "." in domain else domain,
                        "posted_date": "",
                        "employment_type": "full_time",
                    })

            return jobs
        except Exception as e:
            print(f"[Scanner] Google Jobs fallback error: {e}")
        return []

    async def _scan_hackernews(self, keywords: list[str]) -> list[dict[str, Any]]:
        try:
            # Search for "Who is Hiring" posts from the last 30 days
            resp = await self.client.get(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": "Who is Hiring",
                    "tags": "story",
                    "numericFilters": f"created_at_i>{int(time.time()) - 30*86400}",
                    "hitsPerPage": 3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            jobs = []

            for hit in data.get("hits", []):
                story_id = hit.get("objectID", "")
                # Fetch comments for this story
                comments_resp = await self.client.get(
                    f"https://hn.algolia.com/api/v1/items/{story_id}"
                )
                comments_resp.raise_for_status()
                comments_data = comments_resp.json()

                for child in comments_data.get("children", [])[:50]:
                    text = child.get("text", "")
                    if not text:
                        continue
                    # Parse job postings from comment text
                    lines = text.split("\n")
                    title_line = lines[0].strip() if lines else ""
                    # Check if comment mentions any keyword
                    text_lower = text.lower()
                    if not any(k.lower() in text_lower for k in keywords):
                        continue
                    # Extract company from the first line or " | " separator
                    company = title_line.split("|")[0].strip().lstrip(">").strip() if "|" in title_line else "HN"
                    jobs.append({
                        "title": title_line[:100] if title_line else "HN Job",
                        "company": company,
                        "location": "Remote / Onsite",
                        "description": text[:2000],
                        "url": f"https://news.ycombinator.com/item?id={story_id}",
                        "salary_min": 0,
                        "salary_max": 0,
                        "source_board": "hackernews",
                        "posted_date": hit.get("created_at", ""),
                        "employment_type": "full_time",
                    })
                    if len(jobs) >= 15:
                        break
            return jobs
        except Exception as e:
            print(f"[Scanner] HN error: {e}")
            return []

    # ─── New v3.0 Custom Board Scrapers ────────────────────────────────

    async def _scan_himalayas(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Himalayas.app — JSON API (official) with Playwright fallback."""
        keyword_str = " ".join(k.lower() for k in keywords)

        # ── Tier 1: Official JSON API ─────────────────────────────────
        try:
            jobs = []
            # Try search API first
            for api_url in [
                "https://himalayas.app/jobs/api/search",
                "https://himalayas.app/jobs/api",
            ]:
                try:
                    params = {"limit": 20, "offset": 0}
                    if "search" in api_url:
                        params["q"] = keyword_str
                    resp = await self.client.get(api_url, params=params, timeout=15)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    items = data.get("jobs", []) or data.get("data", []) or data.get("results", [])
                    if not items and isinstance(data, list):
                        items = data
                    for job in items[:20]:
                        if isinstance(job, dict):
                            title = job.get("title", "") or job.get("name", "")
                            if not title:
                                continue
                            title_lower = title.lower()
                            if not any(k.lower() in title_lower for k in keywords):
                                continue
                            company_data = job.get("company", {}) or {}
                            company = (job.get("companyName", "") or
                                      (company_data.get("name", "") if isinstance(company_data, dict) else ""))
                            jobs.append({
                                "title": title,
                                "company": company or "",
                                "location": job.get("locationRestrictions", "") or job.get("location", "") or "Remote",
                                "url": job.get("url", "") or f"https://himalayas.app/jobs/{job.get('slug', '')}",
                                "source_board": "himalayas",
                                "posted_date": job.get("pubDate", "") or job.get("publicationDate", ""),
                                "salary_min": job.get("minSalary", 0) or 0,
                                "salary_max": job.get("maxSalary", 0) or 0,
                                "description": job.get("description", "")[:2000],
                                "employment_type": (job.get("employmentType", "") or "full_time").lower(),
                            })
                    if jobs:
                        print(f"[Scanner] Himalayas: {len(jobs)} jobs (API)")
                        return jobs
                except Exception:
                    continue
        except Exception:
            pass

        # ── Tier 2: Google Jobs fallback ─────────────────────────────
        return await self._scan_via_google_jobs("himalayas.app", keywords)

    async def _scan_wellfound(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Wellfound (AngelList) — Playwright primary, __NEXT_DATA__ fallback.

        Tier 1: Playwright renders the React/Next.js page, extracts job cards
        Tier 2: httpx + __NEXT_DATA__ JSON parsing (if page serves static JSON)
        Tier 3: Google Jobs fallback
        """
        keyword_str = " ".join(k.lower() for k in keywords)

        # ── Tier 1: Playwright ────────────────────────────────────────
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                page = await browser.new_page(
                    user_agent=_random_ua(),
                    viewport={"width": 1920, "height": 1080},
                )

                await page.goto(
                    f"https://wellfound.com/jobs?q={keyword_str.replace(' ', '+')}",
                    wait_until="domcontentloaded",
                    timeout=25000,
                )
                await page.wait_for_timeout(3000)

                # Try __NEXT_DATA__ first (fast path)
                next_data_json = await page.evaluate("""() => {
                    const el = document.getElementById('__NEXT_DATA__');
                    if (el) return el.textContent;
                    return null;
                }""")

                jobs = []
                seen_urls = set()

                if next_data_json:
                    import json as _json
                    try:
                        data = _json.loads(next_data_json)
                        apollo = (data.get("props", {}).get("pageProps", {}).get("apolloState", {}) or
                                 data.get("props", {}).get("apolloState", {}))
                        if apollo:
                            for key, val in apollo.items():
                                if isinstance(val, dict) and val.get("__typename") in ("Job", "JobListing"):
                                    title = val.get("title", "") or val.get("name", "")
                                    if not title:
                                        continue
                                    title_lower = title.lower()
                                    if not any(k.lower() in title_lower for k in keywords):
                                        continue
                                    company_data = val.get("company", {}) or val.get("organization", {})
                                    company = company_data.get("name", "") if isinstance(company_data, dict) else str(company_data)
                                    location = val.get("location", "") or val.get("city", "") or ""
                                    job_url = val.get("url", "") or f"https://wellfound.com/jobs/{val.get('slug', '')}"
                                    if job_url in seen_urls:
                                        continue
                                    seen_urls.add(job_url)
                                    jobs.append({
                                        "title": title,
                                        "company": company if company else "Wellfound Startup",
                                        "location": location if location else "Remote / Onsite",
                                        "url": job_url,
                                        "source_board": "wellfound",
                                        "posted_date": val.get("createdAt", "") or val.get("pubDate", ""),
                                        "salary_min": val.get("salaryMin", 0) or val.get("minSalary", 0) or 0,
                                        "salary_max": val.get("salaryMax", 0) or val.get("maxSalary", 0) or 0,
                                        "description": (val.get("description", "") or val.get("overview", ""))[:2000],
                                        "employment_type": "full_time",
                                    })
                                    if len(jobs) >= 20:
                                        break
                    except Exception:
                        pass

                # If __NEXT_DATA__ didn't yield jobs, extract from rendered DOM
                if not jobs:
                    card_data = await page.evaluate("""() => {
                        const cards = [];
                        const selectors = [
                            'a[href*="/jobs/"][class*="card"]',
                            '[class*="JobCard"]',
                            '[class*="job-card"]',
                            'div[class*="styles__card"]',
                            'a[href*="/startup/"][href*="/job/"]',
                        ];
                        let elements = [];
                        for (const sel of selectors) {
                            const found = document.querySelectorAll(sel);
                            if (found.length > 0) {
                                elements = Array.from(found);
                                break;
                            }
                        }
                        // Fallback: find all links with job-like text
                        if (elements.length === 0) {
                            elements = Array.from(document.querySelectorAll('a[href]')).filter(a => {
                                const text = (a.textContent || '').toLowerCase();
                                const href = (a.href || '').toLowerCase();
                                return (text.includes('engineer') || text.includes('developer') ||
                                        text.includes('scientist') || text.includes('designer') ||
                                        text.includes('manager') || text.includes('analyst')) &&
                                       (href.includes('/jobs/') || href.includes('/job/'));
                            });
                        }
                        for (const el of elements.slice(0, 30)) {
                            const text = el.textContent || '';
                            const href = el.href || '';
                            const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                            // Heuristic: title is usually the first substantive line
                            const title = lines.find(l => l.length > 5 && l.length < 100) || lines[0] || '';
                            const company = lines.find(l => l.length > 2 && l !== title && !l.includes('$') && l.length < 60) || '';
                            cards.push({ title: title.trim(), company: company.trim(), url: href });
                        }
                        return cards;
                    }""")

                    for card in card_data:
                        title = card.get("title", "")
                        if not title or len(title) < 5:
                            continue
                        title_lower = title.lower()
                        if not any(k.lower() in title_lower for k in keywords):
                            continue
                        url = card.get("url", "")
                        if url and url in seen_urls:
                            continue
                        if url:
                            seen_urls.add(url)
                        jobs.append({
                            "title": title,
                            "company": card.get("company", "") or "Wellfound Startup",
                            "location": "Remote / Onsite",
                            "url": url,
                            "source_board": "wellfound",
                            "posted_date": "",
                            "salary_min": 0, "salary_max": 0,
                            "description": "",
                            "employment_type": "full_time",
                        })
                        if len(jobs) >= 20:
                            break

                await browser.close()

                if jobs:
                    print(f"[Scanner] Wellfound: {len(jobs)} jobs (Playwright)")
                    return jobs

                print("[Scanner] Wellfound: Playwright found no jobs, falling back")

        except ImportError:
            print("[Scanner] Wellfound: Playwright not installed")
        except Exception as e:
            print(f"[Scanner] Wellfound Playwright error: {e}")

        # ── Tier 2: httpx + __NEXT_DATA__ (legacy) ────────────────────
        try:
            resp = await self.client.get(
                "https://wellfound.com/jobs",
                params={"q": keyword_str},
                timeout=20,
                headers=_rich_headers(),
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                next_data_el = soup.select_one("script#__NEXT_DATA__")
                if next_data_el:
                    import json as _json
                    data = _json.loads(next_data_el.text)
                    jobs = []
                    apollo = (data.get("props", {}).get("pageProps", {}).get("apolloState", {}) or
                             data.get("props", {}).get("apolloState", {}))
                    if apollo:
                        seen_ids = set()
                        for key, val in apollo.items():
                            if isinstance(val, dict) and val.get("__typename") in ("Job", "JobListing"):
                                title = val.get("title", "") or val.get("name", "")
                                if title and any(k.lower() in title.lower() for k in keywords):
                                    job_id = val.get("id", "") or val.get("slug", "")
                                    if job_id not in seen_ids:
                                        seen_ids.add(job_id)
                                        company_data = val.get("company", {}) or val.get("organization", {})
                                        company = company_data.get("name", "") if isinstance(company_data, dict) else ""
                                        jobs.append({
                                            "title": title,
                                            "company": company or "Wellfound Startup",
                                            "location": val.get("location", "") or "",
                                            "url": val.get("url", "") or "",
                                            "source_board": "wellfound",
                                            "posted_date": val.get("createdAt", "") or val.get("pubDate", ""),
                                            "salary_min": val.get("salaryMin", 0) or 0,
                                            "salary_max": val.get("salaryMax", 0) or 0,
                                            "description": (val.get("description", "") or "")[:2000],
                                            "employment_type": "full_time",
                                        })
                    if jobs:
                        print(f"[Scanner] Wellfound: {len(jobs)} jobs (httpx/__NEXT_DATA__)")
                        return jobs
        except Exception:
            pass

        # ── Tier 3: Google Jobs fallback ─────────────────────────────
        return await self._scan_via_google_jobs("wellfound.com", keywords)



    async def _scan_weworkremotely(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape WeWorkRemotely — has a free JSON endpoint."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            # Try JSON API first
            try:
                resp = await self.client.get(
                    "https://weworkremotely.com/categories/remote-jobs.json",
                    timeout=15,
                    headers=_rich_headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    jobs = []
                    for job in data[:30]:
                        if isinstance(job, dict):
                            title = job.get("title", "") or job.get("name", "")
                            if title:
                                title_lower = title.lower()
                                if not any(k.lower() in title_lower for k in keywords):
                                    continue
                                jobs.append({
                                    "title": title,
                                    "company": job.get("company", "") or job.get("organization", ""),
                                    "location": "Remote",
                                    "url": job.get("url", ""),
                                    "source_board": "weworkremotely",
                                    "posted_date": job.get("date", "") or job.get("pub_date", ""),
                                    "salary_min": 0, "salary_max": 0,
                                    "description": job.get("description", "")[:2000],
                                    "employment_type": "full_time",
                                })
                    if jobs:
                        print(f"[Scanner] Found {len(jobs)} jobs on WeWorkRemotely (API)")
                        return jobs
            except Exception:
                pass

            # Fallback: scrape web
            resp = await self.client.get(
                "https://weworkremotely.com/categories/remote-full-time-jobs",
                timeout=20,
                headers=_rich_headers(),
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            for li in soup.select("li.job, li.feature"):
                title_el = li.select_one("span.title a, h4 a")
                company_el = li.select_one("span.company")
                if title_el:
                    title = title_el.text.strip()
                    title_lower = title.lower()
                    if not any(k.lower() in title_lower for k in keywords):
                        continue
                    jobs.append({
                        "title": title,
                        "company": company_el.text.strip() if company_el else "",
                        "location": "Remote",
                        "url": title_el.get("href", "") if hasattr(title_el, "get") else "",
                        "source_board": "weworkremotely",
                        "posted_date": "",
                        "salary_min": 0, "salary_max": 0,
                        "description": "",
                        "employment_type": "full_time",
                    })
            print(f"[Scanner] Found {len(jobs)} jobs on WeWorkRemotely")
            return jobs
        except Exception as e:
            print(f"[Scanner] WeWorkRemotely error: {e}")
            return []

    async def _scan_instahyre(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Instahyre — India-focused tech hiring platform."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            resp = await self.client.get(
                "https://www.instahyre.com/job-search",
                params={"q": keyword_str},
                timeout=20,
                headers=_rich_headers(),
            )
            if resp.status_code != 200:
                return await self._scan_via_google_jobs("instahyre.com", keywords)
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            # Instahyre uses modern CSS class patterns; try multiple selector strategies
            for card in soup.select('[class*="job"]:not([class*="hidden"]):not([class*="ad"]), '
                                   '[class*="card"]:not([class*="hidden"]), '
                                   '.job-listing, article, li[class*="job"]'):
                title_el = (card.select_one('h3, h2, [class*="title"] a, [class*="heading"] a')
                            or card.select_one('[class*="title"]'))
                company_el = card.select_one('[class*="company"] a, [class*="company"], '
                                            '[class*="org"] a, [class*="org"]')
                link_el = card.select_one('a[href*="/job"]') or card.select_one('a[href]')
                if title_el:
                    title = title_el.text.strip()
                    title_lower = title.lower()
                    if not any(k.lower() in title_lower for k in keywords):
                        continue
                    jobs.append({
                        "title": title,
                        "company": company_el.text.strip() if company_el else "",
                        "location": "",
                        "url": link_el.get("href", "") if link_el else "",
                        "source_board": "instahyre",
                        "posted_date": "",
                        "salary_min": 0, "salary_max": 0,
                        "description": "",
                        "employment_type": "full_time",
                    })
            if len(jobs) < 3:
                google_jobs = await self._scan_via_google_jobs("instahyre.com", keywords)
                jobs.extend(google_jobs)
            print(f"[Scanner] Instahyre: {len(jobs)} jobs")
            return jobs
        except Exception as e:
            print(f"[Scanner] Instahyre error: {e}")
            return []

    async def _scan_protocol(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape ProtocolJobs.ai — AI-matched job search."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            resp = await self.client.get(
                "https://www.protocoljobs.ai/jobs",
                params={"q": keyword_str},
                timeout=20,
                headers=_rich_headers(),
            )
            if resp.status_code != 200:
                return await self._scan_via_google_jobs("protocoljobs.ai", keywords)
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            for card in soup.select('[class*="job"]:not([class*="hidden"]), '
                                   '[class*="card"]:not([class*="hidden"]), '
                                   'article[class*="job"], li[class*="job"]'):
                title_el = (card.select_one('h2, h3, [class*="title"] a, [class*="heading"]')
                            or card.select_one('[class*="job-title"]'))
                company_el = card.select_one('[class*="company"] a, [class*="company"], '
                                            '[class*="org"] a, [class*="org"]')
                if title_el:
                    title = title_el.text.strip()
                    title_lower = title.lower()
                    if not any(k.lower() in title_lower for k in keywords):
                        continue
                    jobs.append({
                        "title": title,
                        "company": company_el.text.strip() if company_el else "",
                        "location": "",
                        "url": "",
                        "source_board": "protocol",
                        "posted_date": "",
                        "salary_min": 0, "salary_max": 0,
                        "description": "",
                        "employment_type": "full_time",
                    })
            print(f"[Scanner] Found {len(jobs)} jobs on Protocol")
            return jobs
        except Exception as e:
            print(f"[Scanner] Protocol error: {e}")
            return []

    async def _scan_welcometothejungle(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Welcome to the Jungle — European job board."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            resp = await self.client.get(
                "https://www.welcometothejungle.com/en/jobs",
                params={"query": keyword_str, "remoteOnly": "true"},
                timeout=20,
                headers={"Accept": "application/json", **_rich_headers()},
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                data = resp.json()
                jobs = []
                for job in (data.get("data", []) or data.get("jobs", []) or data.get("results", []))[:30]:
                    if isinstance(job, dict):
                        title = job.get("title", "") or job.get("name", "") or job.get("jobTitle", "")
                        if title:
                            title_lower = title.lower()
                            if not any(k.lower() in title_lower for k in keywords):
                                continue
                            jobs.append({
                                "title": title,
                                "company": job.get("company", {}).get("name", "") if isinstance(job.get("company"), dict) else job.get("organization", ""),
                                "location": job.get("location", "") or job.get("city", ""),
                                "url": job.get("url", "") or job.get("applyUrl", ""),
                                "source_board": "welcometothejungle",
                                "posted_date": job.get("publishedAt", "") or job.get("date", ""),
                                "salary_min": 0, "salary_max": 0,
                                "description": job.get("description", "")[:2000],
                                "employment_type": "full_time",
                            })
                if jobs:
                    print(f"[Scanner] Found {len(jobs)} jobs on WTTJ (API)")
                    return jobs

            # Fallback: web scrape
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            for card in soup.select('[class*="job"], [class*="card"], article'):
                title_el = card.select_one('h2, h3, [class*="title"]')
                company_el = card.select_one('[class*="company"]')
                if title_el:
                    title = title_el.text.strip()
                    title_lower = title.lower()
                    if not any(k.lower() in title_lower for k in keywords):
                        continue
                    jobs.append({
                        "title": title,
                        "company": company_el.text.strip() if company_el else "",
                        "location": "",
                        "url": "",
                        "source_board": "welcometothejungle",
                        "posted_date": "",
                        "salary_min": 0, "salary_max": 0,
                        "description": "",
                        "employment_type": "full_time",
                    })
            print(f"[Scanner] Found {len(jobs)} jobs on WTTJ")
            return jobs
        except Exception as e:
            print(f"[Scanner] WelcomeToTheJungle error: {e}")
            return []

    async def _scan_workingnomads(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape WorkingNomads — remote job board with API."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            # Try their API first
            try:
                resp = await self.client.get(
                    "https://www.workingnomads.com/api/jobs",
                    params={"q": keyword_str},
                    timeout=15,
                    headers={"Accept": "application/json", **_rich_headers()},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    jobs = []
                    job_list = data.get("data", []) or data.get("jobs", []) or data if isinstance(data, list) else []
                    for job in job_list[:30]:
                        if isinstance(job, dict):
                            title = job.get("title", "") or job.get("name", "")
                            if title:
                                title_lower = title.lower()
                                if not any(k.lower() in title_lower for k in keywords):
                                    continue
                                jobs.append({
                                    "title": title,
                                    "company": job.get("company", "") or job.get("organization", {}).get("name", "") if isinstance(job.get("organization"), dict) else job.get("organization", ""),
                                    "location": "Remote",
                                    "url": job.get("url", ""),
                                    "source_board": "workingnomads",
                                    "posted_date": job.get("date", ""),
                                    "salary_min": 0, "salary_max": 0,
                                    "description": job.get("description", "")[:2000],
                                    "employment_type": "full_time",
                                })
                    if jobs:
                        print(f"[Scanner] Found {len(jobs)} jobs on WorkingNomads (API)")
                        return jobs
            except Exception:
                pass

            # Fallback: web scrape
            resp = await self.client.get(
                "https://www.workingnomads.com/jobs",
                timeout=20,
                headers=_rich_headers(),
            )
            if resp.status_code != 200:
                return await self._scan_via_google_jobs("workingnomads.com", keywords)
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            for card in soup.select('[class*="job"], [class*="card"], article'):
                title_el = card.select_one('h2, h3, [class*="title"]')
                if title_el:
                    title = title_el.text.strip()
                    title_lower = title.lower()
                    if not any(k.lower() in title_lower for k in keywords):
                        continue
                    jobs.append({
                        "title": title,
                        "company": "",
                        "location": "Remote",
                        "url": "",
                        "source_board": "workingnomads",
                        "posted_date": "",
                        "salary_min": 0, "salary_max": 0,
                        "description": "",
                        "employment_type": "full_time",
                    })
            print(f"[Scanner] Found {len(jobs)} jobs on WorkingNomads")
            return jobs
        except Exception as e:
            print(f"[Scanner] WorkingNomads error: {e}")
            return []

    async def _scan_hnhiring(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape HN Hiring aggregator for monthly job threads."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            resp = await self.client.get(
                "https://hnhiring.com",
                timeout=20,
                headers=_rich_headers(),
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            for row in soup.select("tr, div.job, li"):
                title_el = row.select_one("a")
                if title_el:
                    title = title_el.text.strip()
                    title_lower = title.lower()
                    if not any(k.lower() in title_lower for k in keywords):
                        continue
                    jobs.append({
                        "title": title,
                        "company": "",
                        "location": "Remote / Onsite",
                        "url": title_el.get("href", ""),
                        "source_board": "hnhiring",
                        "posted_date": "",
                        "salary_min": 0, "salary_max": 0,
                        "description": "",
                        "employment_type": "full_time",
                    })
            print(f"[Scanner] Found {len(jobs)} jobs on HN Hiring")
            return jobs
        except Exception as e:
            print(f"[Scanner] HN Hiring error: {e}")
            return []

    async def _scan_cutshort(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Cutshort using Playwright (React-based, no public API).

        Cutshort uses CSS Modules with obfuscated class names that change
        frequently, making HTML-based scraping unreliable.  Playwright
        renders the JavaScript and extracts job cards via broad selectors
        and text content.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("[Scanner] Cutshort: Playwright not installed, using Google Jobs fallback")
            return await self._scan_via_google_jobs("cutshort.io", keywords)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                keyword_str = " ".join(k.lower() for k in keywords)  # noqa: F841
                jobs = []

                await page.goto(
                    "https://cutshort.io/jobs",
                    wait_until="domcontentloaded",
                    timeout=20000,
                )
                await page.wait_for_timeout(2000)

                # Extract job cards by finding elements with text content
                # that looks like job titles (h2/h3/strong elements)
                job_data = await page.evaluate("""
                    () => {
                        const results = [];
                        const seen = new Set();
                        // Find elements that commonly contain job titles
                        const candidates = document.querySelectorAll(
                            'h2, h3, h4, [class*="title"], [class*="heading"], strong'
                        );
                        for (const el of candidates) {
                            const text = el.textContent.trim();
                            // Skip short text, navigation, footer items
                            if (text.length < 10 || text.length > 150) continue;
                            if (text.includes('Login') || text.includes('Sign up')) continue;
                            // Look for keywords typical of job titles
                            if (/\\b(engineer|developer|designer|manager|analyst|architect|intern|lead|senior|junior|full.?stack|frontend|backend|devops|sde|software|data|product|ml|ai)\\b/i.test(text)) {
                                if (seen.has(text)) continue;
                                seen.add(text);
                                // Try to find the company name nearby
                                const parent = el.closest('div, article, li, section');
                                let company = '';
                                if (parent) {
                                    const allText = parent.textContent;
                                    const lines = allText.split('\\n').map(s => s.trim()).filter(Boolean);
                                    // Company is usually the next distinct line after title
                                    for (let i = 0; i < lines.length; i++) {
                                        if (lines[i] === text && i + 1 < lines.length) {
                                            company = lines[i + 1];
                                            break;
                                        }
                                    }
                                    // If company is too long, it's probably not a company
                                    if (company.length > 60) company = '';
                                }
                                results.push({ title: text, company });
                            }
                        }
                        return results.slice(0, 20);
                    }
                """)

                for item in job_data:
                    title = item.get("title", "")
                    company = item.get("company", "")
                    if title:
                        title_lower = title.lower()
                        if any(k.lower() in title_lower for k in keywords):
                            jobs.append({
                                "title": title,
                                "company": company if company else "Cutshort",
                                "location": "",
                                "url": "",
                                "source_board": "cutshort",
                                "posted_date": "",
                                "salary_min": 0, "salary_max": 0,
                                "description": "",
                                "employment_type": "full_time",
                            })

                await browser.close()

                if not jobs:
                    print("[Scanner] Cutshort: no jobs found via Playwright, falling back to Google Jobs")
                    return await self._scan_via_google_jobs("cutshort.io", keywords)

                print(f"[Scanner] Cutshort: {len(jobs)} jobs")
                return jobs
        except Exception as e:
            print(f"[Scanner] Cutshort error: {e}")
            return await self._scan_via_google_jobs("cutshort.io", keywords)

    async def _scan_relocateme(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Relocate.me — relocation/sponsorship jobs."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            resp = await self.client.get(
                "https://relocate.me/search",
                params={"q": keyword_str, "remote": "true"},
                timeout=20,
                headers=_rich_headers(),
            )
            if resp.status_code != 200:
                return await self._scan_via_google_jobs("relocate.me", keywords)
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            for card in soup.select('[class*="job"], [class*="card"], [class*="listing"]'):
                title_el = card.select_one('h2, h3, [class*="title"]')
                company_el = card.select_one('[class*="company"], [class*="org"]')
                if not title_el:
                    continue
                title = title_el.text.strip()
                title_lower = title.lower()
                if not any(k.lower() in title_lower for k in keywords):
                    continue

                # ── URL extraction ────────────────────────────────────
                # Try: title wrapped in <a>, title itself is <a>, or any detail link in the card
                link_el = None
                if title_el.name == 'a' and title_el.get('href'):
                    link_el = title_el
                elif title_el.find_parent('a') and title_el.find_parent('a').get('href'):
                    link_el = title_el.find_parent('a')
                else:
                    link_el = (card.select_one('a[href*="relocate.me/"]') or
                               card.select_one('a[href*="/"]') or
                               card.select_one('a[href]'))
                href = link_el.get('href', '').strip() if link_el else ''
                if href and not href.startswith('http'):
                    href = 'https://relocate.me' + href if href.startswith('/') else 'https://relocate.me/' + href

                # ── Location extraction ───────────────────────────────
                location_el = (card.select_one('[class*="location"]') or
                               card.select_one('[class*="city"]') or
                               card.select_one('[class*="place"]'))
                location = location_el.text.strip() if location_el else ''

                # ── Description / snippet extraction ──────────────────
                desc_el = (card.select_one('[class*="description"]') or
                           card.select_one('[class*="snippet"]') or
                           card.select_one('[class*="summary"]') or
                           card.select_one('p'))
                description = (desc_el.text.strip()[:2000] if desc_el else '')

                jobs.append({
                    "title": title,
                    "company": company_el.text.strip() if company_el else "",
                    "location": location,
                    "url": href,
                    "source_board": "relocateme",
                    "posted_date": "",
                    "salary_min": 0, "salary_max": 0,
                    "description": description,
                    "employment_type": "full_time",
                })
            print(f"[Scanner] Found {len(jobs)} jobs on Relocate.me")
            return jobs
        except Exception as e:
            print(f"[Scanner] Relocate.me error: {e}")
            return []

    # ─── Playwright-based scrapers ─────────────────────────────────────

    async def _scan_board(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Dispatch to the appropriate scraper based on board name."""
        # JobSpy-backed boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter,
        # Google for Jobs) — stealth scraping maintained by the jobspy library.
        # Falls back to the legacy Playwright/HTTP scraper when unavailable.
        if board in JOBSPY_SITES:
            jobspy_jobs = await self._scan_jobspy_board(board, keywords, location)
            if jobspy_jobs:
                return jobspy_jobs
            if board == "google":
                # Google for Jobs returns nothing from datacenter IPs and has
                # no useful legacy fallback (generic SERP parsing is junk).
                return []

        url = JOB_BOARDS.get(board)
        if not url:
            return []

        # Free API-based sources (no keys needed)
        if board == "remotive":
            return await self._scan_remotive(keywords)
        if board == "remoteok":
            return await self._scan_remoteok()
        if board == "hn_algolia":
            return await self._scan_hackernews(keywords)
        if board == "greenhouse":
            return await self._scan_greenhouse(keywords)
        if board == "ashby":
            return await self._scan_ashby(keywords)
        if board == "lever":
            return await self._scan_lever(keywords)
        if board == "bamboohr":
            return await self._scan_bamboohr(keywords)
        if board == "workday":
            return await self._scan_workday(keywords)

        # ─── New v3.0 boards ────────────────────────────────────────
        if board == "himalayas":
            return await self._scan_himalayas(keywords)
        if board == "wellfound":
            return await self._scan_wellfound(keywords)
        if board == "weworkremotely":
            return await self._scan_weworkremotely(keywords)
        if board == "instahyre":
            return await self._scan_instahyre(keywords)
        if board == "protocol":
            return await self._scan_protocol(keywords)
        if board == "welcometothejungle":
            return await self._scan_welcometothejungle(keywords)
        if board == "cutshort":
            return await self._scan_cutshort(keywords)
        if board == "relocateme":
            return await self._scan_relocateme(keywords)
        if board == "workingnomads":
            return await self._scan_workingnomads(keywords)
        if board == "hnhiring":
            return await self._scan_hnhiring(keywords)

        # Try Playwright first for LinkedIn/Indeed, fall back to HTTP
        if board in ("linkedin", "indeed", "glassdoor"):
            try:
                return await self._scan_with_playwright(board, keywords, location)
            except ImportError:
                print(f"[Scanner] Playwright not installed, using HTTP for {board}")
            except Exception as e:
                print(f"[Scanner] Playwright failed for {board}: {e}")

        # HTTP fallback
        return await self._scan_with_http(board, keywords, location)

    async def _scan_jobspy_board(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Scan an anti-bot-heavy board via the `jobspy` library.

        JobSpy wraps Playwright with stealth and maintains the selectors for
        LinkedIn, Indeed, Glassdoor, ZipRecruiter & Google for Jobs.  Returns
        [] on any failure so _scan_board falls back to the legacy scraper —
        this adapter never breaks a scan, it only makes it stronger.

        Returns:
            List of normalized job listings (source_board = board key).
        """
        try:
            from jobspy import scrape_jobs
        except ImportError:
            print(f"[Scanner] {board}: jobspy not installed — using legacy scraper")
            return []

        try:
            kwargs: dict[str, Any] = {
                "site_name": [_JOBSPY_SITE_NAMES[board]],
                "results_wanted": JOBSPY_RESULTS_PER_SITE,
                "hours_old": JOBSPY_HOURS_OLD,
                "verbose": 0,
                "description_format": "markdown",
            }
            search_term = _jobspy_search_term(keywords)
            if board == "google":
                # Google for Jobs uses its own search-box query ("since
                # yesterday" was too restrictive — it needs the exact
                # syntax Google's jobs widget expects)
                kwargs["google_search_term"] = f"{search_term} jobs"
            else:
                kwargs["search_term"] = search_term
                if location and location.strip().lower() not in ("", "global"):
                    kwargs["location"] = location
                if board in ("indeed", "glassdoor"):
                    kwargs["country_indeed"] = JOBSPY_COUNTRY
                if board == "linkedin":
                    kwargs["linkedin_fetch_description"] = True  # fuller data, direct URLs

            # scrape_jobs is synchronous (Playwright under the hood) — run it
            # off the event loop, capped by the same browser-concurrency
            # semaphore the legacy Playwright scrapers use.
            sem = await self._get_playwright_sem()
            async with sem:
                df = await asyncio.to_thread(scrape_jobs, **kwargs)
            if df is None or len(df) == 0:
                print(f"[Scanner] {board}: JobSpy returned 0 jobs")
                return []
        except Exception as e:
            print(f"[Scanner] {board}: JobSpy error: {e}")
            return []

        jobs: list[dict[str, Any]] = []
        for record in df.to_dict("records"):
            job = _jobspy_row_to_job(record, board)
            if job and _matches_any_keyword(job, keywords):
                jobs.append(job)

        print(f"[Scanner] {board}: {len(jobs)} jobs (JobSpy)")
        return jobs

    # Playwright concurrency semaphore — limit to 2 concurrent browser instances
    _playwright_sem: asyncio.Semaphore | None = None

    async def _get_playwright_sem(self) -> asyncio.Semaphore:
        """Get or create the Playwright concurrency semaphore."""
        if self._playwright_sem is None:
            self._playwright_sem = asyncio.Semaphore(2)
        return self._playwright_sem

    async def _scan_with_playwright(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Scan a job board using Playwright headless browser.

        Playwright launches a full Chromium instance per board, which is
        resource-intensive.  A separate semaphore limits concurrent Playwright
        instances to 2 to avoid exhausting CPU/memory.

        If Playwright fails (timeout, blocked, etc.) falls back to Google Jobs.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print(f"[Scanner] Playwright not installed — Google Jobs fallback for {board}")
            return await self._scan_via_google_jobs(f"{board}.com", keywords)

        sem = await self._get_playwright_sem()
        async with sem:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                    )
                    context = await browser.new_context(
                        user_agent=_random_ua(),
                        viewport={"width": 1920, "height": 1080},
                    )
                    page = await context.new_page()

                    query = "+".join(keywords)
                    url = JOB_BOARDS[board]
                    jobs = []

                    if board == "linkedin":
                        await page.goto(
                            f"{url}?keywords={query}&location={location}",
                            wait_until="domcontentloaded",
                            timeout=25000,
                        )
                        await page.wait_for_timeout(3000)
                        jobs = await self._parse_linkedin_playwright(page)
                    elif board == "indeed":
                        await page.goto(
                            f"{url}?q={query}&l={location}",
                            wait_until="domcontentloaded",
                            timeout=25000,
                        )
                        await page.wait_for_timeout(3000)
                        jobs = await self._parse_indeed_playwright(page)
                    elif board == "glassdoor":
                        await page.goto(
                            f"{url}?q={query}&l={location}&fromAge=30",
                            wait_until="domcontentloaded",
                            timeout=25000,
                        )
                        await page.wait_for_timeout(3000)
                        # Use generic extraction for Glassdoor via Playwright
                        html = await page.content()
                        soup = BeautifulSoup(html, "lxml")
                        jobs = self._parse_glassdoor(soup)

                    await browser.close()

                    if jobs:
                        for job in jobs:
                            job["source"] = board
                            job["scanned_at"] = datetime.now(timezone.utc).isoformat()
                        print(f"[Scanner] {board}: {len(jobs)} jobs (Playwright)")
                        return jobs

                    # Playwright returned no results — try Google Jobs fallback
                    print(f"[Scanner] {board}: Playwright returned 0 jobs, trying Google Jobs")
                    google_jobs = await self._scan_via_google_jobs(f"{board}.com", keywords)
                    if google_jobs:
                        for job in google_jobs:
                            job["source"] = board
                            job["scanned_at"] = datetime.now(timezone.utc).isoformat()
                        return google_jobs
                    return []

            except Exception as e:
                print(f"[Scanner] {board} Playwright error: {e}")
                # Fallback to Google Jobs
                google_jobs = await self._scan_via_google_jobs(f"{board}.com", keywords)
                if google_jobs:
                    for job in google_jobs:
                        job["source"] = board
                        job["scanned_at"] = datetime.now(timezone.utc).isoformat()
                    return google_jobs
                return []

    async def _parse_linkedin_playwright(self, page) -> list[dict[str, Any]]:
        """Parse LinkedIn jobs from Playwright page."""
        jobs = []
        try:
            cards = await page.query_selector_all(".job-search-card, .job-card-container")
            for card in cards[:15]:
                title_el = await card.query_selector("a.job-card-list__title, .base-search-card__title")
                company_el = await card.query_selector(".job-card-container__company-name, .base-search-card__subtitle")
                location_el = await card.query_selector(".job-card-container__metadata-wrapper, .job-search-card__location")
                link = await card.get_attribute("href") if await card.query_selector("a") else ""
                title = await title_el.inner_text() if title_el else ""
                company = await company_el.inner_text() if company_el else ""
                location_text = await location_el.inner_text() if location_el else ""
                if title:
                    jobs.append({"title": title.strip(), "company": company.strip(), "location": location_text.strip(), "url": link or "", "source_board": "linkedin"})
        except Exception as e:
            print(f"[Scanner] LinkedIn Playwright parse error: {e}")
        return jobs

    async def _parse_indeed_playwright(self, page) -> list[dict[str, Any]]:
        """Parse Indeed jobs from Playwright page."""
        jobs = []
        try:
            cards = await page.query_selector_all(".job_seen_beacon, .jobCard")
            for card in cards[:15]:
                title_el = await card.query_selector("h2.jobTitle a, .jobTitle")
                company_el = await card.query_selector(".companyName, .companyInfo")
                location_el = await card.query_selector(".companyLocation")
                href = await title_el.get_attribute("href") if title_el else ""
                title = await title_el.inner_text() if title_el else ""
                company = await company_el.inner_text() if company_el else ""
                location_text = await location_el.inner_text() if location_el else ""
                if title:
                    jobs.append({"title": title.strip(), "company": company.strip(), "location": location_text.strip(), "url": f"https://www.indeed.com{href}" if href else "", "source_board": "indeed"})
        except Exception as e:
            print(f"[Scanner] Indeed Playwright parse error: {e}")
        return jobs

    async def _scan_with_http(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Fallback HTTP-based scanning with rich headers."""
        url = JOB_BOARDS.get(board)
        if not url:
            return []
        query = "+".join(keywords)
        params = {"q": query, "l": location, "sort": "date"}
        try:
            response = await self.client.get(url, params=params, headers=_rich_headers(), timeout=20)
            if response.status_code != 200:
                print(f"[Scanner] HTTP {response.status_code} on {board}")
                return []
            soup = BeautifulSoup(response.text, "lxml")
            jobs = self._parse_listings(board, soup)
            for job in jobs:
                job["source_board"] = board
                job["scanned_at"] = datetime.now(timezone.utc).isoformat()
            return jobs
        except Exception as e:
            print(f"[Scanner] HTTP error on {board}: {e}")
            return []

    def _parse_listings(self, board: str, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse job listings from HTML based on board-specific structure."""
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
            job["source_board"] = board
            job["scanned_at"] = datetime.now(timezone.utc).isoformat()

        return jobs

    def _parse_linkedin(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse LinkedIn job search results (multiple selector strategies)."""
        jobs = []
        # Try multiple LinkedIn card selectors (they change frequently)
        cards = (soup.select(".job-search-card")
                 or soup.select("[class*='search-card']")
                 or soup.select(".base-card")
                 or soup.select("li[class*='job']"))
        for card in cards:
            title_el = (card.select_one(".base-search-card__title")
                        or card.select_one("a[class*='title']")
                        or card.select_one("h3 a, h2 a"))
            company_el = (card.select_one(".base-search-card__subtitle")
                          or card.select_one("[class*='company']")
                          or card.select_one("[class*='subtitle']"))
            location_el = (card.select_one(".job-search-card__location")
                           or card.select_one("[class*='location']"))
            link_el = (card.select_one("a.base-card__full-link")
                       or card.select_one("a[href*='/jobs/view']")
                       or card.select_one("a[href]"))

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": location_el.text.strip() if location_el else "",
                    "url": link_el.get("href", "") if link_el else "",
                })
        return jobs

    def _parse_indeed(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse Indeed job search results (multiple selector strategies)."""
        jobs = []
        cards = (soup.select(".job_seen_beacon")
                 or soup.select("[class*='jobCard']")
                 or soup.select(".jobCard")
                 or soup.select("[data-testid*='job']")
                 or soup.select("li[class*='job']"))
        for card in cards:
            title_el = (card.select_one("h2.jobTitle a")
                        or card.select_one("a[class*='title']")
                        or card.select_one("h2 a, h3 a"))
            company_el = (card.select_one(".companyName")
                          or card.select_one("[class*='company']")
                          or card.select_one("[class*='employer']"))
            location_el = (card.select_one(".companyLocation")
                           or card.select_one("[class*='location']"))

            if title_el and company_el:
                href = title_el.get("href", "")
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": location_el.text.strip() if location_el else "",
                    "url": f"https://www.indeed.com{href}" if href else "",
                })
        return jobs

    def _parse_glassdoor(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse Glassdoor job search results (multiple selector strategies)."""
        jobs = []
        # Glassdoor uses dynamic class names; try multiple patterns
        cards = (soup.select(".jobListing")
                 or soup.select("[class*='JobCard']")
                 or soup.select("[class*='job-card']")
                 or soup.select("li[class*='job']")
                 or soup.select("article"))
        for card in cards:
            title_el = (card.select_one(".jobTitle")
                        or card.select_one("[class*='title'] a")
                        or card.select_one("a[class*='title']")
                        or card.select_one("h2 a, h3 a"))
            company_el = (card.select_one(".employerName")
                          or card.select_one("[class*='company'] a, [class*='company']")
                          or card.select_one("[class*='employer']"))
            location_el = (card.select_one(".location")
                           or card.select_one("[class*='location']"))
            link_el = card.select_one("a[href*='/job-listing']") or card.select_one("a[href]")

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": location_el.text.strip() if location_el else "",
                    "url": link_el.get("href", "") if link_el else "",
                })
        return jobs

    def _parse_generic(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Generic fallback parser for unknown board structures.

        Uses a broad set of selectors that work across many job boards.
        Prioritises structured data (JSON-LD, microdata) when available.
        """
        jobs = []

        # First try JSON-LD structured data (most reliable).
        # Keyword filtering is NOT applied here because this parser
        # doesn't receive the keywords list — filtering happens during
        # dedup/evaluation downstream.
        import json as _json
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = _json.loads(script.text)
                if isinstance(data, dict):
                    items = data.get("itemListElement", [data])
                    for item in items:
                        if isinstance(item, dict):
                            title = (item.get("name", "")
                                     or item.get("title", ""))
                            if not title:
                                continue
                            company = ""
                            if "hiringOrganization" in item:
                                co = item["hiringOrganization"]
                                company = co.get("name", "") if isinstance(co, dict) else str(co)
                            jobs.append({
                                "title": title,
                                "company": company,
                                "location": item.get("jobLocation", {}).get("address", {}).get("addressLocality", "") if isinstance(item.get("jobLocation"), dict) else "",
                                "url": item.get("url", ""),
                                "source_board": "",
                            })
            except Exception:
                pass

        if jobs:
            return jobs

        # Fallback: broad HTML selectors
        for card in soup.select('[class*="job"]:not([class*="hidden"]):not([class*="ad"]), '
                               '[class*="listing"]:not([class*="hidden"]), '
                               '[class*="card"]:not([class*="hidden"]), '
                               'li[class*="job"], tr[class*="job"]'):
            title_el = (card.select_one('h2 a, h3 a, [class*="title"] a, [class*="position"] a')
                        or card.select_one('h2, h3, [class*="title"], [class*="position"]'))
            company_el = (card.select_one('[class*="company"] a, [class*="company"]')
                          or card.select_one('[class*="employer"] a, [class*="employer"]')
                          or card.select_one('[class*="org"]'))
            link_el = card.select_one('a[href*="/job"]') or card.select_one('a[href]')

            if title_el and company_el:
                jobs.append({
                    "title": title_el.text.strip(),
                    "company": company_el.text.strip(),
                    "location": "",
                    "url": link_el.get("href", "") if link_el else "",
                })
        return jobs

    async def close(self):
        await self.client.aclose()
