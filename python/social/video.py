"""
Video assembly pipeline - pulls stock footage, generates voiceovers,
adds captions, and renders final MP4 (Phase 1b: Video v2).

Upgrades over the old text-slideshow renderer:
- Stock footage matched to the script topic / visual cues (Pexels API, free tier)
- Burned-in caption overlays on each clip
- Optional auto voiceover via Deepgram TTS (falls back to silent video)
- Everything degrades gracefully back to styled text slides when
  footage/TTS/ffmpeg is unavailable, so renders never crash.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from config import get_settings

try:
    from moviepy import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        concatenate_videoclips,
    )
    MOVIEPY_AVAILABLE = True
except Exception:  # pragma: no cover - import fallback
    MOVIEPY_AVAILABLE = False


# Vertical video canvas (9:16) for shorts/reels
CANVAS_W = 1080
CANVAS_H = 1920

def _resolve_caption_font() -> str:
    """Return a usable caption font (file path preferred) for this platform.

    Pillow/moviepy can't always resolve bare font names (DejaVu-Sans fails on
    some Linux boxes, Arial on Windows), so resolve a real .ttf path first and
    fall back to the bare name only as a last resort.
    """
    if os.name == "nt":
        win = os.environ.get("WINDIR", "C:/Windows")
        arial = os.path.join(win, "Fonts", "arial.ttf")
        if os.path.exists(arial):
            return arial
        return "Arial"
    for cand in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if os.path.exists(cand):
            return cand
    return "DejaVu-Sans"


_CAPTION_FONT = _resolve_caption_font()


class VideoAssembler:
    """Assembles videos from scripts, voiceovers, and stock footage."""

    def __init__(self):
        self.settings = get_settings()

    # ── Stock footage (Pexels API - free tier, no-cost rule) ────────────

    async def _fetch_stock_footage(self, query: str, count: int = 3) -> list[str]:
        """Download short stock video clips from Pexels for a search query.

        Requires PEXELS_API_KEY in .env (free tier). Returns local file paths
        (empty list if the key is missing, the request fails, or no videos
        match — the caller falls back to text slides).
        """
        api_key = getattr(self.settings, "pexels_api_key", "") or os.getenv("PEXELS_API_KEY", "")
        if not api_key or not query:
            return []

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.pexels.com/videos/search",
                    params={"query": query[:60], "per_page": count, "orientation": "portrait"},
                    headers={"Authorization": api_key},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                videos = data.get("videos", [])

            paths: list[str] = []
            tmp_dir = Path(tempfile.gettempdir()) / "barq_stock"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            for vid in videos[:count]:
                # Pick the first portrait video file URL
                url = ""
                for f in vid.get("video_files", []):
                    if f.get("width", 0) and f.get("width", 0) <= 1080 and f.get("height", 0) >= f.get("width", 0):
                        url = f.get("link", "")
                        break
                if not url:
                    # Fallback: any file
                    files = vid.get("video_files", [])
                    url = files[0].get("link", "") if files else ""

                if not url:
                    continue
                try:
                    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                        dl = await client.get(url)
                        if dl.status_code == 200:
                            ext = ".mp4" if url.endswith(".mp4") else ".mp4"
                            path = tmp_dir / f"stock_{vid.get('id', 'x')}{ext}"
                            path.write_bytes(dl.content)
                            paths.append(str(path))
                except Exception:
                    continue
            return paths
        except Exception as e:
            print(f"[Video] Stock footage fetch failed (non-fatal): {e}")
            return []

    async def _auto_voiceover(self, script_text: str) -> Optional[str]:
        """Generate a voiceover WAV for the script using Deepgram TTS.

        Returns a local file path, or None if TTS is unavailable/uncosted.
        """
        if not script_text or not script_text.strip():
            return None
        try:
            from voice.speech import SpeechProcessor

            proc = SpeechProcessor()
            wav_bytes = await proc.synthesize(script_text[:3000])
            if not wav_bytes:
                return None
            path = Path(tempfile.gettempdir()) / "barq_voiceover.wav"
            path.write_bytes(wav_bytes)
            return str(path)
        except Exception as e:
            print(f"[Video] Voiceover generation failed (non-fatal): {e}")
            return None

    # ── Render ───────────────────────────────────────────────────────────

    async def render(
        self,
        script: dict[str, Any],
        output_path: str | Path,
        voiceover_path: str | Path | None = None,
        stock_footage_paths: list[str | Path] | None = None,
    ) -> Path:
        """
        Render a complete video from script and assets.

        Video v2: prefers real stock footage matched to the script's topic /
        visual cues, burned-in captions, and a voiceover (auto-generated via
        TTS when not supplied). Falls back to styled text slides when footage
        or ffmpeg is unavailable — the render never fails because of media.

        Args:
            script: Script dict from ScriptGenerator (topic, script, sections,
                visual_cues)
            output_path: Where to save the final MP4
            voiceover_path: Optional pre-generated voiceover audio
            stock_footage_paths: Optional stock footage clips

        Returns:
            Path to the rendered video file
        """
        output_path = Path(output_path)

        if not MOVIEPY_AVAILABLE:
            # No moviepy — write a minimal placeholder so the pipeline
            # (and its DB row) still completes.
            output_path.write_bytes(b"")
            return output_path

        script_text = script.get("script", "") or ""
        topic = script.get("topic", "") or ""
        visual_cues = script.get("visual_cues", []) or []
        sections = script.get("sections", ["Hook", "Content", "CTA"])
        section_texts = self._split_into_sections(script_text, sections)

        # ── Stock footage: use provided paths or fetch by topic/cues ─────
        footage: list[str] = [str(p) for p in (stock_footage_paths or []) if Path(p).exists()]
        downloaded_footage: list[str] = []
        if not footage:
            search = topic or (visual_cues[0] if visual_cues else "")
            if search:
                footage = await self._fetch_stock_footage(search, count=len(section_texts) or 3)
                downloaded_footage = list(footage)

        # ── Voiceover: use provided or auto-generate from the script ─────
        voice = str(voiceover_path) if voiceover_path else None
        if not voice:
            voice = await self._auto_voiceover(script_text)

        clips = []
        try:
            if footage:
                clips = await self._build_footage_clips(footage, section_texts)
            if not clips:
                clips = self._build_slide_clips(section_texts)

            if not clips:
                # Nothing to render — empty placeholder
                output_path.write_bytes(b"")
                return output_path

            # Composite: captions over the visual layer
            final_clip = self._composite_with_captions(clips, section_texts)

            # Attach voiceover audio
            if voice and Path(voice).exists():
                try:
                    audio = AudioFileClip(voice)
                    if audio.duration and audio.duration > 0:
                        final_clip = final_clip.with_audio(audio).with_duration(
                            max(audio.duration, final_clip.duration)
                        )
                    else:
                        audio.close()
                except Exception as e:
                    print(f"[Video] Voiceover attach failed (non-fatal): {e}")

            # Write output
            final_clip.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                fps=30,
                preset="medium",
                threads=4,
                logger=None,  # Suppress moviepy logs
            )
            final_clip.close()
        except Exception as e:
            print(f"[Video] Render error (non-fatal): {e}")
            output_path.write_bytes(b"")
        finally:
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass
            # Remove footage we downloaded ourselves (never user-provided paths)
            for f in downloaded_footage:
                try:
                    Path(f).unlink(missing_ok=True)
                except Exception:
                    pass

        return output_path

    # ── Clip builders ───────────────────────────────────────────────────

    async def _build_footage_clips(
        self, footage: list[str], section_texts: list[tuple[str, str]]
    ) -> list:
        """Build video clips from stock footage, one per script section."""
        clips = []
        try:
            for i, path in enumerate(footage):
                section = section_texts[i] if i < len(section_texts) else section_texts[-1] if section_texts else ("", "")
                try:
                    clip = ImageClip(path) if path.lower().endswith((".png", ".jpg", ".jpeg")) else None
                    if clip is None:
                        from moviepy import VideoFileClip
                        clip = VideoFileClip(path)
                    clip = clip.resized(height=CANVAS_H)
                    # Cover-crop horizontally to canvas width
                    if clip.w < CANVAS_W:
                        clip = clip.resized(width=CANVAS_W)
                    clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=CANVAS_W, height=CANVAS_H)
                    clip = clip.with_duration(8.0)
                    clips.append(clip)
                except Exception as e:
                    print(f"[Video] Footage clip {i} skipped: {e}")
                    continue
        except Exception:
            pass
        return clips

    def _build_slide_clips(self, section_texts: list[tuple[str, str]]) -> list:
        """Build styled text slides as a fallback when no footage is available."""
        clips = []
        for i, (section_name, text) in enumerate(section_texts):
            try:
                txt_clip = TextClip(
                    text=(text or section_name or " ")[:200],
                    font_size=48,
                    color="white",
                    bg_color="black",
                    size=(CANVAS_W, CANVAS_H),
                    method="caption",
                    duration=8.0,
                )
                clips.append(txt_clip)
            except Exception as e:
                print(f"[Video] Slide {i} failed: {e}")
        return clips

    def _composite_with_captions(self, base_clips: list, section_texts: list[tuple[str, str]]) -> Any:
        """Stack the visual clips and overlay a caption bar for each section."""
        if len(base_clips) == 1:
            base = base_clips[0]
        else:
            base = concatenate_videoclips(base_clips, method="compose")

        overlays = []
        caption_duration = max(base.duration / max(len(section_texts), 1), 3.0)
        for i, (section_name, text) in enumerate(section_texts):
            try:
                caption = TextClip(
                    text=(text or section_name or " ")[:120],
                    font_size=34,
                    color="white",
                    bg_color=(0, 0, 0, 140),
                    font=_CAPTION_FONT,
                    stroke_color="black",
                    stroke_width=1,
                    method="caption",
                    size=(CANVAS_W - 120, 180),
                )
                caption = caption.with_position(("center", CANVAS_H - 320))
                caption = caption.with_start(i * caption_duration).with_duration(caption_duration)
                overlays.append(caption)
            except Exception as e:
                print(f"[Video] Caption {i} failed: {e}")

        if overlays:
            return CompositeVideoClip([base, *overlays], size=(CANVAS_W, CANVAS_H))
        return base

    def _split_into_sections(
        self, script_text: str, sections: list[str]
    ) -> list[tuple[str, str]]:
        """Split script text into sections based on structure."""
        lines = script_text.strip().split("\n")
        result = []
        current_section = sections[0] if sections else "Content"
        current_text = []
        matched_any = False

        for line in lines:
            line_lower = line.lower()
            matched = False
            for section in sections:
                if section.lower() in line_lower and len(line) < 50:
                    if current_text:
                        result.append((current_section, "\n".join(current_text)))
                    current_section = section
                    current_text = []
                    matched = True
                    matched_any = True
                    break
            if not matched:
                current_text.append(line)

        if current_text:
            result.append((current_section, "\n".join(current_text)))

        # If no real section headers were ever found, the whole script is a
        # single Content block — never report a phantom header (sections[0]).
        if not result or not matched_any:
            result = [("Content", script_text)]

        return result
