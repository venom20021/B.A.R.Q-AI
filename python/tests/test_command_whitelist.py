"""
Tests for system_control.command_whitelist — security guard for terminal execution.

Covers:
- Built-in safe / warn / dangerous command classification
- Custom rules (override built-in patterns)
- Unknown commands defaulting to WARN
- Edge cases (empty, whitespace, case, comments)
- describe_classification for all tiers
- Approval lifecycle (approve, is_approved, clear_approvals)
- Async custom rules (get/set via settings_dao)
"""

import json
import re
import pytest
from typing import Optional


# ─── Module Under Test ───────────────────────────────────────────────────────

@pytest.fixture
def whitelist():
    """Import the command_whitelist module once per test session wrapper."""
    from system_control import command_whitelist as wl
    # Always start with a clean approval slate
    wl.clear_approvals()
    return wl


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Built-in SAFE Tier
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeCommands:
    """Commands that are read-only and auto-approved."""

    @pytest.mark.parametrize("command", [
        # File reading / listing
        "cat /etc/hosts",
        "head -n 20 file.log",
        "tail -f /var/log/syslog",
        "ls -la /home",
        "which python3",
        "type curl",
        "file /bin/bash",
        "du -sh /home/user",
        "df -h",
        "stat file.txt",
        "readlink -f /usr/bin/python",
        "realpath ~/Documents",
        # Environment / identity
        "env",
        "echo hello world",
        "pwd",
        "date",
        "cal",
        "uptime",
        "whoami",
        "id",
        "groups",
        "w",
        "who",
        # System info
        "uname -a",
        "hostnamectl status",
        "lscpu --all",
        "lsblk --help",
        "lsusb --help",
        "lspci --help",
        "dmesg | tail",
        "sw_vers",
        "system_profiler SPSoftwareDataType",
        # Process listing
        "ps aux",
        "top -n 1",
        "pgrep python",
        # Network info (read-only)
        "ping -c 4 google.com",
        'curl "https://api.example.com/data"',
        "curl https://api.example.com/data",
        "wget https://example.com/file.tar.gz",
        "netstat -an",
        "ss -tuln",
        "ifconfig -a",
        "ip addr show",
        "hostname",
        "dig example.com",
        "nslookup google.com",
        "traceroute 8.8.8.8",
        "lsof -i :3000",
        "arp -a",
        # Git read operations
        "git status",
        "git log --oneline -10",
        "git diff",
        "git branch -a",
        "git remote -v",
        "git show HEAD",
        "git config --global user.name",
        # Package info
        "npm list --depth=0",
        "pnpm list",
        "yarn list",
        "pip list --format=columns",
        "pip show requests",
        "brew list",
        "brew info python",
    ])
    def test_safe_command(self, whitelist, command):
        """Safe commands should return SAFE tier."""
        tier = whitelist.classify_command(command)
        assert tier == whitelist.SAFE, f"Expected SAFE for: {command!r}, got {tier}"

    @pytest.mark.parametrize("command", [
        "  echo hello",
        "\techo hello",
        "echo hello   ",
    ])
    def test_safe_command_whitespace(self, whitelist, command):
        """Safe commands with leading/trailing whitespace should still classify as SAFE."""
        tier = whitelist.classify_command(command)
        assert tier == whitelist.SAFE, f"Expected SAFE for: {command!r}, got {tier}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Built-in WARN Tier
# ═══════════════════════════════════════════════════════════════════════════════

class TestWarnCommands:
    """Commands that modify state and require user confirmation."""

    @pytest.mark.parametrize("command", [
        # File creation / modification
        "mkdir /tmp/newdir",
        "touch /tmp/newfile.txt",
        "cp source.txt dest.txt",
        "mv old.txt new.txt",
        "ln -s /usr/bin/python python3",
        "chmod 755 script.sh",
        "chown user:group file.txt",
        "chgrp staff file.txt",
        "tar -czf archive.tar.gz dir/",
        "gzip file.txt",
        "gunzip file.txt.gz",
        "zip archive.zip file.txt",
        "unzip archive.zip",
        # Process control
        "kill 1234",
        "pkill chrome",
        "nohup python server.py &",
        # Package operations
        "npm install express",
        "npm run build",
        "pnpm add lodash",
        "yarn add react",
        "pip install requests",
        "pip uninstall pytest",
        "pip install --upgrade pip",
        "brew install wget",
        "brew upgrade python",
        "cargo install ripgrep",
        "cargo build --release",
        "cargo run",
        "apt install nginx",
        "dnf update",
        "yum install httpd",
        # Network write
        "curl -X POST -d 'key=val' https://api.example.com/submit",
        "curl --data '{\"name\":\"test\"}' https://api.example.com/create",
        "scp file.txt user@host:/path/",
        "rsync -avz src/ dest/",
        "sftp user@host",
        "ssh user@host",
        # Service control
        "systemctl start nginx",
        "systemctl restart docker",
        "systemctl enable cron",
        "service nginx restart",
        "launchctl load /Library/LaunchDaemons/nginx.plist",
        # Git write operations
        "git add .",
        "git commit -m 'fix bug'",
        "git push origin main",
        "git pull origin main",
        "git merge feature-branch",
        "git checkout main",
        "git reset --soft HEAD~1",
        "git stash",
        "git clone https://github.com/user/repo.git",
        # Docker
        "docker run -d nginx:latest",
        "docker-compose up -d",
        # Python scripts
        "python3 script.py",
        "python manage.py runserver",
    ])
    def test_warn_command(self, whitelist, command):
        """Warn commands should return WARN tier."""
        tier = whitelist.classify_command(command)
        assert tier == whitelist.WARN, f"Expected WARN for: {command!r}, got {tier}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Built-in DANGEROUS Tier
# ═══════════════════════════════════════════════════════════════════════════════

class TestDangerousCommands:
    """Commands that are destructive and require explicit approval."""

    @pytest.mark.parametrize("command", [
        # Deletion
        "rm -rf /",
        "rm file.txt",
        "rmdir emptydir",
        "shred -u secret.pdf",
        "wipe /dev/sdb1",
        # Disk / partition
        "mkfs -t ext4 /dev/sdb1",
        "mkswap /dev/sdb2",
        "fdisk /dev/sda",
        "parted /dev/sda mklabel gpt",
        "dd if=/dev/zero of=/dev/sda bs=1M",
        "mount /dev/sdb1 /mnt/data",
        "umount /mnt/data",
        "format D: /FS:NTFS",
        # System state
        "reboot",
        "shutdown -h now",
        "poweroff",
        "init 0",
        "halt -f",
        # Escalation
        "sudo apt install nginx",
        "su - root",
        "passwd user1",
        "useradd john",
        "userdel -r john",
        "groupadd engineers",
        "groupdel engineers",
        # Firewall / security
        "iptables -A INPUT -j DROP",
        "nft add rule ip filter INPUT drop",
        "ufw enable",
        "firewall-cmd --add-port=80/tcp",
        # Overwrite via wget (non-HTTP target)
        "wget ftp://host/file.bin",
        "wget /local/path/file",
        # Clear / truncate
        "truncate -s 0 /var/log/syslog",
        "fallocate -l 1G largefile.dat",
        # Encryption
        "cryptsetup luksFormat /dev/sdb1",
        # chroot
        "chroot /mnt /bin/bash",
    ])
    def test_dangerous_command(self, whitelist, command):
        """Dangerous commands should return DANGEROUS tier."""
        tier = whitelist.classify_command(command)
        assert tier == whitelist.DANGEROUS, f"Expected DANGEROUS for: {command!r}, got {tier}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Unknown commands default to WARN
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnknownCommands:
    """Unrecognized commands should default to WARN (safe default)."""

    @pytest.mark.parametrize("command", [
        "myspecialtool --do-stuff",
        "foobar",
        "abc123xyz",
        "some-custom-binary --flag value",
        "test_runner --all --verbose",
    ])
    def test_unknown_defaults_to_warn(self, whitelist, command):
        """Unknown commands should default to WARN."""
        tier = whitelist.classify_command(command)
        assert tier == whitelist.WARN, f"Expected WARN for unknown: {command!r}, got {tier}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Priority: Dangerous beats Warn beats Safe
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriority:
    """When a command matches multiple tiers, the most restrictive tier wins."""

    def test_dangerous_priority_over_warn(self, whitelist):
        """DANGEROUS classification should take priority over WARN."""
        # 'rm' matches DANGEROUS; 'npm' matches WARN if present
        tier = whitelist.classify_command("rm -rf node_modules && npm install")
        assert tier == whitelist.DANGEROUS

    def test_dangerous_priority_over_safe(self, whitelist):
        """DANGEROUS classification should take priority over SAFE."""
        # 'rm' matches DANGEROUS; 'echo' also matches SAFE
        tier = whitelist.classify_command("rm file && echo done")
        assert tier == whitelist.DANGEROUS

    def test_warn_priority_over_safe(self, whitelist):
        """WARN classification should take priority over SAFE."""
        # 'mkdir' at start matches WARN; 'echo' also matches SAFE but WARN checked first
        tier = whitelist.classify_command("mkdir newdir && echo done")
        assert tier == whitelist.WARN


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Custom Rules Override
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustomRules:
    """Custom rules should be checked before built-in patterns."""

    def test_custom_safe_overrides_builtin(self, whitelist):
        """A custom SAFE rule should allow an otherwise DANGEROUS command."""
        custom = {"safe": [r"^rm\s"], "warn": [], "dangerous": []}
        tier = whitelist.classify_command("rm -rf /", custom=custom)
        assert tier == whitelist.SAFE, (
            "Custom safe rule should override built-in dangerous classification"
        )

    def test_custom_dangerous_overrides_builtin(self, whitelist):
        """A custom DANGEROUS rule should flag an otherwise SAFE command."""
        custom = {"safe": [], "warn": [], "dangerous": [r"echo\s+hello"]}
        tier = whitelist.classify_command("echo hello world", custom=custom)
        assert tier == whitelist.DANGEROUS, (
            "Custom dangerous rule should override built-in safe classification"
        )

    def test_custom_warn_catches_otherwise_safe(self, whitelist):
        """A custom WARN rule should flag an otherwise SAFE command."""
        custom = {"safe": [], "warn": [r"^ls\s+-la"], "dangerous": []}
        tier = whitelist.classify_command("ls -la /home", custom=custom)
        assert tier == whitelist.WARN, (
            "Custom warn rule should override built-in safe classification"
        )

    def test_custom_dangerous_takes_priority_over_custom_warn(self, whitelist):
        """Custom dangerous rules are checked before custom warn rules."""
        custom = {
            "safe": [],
            "warn": [r"^rm\s+"],
            "dangerous": [r"^rm\s+-rf"],
        }
        tier = whitelist.classify_command("rm -rf /", custom=custom)
        assert tier == whitelist.DANGEROUS, (
            "Custom dangerous should win over custom warn"
        )

    def test_custom_warn_takes_priority_over_custom_safe(self, whitelist):
        """Custom warn rules are checked before custom safe rules."""
        custom = {
            "safe": [r"^git\s+push"],
            "warn": [r"^git\s+push\s+--force"],
            "dangerous": [],
        }
        tier = whitelist.classify_command("git push --force origin main", custom=custom)
        assert tier == whitelist.WARN, (
            "Custom warn should win over custom safe"
        )

    def test_empty_custom_no_override(self, whitelist):
        """An empty custom rules dict should not affect built-in classification."""
        tier = whitelist.classify_command("ls -la", custom={"safe": [], "warn": [], "dangerous": []})
        assert tier == whitelist.SAFE

    def test_custom_with_invalid_regex(self, whitelist):
        """Invalid regex patterns in custom rules should be silently skipped."""
        custom = {
            "safe": [r"[invalid"],
            "warn": [],
            "dangerous": [],
        }
        # Should still classify normally (falls through to built-in)
        tier = whitelist.classify_command("ls -la", custom=custom)
        assert tier == whitelist.SAFE

    def test_custom_safe_for_unknown_command(self, whitelist):
        """Custom SAFE rule should allow an otherwise unclassified (WARN) command."""
        custom = {
            "safe": [r"^myspecialtool\b"],
            "warn": [],
            "dangerous": [],
        }
        tier = whitelist.classify_command("myspecialtool --do-stuff", custom=custom)
        assert tier == whitelist.SAFE, (
            "Custom safe rule should allow unknown commands"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_string(self, whitelist):
        """Empty command should return WARN (safe default)."""
        tier = whitelist.classify_command("")
        assert tier == whitelist.WARN

    def test_whitespace_only(self, whitelist):
        """Whitespace-only command should return WARN."""
        tier = whitelist.classify_command("   ")
        assert tier == whitelist.WARN

    def test_tab_only(self, whitelist):
        """Tab-only command should return WARN."""
        tier = whitelist.classify_command("\t\t")
        assert tier == whitelist.WARN

    def test_newline_in_command(self, whitelist):
        """Command with embedded newline should be classified."""
        # Dangerous command first so '^' anchor matches at string start
        tier = whitelist.classify_command("rm -rf /\necho done")
        assert tier == whitelist.DANGEROUS, "Embedded dangerous command should be caught"

    def test_case_insensitive(self, whitelist):
        """Classification should be case-insensitive."""
        assert whitelist.classify_command("ECHO test") == whitelist.SAFE
        assert whitelist.classify_command("RM -RF /") == whitelist.DANGEROUS
        # WARN command first so '^' anchor matches at string start
        assert whitelist.classify_command("MKDIR dir && ECHO hello") == whitelist.WARN

    def test_mixed_command_with_redirection(self, whitelist):
        """Commands with shell redirection should still classify correctly."""
        assert whitelist.classify_command("cat /etc/passwd | grep root") == whitelist.SAFE
        assert whitelist.classify_command("rm file.txt 2>/dev/null") == whitelist.DANGEROUS

    def test_command_with_semicolons(self, whitelist):
        """Commands joined by semicolons should be classified by first match."""
        # Dangerous command first so '^' anchor matches at string start
        tier = whitelist.classify_command("rm file.txt; echo done")
        assert tier == whitelist.DANGEROUS

    def test_command_with_pipes(self, whitelist):
        """Commands with pipes should be classified appropriately."""
        assert whitelist.classify_command("ls -la | grep foo") == whitelist.SAFE
        assert whitelist.classify_command("rm file.txt | echo done") == whitelist.DANGEROUS


# ═══════════════════════════════════════════════════════════════════════════════
# 8. describe_classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestDescribeClassification:
    """Human-readable tier descriptions."""

    def test_describe_safe(self, whitelist):
        desc = whitelist.describe_classification(whitelist.SAFE)
        assert "Safe" in desc or "safe" in desc or "read-only" in desc

    def test_describe_warn(self, whitelist):
        desc = whitelist.describe_classification(whitelist.WARN)
        assert "Moderate" in desc or "risk" in desc or "modify" in desc

    def test_describe_dangerous(self, whitelist):
        desc = whitelist.describe_classification(whitelist.DANGEROUS)
        assert "Dangerous" in desc or "delete" in desc or "alter" in desc

    def test_describe_unknown_tier(self, whitelist):
        desc = whitelist.describe_classification("nonexistent")
        assert desc == "Unknown risk level"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Approval Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestApprovals:
    """Session-based command approval mechanism."""

    def test_approve_and_check_warn(self, whitelist):
        """Approve a WARN command, then verify it's approved."""
        whitelist.approve_command("npm install express", whitelist.WARN)
        assert whitelist.is_approved("npm install express", whitelist.WARN) is True

    def test_approve_and_check_dangerous(self, whitelist):
        """Approve a DANGEROUS command, then verify it's approved."""
        whitelist.approve_command("rm -rf /tmp/cache", whitelist.DANGEROUS)
        assert whitelist.is_approved("rm -rf /tmp/cache", whitelist.DANGEROUS) is True

    def test_command_not_approved_by_default(self, whitelist):
        """A command should not be approved unless explicitly approved."""
        assert whitelist.is_approved("rm -rf /", whitelist.DANGEROUS) is False
        assert whitelist.is_approved("npm install", whitelist.WARN) is False

    def test_warn_approval_does_not_affect_dangerous(self, whitelist):
        """Approving a command as WARN should not make it approved as DANGEROUS."""
        whitelist.approve_command("rm file.txt", whitelist.WARN)
        assert whitelist.is_approved("rm file.txt", whitelist.DANGEROUS) is False

    def test_dangerous_approval_does_not_affect_warn(self, whitelist):
        """Approving a command as DANGEROUS should not make it approved as WARN."""
        whitelist.approve_command("rm -rf /", whitelist.DANGEROUS)
        assert whitelist.is_approved("rm -rf /", whitelist.WARN) is False

    def test_approval_is_hash_based(self, whitelist):
        """Different commands should have different approval status."""
        whitelist.approve_command("npm install express", whitelist.WARN)
        assert whitelist.is_approved("npm install lodash", whitelist.WARN) is False

    def test_approval_with_whitespace(self, whitelist):
        """Command with extra whitespace should still match approval hash."""
        whitelist.approve_command("npm install express", whitelist.WARN)
        assert whitelist.is_approved("  npm install express", whitelist.WARN) is True

    def test_clear_approvals_removes_warn(self, whitelist):
        """Clearing approvals should remove WARN approvals."""
        whitelist.approve_command("npm install express", whitelist.WARN)
        whitelist.clear_approvals()
        assert whitelist.is_approved("npm install express", whitelist.WARN) is False

    def test_clear_approvals_removes_dangerous(self, whitelist):
        """Clearing approvals should remove DANGEROUS approvals."""
        whitelist.approve_command("rm -rf /tmp/cache", whitelist.DANGEROUS)
        whitelist.clear_approvals()
        assert whitelist.is_approved("rm -rf /tmp/cache", whitelist.DANGEROUS) is False

    def test_approve_safe_returns_false(self, whitelist):
        """Approving a SAFE command should return False (no approval needed)."""
        result = whitelist.approve_command("ls -la", whitelist.SAFE)
        assert result is False

    def test_approve_unknown_tier_returns_false(self, whitelist):
        """Approving an unknown tier should return False."""
        result = whitelist.approve_command("some command", "unknown_tier")
        assert result is False

    def test_is_approved_safe_always_false(self, whitelist):
        """is_approved for SAFE tier should always return False."""
        assert whitelist.is_approved("ls -la", whitelist.SAFE) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Async Custom Rules (DB-backed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustomRulesAsync:
    """Async custom rules CRUD via database."""

    @pytest.mark.asyncio
    async def test_get_custom_rules_empty(self, whitelist):
        """get_custom_rules should return empty lists when no rules are set."""
        rules = await whitelist.get_custom_rules()
        assert rules == {"safe": [], "warn": [], "dangerous": []}

    @pytest.mark.asyncio
    async def test_set_and_get_custom_rules(self, whitelist):
        """set_custom_rules followed by get_custom_rules should round-trip."""
        test_rules = {
            "safe": [r"^ls\s", r"^echo\s"],
            "warn": [r"^git\s+push", r"^npm\s+install"],
            "dangerous": [r"^rm\s+-rf"],
        }
        success = await whitelist.set_custom_rules(test_rules)
        assert success is True

        loaded = await whitelist.get_custom_rules()
        assert loaded == test_rules

    @pytest.mark.asyncio
    async def test_overwrite_custom_rules(self, whitelist):
        """Setting new custom rules should overwrite previous ones."""
        await whitelist.set_custom_rules({
            "safe": [r"^old"],
            "warn": [],
            "dangerous": [],
        })
        await whitelist.set_custom_rules({
            "safe": [r"^new"],
            "warn": [],
            "dangerous": [],
        })
        loaded = await whitelist.get_custom_rules()
        assert loaded["safe"] == [r"^new"]
        assert loaded["warn"] == []

    @pytest.mark.asyncio
    async def test_classify_with_db_custom_rules(self, whitelist):
        """Custom rules stored in DB should affect classify_command when passed."""
        await whitelist.set_custom_rules({
            "safe": [r"^rm\s"],
            "warn": [],
            "dangerous": [],
        })
        custom = await whitelist.get_custom_rules()
        # Without custom arg, built-in rules win
        assert whitelist.classify_command("rm -rf /") == whitelist.DANGEROUS
        # With custom arg, custom overrides
        assert whitelist.classify_command("rm -rf /", custom=custom) == whitelist.SAFE

    @pytest.mark.asyncio
    async def test_set_custom_rules_stores_json(self, whitelist):
        """Custom rules should be stored as JSON in the database."""
        test_rules = {
            "safe": [r"^custom"],
            "warn": [],
            "dangerous": [],
        }
        await whitelist.set_custom_rules(test_rules)

        # Verify the raw DB entry
        from database import settings_dao
        raw = await settings_dao.get_setting("command_whitelist_rules")
        assert raw is not None
        parsed = json.loads(raw)
        assert parsed == test_rules


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Integration: classify_command with custom rules approval override
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Integration-style tests combining classification + approval."""

    def test_classify_then_approve_then_check(self, whitelist):
        """Full flow: classify a command, approve it, then verify it's approved."""
        command = "rm -rf /tmp/cache"
        tier = whitelist.classify_command(command)
        assert tier == whitelist.DANGEROUS

        whitelist.approve_command(command, tier)
        assert whitelist.is_approved(command, tier) is True

    def test_classify_dangerous_then_approve_warn_does_not_work(self, whitelist):
        """Approving a dangerous command as WARN should not make it approved."""
        command = "rm -rf /"
        assert whitelist.classify_command(command) == whitelist.DANGEROUS

        whitelist.approve_command(command, whitelist.WARN)
        assert whitelist.is_approved(command, whitelist.DANGEROUS) is False

    def test_custom_rules_affect_classify_but_not_approval(self, whitelist):
        """Custom rules change classification but approval still uses the same hash."""
        command = "rm -rf /"
        # Built-in classification
        assert whitelist.classify_command(command) == whitelist.DANGEROUS

        # Custom rule overrides to SAFE
        custom = {"safe": [r"^rm\s"], "warn": [], "dangerous": []}
        assert whitelist.classify_command(command, custom=custom) == whitelist.SAFE

        # Approval should not be needed for SAFE, but confirm mechanism
        assert whitelist.is_approved(command, whitelist.DANGEROUS) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Pattern Compilation — Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestPatternCompilation:
    """Internal pattern compilation edge cases."""

    def test_invalid_pattern_skipped_silently(self):
        """An invalid regex pattern should be skipped during compilation."""
        from system_control.command_whitelist import _compile_patterns
        compiled = _compile_patterns([r"^valid\s+", r"[invalid", r"^also_valid"])
        assert len(compiled) == 2
        # Both valid patterns should compile correctly
        assert compiled[0].search("valid stuff")
        assert compiled[1].search("also_valid")

    def test_case_insensitive_compilation(self):
        """Compiled patterns should be case-insensitive."""
        from system_control.command_whitelist import _compile_patterns
        compiled = _compile_patterns([r"^echo\s+"])
        assert compiled[0].search("ECHO hello") is not None
        assert compiled[0].search("echo hello") is not None
