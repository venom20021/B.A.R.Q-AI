#!/usr/bin/env bash
# ─── BARQ Oracle Cloud VM Bootstrap Script ───────────────────────────
# Run ONCE on a fresh Oracle Cloud Ubuntu 22.04/24.04 VM.
# Idempotent — safe to re-run if something fails mid-way.
#
# Usage:
#   scp scripts/setup-oracle-vm.sh ubuntu@<VM-IP>:/tmp/
#   ssh ubuntu@<VM-IP> bash /tmp/setup-oracle-vm.sh
# ───────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

BARQ_USER="${BARQ_USER:-ubuntu}"
BARQ_HOME="/home/${BARQ_USER}"
BARQ_DIR="${BARQ_DIR:-${BARQ_HOME}/barq}"

# ─── 1. System Updates & Dependencies ────────────────────────────────

info "Updating system packages..."
sudo env DEBIAN_FRONTEND=noninteractive apt-get update && \
sudo env DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

info "Installing system dependencies..."
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    build-essential pkg-config \
    debian-keyring debian-archive-keyring apt-transport-https \
    git \
    curl wget unzip net-tools openssl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64 \
    && sudo apt-get autoremove -y && sudo apt-get clean

# Install TeX Live for pdflatex-based PDF resume generation
info "Installing TeX Live (LaTeX) for PDF resume generation..."
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-latex-recommended \
    texlive-xetex \
    latex-xcolor \
    texlive-latex-extra-doc \
    && sudo apt-get autoremove -y && sudo apt-get clean

# Verify pdflatex is available
if command -v pdflatex &> /dev/null; then
    ok "pdflatex installed: $(pdflatex --version | head -1)"
else
    warn "pdflatex not found after TeX Live install — check apt logs"
fi

# Install Caddy from official APT repository (works on all architectures including ARM64)
info "Installing Caddy web server..."
if ! command -v caddy &> /dev/null; then
    sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update
    sudo apt-get install -y caddy
    ok "Caddy installed from official APT repository"
else
    ok "Caddy already installed"
fi

ok "System dependencies installed"

# ─── 2. Python Environment (idempotent) ──────────────────────────────

info "Setting up Python virtual environment..."
if [ ! -d "${BARQ_HOME}/venv" ]; then
    sudo -u "${BARQ_USER}" python3 -m venv "${BARQ_HOME}/venv"
    ok "Python venv created at ${BARQ_HOME}/venv"
else
    ok "Python venv already exists at ${BARQ_HOME}/venv"
fi

# ─── 3. Clone BARQ Repository (idempotent) ──────────────────────────

if [ ! -d "${BARQ_DIR}" ]; then
    info "Cloning BARQ repository..."
    sudo -u "${BARQ_USER}" git clone https://github.com/venom20021/B.A.R.Q-AI.git "${BARQ_DIR}"
    ok "BARQ cloned to ${BARQ_DIR}"
else
    ok "BARQ already exists at ${BARQ_DIR}"
    sudo -u "${BARQ_USER}" git -C "${BARQ_DIR}" pull
fi

# ─── 4. Install Python Dependencies (idempotent) ─────────────────────

info "Installing Python dependencies..."
cd "${BARQ_DIR}/python"

sudo -u "${BARQ_USER}" bash -c "source ${BARQ_HOME}/venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt"

ok "Python dependencies installed"

# Install Playwright browsers
info "Installing Playwright Chromium browser..."
sudo -u "${BARQ_USER}" bash -c "source ${BARQ_HOME}/venv/bin/activate && \
    playwright install chromium"
ok "Playwright Chromium installed"

# ─── 5. Create Data Directories ──────────────────────────────────────

mkdir -p "${BARQ_DIR}/python/data/brains" "${BARQ_DIR}/python/data/generated" "${BARQ_DIR}/logs"
ok "Data directories created"

# ─── 6. Set Up .env (preserve existing if present) ───────────────────

if [ ! -f "${BARQ_DIR}/.env" ]; then
    warn ".env not found — creating from template"
    
    # Generate a random API key for inter-service auth
    BARQ_API_KEY=$(openssl rand -hex 24 2>/dev/null || echo "please-generate-a-random-64-char-hex-key")
    
    cat > "${BARQ_DIR}/.env" << EOF
# ─── BARQ Oracle VM Configuration ────────────────────────────────────
# Fill in your actual values below.

# === REQUIRED: Database (Turso) ===
TURSO_ENABLED=true
TURSO_DATABASE_URL=your_turso_db_url
TURSO_AUTH_TOKEN=your_turso_token

# === REQUIRED: Cloud LLM ===
CLOUD_LLM_ENABLED=true
OPENAI_API_KEY=sk-your-openai-api-key
CLOUD_LLM_MODEL=gpt-4o-mini
CLOUD_LLM_BASE_URL=https://api.openai.com/v1

# === SERVER CONFIG ===
SIDECAR_HOST=0.0.0.0
SIDECAR_PORT=8970
BARQ_DEBUG=false
BARQ_API_KEY=${BARQ_API_KEY}

# === OPTIONAL: Notifications ===
# TELEGRAM_BOT_TOKEN=your_token
# TELEGRAM_CHAT_ID=your_chat_id
# SMTP_HOST=smtp.gmail.com
# SMTP_USER=your_email@gmail.com
# SMTP_PASS=your_app_password
EOF

    chown "${BARQ_USER}:${BARQ_USER}" "${BARQ_DIR}/.env"
    chmod 600 "${BARQ_DIR}/.env"

    warn ">>> EDIT ${BARQ_DIR}/.env with your Turso credentials and API keys <<<"
    echo "  Generated BARQ_API_KEY: ${BARQ_API_KEY}"
    echo "  (Save this key — needed to authenticate from the Electron app)"
else
    ok ".env already exists (preserved)"
fi

# ─── 7. Install systemd Service (from standalone file) ───────────────

info "Installing BARQ systemd service..."
if [ -f "${BARQ_DIR}/python/barq.service" ]; then
    sudo cp "${BARQ_DIR}/python/barq.service" /etc/systemd/system/barq.service
    ok "Copied barq.service from repo"
else
    info "barq.service not found in repo — installing inline..."
    sudo tee /etc/systemd/system/barq.service > /dev/null << 'SERVICE'
[Unit]
Description=BARQ Python Backend (FastAPI Sidecar)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/barq/python
Environment=PATH=/home/ubuntu/venv/bin:/usr/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/venv/bin/uvicorn main:app \
    --host 0.0.0.0 --port 8970 --log-level info
Restart=always
RestartSec=5
StartLimitInterval=300
StartLimitBurst=10
MemoryMax=8G
CPUQuota=300%
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
ReadWritePaths=/home/ubuntu/barq/python /var/log
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE
fi

sudo systemctl daemon-reload
sudo systemctl enable barq.service
ok "systemd service installed and enabled"

# ─── 8. Set Up Caddy Reverse Proxy (preserve existing config) ────────

info "Setting up Caddy reverse proxy..."

PUBLIC_IP=$(curl -4 -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "CHANGE_ME")

if [ -f /etc/caddy/Caddyfile ] && [ "$(stat -c%s /etc/caddy/Caddyfile 2>/dev/null)" -gt 200 ]; then
    warn "Caddyfile already exists with content — not overwriting"
    warn "  Edit it manually: sudo nano /etc/caddy/Caddyfile"
    warn "  Then restart:      sudo systemctl restart caddy"
else
    sudo tee /etc/caddy/Caddyfile > /dev/null << CADDY
# ─── BARQ Caddy Configuration ────────────────────────────────────────
# Replace barq.example.com with your domain (A record → ${PUBLIC_IP})
# ─────────────────────────────────────────────────────────────────────

barq.example.com {
    reverse_proxy localhost:8970 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    encode gzip

    # Rate limit: 1000 events/min per client (generous for API usage)
    rate_limit {
        zone dynamic {
            key {remote_host}
            events 1000
            window 1m
        }
    }

    log {
        output file /var/log/caddy/barq.log {
            roll_size 50mb
            roll_keep 5
        }
    }
}

http://${PUBLIC_IP}:80 {
    reverse_proxy localhost:8970 {
        header_up X-Real-IP {remote_host}
    }
}

http://barq.example.com {
    redir https://barq.example.com{uri} 301
}
CADDY

    ok "Caddy configured with IP-based fallback"
fi

# Create log directory
sudo mkdir -p /var/log/caddy
sudo chown -R caddy:caddy /var/log/caddy

# ─── 9. Configure Firewall ───────────────────────────────────────────

info "Configuring firewall..."
sudo ufw --force disable 2>/dev/null || true
sudo ufw allow 22/tcp    comment 'SSH'
sudo ufw allow 80/tcp    comment 'HTTP'
sudo ufw allow 443/tcp   comment 'HTTPS'
sudo ufw --force enable 2>/dev/null || warn "UFW enable failed"
ok "Firewall: SSH (22), HTTP (80), HTTPS (443) allowed"

# ─── 10. Start Services ──────────────────────────────────────────────

info "Starting Caddy..."
sudo systemctl restart caddy
sleep 2
if systemctl is-active --quiet caddy; then
    ok "Caddy is running"
else
    warn "Caddy failed to start — check: sudo journalctl -u caddy -n 20"
fi

info "Starting BARQ backend..."
sudo systemctl restart barq.service

# Health check with polling (waits up to 30 seconds)
info "Waiting for BARQ healthcheck..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8970/health > /dev/null 2>&1; then
        echo ""
        ok "BARQ is RUNNING (responded in ${i}s)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo ""
        warn "BARQ healthcheck not responding after 30s"
        warn "  Check logs: sudo journalctl -u barq.service -n 50 --no-pager"
        warn "  NOTE: first boot may take 60+ seconds to download whisper model"
    fi
    sleep 1
done

# ─── 11. Summary ─────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         BARQ Deployment Complete                     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Server Info:"
echo "    Public IP:     ${PUBLIC_IP}"
echo "    Health check:  http://${PUBLIC_IP}/health"
echo "    (port 80 → Caddy → port 8970 → FastAPI)"
echo ""
echo "  Key Commands:"
echo "    sudo systemctl status barq     — check service"
echo "    sudo journalctl -u barq -f     — view live logs"
echo "    sudo systemctl restart barq    — restart"
echo ""
echo "  Post-Deploy Checklist:"
echo "    1. sudo nano /home/ubuntu/barq/.env    # fill API keys"
echo "    2. sudo systemctl restart barq          # apply changes"
echo "    3. Point a domain A record → ${PUBLIC_IP}"
echo "    4. sudo nano /etc/caddy/Caddyfile       # set domain"
echo "    5. sudo systemctl restart caddy         # apply SSL"
echo ""
echo "  Cost: \$0/mo (Oracle Always Free — 4 OCPU, 24GB RAM, 200GB disk)"
echo ""
