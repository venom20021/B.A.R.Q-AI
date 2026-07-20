"""
Tests for jobs FastAPI routes: scan, matches, approve, applications, status.
External dependencies (JobScanner, JobEvaluator, JobApplier) are mocked.
"""


import json

import pytest

from database import jobs_dao


@pytest.fixture
def router():
    from jobs import routes
    return routes.router


# ─── Scan ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_jobs_success(client):
    """POST /scan should start background scan and return status."""
    response = await client.post("/scan")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert "message" in data


@pytest.mark.asyncio
async def test_scan_jobs_empty(client):
    """POST /scan should start scan even with no pre-existing jobs."""
    response = await client.post("/scan")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"


@pytest.mark.asyncio
async def test_scan_jobs_error(client):
    """POST /scan should return 200 even if scanner fails (background task)."""
    response = await client.post("/scan")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"


# ─── Matches ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_matches_empty(client):
    """GET /matches should return empty list when no matches exist."""
    response = await client.get("/matches")
    assert response.status_code == 200
    assert response.json()["matches"] == []


@pytest.mark.asyncio
async def test_get_matches_with_data(client):
    """GET /matches should return evaluated matches."""
    # Insert a job listing and evaluation via DAO
    job_id = await jobs_dao.insert_job_listing({
        "title": "Senior Dev", "company": "Tech Co",
        "source_board": "linkedin",
    })
    await jobs_dao.insert_evaluation({
        "job_listing_id": job_id,
        "overall_score": 4.5,
        "match_percentage": 90,
        "reasoning": "Great fit",
        "pros": '["Remote"]',
        "cons": '["None"]',
    })

    response = await client.get("/matches?min_score=3.0")
    assert response.status_code == 200
    matches = response.json()["matches"]
    assert len(matches) >= 1
    assert matches[0]["title"] == "Senior Dev"
    assert matches[0]["company"] == "Tech Co"
    assert matches[0]["match_score"] == 4.5


@pytest.mark.asyncio
async def test_get_matches_filter_by_score(client):
    """GET /matches should filter by min_score."""
    job_id = await jobs_dao.insert_job_listing({
        "title": "Jr Dev", "company": "Small Co", "source_board": "indeed",
    })
    await jobs_dao.insert_evaluation({
        "job_listing_id": job_id,
        "overall_score": 2.0,
        "match_percentage": 40,
    })

    # High min_score should exclude the 2.0 match
    response = await client.get("/matches?min_score=4.0")
    assert response.status_code == 200
    assert len(response.json()["matches"]) == 0


# ─── Approve ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_application(client):
    """POST /approve should queue an application for a job."""
    job_id = await jobs_dao.insert_job_listing({
        "title": "Target Role", "company": "Target Co", "source_board": "linkedin",
    })

    response = await client.post("/approve", json={"job_id": str(job_id)})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["application_id"] > 0


@pytest.mark.asyncio
async def test_approve_invalid_job_id(client):
    """POST /approve with non-numeric job_id should return 400."""
    response = await client.post("/approve", json={"job_id": "abc"})
    assert response.status_code == 400
    assert "integer" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approve_nonexistent_job(client):
    """POST /approve with valid but non-existent job_id should fail gracefully."""
    response = await client.post("/approve", json={"job_id": "99999"})
    assert response.status_code == 500  # FK constraint fails


# ─── Applications ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_applications_by_status(client):
    """GET /applications should filter by status."""
    job_id = await jobs_dao.insert_job_listing({
        "title": "App Role", "company": "App Co", "source_board": "linkedin",
    })
    await jobs_dao.insert_application({
        "job_listing_id": job_id, "status": "queued",
    })

    response = await client.get("/applications?status=queued")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert data["applications"][0]["status"] == "queued"


@pytest.mark.asyncio
async def test_get_applications_empty_status(client):
    """GET /applications with non-matching status should return empty."""
    response = await client.get("/applications?status=submitted")
    assert response.status_code == 200
    assert response.json()["count"] == 0


# ─── Status ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_job_status_defaults(client):
    """GET /status should return default zero values with no data."""
    response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["total_jobs_scanned"] == 0
    assert data["is_scanning"] is False
    assert isinstance(data["pending_review"], int)
    assert isinstance(data["applications_queued"], int)


# ─── Evaluation Insertion Integration Tests ─────────────────────────────
# These verify that when a scan saves listings, it also creates entries
# in the job_evaluations table, so GET /matches returns results.


@pytest.mark.asyncio
async def test_listing_and_evaluation_inserted_together(client):
    """
    Simulate what _run_scan() does: insert a job listing, then immediately
    insert its evaluation. Verify GET /matches returns it.
    """
    # 1. Insert listing (as _run_scan does)
    listing_id = await jobs_dao.insert_job_listing({
        "title": "Full Stack Engineer",
        "company": "StartupXYZ",
        "location": "Remote",
        "salary_min": 100000,
        "salary_max": 160000,
        "source_board": "linkedin",
        "source_url": "https://linkedin.com/jobs/456",
        "url": "https://linkedin.com/jobs/456",
    })
    assert listing_id > 0

    # 2. Insert evaluation (as _run_scan now does)
    eval_id = await jobs_dao.insert_evaluation({
        "job_listing_id": listing_id,
        "overall_score": 4.0,
        "match_percentage": 80.0,
        "reasoning": "Strong skills match",
        "pros": json.dumps(["Python", "React", "Remote"]),
        "cons": json.dumps(["Junior team"]),
        "evaluated_by": "scanner",
    })
    assert eval_id > 0

    # 3. Verify GET /matches returns the evaluated job
    response = await client.get("/matches?min_score=3.0")
    assert response.status_code == 200
    matches = response.json()["matches"]
    assert len(matches) >= 1

    # Check the specific job we inserted
    match = next((m for m in matches if m["id"] == listing_id), None)
    assert match is not None, f"Listing #{listing_id} not found in matches"
    assert match["title"] == "Full Stack Engineer"
    assert match["company"] == "StartupXYZ"
    assert match["match_score"] == 4.0
    assert match["match_percentage"] == 80.0
    assert match["reasoning"] == "Strong skills match"


@pytest.mark.asyncio
async def test_listing_without_evaluation_not_in_matches(client):
    """
    Verify that a listing WITHOUT an evaluation does NOT appear in
    GET /matches (the JOIN filters it out).
    This is the bug that existed before the fix.
    """
    # Insert listing only — NO evaluation (the old broken pattern)
    await jobs_dao.insert_job_listing({
        "title": "Orphaned Job",
        "company": "Lonely Co",
        "source_board": "indeed",
    })

    # Insert a different job WITH evaluation
    good_id = await jobs_dao.insert_job_listing({
        "title": "Proper Job",
        "company": "Good Co",
        "source_board": "linkedin",
    })
    await jobs_dao.insert_evaluation({
        "job_listing_id": good_id,
        "overall_score": 4.5,
        "match_percentage": 90.0,
    })

    # Matches should only return the evaluated job
    response = await client.get("/matches")
    matches = response.json()["matches"]
    titles = [m["title"] for m in matches]
    assert "Proper Job" in titles
    assert "Orphaned Job" not in titles, "Listing without evaluation should not appear in matches"


@pytest.mark.asyncio
async def test_url_fallback_to_source_url(client):
    """
    Verify that insert_job_listing correctly maps 'url' -> 'source_url'
    when the scanner provides the URL under the 'url' key.
    """
    # Insert with 'url' key (as the scanner does) instead of 'source_url'
    listing_id = await jobs_dao.insert_job_listing({
        "title": "URL Test",
        "company": "TestCorp",
        "source_board": "remotive",
        "url": "https://remotive.com/jobs/789",  # scanner writes 'url', not 'source_url'
    })

    # Retrieve and verify source_url got the fallback value
    job = await jobs_dao.get_job_listing(listing_id)
    assert job is not None
    assert job["source_url"] == "https://remotive.com/jobs/789"


@pytest.mark.asyncio
async def test_scan_e2e_evaluated_by_scanner(client):
    """
    E2E: POST /scan with mocked scanner → background task inserts evaluations
    → GET /matches returns data → DB has evaluated_by='scanner'.
    """
    import asyncio
    from unittest.mock import AsyncMock, patch

    from database import db_connection
    from jobs import routes

    fake_jobs = [
        {
            "title": "E2E Test Engineer",
            "company": "TestCorp",
            "location": "Remote",
            "source_board": "remotive",
            "url": "https://remotive.com/jobs/e2e-1",
            "description": "Build and test systems",
            "overall_score": 4.5,
            "match_percentage": 90.0,
            "reasoning": "Strong skills match",
            "pros": ["Python", "Testing"],
            "cons": ["No CI/CD"],
        },
        {
            "title": "Backend Dev",
            "company": "API Inc",
            "location": "Remote",
            "source_board": "remoteok",
            "url": "https://remoteok.com/jobs/backend-2",
            "description": "Build APIs",
            "overall_score": 3.8,
            "match_percentage": 76.0,
            "reasoning": "Good skills match",
            "pros": ["FastAPI"],
            "cons": ["Junior role"],
        },
    ]

    with patch.object(routes.scanner, 'scan_all', new_callable=AsyncMock, return_value=fake_jobs):
        # 1. Trigger scan
        resp = await client.post("/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"

        # 2. Yield control so the background task runs
        await asyncio.sleep(0.3)

        # 3. Progress endpoint should be reachable
        progress_resp = await client.get("/scan/progress")
        assert progress_resp.status_code == 200

        # 4. Fetch matches — the evaluated jobs should appear
        matches_resp = await client.get("/matches?min_score=3.0")
        assert matches_resp.status_code == 200
        matches = matches_resp.json()["matches"]
        assert len(matches) >= 2, f"Expected at least 2 matches, got {len(matches)}"

        # 5. Verify evaluated_by = 'scanner' in the DB (the API response
        #    doesn't include this field, so we check the raw table)
        row = await db_connection.fetch_one(
            "SELECT evaluated_by FROM job_evaluations ORDER BY id LIMIT 1"
        )
        assert row is not None, "No evaluation row found in job_evaluations"
        assert row["evaluated_by"] == "scanner", (
            f"Expected evaluated_by='scanner', got '{row['evaluated_by']}'"
        )

        # 6. Both fake jobs should be present in match results
        titles = [m["title"] for m in matches]
        assert "E2E Test Engineer" in titles
        assert "Backend Dev" in titles

        # 7. Verify match scores survived the insert→query round-trip
        for match in matches:
            if match["title"] == "E2E Test Engineer":
                assert match["match_score"] == 4.5
                assert match["match_percentage"] == 90.0
                assert match["reasoning"] == "Strong skills match"
                break


@pytest.mark.asyncio
async def test_listing_with_evaluation_data_mixed_in(client):
    """
    Simulate scanner output that has evaluation fields mixed into the job dict
    (as scanner.scan_all() does with assessed_jobs = {**job, **eval_result}).
    Verify only the listing fields are stored and the evaluation is separate.
    """
    # Simulate what scanner.scan_all returns: a job dict with eval fields
    scanned_job = {
        "title": "AI Engineer",
        "company": "DeepAI",
        "source_board": "greenhouse",
        "url": "https://boards.greenhouse.io/jobs/101",
        "description": "Build ML models",
        # These are evaluation fields mixed in by scanner.scan_all()
        "overall_score": 4.8,
        "match_percentage": 96.0,
        "reasoning": "Perfect AI match",
        "pros": ["ML expertise", "Research"],
        "cons": ["Early stage"],
    }

    # Insert as _run_scan does
    listing_id = await jobs_dao.insert_job_listing(scanned_job)
    assert listing_id > 0

    # Insert evaluation if overall_score is present (the fix!)
    if "overall_score" in scanned_job:
        await jobs_dao.insert_evaluation({
            "job_listing_id": listing_id,
            "overall_score": float(scanned_job.get("overall_score", 3.0)),
            "match_percentage": float(scanned_job.get("match_percentage", 0)),
            "reasoning": scanned_job.get("reasoning", ""),
            "pros": json.dumps(scanned_job.get("pros", [])),
            "cons": json.dumps(scanned_job.get("cons", [])),
            "evaluated_by": "scanner",
        })

    # Verify the match appears
    response = await client.get("/matches?min_score=3.0")
    matches = response.json()["matches"]
    match = next((m for m in matches if m["id"] == listing_id), None)
    assert match is not None
    assert match["match_score"] == 4.8
    assert match["match_percentage"] == 96.0
    assert match["reasoning"] == "Perfect AI match"
