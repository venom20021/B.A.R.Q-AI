"""
Tests for jobs FastAPI routes: scan, matches, approve, applications, status.
External dependencies (JobScanner, JobEvaluator, JobApplier) are mocked.
"""


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
