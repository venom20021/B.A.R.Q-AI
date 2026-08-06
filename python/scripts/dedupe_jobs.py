"""
One-time job-listing dedup + fingerprint backfill.

Collapses duplicate `job_listings` rows that accumulated before the dedup
indexes existed (schema v2) and backfills the `fingerprint` column so the
new partial UNIQUE indexes can be created on the next backend start.

Runs against whichever database the .env points at (local SQLite or Turso).
Idempotent — safe to re-run (a second run finds no duplicate groups).

Usage (from the `python/` directory, with the backend venv):
    python scripts/dedupe_jobs.py
"""

import asyncio
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import db_connection  # noqa: E402


# Inlined copy of the DAO fingerprint so this script also runs against
# deployments that predate the schema-v2 dedup code.
def _normalize_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _job_fingerprint(job: dict[str, Any]) -> str:
    parts = [
        _normalize_text(job.get("title", "")),
        _normalize_text(job.get("company", "")),
        _normalize_text(job.get("location", "")),
    ]
    raw = "|".join(p for p in parts if p)
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

# Each query yields duplicate groups: the surviving id (MIN(id)) + all ids.
DEDUP_QUERIES = [
    (
        "board + external_id",
        """
        SELECT source_board, external_id,
               MIN(id) AS keep_id, GROUP_CONCAT(id) AS ids
        FROM job_listings
        WHERE external_id != ''
        GROUP BY source_board, external_id
        HAVING COUNT(*) > 1
        """,
    ),
    (
        "source_url",
        """
        SELECT source_url,
               MIN(id) AS keep_id, GROUP_CONCAT(id) AS ids
        FROM job_listings
        WHERE source_url != ''
        GROUP BY source_url
        HAVING COUNT(*) > 1
        """,
    ),
    (
        "fingerprint",
        """
        SELECT fingerprint,
               MIN(id) AS keep_id, GROUP_CONCAT(id) AS ids
        FROM job_listings
        WHERE fingerprint != ''
        GROUP BY fingerprint
        HAVING COUNT(*) > 1
        """,
    ),
]


async def ensure_fingerprint_column() -> None:
    """Add the fingerprint column if missing (idempotent across backends)."""
    try:
        await db_connection.execute(
            "ALTER TABLE job_listings ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''"
        )
        await db_connection.commit()
        print("[Dedupe] Added 'fingerprint' column")
    except Exception as e:
        # "duplicate column name" (column already present) is expected.
        print(f"[Dedupe] fingerprint column present or add skipped: {e}")


async def backfill_fingerprints() -> tuple[int, int]:
    """Compute fingerprints for rows that don't have one yet."""
    rows = await db_connection.fetch_all(
        "SELECT id, title, company, location FROM job_listings "
        "WHERE fingerprint = '' OR fingerprint IS NULL"
    )
    updated = 0
    for r in rows:
        fp = _job_fingerprint(r)
        if not fp:
            continue
        await db_connection.execute(
            "UPDATE job_listings SET fingerprint = ? WHERE id = ?",
            (fp, r["id"]),
        )
        updated += 1
    await db_connection.commit()
    return len(rows), updated


async def _collapse_group(keep_id: int, dup_ids: list[int]) -> int:
    """Point children at the surviving row, then delete the duplicates."""
    removed = 0
    for dup_id in dup_ids:
        if dup_id == keep_id:
            continue
        for table, col in (
            ("job_evaluations", "job_listing_id"),
            ("applications", "job_listing_id"),
        ):
            await db_connection.execute(
                f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                (keep_id, dup_id),
            )
        await db_connection.execute(
            "DELETE FROM job_listings WHERE id = ?", (dup_id,)
        )
        removed += 1
    await db_connection.commit()
    return removed


async def dedupe() -> dict:
    """Collapse duplicate groups for each dedup key. Returns per-key stats."""
    stats: dict = {}
    for label, query in DEDUP_QUERIES:
        groups = await db_connection.fetch_all(query)
        removed = 0
        for g in groups:
            ids = [int(x) for x in str(g["ids"]).split(",") if x]
            keep_id = int(g["keep_id"])
            dup_ids = [i for i in ids if i != keep_id]
            removed += await _collapse_group(keep_id, dup_ids)
        stats[label] = {"groups": len(groups), "rows_removed": removed}
        print(
            f"[Dedupe] {label}: {len(groups)} duplicate group(s), "
            f"{removed} row(s) removed"
        )
    return stats


async def dedupe_evaluations() -> int:
    """Collapse duplicate evaluations per listing (keep the latest row)."""
    groups = await db_connection.fetch_all(
        "SELECT job_listing_id, COUNT(*) AS cnt FROM job_evaluations "
        "GROUP BY job_listing_id HAVING COUNT(*) > 1"
    )
    removed = 0
    for g in groups:
        listing_id = int(g["job_listing_id"])
        await db_connection.execute(
            "DELETE FROM job_evaluations WHERE job_listing_id = ? "
            "AND id NOT IN (SELECT MAX(id) FROM job_evaluations "
            "WHERE job_listing_id = ?)",
            (listing_id, listing_id),
        )
        removed += int(g["cnt"]) - 1
    await db_connection.commit()
    print(
        f"[Dedupe] evaluations: kept latest per listing, {removed} row(s) removed"
    )
    return removed


async def main() -> None:
    print("[Dedupe] Connecting to database...")
    await db_connection.connect()
    try:
        before = await db_connection.fetch_one(
            "SELECT COUNT(*) AS c FROM job_listings"
        )
        before_cnt = int(before["c"]) if before else 0

        await ensure_fingerprint_column()
        scanned, backfilled = await backfill_fingerprints()
        print(f"[Dedupe] Fingerprint backfill: {backfilled}/{scanned} rows")

        stats = await dedupe()
        eval_removed = await dedupe_evaluations()

        after = await db_connection.fetch_one(
            "SELECT COUNT(*) AS c FROM job_listings"
        )
        after_cnt = int(after["c"]) if after else 0
        total_removed = sum(s["rows_removed"] for s in stats.values())
        print(
            f"[Dedupe] Done: {before_cnt} -> {after_cnt} job listings "
            f"({total_removed} duplicates collapsed, {eval_removed} stale evaluations removed)"
        )
    finally:
        await db_connection.close()


if __name__ == "__main__":
    asyncio.run(main())
