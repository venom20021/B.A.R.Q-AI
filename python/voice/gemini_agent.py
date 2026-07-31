"""
Gemini Live Voice Agent — uses Google Gemini's native audio WebSocket API.

Architecture (inspired by Mark-L):
  Mic (16 kHz PCM) → Gemini Live Audio WebSocket → Speaker (24 kHz PCM)

Gemini handles STT + LLM + TTS in a single WebSocket connection.
No local STT, no local TTS, no MP3 decoding, no event-loop corruption.

Requires:
  - GEMINI_API_KEY environment variable
  - pip install google-genai
"""

import asyncio
import os
import threading
import time
from typing import Any, Optional

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

from config import get_settings
from .agent_base import VoiceAgentBase
from .function_executor import execute_function, get_function_schemas

LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
MIC_CHUNK_SIZE = 1024       # ~64 ms at 16 kHz
OUTPUT_BLOCK_SIZE = 2400    # ~50 ms at 24 kHz — fast barge-in


class GeminiVoiceAgent(VoiceAgentBase):
    """Voice agent using Gemini Live Audio WebSocket.

    Streams mic audio to Gemini and plays back the audio response.
    Gemini handles STT + LLM + TTS natively — no local processing needed.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self._api_key:
            print("[GeminiAgent] [!!] GEMINI_API_KEY not set - agent will fail to connect")

        self._client: Optional[genai.Client] = None
        self._session: Optional[Any] = None          # LiveSession
        self._live_cm: Optional[Any] = None           # async context manager for session
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

        # Audio queues
        self._audio_out_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._audio_in_queue: asyncio.Queue = asyncio.Queue()

        # Streams
        self._input_stream: Optional[sd.InputStream] = None
        self._output_stream: Optional[sd.RawOutputStream] = None

        # State
        self._is_speaking = False
        self._speaking_lock = threading.Lock()
        self._turn_done_event: Optional[asyncio.Event] = None
        self._started_event = asyncio.Event()   # set after start_conversation()

        # Callbacks (wired by ConversationListener)
        self.on_interim_transcript = None
        self.on_final_transcript = None
        self.on_agent_speaking = None
        self.on_agent_done_speaking = None
        self.on_audio_chunk = None
        self.on_agent_text = None

        # ── Windows asyncio AssertionError suppressor ────────────────
        # Gemini Live uses aiohttp under the hood, which triggers the
        # same ProactorBaseWritePipeTransport bug on Python 3.13+ Windows.
        _install_gemini_assertion_guard()

    # ── VoiceAgentBase interface ──────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    async def connect(self) -> bool:
        """Open the Gemini Live WebSocket session."""
        if not self._api_key:
            print("[GeminiAgent] [XX] Connect failed: GEMINI_API_KEY not set")
            return False
        if self._running:
            return True

        self._loop = asyncio.get_event_loop()

        try:
            self._client = genai.Client(
                api_key=self._api_key,
                http_options={"api_version": "v1beta"},
            )

            system_prompt = self._build_system_prompt()

            # ── Register BARQ's tools as Gemini function declarations ──
            try:
                schemas = get_function_schemas()
                tools = [{"function_declarations": schemas}]
                print(f"[GeminiAgent] [pkg] Registered {len(schemas)} tools")
            except Exception as e:
                print(f"[GeminiAgent] [!!] Tool registration failed: {e}")
                tools = None

            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                output_audio_transcription={},
                input_audio_transcription={},
                system_instruction=system_prompt,
                tools=tools,
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Charon",
                        )
                    )
                ),
            )

            # live.connect() is an async context manager (not a plain awaitable)
            self._live_cm = self._client.aio.live.connect(
                model=LIVE_MODEL,
                config=config,
            )
            self._session = await self._live_cm.__aenter__()

            print("[GeminiAgent] [OK] Connected to Gemini Live")
            self._running = True
            return True

        except Exception as e:
            print(f"[GeminiAgent] [XX] Connect failed: {e}")
            self._running = False
            return False

    async def start_conversation(self, audio_device: Optional[int] = None):
        """Begin streaming mic audio and playing Gemini responses.

        Runs three concurrent tasks inside a TaskGroup:
          1. Send mic PCM → Gemini
          2. Receive audio from Gemini → play through speakers
          3. Receive transcripts / turn-complete events
        """
        if not self._session or not self._running:
            print("[GeminiAgent] Cannot start: not connected")
            return

        self._turn_done_event = asyncio.Event()
        self._started_event.set()

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._send_mic_loop(audio_device))
                tg.create_task(self._play_audio_loop())
                tg.create_task(self._receive_loop())
        except Exception as e:
            print(f"[GeminiAgent] Conversation error: {e}")
        finally:
            self._running = False

    async def stop(self):
        """Gracefully stop the conversation and close WebSocket."""
        self._running = False

        # Close input stream
        if self._input_stream:
            try:
                self._input_stream.stop()
                self._input_stream.close()
            except Exception:
                pass
            self._input_stream = None

        # Close output stream
        if self._output_stream:
            try:
                self._output_stream.stop()
                self._output_stream.close()
            except Exception:
                pass
            self._output_stream = None

        # Close Live session via context manager exit
        if self._live_cm:
            try:
                await self._live_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._live_cm = None
            self._session = None
        elif self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

        print("[GeminiAgent] Stopped")

    async def speak_text(self, text: str) -> None:
        """Synthesise and play a spoken phrase via Gemini Live.

        Sends text as a client message; Gemini responds with audio that
        flows through the standard _play_audio_loop.
        """
        if not self._session or not self._running:
            print("[GeminiAgent] Cannot speak: not connected")
            return

        # If the conversation tasks haven't started yet, send and wait
        if not self._started_event.is_set():
            try:
                await self._session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True,
                )
                print(f"[GeminiAgent] Sent greeting: '{text}'")
            except Exception as e:
                print(f"[GeminiAgent] speak_text error: {e}")
            return

        # Conversation is already active — send as a client message
        try:
            await self._session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True,
            )
            print(f"[GeminiAgent] Queued speech: '{text[:60]}...'")
        except Exception as e:
            print(f"[GeminiAgent] speak_text error: {e}")

    def cancel_current_tts(self) -> None:
        """Interrupt ongoing speech (barge-in)."""
        q = self._audio_in_queue
        drained = 0
        while True:
            try:
                q.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        if drained:
            print(f"[GeminiAgent] [int] Barge-in - {drained} chunks discarded")

    # ── Internal helpers ──────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the system instruction with time context and session memory."""
        from datetime import datetime

        now = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")

        # Inject last session summary (morning recall)
        session_clause = ""
        try:
            from memory.agent_memory_manager import pop_last_session
            last = pop_last_session()
            if last:
                summary = last.get("summary", "")
                s_date = last.get("date", "")
                if summary:
                    session_clause = (
                        f"\nYou were last used on {s_date}. "
                        f"Summary of that session: {summary}"
                    )
        except Exception:
            pass

        return (
            f"[Current date and time: {time_str}]\n"
            f"You are BARQ, a helpful AI desktop assistant. "
            f"Be concise, natural, and conversational. "
            f"Keep responses brief — under three sentences when possible."
            f"{session_clause}"
        )

    async def _send_mic_loop(self, device: Optional[int] = None):
        """Continuously stream mic audio frames to Gemini Live."""
        loop = self._loop or asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[GeminiAgent] Mic status: {status}")
            # Only send when BARQ is not speaking (avoid echo)
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking:
                data = indata.tobytes()
                try:
                    loop.call_soon_threadsafe(
                        self._audio_out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm"},
                    )
                except asyncio.QueueFull:
                    pass  # drop oldest frame, keep moving

        try:
            # Resolve output device
            try:
                from .audio_device import resolve_input_device
                if device is None:
                    device = resolve_input_device(
                        get_settings().audio_input_device
                    )
            except Exception:
                pass

            self._input_stream = sd.InputStream(
                device=device,
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=MIC_CHUNK_SIZE,
                callback=callback,
            )
            self._input_stream.start()
            print("[GeminiAgent] [mic] Mic stream started (16 kHz)")

            while self._running:
                try:
                    msg = await asyncio.wait_for(
                        self._audio_out_queue.get(), timeout=0.1
                    )
                    if self._session:
                        await self._session.send_realtime_input(media=msg)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"[GeminiAgent] Send error: {e}")

        except Exception as e:
            print(f"[GeminiAgent] [XX] Mic error: {e}")
            raise

    async def _play_audio_loop(self):
        """Read PCM audio from Gemini and play through speakers.

        Batches chunks for smoother playback while keeping block size
        small enough for responsive barge-in.
        """
        try:
            # Resolve output device
            try:
                from .audio_device import resolve_output_device
                out_dev = resolve_output_device(
                    get_settings().audio_output_device
                )
            except Exception:
                out_dev = None

            self._output_stream = sd.RawOutputStream(
                device=out_dev,
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=OUTPUT_BLOCK_SIZE,
            )
            self._output_stream.start()
            print("[GeminiAgent] [spk] Output stream started (24 kHz)")

            while self._running:
                try:
                    chunk = await asyncio.wait_for(
                        self._audio_in_queue.get(), timeout=0.15
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self._audio_in_queue.empty()
                    ):
                        self._set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self._set_speaking(True)

                # Batch up to ~200 ms of audio for smooth writes
                batch = bytearray(chunk)
                while len(batch) < 9600:  # 200 ms at 24 kHz / 16-bit
                    try:
                        batch.extend(self._audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                try:
                    await asyncio.to_thread(self._output_stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break

        except Exception as e:
            print(f"[GeminiAgent] [XX] Play error: {e}")
        finally:
            self._set_speaking(False)

    async def _receive_loop(self):
        """Receive streaming responses from Gemini Live.

        Handles:
          - Audio data → _audio_in_queue for playback
          - Output transcription → on_agent_text callback
          - Turn-complete events → _turn_done_event
          - Tool calls → logged for future integration
        """
        out_buf: list[str] = []

        try:
            async for response in self._session.receive():
                if not self._running:
                    break

                # ── Audio data ────────────────────────────────────────
                if response.data:
                    if self._turn_done_event and self._turn_done_event.is_set():
                        self._turn_done_event.clear()

                    audio_data = response.data
                    for i in range(0, len(audio_data), OUTPUT_BLOCK_SIZE):
                        self._audio_in_queue.put_nowait(
                            audio_data[i: i + OUTPUT_BLOCK_SIZE]
                        )

                    # Dispatch to on_audio_chunk for UI visualisation
                    if self.on_audio_chunk:
                        try:
                            arr = np.frombuffer(audio_data, dtype=np.int16)
                            self.on_audio_chunk(arr, RECEIVE_SAMPLE_RATE)
                        except Exception:
                            pass

                # ── Server content (transcripts, turn events) ─────────
                if response.server_content:
                    sc = response.server_content

                    # Output transcription — what Gemini said
                    if sc.output_transcription and sc.output_transcription.text:
                        txt = sc.output_transcription.text.strip()
                        if txt and (not out_buf or txt != out_buf[-1]):
                            out_buf.append(txt)

                    # Input transcription — what the user said
                    if sc.input_transcription and sc.input_transcription.text:
                        txt = sc.input_transcription.text.strip()
                        if txt and self.on_final_transcript:
                            self.on_final_transcript(txt)

                    # Turn complete — Gemini finished speaking
                    if sc.turn_complete:
                        if self._turn_done_event:
                            self._turn_done_event.set()

                        full_out = " ".join(out_buf).strip()
                        if full_out:
                            print(f"[GeminiAgent] BARQ: {full_out}")
                            if self.on_agent_text:
                                self.on_agent_text(full_out)
                            if self.on_final_transcript:
                                self.on_final_transcript(full_out)
                        out_buf = []

                # ── Tool calls — execute via function_executor ───────
                if response.tool_call:
                    fn_responses = []
                    for fc in response.tool_call.function_calls:
                        fn_name = fc.name
                        fn_args = dict(fc.args) if fc.args else {}
                        print(f"[GeminiAgent] [tool] {fn_name}({fn_args})")

                        try:
                            result = await execute_function(fn_name, fn_args)
                            # Pass the result dict directly — Gemini parses it
                            # as structured JSON-like data for its next turn.
                            # Truncate very long string fields to avoid blowing
                            # the session context window.
                            if isinstance(result, dict):
                                for k, v in result.items():
                                    if isinstance(v, str) and len(v) > 2000:
                                        result[k] = v[:2000] + "... [truncated]"
                            fn_responses.append(types.FunctionResponse(
                                id=fc.id,
                                name=fn_name,
                                response={"result": result},
                            ))
                            print(f"[GeminiAgent] [out] {fn_name} -> {str(result)[:100]}")
                        except Exception as e:
                            print(f"[GeminiAgent] [XX] Tool '{fn_name}' failed: {e}")
                            fn_responses.append(types.FunctionResponse(
                                id=fc.id,
                                name=fn_name,
                                response={"error": str(e)},
                            ))

                    if fn_responses and self._session:
                        await self._session.send_tool_response(
                            function_responses=fn_responses
                        )

        except Exception as e:
            print(f"[GeminiAgent] [XX] Receive error: {e}")

    def _set_speaking(self, value: bool):
        with self._speaking_lock:
            changed = self._is_speaking != value
            self._is_speaking = value

        if changed:
            if value and self.on_agent_speaking:
                self.on_agent_speaking()
            elif not value and self.on_agent_done_speaking:
                self.on_agent_done_speaking()


# ── Windows asyncio AssertionError suppressor ──────────────────────────
# Duplicated from pipecat_agent.py so GeminiVoiceAgent has its own guard.
# Python 3.13+'s Proactor event loop on Windows may fire a spurious
# AssertionError from _ProactorBaseWritePipeTransport._loop_writing()
# when a pipe write completes after the transport has been closed.
# This corrupts the event loop and causes "Cannot enter into task"
# cascades.  The fix: monkey-patch the method to suppress the error.
#
# We use a separate copy here (not shared) so each agent module
# is self-contained and importing either agent alone still installs
# the guard.

_ORIG_LOOP_WRITING = None


def _install_gemini_assertion_guard():
    global _ORIG_LOOP_WRITING
    try:
        import asyncio.proactor_events as _pe

        cls = _pe._ProactorBaseWritePipeTransport
        if _ORIG_LOOP_WRITING is None:
            _ORIG_LOOP_WRITING = cls._loop_writing

            def _safe_loop_writing(self, f=None, **kwargs):
                try:
                    _ORIG_LOOP_WRITING(self, f, **kwargs)
                except AssertionError:
                    pass

            cls._loop_writing = _safe_loop_writing
    except Exception:
        pass
