"""
BARQ Database Layer

Provides async SQLite storage for all modules using aiosqlite.
Tables are auto-created on first run.

Usage:
    from database import init_db, get_db, JobsDAO, SocialDAO, AnalyticsDAO, SettingsDAO

    # Initialize database on app startup
    await init_db()

    # Use DAOs for CRUD
    dao = JobsDAO()
    jobs = await dao.get_active_jobs()
"""

from .connection import db_connection, DatabaseConnection
from .schema import initialize_schema, seed_defaults, ALL_TABLES
from .jobs_dao import JobsDAO
from .social_dao import SocialDAO
from .analytics_dao import AnalyticsDAO
from .settings_dao import SettingsDAO


async def init_db():
    """
    Initialize the database: create tables and seed default data.
    Call this once on application startup.
    """
    db = await db_connection.connect()

    # Create all tables
    await initialize_schema(db)

    # Seed defaults (settings, empty profile)
    await seed_defaults(db)

    print(f"[Database] Initialized at: {db_connection.db_path}")
    return db_connection


async def close_db():
    """Close the database connection gracefully."""
    await db_connection.close()
    print("[Database] Connection closed")


def get_db() -> DatabaseConnection:
    """Get the database connection singleton."""
    return db_connection


# Convenience instances
jobs_dao = JobsDAO()
social_dao = SocialDAO()
analytics_dao = AnalyticsDAO()
settings_dao = SettingsDAO()

__all__ = [
    "init_db",
    "close_db",
    "get_db",
    "db_connection",
    "DatabaseConnection",
    "JobsDAO",
    "SocialDAO",
    "AnalyticsDAO",
    "SettingsDAO",
    "jobs_dao",
    "social_dao",
    "analytics_dao",
    "settings_dao",
]
