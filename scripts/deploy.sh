#!/usr/bin/env bash
# ─── BARQ VM Deployment Script ────────────────────────────────────────
# This script runs ON the Oracle VM to pull latest code, update deps,
# clear bytecache, and restart the service.
#
# In CI/CD (GitHub Actions), each step runs as individual SSH commands
# in appleboy/ssh-action. This script exists for manual runs or
# local debugging when you SSH into the VM directly.
# ───────────────────────────────────────────────────────────────────────

set -euo pipefail

BARQ_DIR="${BARQ_DIR:-/home/ubuntu/barq}"
VENV_DIR="${VENV_DIR:-/home/ubuntu/venv}"
SERVICE_NAME="${SERVICE_NAME:-barq}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── 1. Navigate & Pull ──────────────────────────────────────────────

info "Navigating to ${BARQ_DIR}..."
cd "${BARQ_DIR}"

info "Pulling latest code from origin/master..."

# Back up .env before pull (secrets are never in git)
if [ -f .env ]; then
    cp .env /tmp/barq-env-backup
    info ".env backed up"
fi

git pull origin master 2>&1

# Restore .env after pull
if [ -f /tmp/barq-env-backup ]; then
    cp /tmp/barq-env-backup .env
    rm /tmp/barq-env-backup
    ok ".env restored"
fi

ok "Code updated"

# ─── 2. Install Python Dependencies ──────────────────────────────────

info "Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

info "Upgrading pip..."
python3 -m pip install --upgrade pip -q

info "Installing production dependencies..."
pip install --no-cache-dir -r python/requirements.txt -q
ok "Dependencies installed"

# ─── 3. Clear Stale Bytecache ────────────────────────────────────────

info "Clearing Python __pycache__ directories..."
find python -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
find python -name '*.pyc' -delete 2>/dev/null
ok "Bytecache cleared"

# ─── 3.5 Pre-deploy Validation ───────────────────────────────────────

info "Validating code before restart..."
cd python
python3 -c "from config import get_settings; s = get_settings(); print('Settings OK:')" 2>&1
python3 -c "import main; print('app OK')" 2>&1
cd ..
ok "Code validation passed"

# ─── 4. Restart Service ──────────────────────────────────────────────

info "Reloading systemd daemon..."
sudo systemctl daemon-reload

info "Restarting ${SERVICE_NAME}.service..."
sudo systemctl restart "${SERVICE_NAME}.service"
ok "Service restart issued"

# ─── 5. Health Check ─────────────────────────────────────────────────

info "Waiting for health check (up to 30s)..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8970/health > /dev/null 2>&1; then
        echo ""
        ok "BARQ is RUNNING (responded in ${i}s)"
        curl -s http://localhost:8970/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8970/health
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo ""
        error "Health check FAILED after 30s"
        warn "Last 20 service logs:"
        sudo journalctl -u "${SERVICE_NAME}.service" --no-pager -n 20 2>&1 || true
        exit 1
    fi
    sleep 1
done

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   BARQ Deployment Complete ✅            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
