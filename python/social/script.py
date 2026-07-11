"""
AI script generation for various content formats (TikTok shorts, YouTube essays, etc.).
"""

from typing import Any

from config import get_settings

FORMAT_TEMPLATES = {
    "tiktok_short": {
        "max_duration": 60,
        "style": "Fast-paced, hook in first 3 seconds, trending audio",
        "structure": ["Hook", "Problem", "Solution", "CTA"],
    },
    "youtube_shorts": {
        "max_duration": 60,
        "style": "Vertical video, engaging hook, clear value prop",
        "structure": ["Hook", "Value Point 1", "Value Point 2", "CTA"],
    },
    "youtube_essay": {
        "max_duration": 600,
        "style": "In-depth analysis, storytelling, visual examples",
        "structure": [
            "Hook",
            "Context",
            "Deep Dive (3-5 points)",
            "Conclusion",
            "CTA",
        ],
    },
    "instagram_reel": {
        "max_duration": 90,
        "style": "Visual-first, trending audio, text overlays",
        "structure": ["Hook", "Content", "Call to Action"],
    },
    "twitter_thread": {
        "max_length": 20,
        "style": "Concise, scannable, each tweet adds value",
        "structure": ["Lead Tweet", "Supporting Points (10-15)", "Conclusion"],
    },
}


class ScriptGenerator:
    """Generates structured content scripts using local LLM."""

    def __init__(self):
        self.settings = get_settings()

    async def generate(
        self,
        topic: str,
        format: str,
        tone: str = "professional",
        additional_context: str = "",
    ) -> dict[str, Any]:
        """
        Generate a content script for a specific format.

        Args:
            topic: The topic/content idea
            format: Content format (tiktok_short, youtube_essay, etc.)
            tone: Writing tone (professional, casual, humorous)
            additional_context: Any extra context or references

        Returns:
            Dict with script sections, metadata, and visual cues
        """
        template = FORMAT_TEMPLATES.get(format, FORMAT_TEMPLATES["youtube_shorts"])

        prompt = self._build_script_prompt(topic, format, template, tone, additional_context)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert content scriptwriter. Create engaging, "
                            "structured scripts optimized for the specified platform and format. "
                            "Include visual cues and timing suggestions."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.6},
            )

            script_text = response["message"]["content"]
            return {
                "topic": topic,
                "format": format,
                "tone": tone,
                "estimated_duration": template["max_duration"],
                "script": script_text,
                "sections": template["structure"],
                "visual_cues": self._extract_visual_cues(script_text),
            }

        except Exception as e:
            print(f"[Script] Generation failed: {e}")
            return {
                "topic": topic,
                "format": format,
                "script": f"Error generating script: {e}",
                "sections": [],
                "visual_cues": [],
            }

    def _build_script_prompt(
        self,
        topic: str,
        format: str,
        template: dict[str, Any],
        tone: str,
        context: str,
    ) -> str:
        return f"""
Create a {' '.join(format.split('_')).title()} script.

Topic: {topic}
Format: {format}
Style: {template['style']}
Tone: {tone}
Structure: {' → '.join(template['structure'])}
Max Duration: {template['max_duration']} seconds

Additional Context: {context or 'None'}

Write the complete script with:
1. Timestamp markers (e.g., [0:00-0:05])
2. Visual/action cues in brackets
3. Voiceover text
4. Text overlay suggestions

Make it engaging, clear, and optimized for the platform.
"""

    def _extract_visual_cues(self, script: str) -> list[str]:
        """Extract visual/action cues from script text."""
        cues = []
        for line in script.split("\n"):
            line = line.strip()
            if line.startswith("[") and "]" in line:
                cue = line[line.index("[") + 1 : line.index("]")]
                if cue and len(cue) < 100:
                    cues.append(cue)
        return cues
