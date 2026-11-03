# database.py
import os
from pathlib import Path
import aiosqlite

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица юзеров
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT 'gpt-4o'
            )
        """)
        # Таблица для истории сообщений (память бота)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        await db.commit()

async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, balance, model FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"user_id": row[0], "balance": row[1], "model": row[2]}
            return None

async def create_user_if_not_exists(user_id: int, start_balance: int = 100_000):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, start_balance),
        )
        await db.commit()

async def update_balance(user_id: int, new_balance: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        await db.commit()

async def set_user_model(user_id: int, model: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET model = ? WHERE user_id = ?", (model, user_id))
        await db.commit()

# --- Работа с памятью бота ---
async def add_message(user_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        await db.commit()

async def get_history(user_id: int, limit: int = 6) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            # Возвращаем в хронологическом порядке (сначала старые)
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

async def clear_history(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.commit()
