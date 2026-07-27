# Deploy BARQ to Oracle Cloud Free Tier

Deploy the **BARQ Python backend** to Oracle Cloud's Always Free Tier (4 ARM cores, 24 GB RAM, 200 GB disk) — the only free cloud option powerful enough to handle Playwright browser automation and background job processing.

## Why Oracle Cloud?

| Resource | Oracle Free Tier | BARQ Needs | Headroom |
|---|---|---|---|
| **CPU** | 4× Ampere A1 cores | 1-2 cores | ✅ Plenty |
| **RAM** | 24 GB | ~2-3 GB (FastAPI + Playwright) | ✅ 20 GB spare |
| **Disk** | 200 GB | ~10 GB (code + models) | ✅ Tons of space |
| **Bandwidth** | 10 TB/month | ~50 GB/month | ✅ Very generous |
| **Duration** | Always free | 24/7 service | ✅ No sleep/expiry |
| **Credit card** | Required for identity | — | ⚠️ No charge, just verification |

## Architecture

```
Your Machine                          Oracle Cloud VM (Ampere A1)
┌──────────────────────┐              ┌──────────────────────────────────┐
│  Electron App        │              │  ┌────────────────────────────┐  │
│  (React/TS)          │──────────────┼─>│  Caddy (reverse proxy)    │  │
│                      │   HTTPS      │  │  :443 → localhost:8970   │  │
│  Voice (local STT)   │              │  └───────────┬────────────────┘  │
│  Ollama (local LLM)  │              │              │                    │
└──────────────────────┘              │  ┌───────────▼────────────────┐  │
                                      │  │  BARQ FastAPI Backend      │  │
                                      │  │  :8970                     │  │
                                      │  │                            │  │
                                      │  │  • Jobs API (Playwright)  │  │
                                      │  │  • Social API             │  │
                                      │  │  • Analytics              │  │
                                      │  │  • APScheduler            │  │
                                      │  └───────────┬────────────────┘  │
                                      │              │                    │
                                      │  ┌───────────▼────────────────┐  │
                                      │  │  Turso Cloud Database     │  │
                                      │  └────────────────────────────┘  │
                                      └──────────────────────────────────┘
```

## Prerequisites

1. **Oracle Cloud account** — [signup.oracle.com](https://signup.oracle.com/)
   - Requires credit card for identity verification (no charge on free tier)
   - Select "Pay-as-you-go" (don't worry — free tier resources are always free)
2. **SSH key pair** — Generate one: `ssh-keygen -t ed25519 -f ~/.ssh/oracle-barq`
3. **A domain name** (optional, recommended for SSL) — Any cheap domain works

## Step 1: Provision the VM

### Via Oracle Cloud Console

1. Log in to [cloud.oracle.com](https://cloud.oracle.com)
2. Go to **Compute → Instances**
3. Click **"Create Instance"**
4. Configure:
   - **Name:** `barq-server`
   - **Image:** Canonical Ubuntu 22.04 (or 24.04)
   - **Shape:** Select "Specialty and legacy" → **VM.Standard.A1.Flex**
   - **OCPUs:** 4
   - **Memory (GB):** 24
   - **Boot volume:** 200 GB (free tier includes 200 GB total)
   - **SSH keys:** Add your public key
5. Click **"Create"**

### Via OCI CLI (alternative)

```bash
oci compute instance launch \
    --display-name barq-server \
    --shape VM.Standard.A1.Flex \
    --shape-config '{"ocpus": 4, "memory_in_gbs": 24}' \
    --subnet-id <your-subnet-id> \
    --image-id <ubuntu-image-ocid> \
    --ssh-authorized-keys-file ~/.ssh/oracle-barq.pub
```

### Configure Network (Security Lists)

After provisioning, add ingress rules to your subnet's security list:
- **Port 22** (SSH) — source: `0.0.0.0/0`
- **Port 80** (HTTP) — source: `0.0.0.0/0`
- **Port 443** (HTTPS) — source: `0.0.0.0/0`

*Do NOT open port 8970 directly — Caddy handles public access.*

## Step 2: Bootstrap the VM

Copy and run the bootstrap script:

```bash
# From your local machine
scp python/scripts/setup-oracle-vm.sh ubuntu@<VM-IP>:/tmp/
ssh ubuntu@<VM-IP>

# On the VM
bash /tmp/setup-oracle-vm.sh
```

This script automatically:
1. Installs Python, Caddy, system deps
2. Sets up a Python virtual environment
3. Clones the BARQ repo (or uses uploaded code)
4. Installs Python dependencies
5. Installs Playwright Chromium
6. Sets up the `.env` file (template)
7. Installs and enables the `barq.service` systemd service
8. Configures Caddy reverse proxy
9. Opens firewall ports (22, 80, 443)
10. Starts both services

## Step 3: Configure Environment Variables

```bash
ssh ubuntu@<VM-IP>
sudo nano /home/ubuntu/barq/.env
```

Fill in at minimum:

```ini
# === REQUIRED ===
TURSO_ENABLED=true
TURSO_DATABASE_URL=https://barq-venom20021.aws-ap-south-1.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9...
OPENAI_API_KEY=sk-your-openai-api-key

# === OPTIONAL ===
CLOUD_LLM_ENABLED=true
CLOUD_LLM_MODEL=gpt-4o-mini
TELEGRAM_BOT_TOKEN=your_token
# ... etc
```

Then restart:
```bash
sudo systemctl restart barq.service
```

## Step 4: Set Up Domain & SSL

### Option A: With a Domain (Recommended)

1. In your DNS provider, add an **A record** pointing to your VM's public IP:
   ```
   barq.yourdomain.com  →  <VM-PUBLIC-IP>
   ```

2. Update the Caddy config with your domain:
   ```bash
   sudo nano /etc/caddy/Caddyfile
   # Replace barq.example.com with your actual domain
   sudo systemctl restart caddy
   ```

Caddy automatically provisions a Let's Encrypt SSL certificate.

### Option B: Without a Domain (IP only)

Edit the Caddyfile to use direct IP:
```bash
sudo nano /etc/caddy/Caddyfile
```

Replace the domain block with:
```caddy
:80 {
    reverse_proxy localhost:8970 {
        header_up X-Real-IP {remote_host}
    }
    log {
        output file /var/log/caddy/barq-dev.log
    }
}
```

Restart Caddy:
```bash
sudo systemctl restart caddy
```

> **Note:** Without a domain, you'll access BARQ via HTTP only (no SSL). For a personal API, this is acceptable if you use a strong `BARQ_API_KEY`.

## Step 5: Point Local Electron App to Cloud Backend

Update these files in your local BARQ codebase:

**`src/renderer/src/hooks/useStreamingChat.ts`** (line 37):
```diff
- const baseUrl = 'http://127.0.0.1:8970'
+ const baseUrl = 'https://barq.yourdomain.com'
```

**`src/renderer/src/pages/JobsPage.tsx`** (lines 332, 1718):
```diff
- const BACKEND_URL = 'http://127.0.0.1:8970'
+ const BACKEND_URL = 'https://barq.yourdomain.com'
```

**`src/renderer/src/contexts/VoiceContext.tsx`** (line 43):
```diff
- const WS_URL = 'ws://127.0.0.1:8970/voice/ws/status'
+ const WS_URL = 'wss://barq.yourdomain.com/voice/ws/status'
```

Alternatively, set these as environment variables in your shell:
```bash
export BARQ_API_URL=https://barq.yourdomain.com
```

Then start the Electron app as usual:
```bash
npm run dev
```

## Management Commands

```bash
# SSH into the VM
ssh ubuntu@<VM-IP>

# Check BARQ service status
sudo systemctl status barq.service

# View real-time logs
sudo journalctl -u barq.service -f

# Restart BARQ
sudo systemctl restart barq.service

# Check Caddy status
sudo systemctl status caddy

# View Caddy logs
sudo journalctl -u caddy -f

# Update BARQ (pull latest code + restart)
cd /home/ubuntu/barq && git pull
source /home/ubuntu/venv/bin/activate
pip install -r python/requirements.txt
sudo systemctl restart barq.service
```

## Testing

```bash
# Check health endpoint
curl http://localhost:8970/health
# {"status":"ok","service":"barq-sidecar","version":"2.0.0",...}

# Check jobs data from Turso (no Playwright needed for this)
curl http://localhost:8970/jobs/status
# {"total_jobs_scanned": 849, ...}

# Check from outside (via Caddy)
curl https://barq.yourdomain.com/health
```

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `Connection refused` | Service not running | `sudo systemctl status barq.service` |
| `ModuleNotFoundError` | Missing dependency | `source ~/venv/bin/activate && pip install -r requirements.txt` |
| Playwright fails | Missing system libs | `sudo apt-get install -y $(playwright install-deps chromium)` |
| `413 Request Entity Too Large` | Caddy limit | Add `request_body { max_size 50MB }` to Caddy config |
| Port 80/443 not reachable | Oracle firewall | Check Security Lists in OCI Console |
| SSL cert not provisioning | DNS not propagated | Wait 5 minutes, check A record |

## Cost Breakdown

| Resource | Cost |
|---|---|
| VM (4 OCPU, 24 GB RAM) | **$0/mo** (Always Free) |
| Boot volume (200 GB) | **$0/mo** (Always Free) |
| Bandwidth (10 TB/month) | **$0/mo** (Always Free) |
| Domain name | ~$10/year |
| **Total** | **≈ $0.83/mo** |

## Updating BARQ

```bash
ssh ubuntu@<VM-IP>
cd /home/ubuntu/barq
git pull
source /home/ubuntu/venv/bin/activate
pip install -r python/requirements.txt
sudo systemctl restart barq.service
```
