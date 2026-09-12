"""
Async SQLite database layer for Stone FFA Bot.
Handles warnings, tickets, and guild configuration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger("stoneffa.database")


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._initialize_schema()
        logger.info("Database connected: %s", self.db_path)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._connection

    async def _initialize_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                staff_role_id INTEGER,
                admin_role_id INTEGER,
                ticket_category_id INTEGER,
                transcript_channel_id INTEGER,
                max_tickets_per_user INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_warnings_guild_user
                ON warnings (guild_id, user_id);

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                owner_id INTEGER NOT NULL,
                claimed_by INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                closed_at TEXT,
                closed_by INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_guild_owner
                ON tickets (guild_id, owner_id);
            CREATE INDEX IF NOT EXISTS idx_tickets_channel
                ON tickets (channel_id);
            """
        )
        await self.conn.commit()

    async def get_guild_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def upsert_guild_config(self, guild_id: int, **kwargs: Any) -> None:
        allowed = {
            "log_channel_id",
            "staff_role_id",
            "admin_role_id",
            "ticket_category_id",
            "transcript_channel_id",
            "max_tickets_per_user",
        }
        data = {k: v for k, v in kwargs.items() if k in allowed}
        if not data:
            return

        now = datetime.now(timezone.utc).isoformat()
        existing = await self.get_guild_config(guild_id)

        if existing is None:
            columns = ["guild_id", "updated_at"] + list(data.keys())
            placeholders = ", ".join("?" for _ in columns)
            values = [guild_id, now] + list(data.values())
            await self.conn.execute(
                f"INSERT INTO guild_config ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
        else:
            set_clause = ", ".join(f"{k} = ?" for k in data.keys())
            values = list(data.values()) + [now, guild_id]
            await self.conn.execute(
                f"UPDATE guild_config SET {set_clause}, updated_at = ? WHERE guild_id = ?",
                values,
            )
        await self.conn.commit()

    async def add_warning(
        self, guild_id: int, user_id: int, moderator_id: int, reason: str
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, now),
        )
        await self.conn.commit()
        return cursor.lastrowid or 0

    async def get_warnings(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT id, moderator_id, reason, created_at
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (guild_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    async def delete_warning(self, warning_id: int, guild_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
            (warning_id, guild_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def create_ticket(
        self, guild_id: int, channel_id: int, owner_id: int
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO tickets (guild_id, channel_id, owner_id, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (guild_id, channel_id, owner_id, now),
        )
        await self.conn.commit()
        return cursor.lastrowid or 0

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_open_tickets_for_user(
        self, guild_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE guild_id = ? AND owner_id = ? AND status IN ('open', 'claimed')
            """,
            (guild_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def claim_ticket(self, channel_id: int, staff_id: int) -> bool:
        cursor = await self.conn.execute(
            """
            UPDATE tickets
            SET claimed_by = ?, status = 'claimed'
            WHERE channel_id = ? AND status = 'open'
            """,
            (staff_id, channel_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def close_ticket(self, channel_id: int, closed_by: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_at = ?, closed_by = ?
            WHERE channel_id = ? AND status IN ('open', 'claimed')
            """,
            (now, closed_by, channel_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def delete_ticket_record(self, channel_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM tickets WHERE channel_id = ?", (channel_id,)
        )
        await self.conn.commit()
        return cursor.rowcount > 0
