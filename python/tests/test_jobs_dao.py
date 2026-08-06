"""
Tests for JobsDAO - job listings, evaluations, and applications CRUD.
"""

import json
from datetime import datetime, timezone

import pytest

from database import jobs_dao


@pytest.mark.asyncio
async def test_insert_and_get_job_listing():
    """Test creating and retrieving a job listing."""
    job_id = await jobs_dao.insert_job_listing({
        "title": "Senior Developer",
        "company": "TechCorp",
        "location": "Remote",
        "description": "Full-stack developer position",
        "salary_min": 120000,
        "salary_max": 180000,
        "source_board": "linkedin",
        "source_url": "https://linkedin.com/jobs/123",
    })
    job_id = int(job_id)  # Turso returns str, ensure int for comparisons
    assert job_id > 0

    job = await jobs_dao.get_job_listing(job_id)
    assert job is not None
    assert job["title"] == "Senior Developer"
    assert job["company"] == "TechCorp"
    assert job["location"] == "Remote"
    assert job["salary_min"] == 120000
    assert job["salary_max"] == 180000
    assert job["is_active"] == 1


@pytest.mark.asyncio
async def test_search_jobs():
    """Test searching jobs by title/company."""
    await jobs_dao.insert_job_listing({"title": "React Developer", "company": "WebCo", "source_board": "indeed"})
    await jobs_dao.insert_job_listing({"title": "Python Backend", "company": "DataCo", "source_board": "linkedin"})
    await jobs_dao.insert_job_listing({"title": "Full Stack Engineer", "company": "TechCo", "source_board": "glassdoor"})

    results = await jobs_dao.search_jobs("React")
    assert len(results) >= 1
    assert any("React" in r["title"] for r in results)

    # Search by company
    results = await jobs_dao.search_jobs("DataCo")
    assert len(results) >= 1
    assert any("DataCo" in r["company"] for r in results)


@pytest.mark.asyncio
async def test_get_active_jobs():
    """Test retrieving active jobs with evaluations."""
    await jobs_dao.insert_job_listing({"title": "Active Job", "company": "A", "source_board": "linkedin", "is_active": 1})
    await jobs_dao.insert_job_listing({"title": "Inactive Job", "company": "B", "source_board": "linkedin"})

    # Deactivate the second job
    await jobs_dao.deactivate_expired_jobs()

    active = await jobs_dao.get_active_jobs()
    # Our test jobs don't have expiration dates, so they remain active
    assert len(active) >= 1


@pytest.mark.asyncio
async def test_job_evaluation_crud():
    """Test inserting and querying job evaluations."""
    job_id = int(await jobs_dao.insert_job_listing({"title": "Test Job", "company": "TestCo", "source_board": "linkedin"}))

    eval_id = await jobs_dao.insert_evaluation({
        "job_listing_id": job_id,
        "overall_score": 4.5,
        "role_fit_score": 4.0,
        "culture_score": 5.0,
        "compensation_score": 4.0,
        "growth_score": 5.0,
        "red_flag_score": 0.5,
        "match_percentage": 90.0,
        "reasoning": "Great fit for role",
        "pros": json.dumps(["Strong tech stack", "Remote friendly"]),
        "cons": json.dumps(["Requires on-call"]),
    })
    assert int(eval_id) > 0

    evaluation = await jobs_dao.get_evaluation(int(job_id))
    assert evaluation is not None
    assert evaluation["overall_score"] == 4.5
    assert evaluation["match_percentage"] == 90.0


@pytest.mark.asyncio
async def test_application_workflow():
    """Test the application lifecycle: create -> approve -> submit."""
    job_id = int(await jobs_dao.insert_job_listing({"title": "Engineer", "company": "Co", "source_board": "linkedin"}))

    # Create application
    app_id = int(await jobs_dao.insert_application({
        "job_listing_id": job_id,
        "status": "draft",
    }))
    assert app_id > 0

    # Update to queued
    await jobs_dao.update_application_status(app_id, "queued")
    app = await jobs_dao.get_application(app_id)
    assert app["status"] == "queued"

    # Update to submitted
    await jobs_dao.update_application_status(
        app_id, "submitted",
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )
    app = await jobs_dao.get_application(app_id)
    assert app["status"] == "submitted"
    assert app["submitted_at"] is not None


@pytest.mark.asyncio
async def test_get_top_matches():
    """Test retrieving top-scoring job matches."""
    j1 = int(await jobs_dao.insert_job_listing({"title": "Job A", "company": "A", "source_board": "linkedin"}))
    j2 = int(await jobs_dao.insert_job_listing({"title": "Job B", "company": "B", "source_board": "linkedin"}))

    await jobs_dao.insert_evaluation({"job_listing_id": j1, "overall_score": 4.0, "match_percentage": 80.0})
    await jobs_dao.insert_evaluation({"job_listing_id": j2, "overall_score": 2.0, "match_percentage": 40.0})

    top = await jobs_dao.get_top_matches(min_score=3.0)
    titles = [t["title"] for t in top]
    assert "Job A" in titles, f"Job A (score 4.0) should be in matches, got: {titles}"
    assert "Job B" not in titles, f"Job B (score 2.0) should not be in matches with min_score=3.0, got: {titles}"


@pytest.mark.asyncio
async def test_top_matches_deduped_to_latest_evaluation():
    """A listing with several old evaluations appears once, with the latest."""
    j1 = int(await jobs_dao.insert_job_listing({"title": "Re-scanned Job", "company": "R", "source_board": "linkedin"}))
    await jobs_dao.insert_evaluation({"job_listing_id": j1, "overall_score": 3.0, "match_percentage": 60.0, "reasoning": "old"})
    await jobs_dao.insert_evaluation({"job_listing_id": j1, "overall_score": 4.5, "match_percentage": 90.0, "reasoning": "latest"})

    top = await jobs_dao.get_top_matches(min_score=3.0)
    rows = [t for t in top if t["title"] == "Re-scanned Job"]
    assert len(rows) == 1, f"should appear once, got {len(rows)}"
    assert rows[0]["reasoning"] == "latest"


@pytest.mark.asyncio
async def test_get_applications_by_status():
    """Test filtering applications by status."""
    j1 = int(await jobs_dao.insert_job_listing({"title": "Job", "company": "C", "source_board": "linkedin"}))
    await jobs_dao.insert_application({"job_listing_id": j1, "status": "submitted"})
    await jobs_dao.insert_application({"job_listing_id": j1, "status": "draft"})

    submitted = await jobs_dao.get_applications_by_status("submitted")
    assert len(submitted) >= 1
    assert all(a["status"] == "submitted" for a in submitted)


@pytest.mark.asyncio
async def test_get_applications_by_status_excludes_notified():
    """exclude_notified=True skips applications that were already notified."""
    j1 = int(await jobs_dao.insert_job_listing({"title": "Job", "company": "C", "source_board": "linkedin"}))
    app1 = int(await jobs_dao.insert_application({"job_listing_id": j1, "status": "ready_for_review"}))
    app2 = int(await jobs_dao.insert_application({"job_listing_id": j1, "status": "ready_for_review"}))

    await jobs_dao.update_application_status(app1, "ready_for_review", notified_at="2026-08-06T00:00:00Z")

    unnotified = await jobs_dao.get_applications_by_status("ready_for_review", exclude_notified=True)
    ids = [int(a["id"]) for a in unnotified]
    assert app2 in ids
    assert app1 not in ids


@pytest.mark.asyncio
async def test_document_storage():
    """Test storing and retrieving application documents."""
    j1 = int(await jobs_dao.insert_job_listing({"title": "Job", "company": "D", "source_board": "linkedin"}))
    app_id = int(await jobs_dao.insert_application({"job_listing_id": j1}))

    doc_id = int(await jobs_dao.insert_document({
        "application_id": app_id,
        "document_type": "resume",
        "content": "# John Doe\n## Skills\n- Python\n- React",
    }))
    assert doc_id > 0

    docs = await jobs_dao.get_active_documents(app_id)
    assert len(docs) >= 1
    assert docs[0]["document_type"] == "resume"


@pytest.mark.asyncio
async def test_application_count_by_status():
    """Test counting applications grouped by status."""
    j1 = int(await jobs_dao.insert_job_listing({"title": "Job", "company": "E", "source_board": "linkedin"}))
    await jobs_dao.insert_application({"job_listing_id": j1, "status": "submitted"})
    await jobs_dao.insert_application({"job_listing_id": j1, "status": "submitted"})
    await jobs_dao.insert_application({"job_listing_id": j1, "status": "draft"})

    counts = await jobs_dao.get_application_count_by_status()
    status_map = {row["status"]: row["count"] for row in counts}
    assert status_map.get("submitted", 0) >= 2
    assert status_map.get("draft", 0) >= 1


@pytest.mark.asyncio
async def test_duplicate_insert_is_deduped():
    """Re-inserting the same job returns the existing row instead of a duplicate."""
    data = {"title": "Duplicate Job", "company": "F", "source_board": "linkedin"}
    id1 = int(await jobs_dao.insert_job_listing(data))
    id2 = int(await jobs_dao.insert_job_listing(data))

    assert id1 == id2
    jobs = await jobs_dao.search_jobs("Duplicate Job")
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_insert_job_listing_if_new():
    """Already-known jobs return None; genuinely new jobs return their id."""
    job = {"title": "Fresh Role", "company": "NewCo", "source_board": "linkedin"}
    new_id = int(await jobs_dao.insert_job_listing_if_new(job))
    assert new_id > 0

    again = await jobs_dao.insert_job_listing_if_new(job)
    assert again is None

    # find-or-insert still returns the existing row
    same = int(await jobs_dao.insert_job_listing(job))
    assert same == new_id


@pytest.mark.asyncio
async def test_dedup_by_external_id():
    """Same board + external_id maps to the same listing id."""
    job = {"title": "Ext Job", "company": "ExtCo", "source_board": "linkedin", "external_id": "abc-123"}
    id1 = int(await jobs_dao.insert_job_listing(job))
    id2 = int(await jobs_dao.insert_job_listing(job))
    assert id1 == id2


@pytest.mark.asyncio
async def test_dedup_by_source_url():
    """Same source_url maps to the same listing id, even from a different board."""
    job1 = {"title": "URL Job", "company": "UrlCo", "source_board": "linkedin", "source_url": "https://x.com/j/1"}
    job2 = {"title": "URL Job", "company": "UrlCo", "source_board": "indeed", "source_url": "https://x.com/j/1"}
    id1 = int(await jobs_dao.insert_job_listing(job1))
    id2 = int(await jobs_dao.insert_job_listing(job2))
    assert id1 == id2


@pytest.mark.asyncio
async def test_dedup_by_fingerprint_without_ids():
    """No id/url: same title + company + location collapses to one row."""
    base = {"title": "Full Stack Developer", "company": "Acme", "location": "Remote"}
    id1 = int(await jobs_dao.insert_job_listing({**base, "source_board": "linkedin"}))
    id2 = int(await jobs_dao.insert_job_listing({**base, "source_board": "indeed"}))
    assert id1 == id2


@pytest.mark.asyncio
async def test_same_title_different_location_not_deduped():
    """Location is part of the fingerprint — different locations stay separate."""
    base = {"title": "Backend Engineer", "company": "Acme", "source_board": "linkedin"}
    id1 = int(await jobs_dao.insert_job_listing({**base, "location": "London"}))
    id2 = int(await jobs_dao.insert_job_listing({**base, "location": "Berlin"}))
    assert id1 != id2


@pytest.mark.asyncio
async def test_fingerprint_normalization():
    """Fingerprint ignores case/punctuation so near-identical titles match."""
    from database.jobs_dao import _job_fingerprint
    a = _job_fingerprint({"title": "Full-Stack Developer!", "company": "Acme, Inc.", "location": "Remote (EU)"})
    b = _job_fingerprint({"title": "full stack developer", "company": "Acme Inc", "location": "remote eu"})
    assert a == b


@pytest.mark.asyncio
async def test_get_nonexistent():
    """Test retrieving non-existent records returns None."""
    job = await jobs_dao.get_job_listing(99999)
    assert job is None

    eval_ = await jobs_dao.get_evaluation(99999)
    assert eval_ is None

    app = await jobs_dao.get_application(99999)
    assert app is None
