"""
BARQ Database Connection — dual-mode async database layer.

Supports two backends:
  1. Local SQLite via aiosqlite (default, backward-compatible)
  2. Turso Cloud via libsql HTTP API (TURSO_ENABLED=true in .env)

All DAO modules and external code import `db_connection` and call the same
async methods (fetch_one, fetch_all, insert, update, delete, execute).
"""

import os
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from config import get_settings


# ─── Turso HTTP API wrapper ──────────────────────────────────────────────

class TursoConnection:
    """Thin async wrapper around the Turso /v1/execute HTTP API.

    Uses aiohttp internally.  Every public method matches the interface of
    the local aiosqlite branch so callers don't know which backend is active.
    """

    def __init__(self, database_url: str, auth_token: str):
        # Turso URLs use the libsql:// protocol, but the HTTP API requires https://
        url = database_url.rstrip("/")
        if url.startswith("libsql://"):
            url = "https://" + url[9:]
            print("[Turso] Converted libsql:// to https:// for HTTP API")
        self._base_url = url
        self._auth_token = auth_token
        self._session: Optional[Any] = None  # aiohttp.ClientSession

    # ── session lifecycle ────────────────────────────────────────────────

    async def _get_session(self) -> Any:
        """Lazy-create the aiohttp session (thread-safe)."""
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ── value converters ─────────────────────────────────────────────────

    @staticmethod
    def _to_arg(val: Any) -> dict:
        """Python → Turso typed-arg dict."""
        if val is None:
            return {"type": "null"}
        if isinstance(val, bool):
            return {"type": "integer", "value": "1" if val else "0"}
        if isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        if isinstance(val, float):
            return {"type": "float", "value": val}
        return {"type": "text", "value": str(val)}

    @staticmethod
    def _from_val(val_obj: Any) -> Any:
        """Turso typed-value dict → Python value."""
        if val_obj is None:
            return None
        if not isinstance(val_obj, dict):
            return val_obj  # already a scalar
        vtype = val_obj.get("type")
        value = val_obj.get("value")
        if vtype == "null" or value is None:
            return None
        if vtype == "integer":
            try:
                return int(value)
            except (ValueError, TypeError):
                return value
        if vtype == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
        return str(value)  # text / fallback

    # ── core HTTP call ───────────────────────────────────────────────────

    async def _call_v1(self, sql: str, params: tuple = ()) -> dict:
        """POST /v1/execute and return the result dict."""
        session = await self._get_session()
        body: dict[str, Any] = {"stmt": {"sql": sql}}
        if params:
            body["stmt"]["args"] = [self._to_arg(p) for p in params]

        headers = {
            "Authorization": f"Bearer {self._auth_token}",
            "Content-Type": "application/json",
        }
        async with session.post(
            f"{self._base_url}/v1/execute", json=body, headers=headers
        ) as resp:
            data: dict = await resp.json()
            if resp.status != 200:
                err = data.get("error", str(data))
                raise RuntimeError(f"Turso API error ({resp.status}): {err}")
            return data.get("result", {})

    def _rows_to_dicts(self, result: dict) -> list[dict]:
        """Convert Turso result rows to list of dicts."""
        cols = result.get("cols", [])
        rows = result.get("rows", [])
        if not cols or not rows:
            return []
        col_names = [c.get("name", f"col{i}") for i, c in enumerate(cols)]
        return [
            {col_names[i]: self._from_val(row[i]) for i in range(len(col_names))}
            for row in rows
        ]

    # ── Public interface (matches aiosqlite branch) ──────────────────────

    async def commit(self) -> None:
        """No-op: Turso auto-commits each execute() call."""
        pass

    async def rollback(self) -> None:
        """No-op: Turso doesn't support transactions via HTTP API."""
        pass

    async def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute DDL or any statement that doesn't need row output."""
        await self._call_v1(sql, params)

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute the same SQL with multiple parameter sets."""
        for params in params_list:
            await self._call_v1(sql, params)

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        result = await self._call_v1(sql, params)
        dicts = self._rows_to_dicts(result)
        return dicts[0] if dicts else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        result = await self._call_v1(sql, params)
        return self._rows_to_dicts(result)

    async def insert(self, sql: str, params: tuple = ()) -> int:
        result = await self._call_v1(sql, params)
        return result.get("last_insert_rowid") or 0

    async def update(self, sql: str, params: tuple = ()) -> int:
        result = await self._call_v1(sql, params)
        return result.get("affected_row_count", 0)

    async def delete(self, sql: str, params: tuple = ()) -> int:
        return await self.update(sql, params)

    @property
    def db_path(self) -> str:
        return self._base_url  # for display / logging


# ─── Dual-mode connection manager ────────────────────────────────────────

class DatabaseConnection:
    """Manages either an aiosqlite (local) or Turso (cloud) connection.

    Mode is selected once at startup via ``settings.turso_enabled``.
    All public methods work identically regardless of backend.
    """

    def __init__(self):
        self.settings = get_settings()
        self._db: Optional[aiosqlite.Connection] = None
        self._turso: Optional[TursoConnection] = None
        self._db_path: str = self._resolve_db_path()
        self._turso_mode = self.settings.turso_enabled
        if self._turso_mode:
            print(f"[Turso] Mode: ENABLED -> {self.settings.turso_database_url}")
            print(f"[Turso] Auth token present: {bool(self.settings.turso_auth_token)}")
        else:
            print("[Turso] Mode: DISABLED (check TURSO_ENABLED in .env)")
            print(f"[Turso] Raw env TURSO_ENABLED='{os.environ.get('TURSO_ENABLED', '(not set)')}'")

    def _resolve_db_path(self) -> str:
        url = self.settings.database_url
        if url.startswith("sqlite+aiosqlite:///"):
            path = url[len("sqlite+aiosqlite:///"):]
        elif url.startswith("sqlite:///"):
            path = url[len("sqlite:///"):]
        else:
            path = url
        db_dir = os.path.dirname(path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> str:
        if self._turso_mode and self._turso:
            return self._turso.db_path
        return self._db_path

    # ── connect / close ──────────────────────────────────────────────────

    async def connect(self):
        """Get-or-create the connection for the active backend."""
        if self._turso_mode:
            if self._turso is None:
                self._turso = TursoConnection(
                    self.settings.turso_database_url,
                    self.settings.turso_auth_token,
                )
            return self._turso
        else:
            if self._db is None:
                self._db = await aiosqlite.connect(self._db_path)
                self._db.row_factory = aiosqlite.Row
                await self._db.execute("PRAGMA journal_mode=WAL")
                await self._db.execute("PRAGMA foreign_keys=ON")
                await self._db.execute("PRAGMA synchronous=NORMAL")
                await self._db.execute("PRAGMA cache_size=-8000")
                await self._db.execute("PRAGMA busy_timeout=5000")
            return self._db

    async def close(self):
        if self._turso:
            await self._turso.close()
            self._turso = None
        if self._db:
            await self._db.close()
            self._db = None

    # ── proxy methods ────────────────────────────────────────────────────

    async def commit(self):
        """Commit the current transaction (no-op for Turso)."""
        db = await self.connect()
        return await db.commit()

    async def execute(self, sql: str, params: tuple = ()):
        if self._turso_mode:
            return await self._turso.execute(sql, params)
        db = await self.connect()
        return await db.execute(sql, params)

    async def execute_many(self, sql: str, params_list: list[tuple]):
        if self._turso_mode:
            conn = await self.connect()
            return await conn.execute_many(sql, params_list)
        db = await self.connect()
        return await db.executemany(sql, params_list)

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        if self._turso_mode:
            conn = await self.connect()
            return await conn.fetch_one(sql, params)
        db = await self.connect()
        cursor = await db.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if self._turso_mode:
            conn = await self.connect()
            return await conn.fetch_all(sql, params)
        db = await self.connect()
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def insert(self, sql: str, params: tuple = ()) -> int:
        if self._turso_mode:
            conn = await self.connect()
            return await conn.insert(sql, params)
        db = await self.connect()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.lastrowid

    async def update(self, sql: str, params: tuple = ()) -> int:
        if self._turso_mode:
            conn = await self.connect()
            return await conn.update(sql, params)
        db = await self.connect()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount

    async def delete(self, sql: str, params: tuple = ()) -> int:
        if self._turso_mode:
            conn = await self.connect()
            return await conn.delete(sql, params)
        db = await self.connect()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount


# Singleton instance
db_connection = DatabaseConnection()
