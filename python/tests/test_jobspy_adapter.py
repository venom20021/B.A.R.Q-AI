"""Unit tests for the JobSpy board adapter in jobs/scanner.py.

These cover the pure mapping helpers only (no network).  The adapter is
designed so these helpers accept either dict rows or pandas Series rows.
"""

from datetime import datetime

from jobs.scanner import (
    JOBSPY_SITES,
    _jobspy_search_term,
    _jobspy_row_to_job,
    _matches_any_keyword,
)


def test_jobspy_sites_match_requested_boards():
    assert set(JOBSPY_SITES) == {"linkedin", "indeed", "glassdoor", "ziprecruiter", "google"}


def test_jobspy_search_term_truncates():
    assert _jobspy_search_term(["python", "typescript", "react", "fastapi", "aws"]) == "python typescript react"
    assert _jobspy_search_term(["", "  ", "python"]) == "python"
    assert _jobspy_search_term([]) == ""


def test_jobspy_row_to_job_maps_all_fields():
    row = {
        "title": "Senior Software Engineer",
        "company": "Acme Corp",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "job_type": "fulltime",
        "min_amount": 3000000,
        "max_amount": 4000000,
        "job_url": "https://www.linkedin.com/jobs/view/123",
        "description": "Building cool things with Python",
        "date_posted": "2026-08-01",
        "is_remote": True,
    }
    job = _jobspy_row_to_job(row, "linkedin")
    assert job is not None
    assert job["title"] == "Senior Software Engineer"
    assert job["company"] == "Acme Corp"
    assert job["location"] == "Bengaluru, Karnataka, India"
    assert job["url"] == "https://www.linkedin.com/jobs/view/123"
    assert job["salary_min"] == 3000000
    assert job["salary_max"] == 4000000
    assert job["source_board"] == "linkedin"
    assert job["posted_date"] == "2026-08-01"
    assert job["employment_type"] == "fulltime"
    assert job["remote_status"] == "remote"


def test_jobspy_row_to_job_skips_empty_title():
    assert _jobspy_row_to_job({"title": "  "}, "indeed") is None
    assert _jobspy_row_to_job({}, "indeed") is None


def test_jobspy_row_to_job_handles_nan_and_bad_salary():
    job = _jobspy_row_to_job(
        {
            "title": "Dev",
            "company": float("nan"),
            "city": None,
            "min_amount": "not-a-number",
            "max_amount": None,
        },
        "indeed",
    )
    assert job is not None
    assert job["company"] == ""
    assert job["location"] == ""
    assert job["salary_min"] == 0
    assert job["salary_max"] == 0
    assert job["employment_type"] == "fulltime"
    assert job["remote_status"] == "unknown"


def test_jobspy_row_to_job_datetime_posted():
    row = {"title": "Dev", "date_posted": datetime(2026, 8, 1, 10, 30)}
    job = _jobspy_row_to_job(row, "google")
    assert job is not None
    assert job["posted_date"] == "2026-08-01"


def test_jobspy_row_to_job_empty_description_truncation():
    row = {"title": "Dev", "description": "x" * 3000}
    job = _jobspy_row_to_job(row, "google")
    assert job is not None
    assert len(job["description"]) == 2000


def test_matches_any_keyword():
    job = {"title": "React Developer", "description": ""}
    assert _matches_any_keyword(job, ["react"])
    assert _matches_any_keyword(job, ["ruby"]) is False
    assert _matches_any_keyword(job, []) is True
    desc_job = {"title": "Engineer", "description": "Uses python daily"}
    assert _matches_any_keyword(desc_job, ["python"])
