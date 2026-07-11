"""
Data access layer for user settings and profiles.
Handles user preferences, API keys, and profile management.
"""

from typing import Any, Optional

from .connection import db_connection


class SettingsDAO:
    """DAO for user settings and profile operations."""

    # ─── User Settings ──────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        """Get a single setting value by key."""
        row = await db_connection.fetch_one(
            "SELECT value FROM user_settings WHERE key = ?", (key,)
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str, category: str = "general") -> int:
        """Set or update a setting value."""
        existing = await db_connection.fetch_one(
            "SELECT id FROM user_settings WHERE key = ?", (key,)
        )
        if existing:
            return await db_connection.update(
                "UPDATE user_settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (value, key),
            )
        else:
            return await db_connection.insert(
                "INSERT INTO user_settings (key, value, category) VALUES (?, ?, ?)",
                (key, value, category),
            )

    async def get_settings_by_category(self, category: str) -> list[dict]:
        """Get all settings for a given category."""
        return await db_connection.fetch_all(
            "SELECT key, value, is_encrypted, updated_at FROM user_settings WHERE category = ? ORDER BY key",
            (category,),
        )

    async def get_all_settings(self) -> list[dict]:
        """Get all user settings."""
        return await db_connection.fetch_all(
            "SELECT key, value, category, is_encrypted, updated_at FROM user_settings ORDER BY category, key"
        )

    async def delete_setting(self, key: str) -> int:
        """Delete a setting by key."""
        return await db_connection.delete(
            "DELETE FROM user_settings WHERE key = ?", (key,)
        )

    # ─── API Keys (stored in user_settings with encryption flag) ──────────

    async def set_api_key(self, service: str, api_key: str) -> int:
        """Store an encrypted API key."""
        return await self.set_setting(
            f"api_key_{service}", api_key, category="api_keys"
        )

    async def get_api_key(self, service: str) -> Optional[str]:
        """Retrieve an API key."""
        return await self.get_setting(f"api_key_{service}")

    async def get_configured_services(self) -> list[str]:
        """Get list of services that have API keys configured."""
        settings = await self.get_settings_by_category("api_keys")
        return [s["key"].replace("api_key_", "") for s in settings if s["value"]]

    # ─── User Profile ──────────────────────────────────────────────────────

    async def get_profile(self) -> Optional[dict]:
        """Get the user's profile."""
        return await db_connection.fetch_one(
            "SELECT * FROM user_profiles ORDER BY id ASC LIMIT 1"
        )

    async def upsert_profile(self, profile: dict[str, Any]) -> int:
        """Create or update the user profile."""
        existing = await db_connection.fetch_one(
            "SELECT id FROM user_profiles ORDER BY id ASC LIMIT 1"
        )

        if existing:
            sets = ["updated_at = datetime('now')"]
            params = []
            for field in (
                "full_name", "email", "phone", "linkedin_url", "portfolio_url",
                "github_url", "headline", "summary", "skills", "experience",
                "education", "experience_level", "target_salary_min",
                "target_salary_max", "preferred_locations", "remote_preference",
                "preferred_industries",
            ):
                if field in profile:
                    sets.append(f"{field} = ?")
                    params.append(profile[field])

            if not params:
                return 0

            params.append(existing["id"])
            sql = f"UPDATE user_profiles SET {', '.join(sets)} WHERE id = ?"
            return await db_connection.update(sql, tuple(params))
        else:
            sql = """
                INSERT INTO user_profiles (
                    full_name, email, phone, linkedin_url, portfolio_url,
                    github_url, headline, summary, skills, experience,
                    education, experience_level, target_salary_min,
                    target_salary_max, preferred_locations, remote_preference,
                    preferred_industries
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            return await db_connection.insert(sql, (
                profile.get("full_name", ""),
                profile.get("email", ""),
                profile.get("phone", ""),
                profile.get("linkedin_url", ""),
                profile.get("portfolio_url", ""),
                profile.get("github_url", ""),
                profile.get("headline", ""),
                profile.get("summary", ""),
                profile.get("skills", "[]"),
                profile.get("experience", "[]"),
                profile.get("education", "[]"),
                profile.get("experience_level", "mid"),
                profile.get("target_salary_min", 0),
                profile.get("target_salary_max", 0),
                profile.get("preferred_locations", "[]"),
                profile.get("remote_preference", "any"),
                profile.get("preferred_industries", "[]"),
            ))

    async def update_skills(self, skills: list[str]) -> int:
        """Update the user's skills list."""
        import json
        profile = await db_connection.fetch_one(
            "SELECT id FROM user_profiles ORDER BY id ASC LIMIT 1"
        )
        if not profile:
            return 0
        return await db_connection.update(
            "UPDATE user_profiles SET skills = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(skills), profile["id"]),
        )

    # ─── Notifications ────────────────────────────────────────────────────

    async def insert_notification(self, notification: dict[str, Any]) -> int:
        """Create a notification record."""
        sql = """
            INSERT INTO notifications (
                channel, title, body, priority, category,
                related_entity_type, related_entity_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            notification.get("channel", "desktop"),
            notification.get("title", ""),
            notification.get("body", ""),
            notification.get("priority", "normal"),
            notification.get("category", "general"),
            notification.get("related_entity_type"),
            notification.get("related_entity_id"),
        ))

    async def get_unread_notifications(self, limit: int = 20) -> list[dict]:
        """Get unread notifications, highest priority first."""
        return await db_connection.fetch_all(
            """SELECT * FROM notifications
               WHERE read = 0
               ORDER BY
                   CASE priority
                       WHEN 'urgent' THEN 0
                       WHEN 'high' THEN 1
                       WHEN 'normal' THEN 2
                       ELSE 3
                   END,
                   created_at DESC
               LIMIT ?""",
            (limit,),
        )

    async def mark_notification_read(self, notification_id: int) -> int:
        """Mark a notification as read."""
        return await db_connection.update(
            "UPDATE notifications SET read = 1, read_at = datetime('now') WHERE id = ?",
            (notification_id,),
        )

    async def get_notification_count(self) -> dict[str, int]:
        """Get counts of notifications."""
        row = await db_connection.fetch_one("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN read = 0 THEN 1 ELSE 0 END) as unread,
                SUM(CASE WHEN priority = 'urgent' AND read = 0 THEN 1 ELSE 0 END) as urgent
            FROM notifications
        """)
        return dict(row) if row else {"total": 0, "unread": 0, "urgent": 0}

    # ─── Voice Commands ───────────────────────────────────────────────────

    async def log_command(self, command: dict[str, Any]) -> int:
        """Log a voice command."""
        sql = """
            INSERT INTO voice_commands (
                transcript, confidence, action, action_target,
                was_wake_word, processed, success, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        return await db_connection.insert(sql, (
            command.get("transcript", ""),
            command.get("confidence", 0.0),
            command.get("action", "unknown"),
            command.get("action_target", ""),
            1 if command.get("was_wake_word") else 0,
            1 if command.get("processed") else 0,
            1 if command.get("success") else 0,
            command.get("duration_ms", 0),
        ))

    async def get_recent_commands(self, limit: int = 20) -> list[dict]:
        """Get recent voice commands."""
        return await db_connection.fetch_all(
            "SELECT * FROM voice_commands ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
