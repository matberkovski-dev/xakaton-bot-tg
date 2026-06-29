import csv
import os
from typing import Optional

import aiosqlite

DB_PATH = os.path.join(os.path.dirname(__file__), "hackathon.db")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS participants (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    fio TEXT NOT NULL,
    school_class TEXT NOT NULL,
    phone TEXT NOT NULL,
    team_name TEXT NOT NULL,
    registered_at TEXT NOT NULL
)
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(CREATE_TABLE_SQL)
        await conn.commit()


async def get_participant(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM participants WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_participant(
    user_id: int,
    username: str,
    fio: str,
    school_class: str,
    phone: str,
    team_name: str,
    registered_at: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO participants
                (user_id, username, fio, school_class, phone, team_name, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                fio = excluded.fio,
                school_class = excluded.school_class,
                phone = excluded.phone,
                team_name = excluded.team_name,
                registered_at = excluded.registered_at
            """,
            (user_id, username, fio, school_class, phone, team_name, registered_at),
        )
        await conn.commit()


async def team_exists(team_name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM participants WHERE team_name = ? COLLATE NOCASE LIMIT 1",
            (team_name,),
        )
        row = await cursor.fetchone()
        return row is not None


async def get_team_members_count(team_name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM participants WHERE team_name = ? COLLATE NOCASE",
            (team_name,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_team_names() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT team_name, COUNT(*) as members_count
            FROM participants
            GROUP BY team_name COLLATE NOCASE
            ORDER BY team_name COLLATE NOCASE
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_participants() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM participants ORDER BY team_name, fio"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def count_participants() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM participants")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def export_to_csv() -> str:
    participants = await get_all_participants()
    path = os.path.join(os.path.dirname(__file__), "participants_export.csv")

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ФИО", "Класс", "Команда", "Телефон", "Username", "Дата регистрации"])
        for p in participants:
            writer.writerow([
                p["fio"],
                p["school_class"],
                p["team_name"],
                p["phone"],
                p["username"],
                p["registered_at"],
            ])

    return path
