# BARQ Evolution Roadmap

> Status: **Planned** — nothing in this doc is built yet.
> Hardware constraints: local laptop **RTX 3070 (8GB VRAM)**, Oracle VM **4 OCPU / 24GB RAM (CPU-only)**.
> Last updated: 2026-08-07

## Ground truth — what exists today

| Domain | What exists | Gap |
|---|---|---|
| **Web automation** | `python/system_control/browser_control.py` — full Playwright sessions (real browser profiles, navigate/search/click/type/scroll/screenshot, multi-tab, `fill_form`), routed via `POST /system/browser/action` | **No agentic multi-step tasks** — single commands only; **no `browser_action` skill registered** in the SkillRegistry, so the planner can't plan browser goals |
| **Agent stack** | `python/agent/` — `AgentPlanner` (LLM plan generation), `AgentExecutor` (retry/replan/checkpoint/error-recovery), `SkillRegistry` (plugin skills), `AgentTaskQueue` (priority background queue), `checkpoint_store` (resume across restarts) | Complete — the machinery is all there |
| **Voice** | Deepgram + Gemini Live agents, local Pipecat fallback, Kokoro/Edge-TTS, wake word (Vosk), persistent vision stream exposed to voice agent, commands persisted to `agent_chat_history` | Solid — no work needed |
| **Vision** | `python/agent/vision.py` + routes — Gemini screen/camera analysis, streaming, persistent session the voice agent queries mid-conversation | Done — foundation Phase 3 builds on |
| **Video/media** | `python/social/video.py` — MoviePy **text-slideshow** assembly (hook/section text on black bg); `python/social/poster.py` | No footage, no captions, no AI visuals, no images |
| **Jobs** | Scanner with JobSpy board adapters (LinkedIn/Indeed/Glassdoor/ZipRecruiter/Google), LLM evaluation (Ollama qwen2.5:7b on VM), 3-tier dedup, Telegram notifications, "genuinely new" gating | Auto-apply (form fill + submit) not built |
| **Knowledge graph** | Multi-brain (gemini_chats, ai_chats, general…), LLM relationship extraction, node details panel, remove-entity, re-import scheduler + "Re-import now" | Done |

## Guiding principles

1. **Reuse before build.** The agent stack and Playwright session management already exist — most phases are *wiring*, not *new frameworks*.
2. **The VM stays untouched by phases 1–3.** Jobs/Ollama/social/DB live on the CPU-only VM. Anything GPU-heavy runs on the local laptop (RTX 3070 8GB).
3. **One GPU model resident at a time.** ComfyUI runs with `--lowvram`; heavy renders go through `AgentTaskQueue` → Telegram "done" notification, never blocking the UI.
4. **No-cost rule.** Free tiers / local models only. No paid APIs.

---

## Phase 1 — High Impact / Low Friction

Reuses existing infrastructure. Near-zero memory impact (nothing heavy loads locally).

### 1a. Agentic browser task mode ⭐ (anchor — smallest, highest value)

**Key insight:** the planner can't use the browser today because no `browser_action` skill is registered. Registering one + adding an observation action unlocks multi-step browser goals end-to-end.

- **Files:** `python/agent/skill_registry.py`, `python/system_control/browser_control.py`, `python/system_control/routes.py`
- Register `browser_action` skill (route `/system/browser/action`, params: action/url/query/selector/text/…) and `browser_observe` skill (screenshot + visible text for self-verification).
- Add `observe()` to `BrowserSession` (screenshot → short text summary) + `POST /system/browser/observe`.
- Result: "open LinkedIn and search for senior Python jobs" becomes a planned, executed, verified, checkpointed multi-step task with the existing retry/replan machinery.
- **Frontend:** "Browser Task" input on the Workflows page (goal → queue → live step progress via existing SSE/WS).

### 1b. Video v2 — stock footage + captions

- **Files:** `python/social/video.py`, `python/social/routes.py`, renderer Content Studio
- Replace text-slides with **Pexels/Pixabay stock footage (free API)** matched to script topics, burned-in **captions**, and existing TTS voiceovers. Keep MoviePy as assembler.
- Optional AI-visuals mode lands later in 3c.

### 1c. Auto-apply v1 (safe mode)

- **Files:** `python/jobs/applier.py`, system_control
- Form-fill on approved boards using the user's real logged-in Playwright profile; **human-confirm before submit**; whitelist-gated (reuse `command_whitelist` patterns). Telegram notification per outcome.

### 1d. Post images (API)

- **Files:** `python/social/poster.py`, renderer
- Gemini image generation via API for social drafts (cheap, no local VRAM). Phase 3b later replaces this with local ComfyUI when preferred.

---

## Phase 2 — Core Capability Expansion

1. **Hard-site automation** — integrate `browser-use` (or a custom agent loop) for anti-bot sites (Indeed/Glassdoor CAPTCHAs, LinkedIn rate limits).
2. **Full auto-apply** — resume parsing → per-company cover-letter tailoring → submit + track; Telegram notifications per outcome.
3. **Desktop control** — OS-level hooks (mouse/keyboard) for *non-browser* apps, complementing Playwright.
4. **Cloud media generation** — real image gen + short-form clip assembly for the social pipeline (TikTok/Reels formats).

---

## Phase 3 — Heavy Multimodal (RTX 3070 8GB edition)

> **HeyGem.ai avatar: SKIPPED** (2026-08-07) — 30–70GB Docker stack, slow renders, marginal quality benefit on 8GB. Revisit only if a dedicated GPU box appears.

### 3a. ComfyUI as a service

- Run ComfyUI with `--lowvram` (port 8188) as a background service on the laptop.
- Register an **`image_generate` skill** (ComfyUI API wrapper → `POST /comfy/generate`) so the agent and voice can generate images on demand.
- Default model: **FLUX.2 klein 4B GGUF** (~2.6GB, seconds); fallback **SDXL FP8** (15–30s/1024²).

### 3b. Image pipeline integration

- Social **poster.py** + Content Studio: "Generate image" → ComfyUI → draft preview → publish.
- Knowledge graph node avatars (polish).

### 3c. AI video segments

- Social video pipeline gets an **"AI visuals" mode**: AnimateDiff (20–40s / 16–24 frames) or LTX-Video for b-roll and transitions instead of stock footage. MoviePy stays the assembler.
- Wan 2.1 GGUF + temporal tiling is possible (10–15 min / 3–5s clip) but slow — batch/offline only.

### VRAM orchestration rules (all of Phase 3)

1. ComfyUI `--lowvram`; system RAM is the real bottleneck — close heavy apps during video renders.
2. Never run two heavy models simultaneously.
3. All heavy renders → `AgentTaskQueue` → Telegram "done" — never block the UI.
4. VM (jobs/Ollama/social/DB) is untouched — Phase 3 is laptop-side only.

---

## Suggested execution order

1. **Phase 1a** (browser skill) — half day, unlocks agentic web use
2. **Phase 1b** (Video v2) — most visible win
3. **Phase 1c/d** (safe auto-apply, post images)
4. **Phase 3a+3b** (ComfyUI service + image pipeline) — needs local ComfyUI install first
5. **Phase 3c** (AI video segments)
6. **Phase 2** (hard sites, full auto-apply, desktop control)

## Decisions log

| Date | Decision |
|---|---|
| 2026-08-07 | Phase 1 locked first; local GPU = RTX 3070 8GB |
| 2026-08-07 | HeyGem.ai skipped (8GB VRAM cost/benefit) |
| 2026-08-07 | No-cost rule: free/local models only |
