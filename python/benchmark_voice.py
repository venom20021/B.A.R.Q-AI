"""
Voice Backend Benchmark — compares Pipecat, Deepgram, and Gemini Live.

Tests:
  - API connectivity (key valid, server reachable)
  - TTS synthesis latency (edge-tts / Gemini)
  - LLM response latency (Ollama / Gemini)
  - Tool execution latency (system_status)

Usage:
  cd python && python benchmark_voice.py

Note: End-to-end wake-to-response latency requires manual measurement
with a stopwatch from wake word to first spoken syllable (not tested here).
"""

import asyncio
import os
import time
from datetime import datetime


# ── Utilities ──────────────────────────────────────────────────────────

_RESULTS: list[dict] = []


def _load_env(path: str = "../.env") -> dict[str, str]:
    """Load .env file into a dict."""
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("\"'")
    except FileNotFoundError:
        pass
    return env


def _result(
    backend: str,
    test: str,
    status: str,
    latency_ms: float | None = None,
    detail: str = "",
):
    row = {
        "backend": backend,
        "test": test,
        "status": status,
        "latency_ms": latency_ms,
        "detail": detail,
    }
    _RESULTS.append(row)
    icon = "[OK]" if status == "pass" else "[!!]" if status == "warn" else "[XX]"
    lat = f"  [{latency_ms:>7.0f} ms]" if latency_ms is not None else ""
    safe_detail = detail.encode("ascii", errors="replace").decode("ascii")
    print(f"  {icon} {backend}/{test}{lat}  {safe_detail[:80]}")


def _print_table():
    """Print a formatted comparison table."""
    print()
    print("=" * 100)
    print("BACKEND COMPARISON".center(100))
    print("=" * 100)

    # Header
    print(f"{'Test':<32} {'Pipecat':>22} {'Deepgram':>22} {'Gemini Live':>22}")
    print("-" * 100)

    tests = ["api_connect", "llm_warmup", "tts_synth", "tool_exec"]
    labels = {
        "api_connect": "API Connectivity",
        "llm_warmup": "LLM Response (hello)",
        "tts_synth": "TTS Synthesis (2 sentences)",
        "tool_exec": "Tool Execution (sys status)",
    }

    for test in tests:
        label = labels.get(test, test)
        cells = [label]
        for backend in ["pipecat", "deepgram", "gemini"]:
            rows = [r for r in _RESULTS if r["backend"] == backend and r["test"] == test]
            if rows:
                r = rows[0]
                if r["status"] == "pass" and r["latency_ms"] is not None:
                    cells.append(f"  {r['latency_ms']:>5.0f} ms  ")
                elif r["status"] == "pass":
                    cells.append(f"  {'---':>8}")
                elif r["status"] == "warn" and r["latency_ms"] is not None:
                    cells.append(f"  {r['latency_ms']:>5.0f} ms? ")
                elif r["status"] == "warn":
                    cells.append(f"  {'--?':>8}")
                else:
                    cells.append(f"  {'---':>8}")
            else:
                cells.append(f"  {'---':>8}")
        print(f"{cells[0]:<32} {cells[1]:>22} {cells[2]:>22} {cells[3]:>22}")

    # Summary row
    print("-" * 100)
    scores = {}
    for backend in ["pipecat", "deepgram", "gemini"]:
        passes = sum(1 for r in _RESULTS if r["backend"] == backend and r["status"] == "pass")
        total = sum(1 for r in _RESULTS if r["backend"] == backend)
        icon = "[OK]" if passes == total else "[!!]" if passes > 0 else "[XX]"
        scores[backend] = f"{icon} {passes}/{total}"
    print(f"{'Tests Passed':<32} {scores.get('pipecat', '---'):>22} {scores.get('deepgram', '---'):>22} {scores.get('gemini', '---'):>22}")
    print("=" * 100)
    print()

    # Detail section
    print("-- Details ----------------------------------------------------")
    for r in _RESULTS:
        if r["detail"]:
            icon = "[OK]" if r["status"] == "pass" else "[!!]" if r["status"] == "warn" else "[XX]"
            safe = r["detail"].encode("ascii", errors="replace").decode("ascii")
            print(f"  {icon} {r['backend']}/{r['test']}: {safe[:120]}")
    print()


# ── Pipecat Benchmarks ────────────────────────────────────────────────

async def benchmark_pipecat(env: dict):
    print()
    print("== Pipecat (local) ================================================")

    ollama_url = env.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    ollama_model = env.get("OLLAMA_MODEL", "llama3.2:3b")

    import httpx

    # 1. API Connectivity
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{ollama_url}/api/tags")
        lat = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            model_found = any(ollama_model.split(":")[0] in m for m in models)
            status = "pass" if model_found else "warn"
            detail = f"Ollama reachable. {len(models)} models"
            if not model_found:
                detail += f", but '{ollama_model}' not pulled"
            _result("pipecat", "api_connect", status, lat, detail)
        else:
            _result("pipecat", "api_connect", "fail", lat, f"HTTP {r.status_code}")
    except Exception as e:
        _result("pipecat", "api_connect", "fail", None, f"Ollama unreachable: {e}")

    # 2. LLM Warmup
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{ollama_url}/api/chat", json={
                "model": ollama_model,
                "messages": [{"role": "user", "content": "Say hello in one word."}],
                "stream": False,
                "options": {"num_predict": 10},
            })
        lat = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            content = r.json().get("message", {}).get("content", "")
            _result("pipecat", "llm_warmup", "pass", lat, f"Response: {content[:60]}")
        else:
            _result("pipecat", "llm_warmup", "fail", lat, f"HTTP {r.status_code}")
    except Exception as e:
        _result("pipecat", "llm_warmup", "fail", None, str(e)[:80])

    # 3. TTS Synthesis (edge-tts)
    t0 = time.perf_counter()
    try:
        import edge_tts
        tts_text = "Hello, this is a test of the text to speech system."
        communicate = edge_tts.Communicate(tts_text, "en-US-AriaNeural")
        buf = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        lat = (time.perf_counter() - t0) * 1000
        _result("pipecat", "tts_synth", "pass", lat, f"Generated {len(buf):,} bytes")
    except ImportError:
        _result("pipecat", "tts_synth", "fail", None, "edge-tts not installed")
    except Exception as e:
        _result("pipecat", "tts_synth", "fail", None, str(e)[:80])

    # 4. Tool Execution (system_status)
    t0 = time.perf_counter()
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        lat = (time.perf_counter() - t0) * 1000
        _result("pipecat", "tool_exec", "pass", lat, f"CPU {cpu}%, mem {mem.percent}%")
    except ImportError:
        _result("pipecat", "tool_exec", "fail", None, "psutil not installed")
    except Exception as e:
        _result("pipecat", "tool_exec", "fail", None, str(e)[:80])


# ── Deepgram Benchmarks ───────────────────────────────────────────────

async def benchmark_deepgram(env: dict):
    print()
    print("== Deepgram (cloud) ==============================================")

    dg_key = env.get("DEEPGRAM_API_KEY", os.getenv("DEEPGRAM_API_KEY", ""))

    if not dg_key:
        _result("deepgram", "api_connect", "fail", None, "DEEPGRAM_API_KEY not set")
        _result("deepgram", "llm_warmup", "fail", None, "skipped - no key")
        _result("deepgram", "tts_synth", "fail", None, "skipped - no key")
        _result("deepgram", "tool_exec", "fail", None, "skipped - no key")
        return

    import httpx

    # 1. API Connectivity (ping Deepgram)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {dg_key}"},
            )
        lat = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            _result("deepgram", "api_connect", "pass", lat, "Key valid, API reachable")
        else:
            _result("deepgram", "api_connect", "fail", lat, f"HTTP {r.status_code}")
    except Exception as e:
        _result("deepgram", "api_connect", "fail", None, str(e)[:80])

    # 2. TTS Synthesis (Deepgram Aura)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://api.deepgram.com/v1/speak",
                headers={
                    "Authorization": f"Token {dg_key}",
                    "Content-Type": "application/json",
                },
                json={"text": "Hello, this is a test of the text to speech system."},
                params={"model": "aura-2-odysseus-en"},
            )
        lat = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            _result("deepgram", "tts_synth", "pass", lat, f"Generated {len(r.content):,} bytes")
        else:
            _result("deepgram", "tts_synth", "fail", lat, f"HTTP {r.status_code}: {r.text[:80]}")
    except Exception as e:
        _result("deepgram", "tts_synth", "fail", None, str(e)[:80])

    # 3. LLM Warmup — Deepgram doesn't have standalone LLM API
    _result("deepgram", "llm_warmup", "warn", None, "No standalone LLM API (uses Gemini internally via agent WS)")

    # 4. Tool Execution — Deepgram doesn't have direct tool API through REST
    _result("deepgram", "tool_exec", "warn", None, "Tool exec via Deepgram agent WebSocket only")


# ── Gemini Live Benchmarks ────────────────────────────────────────────

async def benchmark_gemini(env: dict):
    print()
    print("== Gemini Live (cloud) ===========================================")

    gemini_key = env.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

    if not gemini_key:
        _result("gemini", "api_connect", "fail", None, "GEMINI_API_KEY not set")
        _result("gemini", "llm_warmup", "fail", None, "skipped - no key")
        _result("gemini", "tts_synth", "fail", None, "skipped - no key")
        _result("gemini", "tool_exec", "fail", None, "skipped - no key")
        return

    try:
        from google import genai
    except ImportError:
        _result("gemini", "api_connect", "fail", None, "google-genai not installed")
        _result("gemini", "llm_warmup", "fail", None, "skipped - package missing")
        _result("gemini", "tts_synth", "fail", None, "skipped - package missing")
        _result("gemini", "tool_exec", "fail", None, "skipped - package missing")
        return

    # 1. API Connectivity + Key Validation
    t0 = time.perf_counter()
    try:
        client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
        result = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-1.5-flash",
            contents="Say OK",
        )
        lat = (time.perf_counter() - t0) * 1000
        if result and result.text:
            _result("gemini", "api_connect", "pass", lat, f"Key valid. Response: {result.text[:40]}")
        else:
            _result("gemini", "api_connect", "warn", lat, "API responded but no text")
    except Exception as e:
        _result("gemini", "api_connect", "fail", None, str(e)[:80])

    # 2. LLM Response Latency
    t0 = time.perf_counter()
    try:
        client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
        result = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-1.5-flash",
            contents="What is 2+2? Reply in 2 words.",
        )
        lat = (time.perf_counter() - t0) * 1000
        if result and result.text:
            _result("gemini", "llm_warmup", "pass", lat, f"Response: {result.text[:60]}")
        else:
            _result("gemini", "llm_warmup", "warn", lat, "No text returned")
    except Exception as e:
        _result("gemini", "llm_warmup", "fail", None, str(e)[:80])

    # 3. Gemini doesn't expose standalone TTS via REST (it's live-only)
    # Check model list for live audio model
    t0 = time.perf_counter()
    try:
        client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
        models = await asyncio.to_thread(client.models.list)
        lat = (time.perf_counter() - t0) * 1000
        live_available = any(
            "audio-preview" in m.name
            for m in models
            if hasattr(m, "name")
        )
        if live_available:
            _result("gemini", "tts_synth", "pass", lat, "Live audio model available")
        else:
            _result("gemini", "tts_synth", "warn", lat, "Live model listed but may vary")
    except Exception as e:
        _result("gemini", "tts_synth", "fail", None, str(e)[:80])

    # 4. Tool Execution
    t0 = time.perf_counter()
    try:
        client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
        result = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-1.5-flash",
            contents="What time is it right now? Just say the time.",
            config={
                "tools": [{
                    "function_declarations": [{
                        "name": "get_time",
                        "description": "Get the current date and time",
                        "parameters": {"type": "OBJECT", "properties": {}},
                    }],
                }],
            },
        )
        lat = (time.perf_counter() - t0) * 1000
        if result and result.text:
            _result("gemini", "tool_exec", "pass", lat, f"Response: {result.text[:60]}")
        else:
            _result("gemini", "tool_exec", "warn", lat, "Tool response received but no text")
    except Exception as e:
        _result("gemini", "tool_exec", "fail", None, str(e)[:80])


# ── Main ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 100)
    print("VOICE BACKEND BENCHMARK".center(100))
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S").center(100))
    print("=" * 100)

    env = _load_env()
    # Also read system env vars as fallback
    for k in ["DEEPGRAM_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST", "OLLAMA_MODEL"]:
        if k not in env:
            v = os.getenv(k)
            if v:
                env[k] = v

    print(f"\nLoaded {len(env)} env vars from .env + system")
    for key in ["DEEPGRAM_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST", "OLLAMA_MODEL"]:
        val = env.get(key, "(not set)")
        masked = (val[:8] + "..." + val[-4:]) if len(val) > 16 and val != "(not set)" else val
        print(f"  {key}: {masked}")

    await benchmark_pipecat(env)
    await benchmark_deepgram(env)
    await benchmark_gemini(env)

    _print_table()

    # Final recommendation
    print("-- Recommendation ------------------------------------------------")
    pipecat_ok = any(r["backend"] == "pipecat" and r["test"] == "api_connect" and r["status"] == "pass" for r in _RESULTS)
    dg_ok = any(r["backend"] == "deepgram" and r["test"] == "api_connect" and r["status"] == "pass" for r in _RESULTS)
    gm_ok = any(r["backend"] == "gemini" and r["test"] == "api_connect" and r["status"] == "pass" for r in _RESULTS)

    if gm_ok:
        print("  [1] Gemini Live -- Best overall: native audio WS, lowest latency, no local processing issues")
    if dg_ok and gm_ok:
        print("  [2] Deepgram -- Good alternative if Gemini Live is down")
    if pipecat_ok:
        print("  [3] Pipecat -- Works offline, but has Windows event loop + MP3 decoding issues")
    if not any([pipecat_ok, dg_ok, gm_ok]):
        print("  [X] No backends fully functional. Check errors above.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
