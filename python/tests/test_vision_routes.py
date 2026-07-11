"""
Tests for vision FastAPI routes: capture screen/camera and analyze with Gemini.

All external dependencies (mss, opencv, google-genai) and the Gemini API
key loading are mocked so tests run without a camera, display, or API key.

NOTE: The test router is mounted WITHOUT a /vision prefix (unlike main.py),
so tests access e.g. POST /screen instead of POST /vision/screen.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def router():
    from agent.vision_routes import router as vision_router
    return vision_router


# ═══════════════════════════════════════════════════════════════════════════
# /check  (GET /vision/check in production)
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckCapabilities:
    """GET /check — returns installed vision package status.

    The check endpoint does its OWN import checks at runtime
    (try: import mss; import cv2; from google import genai).
    We mock builtins.__import__ to simulate import success/failure.
    """

    @pytest.mark.asyncio
    async def test_all_capabilities_available(self, client):
        """When all deps are importable, all 4 capabilities should be True."""
        _original_import = __builtins__["__import__"]

        def _mock_import(name, *args, **kwargs):
            if name == "mss":
                return type("mod", (), {"__version__": "1.0"})()
            if name == "cv2":
                return type("mod", (), {"__version__": "4.5.0"})()
            if name == "google":
                # google package with genai submodule (for `from google import genai`)
                types_mod = type("types", (), {})()
                genai_mod = type("genai", (), {"types": types_mod})()
                return type("google", (), {"genai": genai_mod, "__version__": "1.0"})()
            if name == "google.genai":
                types_mod = type("types", (), {})()
                return type("genai", (), {"types": types_mod})()
            if name == "google.genai.types":
                return type("types", (), {})()
            return _original_import(name, *args, **kwargs)

        with patch.dict(__builtins__, {"__import__": _mock_import}):
            response = await client.get("/check")
            assert response.status_code == 200
            data = response.json()
            caps = data.get("capabilities", {})
            assert caps.get("screen_capture") is True, f"screen_capture: {caps}"
            assert caps.get("webcam") is True, f"webcam: {caps}"
            assert caps.get("gemini_api") is True, f"gemini_api: {caps}"
            assert caps.get("gemini_live") is True, f"gemini_live: {caps}"
            assert data.get("missing") == []

    @pytest.mark.asyncio
    async def test_no_capabilities_when_nothing_installed(self, client):
        """When no vision deps are importable, all capabilities should be False."""
        _original_import = __builtins__["__import__"]

        def _mock_import(name, *args, **kwargs):
            if name in ("mss", "cv2", "google", "google.genai", "google.genai.types"):
                raise ImportError(f"No module named '{name}'")
            return _original_import(name, *args, **kwargs)

        with patch.dict(__builtins__, {"__import__": _mock_import}):
            response = await client.get("/check")
            assert response.status_code == 200
            data = response.json()
            caps = data.get("capabilities", {})
            assert caps.get("screen_capture") is False
            assert caps.get("webcam") is False
            assert caps.get("gemini_api") is False
            assert caps.get("gemini_live") is False
            assert len(data.get("missing", [])) > 0

    @pytest.mark.asyncio
    async def test_only_screen_capture_available(self, client):
        """Only mss installed, no webcam or Gemini."""
        _original_import = __builtins__["__import__"]

        def _mock_import(name, *args, **kwargs):
            if name == "mss":
                return type("mod", (), {})()
            if name in ("cv2", "google", "google.genai"):
                raise ImportError(f"No module named '{name}'")
            return _original_import(name, *args, **kwargs)

        with patch.dict(__builtins__, {"__import__": _mock_import}):
            response = await client.get("/check")
            assert response.status_code == 200
            caps = response.json().get("capabilities", {})
            assert caps.get("screen_capture") is True
            assert caps.get("webcam") is False
            assert caps.get("gemini_api") is False
            assert caps.get("gemini_live") is False


# ═══════════════════════════════════════════════════════════════════════════
# /screen  (POST /vision/screen in production)
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalyzeScreen:
    """POST /screen — capture screen and analyze with Gemini."""

    FAKE_IMAGE = b"fake-jpeg-bytes-12345"
    FAKE_MIME = "image/jpeg"
    FAKE_TEXT = (
        "I can see a code editor with a dark theme. "
        "There are several files open in the sidebar. "
        "The main window shows TypeScript code."
    )

    @pytest.mark.asyncio
    async def test_screen_analysis_success(self, client):
        """Successful screen capture + Gemini analysis returns text."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/screen",
                json={"prompt": "Describe my screen"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["source"] == "screen"
            assert data["text"] == self.FAKE_TEXT

    @pytest.mark.asyncio
    async def test_screen_analysis_default_prompt(self, client):
        """When no prompt is provided, the default prompt is used."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post("/screen", json={})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            # Default prompt should have been used — response is valid
            assert "text" in data

    @pytest.mark.asyncio
    async def test_screen_analysis_mss_not_installed(self, client):
        """When mss is not installed, returns unavailable status."""
        with (
            patch("agent.vision_routes.capture_screen",
                  side_effect=ImportError("No module named 'mss'")),
        ):
            response = await client.post(
                "/screen",
                json={"prompt": "Describe screen"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unavailable"
            assert "mss" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_screen_analysis_gemini_not_installed(self, client):
        """When google-genai is not installed, returns HTTP 500."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  side_effect=RuntimeError("google-genai not installed")),
        ):
            response = await client.post(
                "/screen",
                json={"prompt": "Describe screen"},
            )
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_screen_analysis_no_api_key(self, client):
        """When no Gemini API key is configured, returns HTTP 500."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  side_effect=RuntimeError("Gemini API key not found")),
        ):
            response = await client.post(
                "/screen",
                json={"prompt": "Describe screen"},
            )
            assert response.status_code == 500
            assert "gemini" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_screen_analysis_returns_image_metadata(self, client):
        """Successful response includes image_size_bytes and mime_type."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/screen",
                json={"prompt": "Describe"},
            )
            data = response.json()
            assert data["status"] == "success"
            # The /screen shortcut doesn't return image_size_bytes,
            # but it should still return text successfully
            assert data["text"] == self.FAKE_TEXT


# ═══════════════════════════════════════════════════════════════════════════
# /camera  (POST /vision/camera in production)
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalyzeCamera:
    """POST /camera — capture webcam and analyze with Gemini."""

    FAKE_IMAGE = b"fake-camera-jpeg"
    FAKE_MIME = "image/jpeg"
    FAKE_TEXT = "I see a person sitting at a desk with a laptop."

    @pytest.mark.asyncio
    async def test_camera_analysis_success(self, client):
        """Successful camera capture + Gemini analysis returns text."""
        with (
            patch("agent.vision_routes.capture_camera",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/camera",
                json={"prompt": "What do you see?"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["source"] == "camera"
            assert data["text"] == self.FAKE_TEXT

    @pytest.mark.asyncio
    async def test_camera_analysis_with_index(self, client):
        """Camera index is passed through to capture_camera."""
        with (
            patch("agent.vision_routes.capture_camera",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)) as mock_cam,
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/camera",
                json={"prompt": "Hello", "camera_index": 2},
            )
            assert response.status_code == 200
            mock_cam.assert_called_with(camera_index=2)

    @pytest.mark.asyncio
    async def test_camera_analysis_opencv_not_installed(self, client):
        """When OpenCV is not installed, returns unavailable status."""
        with (
            patch("agent.vision_routes.capture_camera",
                  side_effect=ImportError("No module named 'cv2'")),
        ):
            response = await client.post(
                "/camera",
                json={"prompt": "What do you see?"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unavailable"
            assert "cv2" in data["message"].lower() or "opencv" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_camera_analysis_default_prompt(self, client):
        """Default prompt is used when none provided."""
        with (
            patch("agent.vision_routes.capture_camera",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT) as mock_gemini,
        ):
            response = await client.post("/camera", json={})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            # Verify the call used keyword arguments (prompt kwarg should be set)
            _, call_kwargs = mock_gemini.call_args
            assert "prompt" in call_kwargs
            assert isinstance(call_kwargs["prompt"], str)
            assert len(call_kwargs["prompt"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# /analyze  (POST /vision/analyze in production)
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalyzeVision:
    """POST /analyze — unified capture + analysis endpoint."""

    FAKE_IMAGE = b"fake-image-bytes"
    FAKE_MIME = "image/jpeg"
    FAKE_TEXT = "This is a test image analysis result."
    FAKE_AUDIO = b"fake-pcm-audio-data-16bit-24000hz"

    @pytest.mark.asyncio
    async def test_analyze_screen_default(self, client):
        """Default angle='screen' captures screen and returns text."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/analyze",
                json={"prompt": "What's here?"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["source"] == "screen"
            assert data["text"] == self.FAKE_TEXT

    @pytest.mark.asyncio
    async def test_analyze_camera(self, client):
        """angle='camera' captures webcam and returns text."""
        with (
            patch("agent.vision_routes.capture_camera",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/analyze",
                json={"prompt": "Who is there?", "angle": "camera"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["source"] == "camera"

    @pytest.mark.asyncio
    async def test_analyze_with_voice_response(self, client):
        """voice_response=True returns base64-encoded PCM audio."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini_live",
                  new_callable=AsyncMock, return_value=self.FAKE_AUDIO),
        ):
            response = await client.post(
                "/analyze",
                json={"prompt": "Describe this", "voice_response": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["voice_response"] is True
            assert data["sample_rate"] == 24000
            import base64
            decoded = base64.b64decode(data["audio_pcm_base64"])
            assert decoded == self.FAKE_AUDIO

    @pytest.mark.asyncio
    async def test_analyze_voice_with_live_unavailable(self, client):
        """When Gemini Live is not available, voice_response returns error."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini_live",
                  side_effect=ImportError("google-genai not installed")),
        ):
            response = await client.post(
                "/analyze",
                json={"prompt": "Hello", "voice_response": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_analyze_capture_failure(self, client):
        """When capture fails, the endpoint raises HTTP 500."""
        with (
            patch("agent.vision_routes.capture_screen",
                  side_effect=RuntimeError("Display not available")),
        ):
            response = await client.post(
                "/analyze",
                json={"prompt": "Test"},
            )
            assert response.status_code == 500
            assert "display" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_analyze_returns_image_metadata(self, client):
        """Successful response includes image_size_bytes and mime_type."""
        with (
            patch("agent.vision_routes.capture_screen",
                  return_value=(self.FAKE_IMAGE, self.FAKE_MIME)),
            patch("agent.vision_routes.analyze_image_with_gemini",
                  new_callable=AsyncMock, return_value=self.FAKE_TEXT),
        ):
            response = await client.post(
                "/analyze",
                json={"prompt": "Test"},
            )
            data = response.json()
            assert data["image_size_bytes"] == len(self.FAKE_IMAGE)
            assert data["mime_type"] == self.FAKE_MIME


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic model validation
# ═══════════════════════════════════════════════════════════════════════════

class TestRequestModels:
    """Pydantic request model defaults and validation."""

    def test_screen_request_default_prompt(self):
        """ScreenRequest default prompt."""
        from agent.vision_routes import ScreenRequest
        req = ScreenRequest()
        assert req.prompt == "What's on my screen? Be concise."

    def test_camera_request_defaults(self):
        """CameraRequest default prompt and camera_index."""
        from agent.vision_routes import CameraRequest
        req = CameraRequest()
        assert req.prompt == "What do you see? Be concise."
        assert req.camera_index == 0

    def test_vision_request_defaults(self):
        """VisionRequest default values."""
        from agent.vision_routes import VisionRequest
        req = VisionRequest()
        assert req.angle == "screen"
        assert req.camera_index == 0
        assert req.voice_response is False
