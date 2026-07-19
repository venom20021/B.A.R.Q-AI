"""
Job Discovery Aggregator.

Combines job results from multiple sources:
  1. TinyFish API (from autopilot-jobhunt) — 130+ company careers pages
  2. BARQ multi-board scanner — 35+ boards (Remotive, Greenhouse, Lever, etc.)
  3. LinkedIn search — targeted search via LinkedIn

Deduplicates by URL and sorts by match score.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

logger = logging.getLogger("barq.auto_applier.discovery")


class JobAggregator:
    """Aggregates job listings from multiple discovery sources."""

    def __init__(self):
        self._sources: list[str] = []

    async def discover_all(self) -> list[dict[str, Any]]:
        """Run all configured discovery sources and return deduplicated results."""
        seen_urls: set[str] = set()
        all_jobs: list[dict[str, Any]] = []

        # 1. TinyFish (check autopilot-jobhunt state file)
        tinyfish_jobs = await self._from_tinyfish()
        for job in tinyfish_jobs:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)

        # 2. BARQ database
        barq_jobs = await self._from_barq_db()
        for job in barq_jobs:
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)

        # 3. TinyFish direct API (if configured)
        if CONFIG.tinyfish_api_key:
            tf_jobs = await self._from_tinyfish_api()
            for job in tf_jobs:
                url = job.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_jobs.append(job)

        all_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
        logger.info("Discovered %d unique jobs from %d sources", len(all_jobs), len(self._sources))
        return all_jobs

    async def _from_tinyfish(self) -> list[dict[str, Any]]:
        """Load jobs from autopilot-jobhunt's last_scan.json."""
        import os as _os
        roots = [
            str(Path(CONFIG.project_root) / ".." / "JOb scrapper" / "autopilot-jobhunt"),
            str(Path(CONFIG.project_root).parent / "autopilot-jobhunt"),
            _os.getenv("AUTOPILOT_ROOT", ""),
        ]
        for root in roots:
            state_file = Path(root) / "state" / "last_scan.json"
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text())
                    if isinstance(data, list):
                        self._sources.append("tinyfish")
                        return [{
                            "url": j.get("url", ""),
                            "company": j.get("company", ""),
                            "title": j.get("extracted_title") or j.get("title", ""),
                            "context": j.get("content", ""),
                            "score": j.get("score", 60),
                            "source": "tinyfish",
                            "location": j.get("location_remote") or j.get("location", ""),
                            "reason": j.get("reason", ""),
                        } for j in data if j.get("url")]
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", state_file, exc)
        return []

    async def _from_tinyfish_api(self) -> list[dict[str, Any]]:
        """Query TinyFish API directly for targeted searches."""
        try:
            import httpx
            from tinyfish import TinyFish
            tf = TinyFish(api_key=CONFIG.tinyfish_api_key)
            # Search for Full-Stack / Software Engineer roles
            query = "full-stack developer OR software engineer OR .NET developer (remote OR hybrid)"
            resp = tf.search.query(query, language="en")
            self._sources.append("tinyfish_api")
            jobs = []
            for r in resp.results[:30]:
                jobs.append({
                    "url": r.url,
                    "title": r.title or r.url.split("/")[-1].replace("-", " ").title(),
                    "company": "",
                    "context": r.text[:2000] if hasattr(r, "text") else "",
                    "score": 60,
                    "source": "tinyfish_api",
                    "location": "Remote",
                })
            return jobs
        except Exception as exc:
            logger.warning("TinyFish API query failed: %s", exc)
            return []

    async def _from_barq_db(self) -> list[dict[str, Any]]:
        """Load jobs from BARQ's database (scanned by the multi-board scanner)."""
        try:
            from database import jobs_dao
            matches = await jobs_dao.get_top_matches(min_score=CONFIG.match_threshold, limit=20)
            self._sources.append("barq_db")
            return [{
                "url": m.get("source_url", ""),
                "company": m.get("company", ""),
                "title": m.get("title", ""),
                "context": m.get("description", ""),
                "score": m.get("match_percentage", m.get("overall_score", 0)),
                "source": m.get("source_board", "barq"),
                "location": m.get("location", ""),
            } for m in matches if m.get("source_url")]
        except Exception as exc:
            logger.warning("BARQ DB query failed: %s", exc)
            return []
