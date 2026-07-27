# BARQ — Agentic OS Improvements Reference

> Based on research of AIOS (agiresearch/AIOS), Agentic-OS (modimihir07),
> and Agentic-OS (itseffi). Generated: July 2026.

---

## 1. Agent Kernel / Scheduler (🔴 HIGH)

**What AIOS does:** Central Agent Kernel mediates ALL agent↔resource access.
Manages lifecycle, coordinates shared LLM engine, memory, and tools.
Prevents any single agent from monopolizing resources.

**BARQ currently:**
- Agents talk directly to tools via `SkillRegistry.call()` → HTTP dispatch
- `AgentPlanner`, `AgentExecutor`, `AgentTaskQueue` all create their own OllamaClient
- **No central mediation**, no request queuing, no resource isolation

**Implementation status:** ❌ Not implemented

**Files to create/modify:**
- `python/agent/agent_kernel.py` — NEW: Central kernel class
- `python/agent/agent_executor.py` — MODIFY: Route through kernel
- `python/agent/agent_planner.py` — MODIFY: Route through kernel

---

## 2. Unified Memory Bus (🔴 HIGH)

**What others do:** Hierarchical memory with short-term (session) ↔ long-term
(storage), shared across agents. AIOS uses kernel-managed memory.
Agentic-OS uses SQLite FTS5 for full-text searchable memory.

**BARQ currently:**
- `python/memory/agent_memory_manager.py` — Agent memory with categories
  (identity, preferences, projects, relationships, wishes, notes)
- `python/memory/long_term.json` — JSON blob, no search
- `python/memory_knowledge/` — Knowledge graph, graph brain, multi-brain
- `python/memory_knowledge/ingestion.py` — Knowledge ingestion pipeline
- Frontend: `agentHistory` in localStorage (per-agent chat history)
- **Scattered across 3+ systems, no unified query interface**

**Implementation status:** ⚠️ Partial (multiple systems exist but fragmented)

**Files to create/modify:**
- `python/memory/memory_bus.py` — NEW: Unified query interface
- `python/memory/` — CONSOLIDATE existing systems
- `python/database/schema.py` — ADD: FTS5 virtual table for full-text search

---

## 3. Skill Performance Analytics (🔴 HIGH)

**What Agentic-OS does:** Skills Hub with eval scoring, learnings,
and score history. Tracks how well each skill performed over time.
Users can see success rates and optimize.

**BARQ currently:**
- `SkillRegistry.call()` executes skills but tracks nothing
- No success/failure rates, no timing metrics
- No way to identify which tools are effective

**Implementation status:** ❌ Not implemented

**Files to create/modify:**
- `python/agent/skill_registry.py` — MODIFY: Add execution metrics
- `python/database/schema.py` — ADD: skill_metrics table
- `src/renderer/src/` — ADD: Skill performance dashboard widget

---

## 4. Agent Checkpointing (🟡 MEDIUM)

**What AIOS does:** Separates agent "logic" (SDK layer) from "status"
(Kernel layer). Enables checkpointing — agents resume after restarts
or across devices.

**BARQ currently:**
- No checkpointing at all
- Agent state (completed steps, step results, current plan) is in-memory only
- On BARQ restart, any running agent task is lost

**Implementation status:** ❌ Not implemented

**Files to create/modify:**
- `python/agent/agent_executor.py` — MODIFY: Persist plan + completed steps
- `python/database/schema.py` — ADD: agent_checkpoints table
- `python/main.py` — MODIFY: Restore checkpoints on startup

---

## 5. Cron / Scheduled Agent Tasks (🟡 MEDIUM)

**What Agentic-OS does:** Cron Scheduler (APScheduler) for automated
workflows — daily standups, weekly memory consolidation, periodic audits.

**BARQ currently:**
- ✅ **APScheduler IS implemented** in `python/main.py`:
  - `start_scheduler()` creates `AsyncIOScheduler` with 3 jobs:
    1. Job scanning (configurable interval)
    2. Memory consolidation
    3. Auto-extraction
  - `python/database/schema.py` has `scheduled_tasks` table with cron expressions
  - `python/jobs/auto_applier/pipeline/` has pipeline scheduler
- **But:** No user-facing scheduling UI, no agent task scheduler
  (only job-related scheduling)

**Implementation status:** ✅ Partial (backend scheduler exists, needs agent task support)

**Files to modify:**
- `python/main.py` — ADD: Agent task cron jobs
- `src/renderer/src/` — ADD: Schedule management UI

---

## 6. Inter-Agent Communication (🟡 MEDIUM)

**What AIOS does:** Message broker / service bus through kernel. Agents
discover each other, share context, delegate tasks via the kernel.

**BARQ currently:**
- No inter-agent communication at all
- No message bus, no service discovery
- Each agent workspace runs independently

**Implementation status:** ❌ Not implemented

**Files to create:**
- `python/agent/message_bus.py` — NEW: asyncio.Queue-based message broker
- `python/agent/agent_kernel.py` — INTEGRATE: Message routing

---

## 7. Agent Sandboxing (🟢 LOW)

**What AIOS does:** Kernel-enforced resource isolation. Prevents agents
from interfering with each other or the system.

**BARQ currently:**
- ✅ `python/system_control/command_whitelist.py` — Tiered classification:
  - `SAFE` — allowed without approval
  - `WARN` — requires approval
  - `DANGEROUS` — blocked
- ✅ `python/system_control/routes.py` — API to get/set whitelist rules
- ✅ Rule persistence via DB (`settings_dao`)
- ✅ `python/tests/test_command_whitelist.py` — 150+ test cases
- ✅ Voice whitelist approval flow in `python/voice/routes.py`
- **But:** Only applies to terminal commands, not to ALL tool calls

**Implementation status:** ✅ Good foundation, needs expansion to cover all skills

**Files to modify:**
- `python/agent/skill_registry.py` — MODIFY: Add permission levels per skill
- `python/system_control/command_whitelist.py` — EXTEND: Generic permission model

---

## 8. Self-Evolution / Learning (🟢 LOW)

**What Agentic-OS does:** Layer 6 "Self-Evolution" — mechanisms for agent
improvement over time based on past execution data.

**BARQ currently:**
- `python/agent/error_handler.py` — Error analysis per step, but no cross-session learning
- `python/agent/agent_executor.py` — Retry/skip/replan/abort per execution
- **No cross-session learning** — doesn't improve planning based on past failures

**Implementation status:** ❌ Not implemented

**Files to create:**
- `python/agent/learning_engine.py` — NEW: Analyze past executions, improve planning
- `python/database/schema.py` — ADD: execution_history table

---

## 9. Skill Marketplace / Plugin Registry (🟢 LOW)

**What Agentic-OS does:** Plugin Registry with 16+ pre-defined skills.
Extensible via custom skills. Users browse, install, manage plugins.

**BARQ currently:**
- ✅ `python/agent/skill_registry.py` — `discover()` scans for `*.skill.json` files
- ✅ File-based skill descriptors with HTTP dispatch
- ✅ `create_skill_from_handler()` — Register Python handler as a skill
- ✅ 15 built-in skills across 6 categories
- **But:** No UI for browsing/installing plugins, no marketplace

**Implementation status:** ✅ Good backend, no frontend

**Files to modify:**
- `src/renderer/src/` — ADD: Skill browser/manager UI
- `python/agent/skill_registry.py` — ADD: Skill marketplace API

---

## Quick Wins Summary

| # | Improvement | Priority | Backend | Frontend | Current Status |
|---|---|---|---|---|---|
| 1 | Agent Kernel / Scheduler | 🔴 HIGH | ~3 days | — | ❌ Missing |
| 2 | Unified Memory Bus | 🔴 HIGH | ~2 days | ~1 day | ⚠️ Partial (fragmented) |
| 3 | Skill Performance Analytics | 🔴 HIGH | ~4 hours | ~4 hours | ❌ Missing |
| 4 | Agent Checkpointing | 🟡 MEDIUM | ~1 day | — | ❌ Missing |
| 5 | Cron / Scheduled Tasks | 🟡 MEDIUM | ~4 hours | ~1 day | ✅ Good backend |
| 6 | Inter-Agent Communication | 🟡 MEDIUM | ~2 days | — | ❌ Missing |
| 7 | Agent Sandboxing | 🟢 LOW | ~4 hours | — | ✅ Good foundation |
| 8 | Self-Evolution / Learning | 🟢 LOW | ~2 days | — | ❌ Missing |
| 9 | Skill Marketplace / UI | 🟢 LOW | ~1 day | ~2 days | ✅ Good backend |

## Architecture Scorecard

| Component | BARQ | AIOS | Agentic-OS (modi) | Agentic-OS (itseffi) |
|---|---|---|---|---|
| Skill/Tool Registry | ✅ 15 skills | ✅ Kernel-managed | ✅ 16+ skills | ❌ Wraps external |
| Planner | ✅ LLM-based | ✅ Kernel-level | ❌ Static routing | ✅ Workflow chaining |
| Executor | ✅ Retry/skip/replan | ✅ Scheduler-driven | ❌ Basic | ✅ Pipeline |
| Error Handling | ✅ 4 strategies | ✅ Kernel recovery | ❌ Manual | ❌ Per-tool |
| Task Queue | ✅ Priority queue | ✅ Process scheduler | ✅ Cron-based | ❌ Sequential |
| Memory | ⚠️ Fragmented | ✅ Hierarchical | ✅ SQLite FTS5 | ❌ None |
| Sandboxing | ⚠️ Commands only | ✅ Full isolation | ❌ Local-hosted | ❌ None |
| Inter-agent Comm | ❌ Missing | ✅ Message bus | ✅ Shared memory | ✅ Chaining |
| Checkpointing | ❌ Missing | ✅ Kernel-managed | ❌ Not found | ❌ Not found |
| Cron/Scheduler | ✅ APScheduler | ❌ Not found | ✅ APScheduler | ❌ Not found |
| Skill Analytics | ❌ Missing | ❌ Not found | ✅ Eval scoring | ❌ Not found |
| Self-Evolution | ❌ Missing | ❌ Not found | ✅ Layer 6 | ❌ Not found |
| Plugin System | ✅ File-based | ❌ Not found | ✅ Registry | ✅ Marketplaces |
