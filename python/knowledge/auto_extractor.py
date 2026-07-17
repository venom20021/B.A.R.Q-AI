"""
BARQ Auto Extractor — automatically extracts knowledge triplets from
job descriptions and social media content as they are processed.

Hooks into:
  - Job pipeline: extracts triplets from job descriptions after scanning
  - Social pipeline: extracts triplets from trending topics and scripts
  - Periodic batch: runs scheduled extraction on unprocessed content

All extracted triplets are fed into the BARQ Graph Brain (NetworkX).
"""

import logging

from database import analytics_dao, db_connection
from graph_brain import graph_brain

logger = logging.getLogger("barq.auto_extractor")


class AutoExtractor:
    """Extracts knowledge triplets from content and feeds them into the Graph Brain.

    Tracks which content has already been processed to avoid duplicate extraction.
    """

    def __init__(self):
        self._processed_ids: set[str] = set()

    # ── Job Description Extraction ──────────────────────────────────

    async def extract_from_job(self, job_id: int, title: str, description: str, company: str) -> int:
        """Extract triplets from a single job description.

        Args:
            job_id: Database ID of the job listing.
            title: Job title.
            description: Full job description text.
            company: Company name.

        Returns:
            Number of triplets added to the graph.
        """
        dedup_key = f"job_{job_id}"
        if dedup_key in self._processed_ids:
            return 0
        self._processed_ids.add(dedup_key)

        text_content = f"Job Title: {title}\nCompany: {company}\n\n{description}"
        count = graph_brain.add_knowledge(text_content)

        if count > 0:
            await analytics_dao.log_activity(
                "knowledge", "extract_job",
                f"Extracted {count} triplets from job: {title} @ {company}",
            )
            logger.info("Extracted %d triplets from job %d (%s @ %s)", count, job_id, title, company)

        return count

    async def extract_from_jobs_batch(self, limit: int = 20) -> int:
        """Find unprocessed job descriptions and extract triplets from them.

        Args:
            limit: Maximum number of jobs to process.

        Returns:
            Total triplets added.
        """
        try:
            rows = await db_connection.fetch_all(
                "SELECT id, title, company, description FROM job_listings "
                "WHERE is_active = 1 AND description != '' "
                "ORDER BY scanned_at DESC LIMIT ?",
                (limit,),
            )
        except Exception:
            return 0

        total = 0
        for row in rows:
            count = await self.extract_from_job(
                job_id=row["id"],
                title=row.get("title", ""),
                description=row.get("description", ""),
                company=row.get("company", ""),
            )
            total += count

        if total > 0:
            await analytics_dao.log_activity(
                "knowledge", "extract_jobs_batch",
                f"Batch extracted {total} triplets from {len(rows)} jobs",
            )

        return total

    # ── Social Content Extraction ───────────────────────────────────

    async def extract_from_trend(self, trend_id: int, title: str, description: str = "") -> int:
        """Extract triplets from a trending topic.

        Args:
            trend_id: Database ID of the trend.
            title: Trend title.
            description: Optional trend description or content.

        Returns:
            Number of triplets added.
        """
        dedup_key = f"trend_{trend_id}"
        if dedup_key in self._processed_ids:
            return 0
        self._processed_ids.add(dedup_key)

        text_content = f"Trend: {title}\n\n{description}" if description else f"Trend: {title}"
        count = graph_brain.add_knowledge(text_content)

        if count > 0:
            await analytics_dao.log_activity(
                "knowledge", "extract_trend",
                f"Extracted {count} triplets from trend: {title[:60]}",
            )

        return count

    async def extract_from_trends_batch(self, limit: int = 10) -> int:
        """Extract triplets from recent trends that haven't been processed.

        Args:
            limit: Maximum trends to process.

        Returns:
            Total triplets added.
        """
        try:
            rows = await db_connection.fetch_all(
                "SELECT id, title FROM trends ORDER BY fetched_at DESC LIMIT ?",
                (limit,),
            )
        except Exception:
            return 0

        total = 0
        for row in rows:
            count = await self.extract_from_trend(
                trend_id=row["id"],
                title=row.get("title", ""),
            )
            total += count

        return total

    # ── Full Pipeline Hook ──────────────────────────────────────────

    async def run_full_extraction(self) -> dict[str, int]:
        """Run extraction on all unprocessed content types.

        Returns:
            Dict with counts per content type.
        """
        job_triplets = await self.extract_from_jobs_batch(limit=20)
        trend_triplets = await self.extract_from_trends_batch(limit=10)

        stats = graph_brain.get_statistics()

        if job_triplets > 0 or trend_triplets > 0:
            await analytics_dao.log_activity(
                "knowledge", "full_extraction",
                f"Full extraction: {job_triplets} from jobs, {trend_triplets} from trends. "
                f"Graph: {stats['nodes']} nodes, {stats['edges']} edges",
            )

        return {
            "job_triplets": job_triplets,
            "trend_triplets": trend_triplets,
            "total_triplets": job_triplets + trend_triplets,
            "graph_nodes": stats.get("nodes", 0),
            "graph_edges": stats.get("edges", 0),
        }


# ─── Standalone function for scheduler use ──────────────────────────────

async def run_auto_extraction() -> dict[str, int]:
    """Convenience function for the APScheduler to call."""
    extractor = AutoExtractor()
    return await extractor.run_full_extraction()
