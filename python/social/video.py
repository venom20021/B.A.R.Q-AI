"""
Video assembly pipeline - pulls stock footage, generates voiceovers,
adds overlays, and renders final MP4.
"""

from pathlib import Path
from typing import Any

from moviepy import (
    AudioFileClip,
    TextClip,
    concatenate_videoclips,
)

from config import get_settings


class VideoAssembler:
    """Assembles videos from scripts, voiceovers, and stock footage."""

    def __init__(self):
        self.settings = get_settings()

    async def render(
        self,
        script: dict[str, Any],
        output_path: str | Path,
        voiceover_path: str | Path | None = None,
        stock_footage_paths: list[str | Path] | None = None,
    ) -> Path:
        """
        Render a complete video from script and assets.

        Args:
            script: Script dict from ScriptGenerator
            output_path: Where to save the final MP4
            voiceover_path: Optional pre-generated voiceover audio
            stock_footage_paths: Optional stock footage clips

        Returns:
            Path to the rendered video file
        """
        output_path = Path(output_path)

        # Create a simple slideshow-style video
        clips = []

        # If no stock footage, create text-based slides
        sections = script.get("sections", ["Hook", "Content", "CTA"])
        script_text = script.get("script", "")

        # Split script into sections (by timestamp markers)
        section_texts = self._split_into_sections(script_text, sections)

        for i, (section_name, text) in enumerate(section_texts):
            # Create a text clip as placeholder
            txt_clip = TextClip(
                text=text[:200],  # Limit text length
                font_size=40,
                color="white",
                bg_color="black",
                size=(1080, 1920),
                method="caption",
                duration=10.0,
            )
            clips.append(txt_clip)

        # Add voiceover if provided
        if voiceover_path:
            audio = AudioFileClip(str(voiceover_path))
            # Match video duration to audio
            total_duration = audio.duration
            # Adjust clip durations proportionally
            for clip in clips:
                clip = clip.with_duration(total_duration / len(clips))
        else:
            total_duration = min(len(clips) * 10, 60)

        # Composite all clips
        if len(clips) == 1:
            final_clip = clips[0]
        else:
            final_clip = concatenate_videoclips(clips, method="compose")

        # Add voiceover
        if voiceover_path:
            audio = AudioFileClip(str(voiceover_path))
            final_clip = final_clip.with_audio(audio)

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

        # Cleanup
        final_clip.close()
        for clip in clips:
            clip.close()

        return output_path

    def _split_into_sections(
        self, script_text: str, sections: list[str]
    ) -> list[tuple[str, str]]:
        """Split script text into sections based on structure."""
        lines = script_text.strip().split("\n")
        result = []
        current_section = sections[0] if sections else "Content"
        current_text = []

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
                    break
            if not matched:
                current_text.append(line)

        if current_text:
            result.append((current_section, "\n".join(current_text)))

        # If no sections were parsed, treat entire text as one section
        if not result:
            result = [("Content", script_text)]

        return result
