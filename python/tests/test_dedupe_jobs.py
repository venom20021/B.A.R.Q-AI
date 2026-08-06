"""
Tests for the one-time job dedup script (scripts/dedupe_jobs.py).

Runs the script's collapse functions against the in-memory test DB to
verify duplicate listings are collapsed without losing child rows
(evaluations / applications) and that re-running is a no-op.
"""

import pytest

from database import jobs_dao
from database.connection import db_connection

import scripts.dedupe_jobs as dedupe


@pytest.fixture(autouse=True)
async def drop_dedup_indexes():
    """The schema's UNIQUE indexes prevent seeding duplicates — drop them here."""
    for idx in (
        "uq_job_listings_board_external",
        "uq_job_listings_source_url",
        "uq_job_listings_fingerprint",
    ):
        try:
            await db_connection.execute(f"DROP INDEX IF EXISTS {idx}")
        except Exception:
            pass
    await db_connection.commit()
    yield


async def _insert_raw(**fields) -> int:
    cols = ", ".join(fields.keys())
    ph = ", ".join("?" for _ in fields)
    return int(await db_connection.insert(
        f"INSERT INTO job_listings ({cols}) VALUES ({ph})", tuple(fields.values())
    ))


@pytest.mark.asyncio
async def test_dedupe_collapses_listings_and_remaps_children():
    """A fingerprint group collapses to one row; children survive + remap."""
    ids = []
    for i in range(3):
        jid = await _insert_raw(
            title="Full Stack Engineer", company="Acme", location="Remote",
            source_board="linkedin", fingerprint="",
        )
        ids.append(jid)
        await jobs_dao.insert_evaluation({
            "job_listing_id": jid, "overall_score": 4.0,
            "match_percentage": 80.0, "reasoning": f"eval-{i}",
        })
    app_id = int(await db_connection.insert(
        "INSERT INTO applications (job_listing_id, status) VALUES (?, ?)",
        (ids[1], "submitted"),
    ))

    scanned, backfilled = await dedupe.backfill_fingerprints()
    assert backfilled == 3
    await dedupe.dedupe()

    remaining = await db_connection.fetch_all("SELECT id, fingerprint FROM job_listings")
    assert len(remaining) == 1
    keep_id = remaining[0]["id"]

    evals = await db_connection.fetch_all("SELECT job_listing_id FROM job_evaluations")
    assert len(evals) == 3
    assert all(e["job_listing_id"] == keep_id for e in evals)

    app = await db_connection.fetch_one(
        "SELECT job_listing_id FROM applications WHERE id = ?", (app_id,)
    )
    assert app["job_listing_id"] == keep_id


@pytest.mark.asyncio
async def test_dedupe_by_source_url():
    """Same URL across boards collapses to one row."""
    await _insert_raw(
        title="Backend Dev", company="X", location="",
        source_board="linkedin", source_url="https://jobs.example.com/42",
    )
    await _insert_raw(
        title="Backend Dev", company="X", location="",
        source_board="indeed", source_url="https://jobs.example.com/42",
    )

    await dedupe.backfill_fingerprints()
    await dedupe.dedupe()

    remaining = await db_connection.fetch_all("SELECT id FROM job_listings")
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_dedupe_evaluations_keeps_latest():
    """Stale evaluations collapse to the newest one per listing."""
    jid = await _insert_raw(title="Eval Job", company="E", location="", source_board="linkedin")
    for i, score in enumerate((3.0, 4.5)):
        await jobs_dao.insert_evaluation({
            "job_listing_id": jid, "overall_score": score,
            "match_percentage": score * 20, "reasoning": f"r{i}",
        })

    removed = await dedupe.dedupe_evaluations()
    assert removed == 1

    evals = await db_connection.fetch_all(
        "SELECT overall_score, reasoning FROM job_evaluations WHERE job_listing_id = ?",
        (jid,),
    )
    assert len(evals) == 1
    assert evals[0]["reasoning"] == "r1"


@pytest.mark.asyncio
async def test_dedupe_is_idempotent():
    """Re-running the collapse changes nothing the second time."""
    for i in range(2):
        jid = await _insert_raw(
            title="Dup Job", company="D", location="", source_board="linkedin", fingerprint="",
        )
        await jobs_dao.insert_evaluation({
            "job_listing_id": jid, "overall_score": 4.0, "match_percentage": 80.0,
        })

    await dedupe.backfill_fingerprints()
    await dedupe.dedupe()
    await dedupe.dedupe_evaluations()

    first_count = (await db_connection.fetch_one(
        "SELECT COUNT(*) AS c FROM job_listings"))["c"]

    await dedupe.dedupe()
    await dedupe.dedupe_evaluations()

    second_count = (await db_connection.fetch_one(
        "SELECT COUNT(*) AS c FROM job_listings"))["c"]
    assert first_count == second_count
