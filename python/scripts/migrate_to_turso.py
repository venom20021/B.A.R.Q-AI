"""
BARQ → Turso Migration Script

Copies all data from the local SQLite database to a Turso cloud database.
Requires TURSO_ENABLED=true, TURSO_DATABASE_URL, and TURSO_AUTH_TOKEN in .env.

Usage:
    cd python
    python scripts/migrate_to_turso.py [--reset]

    --reset:  DROP all existing tables in Turso before re-creating them
              (WARNING: destroys all existing cloud data)
"""

import argparse
import asyncio
import os
import sys
import time

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite
from dotenv import load_dotenv

# Load .env from project root (handle any working directory)
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path, override=True)

from database.connection import TursoConnection
from database.schema import ALL_TABLES
from config import get_settings


# ─── Helper: get all rows from a local SQLite table ─────────────────────

async def get_local_rows(db_path: str, table_name: str) -> tuple[list[str], list[tuple]]:
    """Return (column_names, rows) for a given table from local SQLite."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Get column info
        cursor = await db.execute(f"PRAGMA table_info(\"{table_name}\")")
        cols_info = await cursor.fetchall()
        col_names = [c[1] for c in cols_info]  # name is column 1

        # Get all rows
        cursor = await db.execute(f"SELECT * FROM \"{table_name}\"")
        rows = await cursor.fetchall()
        return col_names, [tuple(r) for r in rows]


# ─── Helper: build INSERT statement ─────────────────────────────────────

def build_insert_sql(table: str, col_names: list[str]) -> str:
    cols = ", ".join(f'"{c}"' for c in col_names)
    placeholders = ", ".join("?" for _ in col_names)
    return f'INSERT OR IGNORE INTO "{table}" ({cols}) VALUES ({placeholders})'


# ─── Migration runner ───────────────────────────────────────────────────

async def migrate(reset: bool = False):
    settings = get_settings()

    # Source: local SQLite file
    db_url = settings.database_url
    if db_url.startswith("sqlite+aiosqlite:///"):
        local_path = db_url[len("sqlite+aiosqlite:///"):]
    elif db_url.startswith("sqlite:///"):
        local_path = db_url[len("sqlite:///"):]
    else:
        local_path = db_url

    if not os.path.exists(local_path):
        print(f"❌ Local database not found: {local_path}")
        sys.exit(1)

    # Destination: Turso cloud
    turso_url = settings.turso_database_url
    turso_token = settings.turso_auth_token
    if not turso_url or not turso_token:
        print("❌ TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set in .env")
        sys.exit(1)

    print(f"📦 Source:      {local_path}")
    print(f"☁️  Destination: {turso_url}")
    print()

    turso = TursoConnection(turso_url, turso_token)

    try:
        # ── Step 1: Bootstrap schema ────────────────────────────────────
        if reset:
            print("⚠️  --reset: Dropping all existing Turso tables...")
            # Drop in reverse order to respect foreign keys
            for table_name, _ in reversed(ALL_TABLES):
                try:
                    await turso.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                except Exception as e:
                    print(f"   ⚠️  Could not drop {table_name}: {e}")
            print("   ✅ Tables dropped")

        print("🔨 Creating tables in Turso...")
        for table_name, ddl in ALL_TABLES:
            try:
                await turso.execute(ddl)
                print(f"   ✅ {table_name}")
            except Exception as e:
                print(f"   ❌ {table_name}: {e}")

        # ── Step 2: Migrate data ────────────────────────────────────────
        # Disable foreign keys during migration to avoid ordering issues
        print()
        print("📤 Migrating data...")

        total_rows = 0
        start = time.time()

        for table_name, _ in ALL_TABLES:
            try:
                col_names, rows = await get_local_rows(local_path, table_name)
                if not rows:
                    print(f"   ⏭️  {table_name} — empty, skipped")
                    continue

                sql = build_insert_sql(table_name, col_names)
                batch_size = 50

                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    # Turso v1/execute handles one statement at a time,
                    # so we insert row-by-row (acceptable for migration)
                    for row in batch:
                        await turso.execute(sql, row)

                print(f"   ✅ {table_name} — {len(rows)} rows")
                total_rows += len(rows)

            except Exception as e:
                print(f"   ❌ {table_name}: {e}")

        elapsed = time.time() - start
        print()
        print(f"🎉 Migration complete! {total_rows} rows migrated in {elapsed:.1f}s")
        print()

        # ── Step 3: Verify ──────────────────────────────────────────────
        print("🔍 Verifying row counts...")
        for table_name, _ in ALL_TABLES:
            try:
                local_cols, local_rows = await get_local_rows(local_path, table_name)
                local_count = len(local_rows)
                turso_result = await turso.fetch_one(f'SELECT COUNT(*) as cnt FROM "{table_name}"')
                turso_count = turso_result["cnt"] if turso_result else 0
                status = "✅" if local_count == turso_count else "⚠️"
                print(f"   {status} {table_name}: local={local_count} turso={turso_count}")
            except Exception as e:
                print(f"   ❌ {table_name}: verify failed — {e}")

    finally:
        await turso.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate BARQ data to Turso cloud")
    parser.add_argument("--reset", action="store_true",
                       help="Drop existing Turso tables before migration")
    args = parser.parse_args()
    asyncio.run(migrate(reset=args.reset))


if __name__ == "__main__":
    main()
