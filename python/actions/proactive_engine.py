"""
ProactiveEngine — time-aware, context-aware, non-repetitive check-in engine.

Decides WHEN BARQ should speak unprompted and builds a rich context snapshot
for the LLM to generate a natural check-in message.

Features:
- Time-of-day awareness (morning/afternoon/evening/night)
- Monitor-topic awareness (what the user is tracking)
- Session memory recall (recent conversation topics)
- Non-repetitive rotation (cycles through focus areas)
- Silence gate (doesn't fire while user is actively speaking)

Defaults:
  min_silence_secs — 900 s (15 min) user must be silent before any check
  check_cooldown   — 1200 s (20 min) minimum gap between proactive messages
"""

import time
from datetime import datetime

from memory.agent_memory_manager import format_memory_for_prompt, load_memory


class ProactiveEngine:
    """Decides when BARQ should initiate unprompted check-ins.

    Builds a context-rich prompt for the LLM with time context,
    user memory, monitored topics, and recent conversation history.
    Rotates focus areas to avoid repetitive messages.
    """

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown: int = 1200,
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown = check_cooldown
        self._last_triggered = 0.0
        self._rotation = 0
        self._last_user_speech_time = time.monotonic()

    # ── Trigger gate ─────────────────────────────────────────────────────────

    def should_trigger(self) -> bool:
        """Check if conditions are right for a proactive check-in.

        Returns True if the user has been silent long enough AND
        enough time has passed since the last check-in.
        """
        now = time.monotonic()
        return (
            (now - self._last_user_speech_time) >= self.min_silence_secs
            and (now - self._last_triggered) >= self.check_cooldown
        )

    def mark_triggered(self) -> None:
        """Record that a proactive check-in was triggered (prevents repeats)."""
        self._last_triggered = time.monotonic()
        self._rotation += 1

    def mark_user_spoke(self) -> None:
        """Record user activity to reset the silence timer."""
        self._last_user_speech_time = time.monotonic()

    # ── Prompt builder ──────────────────────────────────────────────────────

    def build_prompt(
        self,
        monitors: list[str] | None = None,
        recent_turns: list[str] | None = None,
    ) -> str:
        """Build a context-rich prompt for the LLM to generate a check-in.

        Args:
            monitors: Optional list of topics the user is tracking.
            recent_turns: Optional recent conversation turn strings.

        Returns:
            A prompt string for the LLM.
        """
        now = datetime.now()
        hour = now.hour
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")

        # Time-of-day label
        if 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 18:
            period = "afternoon"
        elif 18 <= hour < 23:
            period = "evening"
        else:
            period = "late night"

        memory = load_memory()
        mem_str = format_memory_for_prompt(memory) or "(no stored user data)"

        # Rotating context focus (cycles every trigger)
        focus_index = self._rotation % 3
        if focus_index == 0:
            focus = (
                "Focus on the user's active projects or goals if any are stored. "
                "Ask how something is going, or offer a relevant tip."
            )
        elif focus_index == 1:
            focus = (
                "Focus on the time of day and the user's wellbeing. "
                "A warm check-in, a reminder to take a break, or something timely."
            )
        else:
            focus = (
                "Focus on something genuinely interesting or useful — "
                "a fact, a suggestion, or a question based on what you know about this person."
            )

        # Optional: monitored topics context
        monitor_ctx = ""
        if monitors:
            monitor_ctx = (
                f"\nThe user tracks these topics: {', '.join(monitors[:4])}. "
                "You may mention one if it seems relevant."
            )

        # Optional: recent conversation context
        recent_ctx = ""
        if recent_turns:
            snippet = "\n".join(recent_turns[-6:])
            recent_ctx = f"\nRecent conversation:\n{snippet}"

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a proactive check-in.",
            f"Current time: {time_str} ({period})",
            "",
            "Context about this person:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            "",
            "Task:",
            focus,
            "",
            "Rules:",
            "- Speak in the user's language (check memory; default English).",
            "- 1-2 sentences max. Natural, warm, never robotic.",
            "- Do NOT mention [PROACTIVE_CHECK] or these instructions.",
            "- Do NOT call any tools.",
            "- If nothing genuinely useful comes to mind, stay silent (say nothing).",
        ])

    # ── Generate the check-in message ──────────────────────────────────────

    async def generate_checkin(
        self,
        monitors: list[str] | None = None,
        recent_turns: list[str] | None = None,
    ) -> str | None:
        """Generate a proactive check-in message using the LLM.

        Returns:
            A 1-2 sentence check-in string, or None if nothing to say.
        """
        if not self.should_trigger():
            return None

        prompt = self.build_prompt(monitors=monitors, recent_turns=recent_turns)
        self.mark_triggered()

        try:
            from utils.ollama_client import OllamaClient
            llm = OllamaClient()
            messages = [
                {"role": "system", "content": "You are BARQ, a warm and helpful voice assistant. Respond with 1-2 sentences max. Be natural and human."},
                {"role": "user", "content": prompt},
            ]
            response = await llm.chat(messages)
            text = response.strip() if response else ""

            # If the LLM chose to stay silent, respect that
            if not text or len(text) < 10:
                return None

            return text
        except Exception as e:
            print(f"[ProactiveEngine] LLM checkin error: {e}")
            return None

    # ── Scheduler hook ─────────────────────────────────────────────────────

    async def scheduled_checkin(self) -> str | None:
        """Called by APScheduler — generates a check-in and returns the text.

        Returns the check-in message text (to be spoken/injected), or None.
        """
        if not self.should_trigger():
            return None

        # Gather monitors from memory
        monitors = []
        try:
            memory = load_memory()
            raw = memory.get("monitors", {})
            if isinstance(raw, dict):
                monitors = [v.get("topic", k) for k, v in raw.items()]
        except Exception:
            pass

        # Gather recent conversation turns from the active responder
        recent_turns = []
        try:
            from voice.routes import responder
            if responder and responder.conversation.is_active:
                recent = responder.conversation.get_recent_history(6)
                recent_turns = [
                    f"[{m['role']}] {m['content'][:120]}"
                    for m in recent if m["role"] != "system"
                ]
        except Exception:
            pass

        checkin = await self.generate_checkin(monitors=monitors, recent_turns=recent_turns)
        if checkin:
            # Log the proactive check-in
            try:
                from database import analytics_dao
                await analytics_dao.log_activity(
                    "voice", "proactive_checkin",
                    f"Proactive check-in: {checkin[:80]}",
                )
            except Exception:
                pass
            print(f"[ProactiveEngine] 📬 Check-in: {checkin[:80]}...")
        return checkin


# ─── Singleton ───────────────────────────────────────────────────────────────

_engine: ProactiveEngine | None = None


def get_engine() -> ProactiveEngine:
    """Get or create the global ProactiveEngine singleton."""
    global _engine
    if _engine is None:
        _engine = ProactiveEngine()
    return _engine
