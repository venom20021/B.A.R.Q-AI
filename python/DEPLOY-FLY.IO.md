# Deploy BARQ Python Backend to Fly.io

This guide walks through deploying the **BARQ Python backend** (FastAPI sidecar) to Fly.io's free tier, while keeping the **Electron frontend** running locally on your machine.

## Architecture

```
┌──────────────────────┐       ┌──────────────────────┐
│   Your Machine       │       │   Fly.io (free VM)   │
│                      │       │                      │
│  ┌──────────────┐    │       │  ┌──────────────┐    │
│  │ Electron App │────┼───────┼─>│  FastAPI      │    │
│  │ (React/TS)   │    │  API  │  │  Sidecar      │    │
│  └──────────────┘    │       │  │              │    │
│                      │       │  │ - Jobs API   │    │
│  ┌──────────────┐    │       │  │ - Social API │    │
│  │ Voice (local)│    │       │  │ - Analytics  │    │
│  │ STT / TTS    │    │       │  │ - Playwright │    │
│  └──────────────┘    │       │  │ - Scheduler  │    │
│                      │       │  └──────┬───────┘    │
│  ┌──────────────┐    │       │         │            │
│  │ Ollama (local)│    │       │  ┌──────▼───────┐    │
│  │ LLM          │    │       │  │  Turso Cloud  │    │
│  └──────────────┘    │       │  │  Database     │    │
│                      │       │  └──────────────┘    │
└──────────────────────┘       └──────────────────────┘
```

- **Voice & Ollama stay local** — low-latency, no audio over the network
- **API & DB go to the cloud** — job scanning, social media, auto-apply run 24/7
- **Turso DB is already cloud-based** — both local and Fly.io share the same data

## Prerequisites

1. [Fly.io account](https://fly.io/signup) — no credit card required
2. [flyctl CLI](https://fly.io/docs/flyctl/install/) — `curl -fsSL https://fly.io/install.sh | sh`
3. [Docker Desktop](https://docs.docker.com/get-docker/) — for building the container
4. Your Turso database credentials from `.env` (already configured)
5. Your OpenAI API key (set in .env or get one from [OpenAI](https://platform.openai.com/api-keys))

## Step 1: Set Up Your Fly.io Environment

```bash
# Log in (opens browser)
flyctl auth login

# Copy the secrets template and fill in your API keys
cp .env.production .env.production.local
# Edit .env.production.local with your real keys
```

**Required secrets to set (fill these in `.env.production.local`):**

| Secret | Where to get it |
|---|---|
| `TURSO_DATABASE_URL` | Already in your `.env` |
| `TURSO_AUTH_TOKEN` | Already in your `.env` |
| `OPENAI_API_KEY` | [OpenAI API Keys](https://platform.openai.com/api-keys) |

Everything else is optional — the backend will work without Telegram, email, etc.

## Step 2: Deploy with the Helper Script

```bash
# Option A: Full pipeline (setup → secrets → deploy)
bash scripts/deploy-fly.sh --all

# Option B: Step by step
# 1. Create the Fly.io app
bash scripts/deploy-fly.sh --setup

# 2. Set your secrets
bash scripts/deploy-fly.sh --secrets

# 3. Deploy
bash scripts/deploy-fly.sh --deploy
```

The deployment takes 3–5 minutes on first run (Docker build + upload).

## Step 3: Verify the Deployment

```bash
# Check status
flyctl status --app barq-sidecar

# Test health endpoint
curl https://barq-sidecar.fly.dev/health

# Expected response:
# {"status":"ok","service":"barq-sidecar","version":"2.0.0",...}

# Test data from Turso
curl https://barq-sidecar.fly.dev/jobs/status

# Expected response:
# {"total_jobs_scanned": 849, ...}
```

## Step 4: Point Your Local Electron App to the Cloud API

The Electron frontend needs to connect to the Fly.io URL instead of `http://127.0.0.1:8956`.

### Option A: Update the hardcoded URLs (quickest)

The backend URL is hardcoded in several frontend files. Update these to point to your Fly.io app:

**1. Chat streaming** — `src/renderer/src/hooks/useStreamingChat.ts`
```diff
- const baseUrl = 'http://127.0.0.1:8970'
+ const baseUrl = 'https://barq-sidecar.fly.dev'
```

**2. Jobs & scanning** — `src/renderer/src/pages/JobsPage.tsx`
```diff
- const BACKEND_URL = 'http://127.0.0.1:8970'
+ const BACKEND_URL = 'https://barq-sidecar.fly.dev'
```
(Replace on both lines 332 and 1718)

**3. Voice WebSocket** — `src/renderer/src/contexts/VoiceContext.tsx`
```diff
- const WS_URL = 'ws://127.0.0.1:8970/voice/ws/status'
+ const WS_URL = 'wss://barq-sidecar.fly.dev/voice/ws/status'
```
(**Note:** WebSocket URL changes from `ws://` to `wss://` for secure connection)

### Option B: Set environment variable

```bash
# Set this before starting the Electron app (if the codebase respects it)
export BARQ_API_URL=https://barq-sidecar.fly.dev
```

### After connecting:

Start the Electron app as usual:
```bash
npm run dev
```

Voice controls and Ollama stay local. All API calls (jobs, social, analytics) go to the Fly.io server.

## Updating

```bash
# After making changes to the Python backend:
cd python
bash scripts/deploy-fly.sh --deploy

# Or manually:
flyctl deploy --dockerfile Dockerfile
```

## Monitoring

```bash
# View logs
flyctl logs --app barq-sidecar

# SSH into the VM
flyctl ssh console --app barq-sidecar

# View metrics (CPU, memory, network)
flyctl metrics --app barq-sidecar

# Check free tier usage
flyctl billing dashboard
```

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `Connection refused` | App not deployed yet | Wait 2 min, check `flyctl status` |
| `401 Unauthorized` | Missing/invalid API key | Check `BARQ_API_KEY` secret |
| `Database errors` | Wrong Turso credentials | Verify `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` |
| `App runs out of memory` | 256MB too small | Upgrade to paid plan or reduce memory usage |
| `Playwright fails` | Missing browser deps | Check Dockerfile installs Chromium |
| Free tier exhausted | Over 3GB egress/month | Check usage in Fly.io dashboard |

## Free Tier Limits

| Resource | Fly.io Free Tier |
|---|---|
| **VMs** | 3 shared VMs (256MB each) |
| **Storage** | 3GB total |
| **Bandwidth** | 3GB/month egress |
| **SSL certs** | Auto-provisioned |
| **Custom domains** | Yes |
| **Credit card** | Not required |
