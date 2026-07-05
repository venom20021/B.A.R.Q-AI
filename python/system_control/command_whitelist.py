"""
BARQ Command Whitelist — Security guard for terminal execution.

Categorizes shell commands into three tiers of safety:
- SAFE: Read-only, informational commands (auto-approved)
- WARN: Moderately risky commands (requires user confirmation)
- DANGEROUS: Destructive / system-altering commands (requires explicit approval)

Each category is defined by regex patterns. Custom rules can be added
via the database settings system and are merged at runtime.
"""

import re
import json
from typing import Optional
from database import settings_dao


# ─── Safety Tiers ────────────────────────────────────────────────────────────

SAFE = "safe"
WARN = "warn"
DANGEROUS = "dangerous"


# ─── Built-in Command Patterns ───────────────────────────────────────────────
# These are the default rules. Custom rules from the DB are merged on top.

_BUILTIN_SAFE_PATTERNS = [
    # File reading / listing
    r"^\s*(cat|head|tail|less|more|wc|nl|od|xxd)\s+",
    r"^\s*ls\s+",
    r"^\s*find\s+",
    r"^\s*locate\s+",
    r"^\s*which\s+",
    r"^\s*type\s+",
    r"^\s*file\s+",
    r"^\s*du\s+",
    r"^\s*df\s+",
    r"^\s*stat\s+",
    r"^\s*readlink\s+",
    r"^\s*realpath\s+",
    # Process listing
    r"^\s*ps\s+",
    r"^\s*top\s+",
    r"^\s*htop\s+",
    r"^\s*btop\s+",
    r"^\s*pgrep\s+",
    # Network info (read-only)
    r"^\s*ping\s+",
    r"^\s*curl\s+(?:-\w+\s+)*['\"]?https?://",  # HTTP GET requests
    r"^\s*wget\s+(?:-\w+\s+)*['\"]?https?://",  # HTTP GET via wget
    r"^\s*netstat\s+",
    r"^\s*ss\s+",
    r"^\s*ifconfig\s+",
    r"^\s*ip\s+(?:addr|link|route|neigh)\s+",
    r"^\s*hostname\s*$",
    r"^\s*dig\s+",
    r"^\s*nslookup\s+",
    r"^\s*traceroute\s+",
    r"^\s*lsof\s+",
    r"^\s*arp\s+",
    # System info
    r"^\s*uname\s+",
    r"^\s*hostnamectl\s+",
    r"^\s*lscpu\s+",
    r"^\s*lsblk\s+",
    r"^\s*lsusb\s+",
    r"^\s*lspci\s+",
    r"^\s*dmesg\s+",
    r"^\s*sysctl\s+",
    r"^\s*sw_vers\s*$",
    r"^\s*system_profiler\s+",
    # Date / time
    r"^\s*date\s*$",
    r"^\s*cal\s*$",
    r"^\s*uptime\s*$",
    r"^\s*w\s*$",
    r"^\s*who\s*$",
    r"^\s*whoami\s*$",
    r"^\s*id\s*$",
    r"^\s*groups\s*$",
    # Environment
    r"^\s*env\s*$",
    r"^\s*printenv\s+",
    r"^\s*echo\s+",
    r"^\s*pwd\s*$",
    r"^\s*readlink\s+",
    # Git read operations
    r"^\s*git\s+(?:status|log|diff|branch|remote|show|stash\s+list|tag)",
    r"^\s*git\s+config",
    # Package info
    r"^\s*(?:npm|pnpm|yarn)\s+(?:list|info|search|view)",
    r"^\s*pip\s+(?:list|show|search)",
    r"^\s*brew\s+(?:list|info|search)",
    r"^\s*cargo\s+(?:search|info)",
]

_BUILTIN_WARN_PATTERNS = [
    # File creation / modification
    r"^\s*mkdir\s+",
    r"^\s*touch\s+",
    r"^\s*cp\s+",
    r"^\s*mv\s+",
    r"^\s*ln\s+",
    r"^\s*chmod\s+",
    r"^\s*chown\s+",
    r"^\s*chgrp\s+",
    r"^\s*tar\s+",
    r"^\s*gzip\s+",
    r"^\s*gunzip\s+",
    r"^\s*zip\s+",
    r"^\s*unzip\s+",
    # Process control
    r"^\s*kill\s+",
    r"^\s*pkill\s+",
    r"^\s*nohup\s+",
    # Package operations
    r"^\s*(?:npm|pnpm|yarn)\s+(?:install|add|remove|update|run)",
    r"^\s*pip\s+(?:install|uninstall|update|--upgrade)",
    r"^\s*brew\s+(?:install|uninstall|update|upgrade)",
    r"^\s*cargo\s+(?:install|uninstall|update|build|run)",
    r"^\s*apt(?:\-get)?\s+(?:install|remove|update|upgrade)",
    r"^\s*dnf\s+",
    r"^\s*yum\s+",
    # Network write
    r"^\s*curl\s+(?:-\w+\s+)*(?:-X\s+(?:POST|PUT|DELETE|PATCH)|-d\s+|--data)",
    r"^\s*scp\s+",
    r"^\s*rsync\s+",
    r"^\s*sftp\s+",
    r"^\s*ssh\s+",
    # Service control
    r"^\s*systemctl\s+(?:start|stop|restart|reload|enable|disable)",
    r"^\s*service\s+",
    r"^\s*launchctl\s+",
    # Git write operations
    r"^\s*git\s+(?:add|commit|push|pull|merge|rebase|checkout|switch|reset|stash|tag)",
    r"^\s*git\s+clone",
    # Docker
    r"^\s*docker\s+(?:run|exec|start|stop|restart|build|push|pull|compose)",
    r"^\s*docker-compose\s+",
    # Python
    r"^\s*python3?\s+",
]

_BUILTIN_DANGEROUS_PATTERNS = [
    # Deletion
    r"^\s*rm\s+",
    r"^\s*rmdir\s+",
    r"^\s*shred\s+",
    r"^\s*wipe\s+",
    # Disk / partition operations
    r"^\s*mkfs\s+",
    r"^\s*mkswap\s+",
    r"^\s*fdisk\s+",
    r"^\s*parted\s+",
    r"^\s*dd\s+",
    r"^\s*mount\s+",
    r"^\s*umount\s+",
    r"^\s*format\s+",
    # Reboot / shutdown
    r"^\s*reboot\s*$",
    r"^\s*shutdown\s+",
    r"^\s*poweroff\s*$",
    r"^\s*init\s+",
    r"^\s*halt\s+",
    # User / permission escalation
    r"^\s*sudo\s+",
    r"^\s*su\s+",
    r"^\s*passwd\s+",
    r"^\s*useradd\s+",
    r"^\s*userdel\s+",
    r"^\s*groupadd\s+",
    r"^\s*groupdel\s+",
    # Firewall / security
    r"^\s*iptables\s+",
    r"^\s*nft\s+",
    r"^\s*ufw\s+",
    r"^\s*firewall-cmd\s+",
    # Wget / curl to local files (overwrite risk)
    r"^\s*wget\s+(?!https?://)",
    # Clear / truncate
    r"^\s*truncate\s+",
    r"^\s*fallocate\s+",
    # Encrypt / crypt
    r"^\s*cryptsetup\s+",
    # chroot
    r"^\s*chroot\s+",
]


def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile a list of regex pattern strings."""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE))
        except re.error:
            print(f"[CommandWhitelist] Invalid pattern skipped: {p}")
    return compiled


# Pre-compiled built-in patterns
_BUILTIN_SAFE_COMPILED = _compile_patterns(_BUILTIN_SAFE_PATTERNS)
_BUILTIN_WARN_COMPILED = _compile_patterns(_BUILTIN_WARN_PATTERNS)
_BUILTIN_DANGEROUS_COMPILED = _compile_patterns(_BUILTIN_DANGEROUS_PATTERNS)


# ─── Custom rules management ─────────────────────────────────────────────────

async def get_custom_rules() -> dict[str, list[str]]:
    """Load custom whitelist rules from the database."""
    raw = await settings_dao.get_setting("command_whitelist_rules")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {"safe": [], "warn": [], "dangerous": []}


async def set_custom_rules(rules: dict[str, list[str]]) -> bool:
    """Save custom whitelist rules to the database."""
    return await settings_dao.set_setting(
        "command_whitelist_rules", json.dumps(rules), category="system"
    )


# ─── Evaluation ──────────────────────────────────────────────────────────────

def classify_command(command: str, custom: Optional[dict[str, list[str]]] = None) -> str:
    """
    Classify a shell command into SAFE, WARN, or DANGEROUS.

    Checks custom rules first (if provided), then falls back to built-in patterns.
    The first matching category wins.
    """
    cmd_stripped = command.strip()

    # 1. Check custom rules (user overrides — checked first so users can allowlist)
    if custom:
        # Dangerous custom
        for pattern in custom.get("dangerous", []):
            try:
                if re.search(pattern, cmd_stripped, re.IGNORECASE):
                    return DANGEROUS
            except re.error:
                continue

        # Warn custom
        for pattern in custom.get("warn", []):
            try:
                if re.search(pattern, cmd_stripped, re.IGNORECASE):
                    return WARN
            except re.error:
                continue

        # Safe custom
        for pattern in custom.get("safe", []):
            try:
                if re.search(pattern, cmd_stripped, re.IGNORECASE):
                    return SAFE
            except re.error:
                continue

    # 2. Check built-in patterns (dangerous first for safety)
    for pattern in _BUILTIN_DANGEROUS_COMPILED:
        if pattern.search(cmd_stripped):
            return DANGEROUS

    for pattern in _BUILTIN_WARN_COMPILED:
        if pattern.search(cmd_stripped):
            return WARN

    for pattern in _BUILTIN_SAFE_COMPILED:
        if pattern.search(cmd_stripped):
            return SAFE

    # 3. Unknown commands default to WARN (safe default for unrecognized)
    return WARN


def describe_classification(tier: str) -> str:
    """Return a human-readable description of a safety tier."""
    descriptions = {
        SAFE: "Safe — read-only informational command",
        WARN: "Moderate risk — may modify files or run processes",
        DANGEROUS: "Dangerous — can delete data or alter system state",
    }
    return descriptions.get(tier, "Unknown risk level")


# ─── Quick allowlist for currently-approved WARN commands ─────────────────────
# In-memory set of approved command hashes for the current session.
# Cleared on server restart.

_approved_warn: set[str] = set()
_approved_dangerous: set[str] = set()


def approve_command(command: str, tier: str) -> bool:
    """Temporarily approve a command for this session."""
    cmd_hash = _command_hash(command)
    if tier == WARN:
        _approved_warn.add(cmd_hash)
        return True
    elif tier == DANGEROUS:
        _approved_dangerous.add(cmd_hash)
        return True
    return False


def is_approved(command: str, tier: str) -> bool:
    """Check if a command was previously approved in this session."""
    cmd_hash = _command_hash(command)
    if tier == WARN:
        return cmd_hash in _approved_warn
    elif tier == DANGEROUS:
        return cmd_hash in _approved_dangerous
    return False


def clear_approvals():
    """Clear all temporary approvals."""
    _approved_warn.clear()
    _approved_dangerous.clear()


def _command_hash(command: str) -> str:
    """Create a stable hash for command approval tracking."""
    import hashlib
    return hashlib.md5(command.strip().encode("utf-8")).hexdigest()[:16]
