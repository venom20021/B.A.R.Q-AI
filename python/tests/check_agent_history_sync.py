"""Test agent chat history persistence (cross-device sync)."""

import os
import sys
import threading
import time

import httpx
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

HOST = "127.0.0.1"
PORT = 18970
BASE = f"http://{HOST}:{PORT}"

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {label}" + (f" - {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {label}" + (f" - {detail}" if detail else ""))


def start_server():
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="error")
    server = uvicorn.Server(config)
    server.run()


# Override settings port
import config as cfg
cfg.get_settings.cache_clear()
os.environ["SIDECAR_PORT"] = str(PORT)

# Start server in background thread
server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
time.sleep(5)

client = httpx.Client(base_url=BASE, timeout=10)

try:
    print("--- Test: Agent Chat History Sync ---")
    print()

    # Step 1: Health check
    r = client.get("/health")
    check("Backend healthy", r.status_code == 200, f"status={r.status_code}")
    if r.status_code != 200:
        print("Backend not available - aborting")
        sys.exit(1)

    # Step 2: Save agent chat history
    test_history = {
        "Strategist": [
            {"role": "user", "content": "What is the market trend?"},
            {"role": "assistant", "content": "Analyzing current market conditions..."},
        ],
        "Analytics": [
            {"role": "user", "content": "Show me last quarter metrics"},
        ],
    }
    r = client.post("/memory/agent-history", json={"history": test_history})
    check("Save agent history", r.status_code == 200)
    if r.status_code == 200:
        check("Save returns status=saved", r.json().get("status") == "saved")

    # Step 3: Reload and verify
    r = client.get("/memory/agent-history")
    check("Load agent history", r.status_code == 200)
    if r.status_code == 200:
        data = r.json()
        loaded = data.get("history", {})
        check("Strategist key present", "Strategist" in loaded)
        check("Analytics key present", "Analytics" in loaded)
        if "Strategist" in loaded:
            check("Strategist msg 1", loaded["Strategist"][0]["content"] == "What is the market trend?")
            check("Strategist msg 2", loaded["Strategist"][1]["content"] == "Analyzing current market conditions...")
        if "Analytics" in loaded:
            check("Analytics msg 1", loaded["Analytics"][0]["content"] == "Show me last quarter metrics")

    # Step 4: Save updated history (more messages)
    updated_history = dict(test_history)
    updated_history["Strategist"].append(
        {"role": "assistant", "content": "The market is showing bullish trends in tech sector."}
    )
    r = client.post("/memory/agent-history", json={"history": updated_history})
    check("Save updated history", r.status_code == 200)

    # Step 5: Reload and verify update
    r = client.get("/memory/agent-history")
    reloaded = r.json()["history"]
    strategist_msgs = reloaded.get("Strategist", [])
    check("Update persisted", len(strategist_msgs) == 3, f"got {len(strategist_msgs)} msgs")
    if len(strategist_msgs) == 3:
        check("Update content correct", strategist_msgs[2]["content"] == "The market is showing bullish trends in tech sector.")

    # Step 6: Clear history
    r = client.post("/memory/agent-history", json={"history": {}})
    check("Clear history", r.status_code == 200)

    # Step 7: Verify empty
    r = client.get("/memory/agent-history")
    empty = r.json()["history"]
    check("Empty history confirmed", empty == {}, f"got {empty}")

    print()
    print(f"--- Results: {passed} passed, {failed} failed ---")

except Exception as e:
    print(f"\n[ERROR] {e}")
    failed += 1
finally:
    client.close()
    if failed > 0:
        sys.exit(1)
    sys.exit(0)
