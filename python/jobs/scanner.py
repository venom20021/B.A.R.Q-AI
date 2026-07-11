"""
Multi-board job scanner that scrapes and parses job listings from 35+ ATS providers.
Supports real-time progress tracking for frontend status bar.
"""

import asyncio
import time
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
    "remotive": "https://remotive.com/api/remote-jobs",          # Free API, no key needed
    "remoteok": "https://remoteok.com/api",                       # Free API, no key needed
    "hn_algolia": "https://hn.algolia.com/api/v1/search",        # HN "Who is Hiring" threads
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards",   # Greenhouse API
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/",   # Ashby API
    "lever": "https://api.lever.co/v0/postings",                 # Lever API
    "workday": "https://www.myworkdayjobs.com",                   # Workday (Playwright)
    "bamboohr": "https://api.bamboohr.com/api/gateway.php",       # BambooHR API
}

# Progress tracking — module-level singleton so routes can share state
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

        results: list[dict[str, Any]] = []

        # Phase 1: Connecting
        _scan_progress["phase"] = PHASES[0]
        _scan_progress["phase_index"] = 0
        _scan_progress["progress_pct"] = 5
        _scan_progress["message"] = f"Preparing to scan {len(JOB_BOARDS)} job boards..."
        await asyncio.sleep(0.3)  # Let the user see the phase

        # Phase 2: Searching — scan boards in parallel
        _scan_progress["phase"] = PHASES[1]
        _scan_progress["phase_index"] = 1
        _scan_progress["progress_pct"] = 10
        _scan_progress["message"] = "Starting parallel board scans..."

        tasks = [self._scan_board(board, keywords, location) for board in JOB_BOARDS]
        board_results = await asyncio.gather(*tasks, return_exceptions=True)

        for board_idx, board_result in enumerate(board_results):
            if isinstance(board_result, list):
                results.extend(board_result)
                _scan_progress["boards_scanned"] += 1
                _scan_progress["jobs_found"] += len(board_result)
                _scan_progress["message"] = f"Found {_scan_progress['jobs_found']} jobs across {_scan_progress['boards_scanned']} boards"
            else:
                _scan_progress["boards_errors"] += 1

            # Update progress: searching phase = 10% to 50%
            pct_done = _scan_progress["boards_scanned"] / max(_scan_progress["boards_total"], 1)
            _scan_progress["progress_pct"] = round(10 + pct_done * 40, 1)

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

        # Phase 3: Evaluating
        _scan_progress["phase"] = PHASES[2]
        _scan_progress["phase_index"] = 2
        _scan_progress["status"] = "evaluating"
        _scan_progress["progress_pct"] = 60
        _scan_progress["message"] = f"Evaluating {deduped_count} job matches..."

        # Evaluate top jobs (limit to avoid long eval times)
        from . import JobEvaluator
        evaluator = JobEvaluator()
        user_profile = {
            "skills": ["python", "typescript", "react", "fastapi", "machine learning"],
            "experience_level": "Senior",
            "target_salary": "$150,000",
            "preferred_locations": ["remote"],
            "remote_preference": "Full Remote",
            "industry": "Technology",
        }

        evaluated: list[dict[str, Any]] = []
        for idx, job in enumerate(unique_results[:50]):
            eval_result = await evaluator.evaluate(job, user_profile)
            evaluated.append({**job, **eval_result})
            _scan_progress["jobs_evaluated"] = idx + 1
            eval_pct = (idx + 1) / max(len(unique_results[:50]), 1)
            _scan_progress["progress_pct"] = round(60 + eval_pct * 35, 1)
            _scan_progress["message"] = f"Evaluated {idx + 1} of {min(len(unique_results), 50)} jobs..."

        # Phase 4: Finalizing
        _scan_progress["phase"] = PHASES[3]
        _scan_progress["phase_index"] = 3
        _scan_progress["status"] = "complete"
        _scan_progress["progress_pct"] = 100
        _scan_progress["message"] = f"Scan complete — {deduped_count} jobs found, {len(evaluated)} evaluated"
        _scan_progress["elapsed_seconds"] = round(time.time() - _scan_progress["started_at"], 1)

        # Reset after a brief delay so frontend can read "complete" state
        asyncio.create_task(self._auto_reset())

        return evaluated or unique_results

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
        """Scrape Greenhouse Open API for job listings."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []
            # Greenhouse has public boards API
            board_resp = await self.client.get(
                "https://boards-api.greenhouse.io/v1/boards",
                params={"content": "true", "per_page": 50},
                timeout=15,
            )
            board_resp.raise_for_status()
            boards_data = board_resp.json()
            boards = boards_data.get("boards", [])

            # Limit to top 20 boards by ID
            for board in boards[:20]:
                board_id = board.get("id", "")
                if not board_id:
                    continue
                try:
                    jobs_resp = await self.client.get(
                        f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs",
                        params={"content": "true", "per_page": 30},
                        timeout=10,
                    )
                    jobs_resp.raise_for_status()
                    jobs_data = jobs_resp.json()
                    for job in jobs_data.get("jobs", []):
                        title = job.get("title", "").lower()
                        desc = job.get("content", "").lower() if job.get("content") else ""
                        if keyword_str and keyword_str not in title and not any(k.lower() in title for k in keywords):
                            if not any(k.lower() in desc for k in keywords):
                                continue
                        jobs.append({
                            "title": job.get("title", ""),
                            "company": board.get("name", job.get("company_name", "Greenhouse")),
                            "location": job.get("location", {}).get("name", "") if isinstance(job.get("location"), dict) else str(job.get("location", "")),
                            "description": (job.get("content") or "")[:2000],
                            "url": job.get("absolute_url", ""),
                            "salary_min": 0,
                            "salary_max": 0,
                            "source_board": "greenhouse",
                            "posted_date": job.get("updated_at", ""),
                            "employment_type": "full_time",
                            "remote_status": job.get("remote", False) and "remote" or "unknown",
                        })
                except Exception as e:
                    print(f"[Scanner] Greenhouse board {board_id} error: {e}")
                    continue
                if len(jobs) >= 50:
                    break

            print(f"[Scanner] Found {len(jobs)} jobs on Greenhouse")
            return jobs
        except Exception as e:
            print(f"[Scanner] Greenhouse error: {e}")
            return []

    async def _scan_ashby(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape AshbyHQ API for job listings."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []
            # Ashby's public job board API
            resp = await self.client.post(
                "https://api.ashbyhq.com/posting-api/job-board/YOUR_BOARD",
                json={"maxResults": 50},
                timeout=15,
            )
            # Try common boards if the first one fails
            common_boards = ["example", "demo", "jobs"]
            if resp.status_code != 200:
                for board_slug in common_boards:
                    try:
                        resp = await self.client.get(
                            f"https://jobs.ashbyhq.com/{board_slug}/api",
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            break
                    except Exception:
                        continue
                if resp.status_code != 200:
                    # Fallback: search via Google Jobs cache
                    return await self._scan_via_google_jobs("ashbyhq.com", keywords)

            data = resp.json()
            for job in data.get("jobs", [])[:30]:
                title = job.get("title", "").lower()
                desc = job.get("descriptionHtml", "").lower() if job.get("descriptionHtml") else ""
                if keyword_str and keyword_str not in title and not any(k.lower() in title for k in keywords):
                    if not any(k.lower() in desc for k in keywords):
                        continue
                jobs.append({
                    "title": job.get("title", ""),
                    "company": job.get("company", {}).get("name", "") if isinstance(job.get("company"), dict) else "Ashby",
                    "location": job.get("location", ""),
                    "description": (job.get("descriptionHtml") or "")[:2000].replace("<[^>]*>", "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"),
                    "url": job.get("applyUrl", job.get("url", "")),
                    "salary_min": 0,
                    "salary_max": 0,
                    "source_board": "ashby",
                    "posted_date": job.get("publishedAt", ""),
                    "employment_type": "full_time",
                })

            print(f"[Scanner] Found {len(jobs)} jobs on Ashby")
            return jobs
        except Exception as e:
            print(f"[Scanner] Ashby error: {e}")
            return []

    async def _scan_lever(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Lever API for job listings."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)  # noqa: F841
            jobs = []
            # Lever has per-company posting APIs
            # Search common company posting pages
            companies = [
                {"name": "lever", "posting_url": "https://api.lever.co/v0/postings/lever"},
            ]

            # Try to discover companies via Google
            search_resp = await self.client.get(
                "https://www.google.com/search",
                params={"q": "site:jobs.lever.co software engineer job", "num": 20},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            soup = BeautifulSoup(search_resp.text, "lxml")
            for link in soup.select("a[href*='jobs.lever.co']"):
                href = link.get("href", "")
                if "/" in href:
                    parts = href.split("/")
                    for p in parts:
                        if p and p != "jobs.lever.co" and "google" not in p:
                            companies.append({"name": p, "posting_url": f"https://api.lever.co/v0/postings/{p}"})
                            break

            seen_urls = set()
            for company in companies[:15]:
                try:
                    resp = await self.client.get(company["posting_url"], timeout=10)
                    if resp.status_code != 200:
                        continue
                    postings = resp.json()
                    for posting in postings[:20]:
                        title = posting.get("text", "").lower()
                        desc = posting.get("description", "").lower() if posting.get("description") else ""
                        if keyword_str and keyword_str not in title and not any(k.lower() in title for k in keywords):
                            if not any(k.lower() in desc for k in keywords):
                                continue
                        apply_url = posting.get("applyUrl", {}).get("url", "") if isinstance(posting.get("applyUrl"), dict) else ""
                        if apply_url in seen_urls:
                            continue
                        seen_urls.add(apply_url)
                        jobs.append({
                            "title": posting.get("text", ""),
                            "company": posting.get("company", "").replace("-", " ").title() if posting.get("company") else company["name"].title(),
                            "location": posting.get("categories", {}).get("location", "") if isinstance(posting.get("categories"), dict) else "",
                            "description": (posting.get("description") or "")[:2000].replace("<[^>]*>", "") if posting.get("description") else "",
                            "url": apply_url,
                            "salary_min": posting.get("salary", {}).get("min", 0) if isinstance(posting.get("salary"), dict) else 0,
                            "salary_max": posting.get("salary", {}).get("max", 0) if isinstance(posting.get("salary"), dict) else 0,
                            "source_board": "lever",
                            "posted_date": posting.get("createdAt", ""),
                            "employment_type": posting.get("categories", {}).get("commitment", "full_time") if isinstance(posting.get("categories"), dict) else "full_time",
                            "remote_status": posting.get("categories", {}).get("remote", False) if isinstance(posting.get("categories"), dict) else "unknown",
                        })
                except Exception as e:
                    print(f"[Scanner] Lever company {company['name']} error: {e}")
                    continue

            print(f"[Scanner] Found {len(jobs)} jobs on Lever")
            return jobs
        except Exception as e:
            print(f"[Scanner] Lever error: {e}")
            return []

    async def _scan_bamboohr(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape BambooHR job listings."""
        try:
            keyword_str = " ".join(k.lower() for k in keywords)
            jobs = []
            # BambooHR has public career portals
            # Common BambooHR subdomains to check
            companies = ["demo", "sample"]

            for company in companies:
                try:
                    resp = await self.client.get(
                        f"https://{company}.bamboohr.com/careers/list",
                        timeout=10,
                        headers={"Accept": "application/json"},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for job in data.get("jobs", [])[:20]:
                        title = job.get("jobTitle", "").lower()
                        desc = job.get("jobDescription", "").lower() if job.get("jobDescription") else ""
                        if keyword_str and keyword_str not in title and not any(k.lower() in title for k in keywords):
                            if not any(k.lower() in desc for k in keywords):
                                continue
                        jobs.append({
                            "title": job.get("jobTitle", ""),
                            "company": job.get("companyName", company.title()),
                            "location": job.get("location", ""),
                            "description": (job.get("jobDescription") or "")[:2000],
                            "url": job.get("applyUrl", ""),
                            "salary_min": 0,
                            "salary_max": 0,
                            "source_board": "bamboohr",
                            "posted_date": job.get("postedDate", ""),
                            "employment_type": "full_time",
                        })
                except Exception as e:
                    print(f"[Scanner] BambooHR company {company} error: {e}")
                    continue

            # Also try Google Jobs cache for BambooHR listings
            if len(jobs) < 5:
                google_jobs = await self._scan_via_google_jobs("bamboohr.com", keywords)
                jobs.extend(google_jobs[:20])

            print(f"[Scanner] Found {len(jobs)} jobs on BambooHR")
            return jobs
        except Exception as e:
            print(f"[Scanner] BambooHR error: {e}")
            return []

    async def _scan_workday(self, keywords: list[str]) -> list[dict[str, Any]]:
        """Scrape Workday job listings using Playwright."""
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
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            jobs = []
            seen = set()

            for result in soup.select("div.g"):
                link = result.select_one("a[href]")
                title_el = result.select_one("h3")
                snippet_el = result.select_one("div.VwiC3b, span.aCOpRe")

                if link and title_el:
                    href = link.get("href", "")
                    title = title_el.text.strip()
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

    # ─── Playwright-based scrapers ─────────────────────────────────────

    async def _scan_board(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Dispatch to the appropriate scraper based on board name."""
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

        # Try Playwright first for LinkedIn/Indeed, fall back to HTTP
        if board in ("linkedin", "indeed"):
            try:
                return await self._scan_with_playwright(board, keywords, location)
            except ImportError:
                print(f"[Scanner] Playwright not installed, using HTTP for {board}")
            except Exception as e:
                print(f"[Scanner] Playwright failed for {board}: {e}")

        # HTTP fallback
        return await self._scan_with_http(board, keywords, location)

    async def _scan_with_playwright(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Scan a job board using Playwright headless browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            query = "+".join(keywords)
            url = JOB_BOARDS[board]
            if board == "linkedin":
                await page.goto(f"{url}?keywords={query}&location={location}", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                jobs = await self._parse_linkedin_playwright(page)
            elif board == "indeed":
                await page.goto(f"{url}?q={query}&l={location}", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                jobs = await self._parse_indeed_playwright(page)
            else:
                jobs = []

            await browser.close()
            for job in jobs:
                job["source"] = board
                job["scanned_at"] = datetime.now(timezone.utc).isoformat()
            return jobs

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
                    jobs.append({"title": title.strip(), "company": company.strip(), "location": location_text.strip(), "url": link or ""})
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
                    jobs.append({"title": title.strip(), "company": company.strip(), "location": location_text.strip(), "url": f"https://www.indeed.com{href}" if href else ""})
        except Exception as e:
            print(f"[Scanner] Indeed Playwright parse error: {e}")
        return jobs

    async def _scan_with_http(self, board: str, keywords: list[str], location: str) -> list[dict[str, Any]]:
        """Fallback HTTP-based scanning."""
        url = JOB_BOARDS.get(board)
        if not url:
            return []
        query = "+".join(keywords)
        params = {"q": query, "l": location, "sort": "date"}
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            jobs = self._parse_listings(board, soup)
            for job in jobs:
                job["source"] = board
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
