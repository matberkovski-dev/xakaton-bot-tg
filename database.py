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
    registered_at TEXT NOT NULL,
    is_captain INTEGER NOT NULL DEFAULT 0
)
"""

CREATE_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""

# Ключи настраиваемых текстов и их подписи для меню /editinfo
SETTINGS_KEYS = {
    "event_date": "Дата и время проведения",
    "address": "Адрес проведения",
    "schedule": "Программа/расписание дня",
    "what_to_bring": "Что взять с собой",
    "criteria": "Критерии оценки",
    "prizes": "Призы и награды",
    "contacts": "Контакты организаторов",
    "rules": "Правила хакатона",
}

DEFAULT_SETTINGS = {
    "event_date": "пока не назначена",
    "address": "Курчатовская школа, корпус «Факультет», г. Москва, ул. Маршала Конева, д. 10",
    "schedule": "пока не опубликована",
    "what_to_bring": "пока не опубликован список",
    "criteria": "пока не опубликованы",
    "prizes": "пока не объявлены",
    "contacts": "пока не указаны",
    "rules": "пока не опубликованы",
}


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(CREATE_TABLE_SQL)
        await conn.execute(CREATE_SETTINGS_TABLE_SQL)

        # Миграция: если база создавалась раньше без колонки is_captain — добавляем её.
        cursor = await conn.execute("PRAGMA table_info(participants)")
        columns = [row[1] async for row in cursor]
        if "is_captain" not in columns:
            await conn.execute(
                "ALTER TABLE participants ADD COLUMN is_captain INTEGER NOT NULL DEFAULT 0"
            )

        # Заполняем настройки значениями по умолчанию, если их ещё нет.
        for key, default_value in DEFAULT_SETTINGS.items():
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, default_value),
            )

        await conn.commit()


async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else DEFAULT_SETTINGS.get(key, "пока не указано")


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {k: v for k, v in rows}


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
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


async def search_participants(query: str) -> list[dict]:
    """Ищет участников по ФИО (частичное совпадение, без учёта регистра)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM participants WHERE fio LIKE ? COLLATE NOCASE ORDER BY fio",
            (f"%{query}%",),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_participant(user_id: int) -> bool:
    """Удаляет участника по user_id. Возвращает True, если кто-то был удалён."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "DELETE FROM participants WHERE user_id = ?", (user_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0


async def change_team(user_id: int, new_team_name: str) -> bool:
    """Переводит участника в другую команду. Возвращает True, если запись была обновлена."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE participants SET team_name = ? WHERE user_id = ?",
            (new_team_name, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_team_members(team_name: str) -> list[dict]:
    """Возвращает всех участников команды (для просмотра состава)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM participants WHERE team_name = ? COLLATE NOCASE ORDER BY is_captain DESC, fio",
            (team_name,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_captain(team_name: str) -> Optional[dict]:
    """Возвращает капитана команды, если назначен."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM participants WHERE team_name = ? COLLATE NOCASE AND is_captain = 1 LIMIT 1",
            (team_name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_captain(team_name: str, user_id: int) -> bool:
    """Назначает участника капитаном его команды, снимая капитанство с предыдущего.

    Возвращает True, если участник найден и состоит именно в этой команде.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT team_name FROM participants WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row or row["team_name"].lower() != team_name.lower():
            return False

        # снимаем капитанство со всех в команде, затем назначаем нового
        await conn.execute(
            "UPDATE participants SET is_captain = 0 WHERE team_name = ? COLLATE NOCASE",
            (team_name,),
        )
        await conn.execute(
            "UPDATE participants SET is_captain = 1 WHERE user_id = ?", (user_id,)
        )
        await conn.commit()
        return True


async def remove_from_team(user_id: int) -> Optional[str]:
    """Удаляет участника из его команды (полностью убирает из базы).

    Возвращает имя команды, из которой он вышел, или None если участник не найден.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT team_name FROM participants WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        team_name = row["team_name"]
        await conn.execute("DELETE FROM participants WHERE user_id = ?", (user_id,))
        await conn.commit()
        return team_name


async def export_to_csv() -> str:
    participants = await get_all_participants()
    path = os.path.join(os.path.dirname(__file__), "participants_export.csv")

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["ФИО", "Класс", "Команда", "Капитан", "Телефон", "Username", "Дата регистрации"])
        for p in participants:
            writer.writerow([
                p["fio"],
                p["school_class"],
                p["team_name"],
                "Да" if p.get("is_captain") else "",
                p["phone"],
                p["username"],
                p["registered_at"],
            ])

    return path
