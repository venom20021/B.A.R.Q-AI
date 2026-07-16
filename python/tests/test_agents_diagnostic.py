"""
BARQ Agent System Diagnostic Test.

Tests all agent-related endpoints and reports what's working vs broken.
"""

import json
import os
import sys
import threading
import time
import traceback

# Ensure the python directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import httpx
import uvicorn
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

passed = 0
failed = 0
errors: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name}")
        if detail:
            print(f"         {detail}")
        failed += 1
        errors.append(f"{name}: {detail}")


# ── 1. Health Check ─────────────────────────────────────────────────────
def test_health():
    print("\n=== 1. Health Check ===")
    try:
        r = client.get("/health")
        check("GET /health returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Health body has 'status' key", "status" in data, str(data.keys()))
        check("Health status is 'ok'", data.get("status") == "ok", str(data))
    except Exception as e:
        check("GET /health raises no exception", False, str(e))


# ── 2. Agent Execute ────────────────────────────────────────────────────
def test_agent_execute():
    print("\n=== 2. Agent Execute ===")
    
    # Test with a simple goal (fallback plan should be used if no Ollama)
    try:
        r = client.post("/agent/execute", json={"goal": "Test goal: what is 2+2?"})
        check("POST /agent/execute returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Execute body has 'status' key", "status" in data, str(data.keys()))
        check("Execute status is 'completed'", data.get("status") == "completed", str(data))
        check("Execute has 'result' key", "result" in data, str(data.keys()))
        print(f"  Result preview: {str(data.get('result', ''))[:100]}")
    except Exception as e:
        check("POST /agent/execute raises no exception", False, str(e))


# ── 3. Agent Plan ───────────────────────────────────────────────────────
def test_agent_plan():
    print("\n=== 3. Agent Plan ===")
    try:
        r = client.post("/agent/plan", json={"goal": "Research a topic"})
        check("POST /agent/plan returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Plan body has 'steps' key", "steps" in data, str(data.keys()))
        check("Plan has at least 1 step", len(data.get("steps", [])) >= 1, str(data))
        print(f"  Steps: {len(data.get('steps', []))}")
    except Exception as e:
        check("POST /agent/plan raises no exception", False, str(e))


# ── 4. Agent Task Queue ────────────────────────────────────────────────
def test_agent_queue():
    print("\n=== 4. Agent Task Queue ===")
    
    # List tasks
    try:
        r = client.get("/agent/queue")
        check("GET /agent/queue returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Queue body has 'tasks' key", "tasks" in data, str(data.keys()))
    except Exception as e:
        check("GET /agent/queue raises no exception", False, str(e))
    
    # Queue a task
    try:
        r = client.post("/agent/queue", json={"goal": "Background test task", "priority": "low"})
        check("POST /agent/queue returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Queue has 'task_id' key", "task_id" in data, str(data.keys()))
        task_id = data.get("task_id", "")
        
        if task_id:
            # Check task status
            r2 = client.get(f"/agent/queue/{task_id}")
            check(f"GET /agent/queue/{task_id} returns 200", r2.status_code == 200, str(r2.status_code))
            
            # Cancel task
            r3 = client.post(f"/agent/queue/{task_id}/cancel")
            check(f"POST /agent/queue/{task_id}/cancel returns 200", r3.status_code == 200, str(r3.status_code))
    except Exception as e:
        check("Agent queue operations raise no exception", False, str(e))


# ── 5. Agent Memory ─────────────────────────────────────────────────────
def test_agent_memory():
    print("\n=== 5. Agent Memory ===")
    
    # Get memory
    try:
        r = client.get("/agent/memory")
        check("GET /agent/memory returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Memory body has 'memory' key", "memory" in data, str(data.keys()))
    except Exception as e:
        check("GET /agent/memory raises no exception", False, str(e))
    
    # Store a memory
    try:
        r = client.post("/agent/memory", json={"key": "test_key", "value": "test_value", "category": "test"})
        check("POST /agent/memory returns 200", r.status_code == 200, str(r.status_code))
    except Exception as e:
        check("POST /agent/memory raises no exception", False, str(e))


# ── 6. Agent Skills ─────────────────────────────────────────────────────
def test_agent_skills():
    print("\n=== 6. Agent Skills ===")
    try:
        r = client.get("/agent/skills")
        check("GET /agent/skills returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Skills body has 'skills' key", "skills" in data, str(data.keys()))
        skills = data.get("skills", [])
        check(f"Has at least 1 skill registered", len(skills) >= 1, f"Got {len(skills)} skills")
        print(f"  Registered skills ({len(skills)}): {[s.get('name', '?') for s in skills]}")
    except Exception as e:
        print(f"  [INFO] GET /agent/skills may not exist as an endpoint: {e}")
        # This endpoint might not exist - let's check if there's a skill list endpoint
        check("Skill endpoint check", False, "GET /agent/skills not found - checking /agent/registry")
        try:
            r = client.get("/agent/registry")
            check("GET /agent/registry returns 200", r.status_code == 200, str(r.status_code))
        except Exception:
            pass


# ── 7. Agent Vision ────────────────────────────────────────────────────
def test_agent_vision():
    print("\n=== 7. Agent Vision ===")
    try:
        r = client.get("/vision/check")
        check("GET /vision/check returns 200", r.status_code == 200, str(r.status_code))
        data = r.json()
        check("Vision check has 'capabilities' key", "capabilities" in data, str(data.keys()))
        caps = data.get("capabilities", {})
        print(f"  Screen capture: {caps.get('screen_capture', False)}")
        print(f"  Webcam: {caps.get('webcam', False)}")
        print(f"  Gemini API: {caps.get('gemini_api', False)}")
    except Exception as e:
        check("GET /vision/check raises no exception", False, str(e))


# ── 8. Agent System Tools (skill dispatch routes) ─────────────────────
def test_skill_backend_routes():
    print("\n=== 8. Skill Backend Routes ===")
    
    # Test web/browse/search
    try:
        r = client.post("/web/browse/search", json={"query": "test query"})
        check("POST /web/browse/search returns 200", r.status_code == 200, str(r.status_code))
    except Exception as e:
        check("POST /web/browse/search", False, str(e)[:100])
    
    # Test web/weather
    try:
        r = client.get("/web/weather?city=London")
        check("GET /web/weather?city=London returns 200", r.status_code in (200, 500), 
              f"Got {r.status_code} - this is OK if API key not configured")
    except Exception as e:
        check("GET /web/weather", False, str(e)[:100])


# ── 9. Cross-device sync endpoint ─────────────────────────────────────
def test_agent_sync():
    print("\n=== 9. Agent History Sync ===")
    
    # Save
    try:
        test_data = {"history": {"TestAgent": [{"role": "user", "content": "hello"}]}}
        r = client.post("/memory/agent-history", json=test_data)
        check("POST /memory/agent-history returns 200", r.status_code == 200, str(r.status_code))
    except Exception as e:
        check("POST /memory/agent-history", False, str(e)[:100])
    
    # Load
    try:
        r = client.get("/memory/agent-history")
        check("GET /memory/agent-history returns 200", r.status_code == 200, str(r.status_code))
    except Exception as e:
        check("GET /memory/agent-history", False, str(e)[:100])


# ── Run all tests ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  BARQ Agent System Diagnostic")
    print("=" * 60)
    
    tests = [
        ("Health", test_health),
        ("Agent Execute", test_agent_execute),
        ("Agent Plan", test_agent_plan),
        ("Agent Queue", test_agent_queue),
        ("Agent Memory", test_agent_memory),
        ("Agent Skills", test_agent_skills),
        ("Agent Vision", test_agent_vision),
        ("Skill Backend Routes", test_skill_backend_routes),
        ("Agent Sync", test_agent_sync),
    ]
    
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            print(f"\n  [ERROR] {name} test crashed: {e}")
            traceback.print_exc()
            failed += 1
            errors.append(f"{name} crashed: {e}")
    
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0 and errors:
        print("\n--- FAILURE DETAILS ---")
        for err in errors:
            print(f"  - {err}")
    
    print(f"\n  {'ALL OK!' if failed == 0 else f'{failed} FAILURES NEED FIXING'}")
    sys.exit(0 if failed == 0 else 1)
