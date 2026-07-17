"""
Tests for the BARQ Ingestion Pipeline — IngestionParser, TripletExtractor,
_ProcessedFiles, DropFolderMonitor, and standalone runner.

These tests use mocks for the Ollama HTTP client so they run without a
local LLM.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from memory_knowledge.ingestion import (
    BRAIN_FOLDER_MAP,
    IngestionParser,
    TripletExtractor,
    _ProcessedFiles,
    get_dropbox_base,
    run_ingestion_once,
)
from memory_knowledge.multi_brain import multi_brain_manager


# ═════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_brains():
    """Clear the multi-brain singleton before each test."""
    multi_brain_manager.clear_all()
    yield


@pytest.fixture
def parser() -> IngestionParser:
    """Fresh IngestionParser instance."""
    return IngestionParser()


@pytest.fixture
def mock_httpx_client():
    """Patch httpx.Client to return a controlled mock."""
    with patch("memory_knowledge.ingestion.httpx.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def extractor(mock_httpx_client) -> TripletExtractor:
    """TripletExtractor with mocked HTTP client."""
    return TripletExtractor()


# ═════════════════════════════════════════════════════════════════════════════
#  IngestionParser
# ═════════════════════════════════════════════════════════════════════════════


class TestIngestionParser:
    def test_txt_passthrough(self, parser):
        """Plain text file content is returned as-is (cleaned)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Hello world\n\nThis is a test.")
            path = f.name
        try:
            result = parser.parse(path)
            assert "Hello world" in result
            assert "This is a test" in result
        finally:
            os.unlink(path)

    def test_md_passthrough(self, parser):
        """Already Markdown content is returned as-is."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Title\n\n**bold** and *italic*")
            path = f.name
        try:
            result = parser.parse(path)
            assert "# Title" in result
            assert "**bold**" in result
        finally:
            os.unlink(path)

    def test_json_chat_array(self, parser):
        """JSON array of messages is converted to Markdown conversation."""
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(messages, f)
            path = f.name
        try:
            result = parser.parse(path)
            assert "User" in result
            assert "Assistant" in result
            assert "What is Python?" in result
            assert "Python is a programming language" in result
        finally:
            os.unlink(path)

    def test_json_chat_dict_with_messages_key(self, parser):
        """JSON dict with 'messages' key is converted correctly."""
        data = {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = parser.parse(path)
            assert "**User:**" in result
            assert "**Assistant:**" in result
        finally:
            os.unlink(path)

    def test_json_chat_with_title_and_content(self, parser):
        """JSON dict with title+content keys is parsed correctly."""
        data = {"title": "My Note", "content": "Some important content here"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = parser.parse(path)
            assert "My Note" in result
            assert "Some important content" in result
        finally:
            os.unlink(path)

    def test_html_parsing(self, parser):
        """HTML content is stripped to clean Markdown."""
        html = "<html><head><title>Test Doc</title></head><body><h1>Hello</h1><p>This is <b>bold</b> text.</p></body></html>"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = f.name
        try:
            result = parser.parse(path)
            assert "Hello" in result
            assert "This is" in result
        finally:
            os.unlink(path)

    def test_html_preserves_title(self, parser):
        """HTML <title> is used as the first heading if no h1 present."""
        html = "<html><head><title>Page Title</title></head><body><p>Content here.</p></body></html>"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = f.name
        try:
            result = parser.parse(path)
            assert "# Page Title" in result
        finally:
            os.unlink(path)

    def test_html_strips_style_and_script(self, parser):
        """<style> and <script> blocks are removed."""
        html = "<html><head><style>.cls{color:red}</style><script>alert('x')</script></head><body><p>Text</p></body></html>"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = f.name
        try:
            result = parser.parse(path)
            assert "Text" in result
            assert "color:red" not in result
            assert "alert" not in result
        finally:
            os.unlink(path)

    def test_unknown_suffix_treated_as_text(self, parser):
        """Unknown file extensions are treated as plain text."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write("Some log content")
            path = f.name
        try:
            result = parser.parse(path)
            assert "Some log content" in result
        finally:
            os.unlink(path)

    def test_non_existent_file_returns_empty(self, parser):
        """Parsing a non-existent file returns an empty string."""
        result = parser.parse("/nonexistent/path/file.txt")
        assert result == ""

    def test_bom_stripped(self, parser):
        """UTF-8 BOM is stripped from text content."""
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".txt", delete=False
        ) as f:
            f.write(b"\xef\xbb\xbfHello with BOM")
            path = f.name
        try:
            result = parser.parse(path)
            assert result == "Hello with BOM"
        finally:
            os.unlink(path)

    def test_empty_file_returns_empty_string(self, parser):
        """Empty file returns empty string."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            path = f.name
        try:
            result = parser.parse(path)
            assert result == ""
        finally:
            os.unlink(path)

    def test_invalid_json_falls_back_to_text(self, parser):
        """Invalid JSON file falls back to raw text."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("This is not JSON {{")
            path = f.name
        try:
            result = parser.parse(path)
            assert "This is not JSON" in result
        finally:
            os.unlink(path)

    def test_html_link_conversion(self, parser):
        """HTML <a> tags are converted to Markdown links."""
        html = '<p>Visit <a href="https://example.com">Example</a> today.</p>'
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            path = f.name
        try:
            result = parser.parse(path)
            assert "[Example](https://example.com)" in result
        finally:
            os.unlink(path)


# ═════════════════════════════════════════════════════════════════════════════
#  TripletExtractor
# ═════════════════════════════════════════════════════════════════════════════


class TestTripletExtractor:
    def test_successful_extraction(self, extractor, mock_httpx_client):
        """Successful Ollama response adds triplets to the brain."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "response": json.dumps([
                ["python", "USED_FOR", "data science"],
                ["python", "USED_AT", "google"],
            ])
        }
        mock_httpx_client.post.return_value = mock_post

        count = extractor.process_document("general", "Python is used for data science at Google.")
        assert count == 2

        graph = multi_brain_manager.get_brain("general")
        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 2

    def test_empty_extraction(self, extractor, mock_httpx_client):
        """Ollama returning empty array adds zero triplets."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"response": "[]"}
        mock_httpx_client.post.return_value = mock_post

        count = extractor.process_document("general", "Some text with no relationships.")
        assert count == 0

    def test_ollama_http_error(self, extractor, mock_httpx_client):
        """Ollama HTTP error is handled gracefully."""
        from httpx import HTTPStatusError, RequestError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_httpx_client.post.side_effect = HTTPStatusError(
            "500 error", request=MagicMock(), response=mock_response
        )

        count = extractor.process_document("general", "Some text.")
        assert count == 0
        assert extractor.stats["last_error"] is not None

    def test_ollama_connection_error(self, extractor, mock_httpx_client):
        """Ollama connection error is handled gracefully."""
        from httpx import RequestError

        mock_httpx_client.post.side_effect = RequestError("Connection refused")

        count = extractor.process_document("general", "Some text.")
        assert count == 0
        assert extractor.stats["last_error"] is not None

    def test_empty_content_returns_zero(self, extractor):
        """Empty or whitespace-only content returns zero triplets."""
        count = extractor.process_document("general", "")
        assert count == 0
        count = extractor.process_document("general", "   ")
        assert count == 0

    def test_extractor_tracks_stats(self, extractor, mock_httpx_client):
        """Extractor statistics are correctly tracked."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "response": json.dumps([["a", "RELATED_TO", "b"]])
        }
        mock_httpx_client.post.return_value = mock_post

        assert extractor.stats["total_documents_processed"] == 0
        assert extractor.stats["total_triplets_extracted"] == 0

        extractor.process_document("general", "Some text")
        assert extractor.stats["total_documents_processed"] == 1
        assert extractor.stats["total_triplets_extracted"] == 1

        extractor.process_document("general", "More text")
        assert extractor.stats["total_documents_processed"] == 2
        assert extractor.stats["total_triplets_extracted"] == 2

    def test_reset_stats(self, extractor, mock_httpx_client):
        """reset_stats clears all counters."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"response": "[]"}
        mock_httpx_client.post.return_value = mock_post

        extractor.process_document("general", "text")
        extractor.reset_stats()
        stats = extractor.stats
        assert stats["total_documents_processed"] == 0
        assert stats["total_triplets_extracted"] == 0
        assert stats["last_error"] is None

    def test_malformed_json_response(self, extractor, mock_httpx_client):
        """Malformed Ollama JSON response is handled gracefully."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"response": "not valid json"}
        mock_httpx_client.post.return_value = mock_post

        count = extractor.process_document("general", "Some text.")
        assert count == 0

    def test_non_array_response(self, extractor, mock_httpx_client):
        """Non-array JSON response is handled gracefully."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"response": '{"key": "value"}'}
        mock_httpx_client.post.return_value = mock_post

        count = extractor.process_document("general", "Some text.")
        assert count == 0

    def test_process_file(self, extractor, mock_httpx_client):
        """process_file reads and processes a file from disk."""
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "response": json.dumps([["python", "USED_FOR", "data science"]])
        }
        mock_httpx_client.post.return_value = mock_post

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Python is used for data science.")
            path = f.name
        try:
            count = extractor.process_file("general", path)
            assert count == 1
        finally:
            os.unlink(path)

    def test_process_file_nonexistent(self, extractor):
        """process_file returns 0 for non-existent file."""
        count = extractor.process_file("general", "/nonexistent/file.txt")
        assert count == 0

    def test_extractor_singleton(self):
        """get_extractor returns the same instance."""
        from memory_knowledge.ingestion import get_extractor
        e1 = get_extractor()
        e2 = get_extractor()
        assert e1 is e2


# ═════════════════════════════════════════════════════════════════════════════
#  _ProcessedFiles
# ═════════════════════════════════════════════════════════════════════════════


class TestProcessedFiles:
    def test_was_processed_returns_true_after_mark(self):
        """A file marked as processed returns True."""
        pf = _ProcessedFiles()
        pf.mark_processed("/path/to/file.txt")
        assert pf.was_processed("/path/to/file.txt") is True

    def test_unprocessed_file_returns_false(self):
        """An unmarked file returns False."""
        pf = _ProcessedFiles()
        assert pf.was_processed("/path/to/other.txt") is False

    def test_resolves_absolute_path(self):
        """Relative paths are resolved to absolute."""
        pf = _ProcessedFiles()
        pf.mark_processed("relative/path.txt")
        assert pf.was_processed("relative/path.txt") is True

    def test_max_size_trims_old_entries(self):
        """When max_size is exceeded, old entries are trimmed."""
        pf = _ProcessedFiles(max_size=10)
        for i in range(15):
            pf.mark_processed(f"/path/file_{i}.txt")
        assert len(pf._set) <= 10


# ═════════════════════════════════════════════════════════════════════════════
#  DropFolderMonitor
# ═════════════════════════════════════════════════════════════════════════════


class TestDropFolderMonitor:
    def test_monitor_init(self):
        """Monitor initialises without watchdog."""
        from memory_knowledge.ingestion import DropFolderMonitor
        monitor = DropFolderMonitor()
        assert monitor.is_running is False

    def test_start_and_stop_lifecycle(self):
        """Monitor can be started and stopped (no-op without watchdog)."""
        from memory_knowledge.ingestion import DropFolderMonitor
        monitor = DropFolderMonitor()
        monitor.start()
        # Without watchdog, start just logs a warning
        monitor.stop()
        assert monitor.is_running is False

    def test_process_all_existing(self, mock_httpx_client):
        """process_all_existing processes files in drop-folders."""
        from memory_knowledge.ingestion import DropFolderMonitor, TripletExtractor

        # Setup mock Ollama response
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "response": json.dumps([["python", "USED_FOR", "data science"]])
        }
        mock_httpx_client.post.return_value = mock_post

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a drop-folder with a test file
            brain_folder = Path(tmpdir) / "general"
            brain_folder.mkdir(parents=True)
            test_file = brain_folder / "test.txt"
            test_file.write_text("Python is used for data science.", encoding="utf-8")

            # Use a fixture-created extractor (has mocked httpx) instead of module singleton
            extr = TripletExtractor()
            monitor = DropFolderMonitor(extractor=extr, dropbox_dir=tmpdir)
            results = monitor.process_all_existing()
            assert "general" in results
            assert results["general"] >= 1


# ═════════════════════════════════════════════════════════════════════════════
#  get_dropbox_base
# ═════════════════════════════════════════════════════════════════════════════


class TestGetDropboxBase:
    def test_creates_folders(self):
        """get_dropbox_base creates the base directory and all brain folders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("memory_knowledge.ingestion._DEFAULT_DROPBOX", tmpdir):
                base = get_dropbox_base()
                assert Path(base).exists()
                for folder in BRAIN_FOLDER_MAP:
                    assert (Path(base) / folder).exists()

    def test_returns_string_path(self):
        """get_dropbox_base returns a string path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("memory_knowledge.ingestion._DEFAULT_DROPBOX", tmpdir):
                base = get_dropbox_base()
                assert isinstance(base, str)


# ═════════════════════════════════════════════════════════════════════════════
#  run_ingestion_once
# ═════════════════════════════════════════════════════════════════════════════


class TestRunIngestionOnce:
    def test_run_all_brains(self, mock_httpx_client):
        """run_ingestion_once processes all brain folders with correct counts."""
        # Module-level _triplet_extractor has a real httpx.Client; patch get_extractor
        # to return a fixture-created extractor with mocked HTTP.
        from unittest.mock import patch as _patch
        from memory_knowledge.ingestion import TripletExtractor as TE
        import memory_knowledge.ingestion as _ing

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "response": json.dumps([["a", "RELATED_TO", "b"]])
        }
        mock_httpx_client.post.return_value = mock_post

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple brain folders with test files
            for brain in ["general", "ai_chats"]:
                folder = Path(tmpdir) / brain
                folder.mkdir(parents=True)
                (folder / f"{brain}_test.txt").write_text(f"A {brain} file.", encoding="utf-8")

            fixture_extractor = TE()
            with _patch.object(_ing, "get_extractor", return_value=fixture_extractor):
                results = run_ingestion_once(dropbox_dir=tmpdir)
                assert results.get("general", 0) >= 1
                assert results.get("ai_chats", 0) >= 1

    def test_run_single_brain(self, mock_httpx_client):
        """run_ingestion_once with brain_type processes only that brain."""
        from unittest.mock import patch as _patch
        from memory_knowledge.ingestion import TripletExtractor as TE
        import memory_knowledge.ingestion as _ing

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {
            "response": json.dumps([["a", "RELATED_TO", "b"]])
        }
        mock_httpx_client.post.return_value = mock_post

        with tempfile.TemporaryDirectory() as tmpdir:
            for brain in ["general", "career"]:
                folder = Path(tmpdir) / brain
                folder.mkdir(parents=True)
                (folder / f"{brain}_test.txt").write_text(f"A {brain} file.", encoding="utf-8")

            fixture_extractor = TE()
            with _patch.object(_ing, "get_extractor", return_value=fixture_extractor):
                results = run_ingestion_once(brain_type="career", dropbox_dir=tmpdir)
                assert results.get("career", 0) >= 1
                assert results.get("general", 0) == 0

    def test_no_files_returns_zeros(self):
        """Empty drop-folders return zero triplets for all brains."""
        from memory_knowledge.ingestion import get_dropbox_base

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty brain folders
            for brain in BRAIN_FOLDER_MAP:
                (Path(tmpdir) / brain).mkdir(parents=True)

            results = run_ingestion_once(dropbox_dir=tmpdir)
            for brain in BRAIN_FOLDER_MAP:
                assert results[brain] == 0

    def test_skips_temporary_files(self, mock_httpx_client):
        """run_ingestion_once skips .tmp, .part, and .processed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "general"
            folder.mkdir(parents=True)
            (folder / "file.tmp").write_text("temp", encoding="utf-8")
            (folder / "file.part").write_text("part", encoding="utf-8")
            (folder / "file.processed").write_text("processed", encoding="utf-8")

            results = run_ingestion_once(dropbox_dir=tmpdir)
            assert results["general"] == 0
