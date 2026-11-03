import aiosqlite

DB_PATH = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT 'gpt-4o'
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
