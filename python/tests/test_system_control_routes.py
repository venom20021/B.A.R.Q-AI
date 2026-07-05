"""
Tests for system_control FastAPI routes: file operations, system status, terminal.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def router():
    from system_control import routes
    return routes.router


# ─── System Status ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_status(client):
    """GET /status should return platform info."""
    response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "platform" in data
    assert "hostname" in data
    assert "python_version" in data
    assert "cpus" in data
    assert isinstance(data["cpus"], int)
    assert data["cpus"] > 0


# ─── File Operations ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_folder(client):
    """POST /file/create-folder should create a directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = os.path.join(tmpdir, "test_folder/nested")
        response = await client.post(
            "/file/create-folder",
            json={"path": test_path},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert os.path.isdir(test_path)


@pytest.mark.asyncio
async def test_create_folder_already_exists(client):
    """POST /file/create-folder should not error if folder exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        response = await client.post(
            "/file/create-folder",
            json={"path": tmpdir},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "created"


@pytest.mark.asyncio
async def test_write_and_read_file(client):
    """POST /file/write then POST /file/read should round-trip content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "hello.txt")
        content = "Hello, BARQ!"

        # Write
        write_resp = await client.post(
            "/file/write",
            json={"path": file_path, "content": content},
        )
        assert write_resp.status_code == 200
        assert write_resp.json()["status"] == "written"
        assert write_resp.json()["size_bytes"] == len(content)

        # Read
        read_resp = await client.post(
            "/file/read",
            json={"path": file_path},
        )
        assert read_resp.status_code == 200
        data = read_resp.json()
        assert data["content"] == content
        assert data["size_bytes"] == len(content)


@pytest.mark.asyncio
async def test_write_file_no_content(client):
    """POST /file/write without content should return 400."""
    response = await client.post(
        "/file/write",
        json={"path": "/tmp/test.txt"},
    )
    assert response.status_code == 400
    assert "Content is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_read_file_not_found(client):
    """POST /file/read on non-existent file should return 404."""
    response = await client.post(
        "/file/read",
        json={"path": "/nonexistent/file.txt"},
    )
    assert response.status_code == 404
    assert "File not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_file(client):
    """POST /file/delete should remove a file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "todelete.txt")
        Path(file_path).write_text("delete me")

        response = await client.post(
            "/file/delete",
            json={"path": file_path},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert not os.path.exists(file_path)


@pytest.mark.asyncio
async def test_delete_folder(client):
    """POST /file/delete should remove a folder recursively."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, "sub", "dir")
        os.makedirs(nested)

        response = await client.post(
            "/file/delete",
            json={"path": tmpdir},
        )
        assert response.status_code == 200
        # Temp dir is removed by our call, but the context manager may warn
        assert not os.path.exists(tmpdir)


@pytest.mark.asyncio
async def test_delete_not_found(client):
    """POST /file/delete on non-existent path should return 404."""
    response = await client.post(
        "/file/delete",
        json={"path": "/nonexistent_path_12345"},
    )
    assert response.status_code == 404
    assert "Path not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_move_file(client):
    """POST /file/move should move a file to destination."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "source.txt")
        dst = os.path.join(tmpdir, "dest", "moved.txt")
        Path(src).write_text("move me")

        response = await client.post(
            "/file/move",
            json={"path": src, "destination": dst},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "moved"
        assert not os.path.exists(src)
        assert os.path.isfile(dst)


@pytest.mark.asyncio
async def test_move_no_destination(client):
    """POST /file/move without destination should return 400."""
    response = await client.post(
        "/file/move",
        json={"path": "/tmp/test.txt"},
    )
    assert response.status_code == 400
    assert "Destination is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_search_files(client):
    """POST /file/search should find matching files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(os.path.join(tmpdir, "report_q4.pdf")).write_text("data")
        Path(os.path.join(tmpdir, "notes.txt")).write_text("data")

        response = await client.post(
            f"/file/search?query=report&directory={tmpdir}",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "report"
        assert len(data["results"]) >= 1
        assert any("report" in r["name"].lower() for r in data["results"])


@pytest.mark.asyncio
async def test_sort_files_by_type(client):
    """POST /file/sort/execute should sort files by type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        Path(os.path.join(tmpdir, "doc.pdf")).write_text("pdf")
        Path(os.path.join(tmpdir, "image.png")).write_text("png")
        Path(os.path.join(tmpdir, "script.py")).write_text("py")

        response = await client.post(
            "/file/sort/execute",
            json={"directory": tmpdir, "strategy": "type"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["files_sorted"] >= 0
        assert "undo_id" in data


# ─── Terminal Execution ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_command_success(client):
    """POST /terminal/run should execute a command."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "Hello BARQ\n"
        mock_run.return_value.stderr = ""
        mock_run.return_value.returncode = 0

        response = await client.post(
            "/terminal/run",
            json={"command": "echo Hello BARQ"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "Hello BARQ" in data["output"]
        assert data["return_code"] == 0


@pytest.mark.asyncio
async def test_run_command_with_cwd(client):
    """POST /terminal/run should respect cwd parameter."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "done"
        mock_run.return_value.stderr = ""
        mock_run.return_value.returncode = 0

        response = await client.post(
            "/terminal/run",
            json={"command": "echo test", "cwd": "/tmp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        # Verify cwd was passed to subprocess
        assert mock_run.call_args[1]["cwd"] == "/tmp"


@pytest.mark.asyncio
async def test_run_command_failure(client):
    """POST /terminal/run should handle non-zero exit codes.
    Pre-approve the command since unrecognized commands default to WARN tier.
    """
    # First, approve the command (exit 1 is unrecognized → WARN tier)
    await client.post(
        "/command/approve",
        json={"command": "exit 1", "tier": "warn"},
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "error occurred"
        mock_run.return_value.stderr = "exit code 1"
        mock_run.return_value.returncode = 1

        response = await client.post(
            "/terminal/run",
            json={"command": "exit 1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["return_code"] == 1
        assert "exit code 1" in data["output"]


# ─── Tunneling ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expose_port_no_cloudflared(client):
    """POST /tunnel/expose without cloudflared should return unavailable."""
    response = await client.post(
        "/tunnel/expose",
        json={"port": 3000},
    )
    # Should handle gracefully (FileNotFoundError for cloudflared not installed)
    assert response.status_code == 200
    assert response.json()["status"] in ("tunnel_unavailable",)


# ─── System Events ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_events_returns_filtered(client):
    """GET /events should return only system-type events from the activity log."""
    from database import analytics_dao

    # Seed some system events
    await analytics_dao.log_activity("system", "startup", "System started", severity="info")
    await analytics_dao.log_activity("system", "shutdown", "System shutdown", severity="info")
    await analytics_dao.log_activity("system", "launch_app_error", "Failed to launch app", severity="error")

    # Seed a non-system event that should NOT appear
    await analytics_dao.log_activity("voice", "wake_word", "Wake word detected", severity="info")
    await analytics_dao.log_activity("job", "scan_jobs", "Scanned job listings", severity="info")

    response = await client.get("/events?limit=50")
    assert response.status_code == 200
    data = response.json()

    assert "events" in data
    assert "total" in data
    assert data["total"] == 3  # Only the 3 system events
    assert len(data["events"]) == 3

    # Verify all returned events are system type
    for event in data["events"]:
        assert event["type"] == "system"
        assert "id" in event
        assert "action" in event
        assert "description" in event
        assert "severity" in event
        assert "created_at" in event


@pytest.mark.asyncio
async def test_system_events_limit(client):
    """GET /events should respect the limit parameter."""
    from database import analytics_dao

    # Seed more events than the limit
    for i in range(5):
        await analytics_dao.log_activity("system", "test_event", f"Test event {i}", severity="info")

    response = await client.get("/events?limit=2")
    assert response.status_code == 200
    data = response.json()

    # total reflects the count after limit is applied
    assert data["total"] == 2
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_system_events_empty(client):
    """GET /events should return empty list when no system events exist."""
    from database import analytics_dao

    # Only add non-system events
    await analytics_dao.log_activity("voice", "test", "Voice command", severity="info")

    response = await client.get("/events?limit=50")
    assert response.status_code == 200
    data = response.json()

    assert data["events"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_system_events_default_limit(client):
    """GET /events without limit should use default of 50."""
    from database import analytics_dao

    for i in range(3):
        await analytics_dao.log_activity("system", "test", f"Event {i}", severity="info")

    response = await client.get("/events")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert len(data["events"]) == 3
