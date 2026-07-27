#!/usr/bin/env bash
# ─── BARQ → Fly.io Automated Deployment Script ───────────────────────
# Usage:
#   chmod +x scripts/deploy-fly.sh
#   ./scripts/deploy-fly.sh [--setup|--deploy|--secrets|--all]
#
# Modes:
#   --setup     Install flyctl, launch Fly.io app (first time only)
#   --secrets   Set all production secrets from .env.production
#   --deploy    Deploy the app (build + push)
#   --all       Run full pipeline: setup → secrets → deploy
# ───────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="barq-sidecar"
ENV_FILE="$PROJECT_DIR/.env.production"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── Check prerequisites ─────────────────────────────────────────────

check_prereqs() {
    info "Checking prerequisites..."

    if ! command -v flyctl &> /dev/null && ! command -v fly &> /dev/null; then
        warn "flyctl not found. Install it first:"
        warn "  curl -fsSL https://fly.io/install.sh | sh"
        warn "  Then add ~/.fly/bin to your PATH."
        exit 1
    fi

    FLY_CMD=$(command -v flyctl || command -v fly)
    ok "flyctl found: $FLY_CMD"

    if ! command -v docker &> /dev/null; then
        warn "docker not found. Docker is required for Fly.io builds."
        warn "Install from: https://docs.docker.com/get-docker/"
        exit 1
    fi
    ok "docker found"

    # Check logged into Fly.io
    if ! $FLY_CMD auth whoami &> /dev/null; then
        warn "Not logged into Fly.io. Running 'flyctl auth login'..."
        $FLY_CMD auth login
    fi
    ok "Logged into Fly.io"
}

# ─── Setup: create Fly.io app (first time) ──────────────────────────

setup_app() {
    info "Setting up Fly.io app '$APP_NAME'..."

    # Check if app already exists
    if $FLY_CMD apps list 2>/dev/null | grep -q "$APP_NAME"; then
        ok "App '$APP_NAME' already exists"
        return
    fi

    cd "$PROJECT_DIR"
    $FLY_CMD launch \
        --name "$APP_NAME" \
        --region "ams" \
        --org personal \
        --no-deploy \
        --ha=false

    ok "App '$APP_NAME' created in region ams (Amsterdam)"
    info "Free tier: 1 VM, 256MB RAM, 3GB transfer/month"
    info "To change region, see: https://fly.io/docs/reference/regions/"
}

# ─── Set secrets ─────────────────────────────────────────────────────

set_secrets() {
    if [ ! -f "$ENV_FILE" ]; then
        error "Environment file not found: $ENV_FILE"
        error "Copy .env.production and fill in your values first:"
        error "  cp $ENV_FILE $ENV_FILE.local"
        error "  # Edit .env.production.local with your API keys"
        exit 1
    fi

    info "Setting Fly.io secrets from $(basename $ENV_FILE)..."

    # Filter out comments and blank lines, join with -s KEY=VALUE syntax
    SECRETS=$(grep -v '^#' "$ENV_FILE" | grep -v '^$' | grep -v '^===' | \
              sed 's/ *= */=/' | tr '\n' ' ')

    # Don't set empty values
    FILTERED=""
    for pair in $SECRETS; do
        KEY="${pair%%=*}"
        VAL="${pair#*=}"
        if [ -n "$VAL" ] && [[ ! "$VAL" =~ ^your_ ]] && [[ ! "$VAL" =~ ^sk-your ]]; then
            FILTERED="$FILTERED -s $KEY=$VAL"
        fi
    done

    if [ -z "$FILTERED" ]; then
        warn "No non-empty secrets found in $ENV_FILE"
        warn "Fill in your API keys first, then re-run."
        exit 0
    fi

    # shellcheck disable=SC2086
    $FLY_CMD secrets set $FILTERED --app "$APP_NAME"

    ok "Secrets set successfully ($(echo "$FILTERED" | wc -w | tr -d ' ') values)"
    warn "Sensitive values are encrypted at rest in Fly.io."
}

# ─── Deploy ──────────────────────────────────────────────────────────

deploy_app() {
    info "Deploying BARQ to Fly.io..."

    cd "$PROJECT_DIR"

    info "Building and deploying Docker image..."
    $FLY_CMD deploy \
        --app "$APP_NAME" \
        --dockerfile Dockerfile \
        --build-target runtime \
        --strategy immediate

    ok "Deployment complete!"

    # Show status
    echo ""
    $FLY_CMD status --app "$APP_NAME"
    echo ""

    APP_URL="https://$APP_NAME.fly.dev"
    info "Your BARQ backend is live at: $APP_URL"
    info "   Health check: $APP_URL/health"
    info "   API docs:    $APP_URL/docs (if debug enabled)"
    info "   Jobs API:    $APP_URL/jobs/status"
}

# ─── Main ────────────────────────────────────────────────────────────

main() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        BARQ → Fly.io Deployment                 ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""

    MODE="${1:---all}"

    case "$MODE" in
        --setup)
            check_prereqs
            setup_app
            ;;
        --secrets)
            set_secrets
            ;;
        --deploy)
            deploy_app
            ;;
        --all|*)
            check_prereqs
            setup_app
            set_secrets
            deploy_app
            ;;
    esac

    echo ""
    ok "Done!"
}

main "$@"
