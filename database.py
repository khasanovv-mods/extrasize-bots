import aiosqlite
from datetime import datetime, timedelta

DB_NAME = "bot_database.db"


# ==================== ИНИЦИАЛИЗАЦИЯ ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Тикеты
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_username TEXT,
                type TEXT NOT NULL,
                content TEXT,
                media_type TEXT,
                media_file_id TEXT,
                status TEXT DEFAULT 'pending',
                taken_by INTEGER,
                taken_by_username TEXT,
                taken_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Живые чаты
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                admin_id INTEGER,
                admin_username TEXT,
                active INTEGER DEFAULT 0,
                closed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP
            )
            """
        )

        await db.commit()


# ==================== ТИКЕТЫ ====================
async def create_ticket(user_id, username, ticket_type, content, media_type=None, media_file_id=None):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO tickets (user_id, user_username, type, content, media_type, media_file_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, ticket_type, content or "", media_type, media_file_id)
        )
        await db.commit()
        return cursor.lastrowid


async def get_ticket(ticket_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_ticket_status(ticket_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_old_pending_tickets(hours=24):
    async with aiosqlite.connect(DB_NAME) as db:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tickets WHERE status = 'pending' AND created_at < ? "
            "ORDER BY created_at ASC",
            (cutoff,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def take_ticket(ticket_id, admin_id, admin_username):
    """Атомарный захват. True — успех."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "UPDATE tickets "
            "SET status = 'taken', taken_by = ?, taken_by_username = ?, taken_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (admin_id, admin_username, datetime.now().isoformat(), ticket_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_status(ticket_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        await db.commit()


# ==================== ЖИВЫЕ ЧАТЫ ====================
async def close_stale_chats():
    """Сбросить незавершённые чаты при старте бота."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE chats SET active = 0, closed = 1 WHERE active = 1")
        await db.commit()


async def create_chat_request(user_id, username):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO chats (user_id, username, active, closed) VALUES (?, ?, 0, 0)",
            (user_id, username)
        )
        await db.commit()
        return cursor.lastrowid


async def get_chat(chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def accept_chat(chat_id, admin_id, admin_username):
    """Атомарный приём заявки. True — успех."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "UPDATE chats "
            "SET admin_id = ?, admin_username = ?, active = 1, accepted_at = ? "
            "WHERE id = ? AND active = 0 AND closed = 0 AND admin_id IS NULL",
            (admin_id, admin_username, datetime.now().isoformat(), chat_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def close_chat(chat_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE chats SET active = 0, closed = 1 WHERE id = ?",
            (chat_id,)
        )
        await db.commit()


async def get_active_chat_partner(user_id):
    """Вернёт partner_id, если есть активный чат, иначе None."""
    async with aiosqlite.connect(DB_NAME) as db:
        # юзер ищет админа
        cursor = await db.execute(
            "SELECT admin_id FROM chats WHERE user_id = ? AND active = 1 AND closed = 0",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return row[0]

        # админ ищет юзера
        cursor = await db.execute(
            "SELECT user_id FROM chats WHERE admin_id = ? AND active = 1 AND closed = 0",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_open_chat_by_user(user_id):
    """Активный или ожидающий чат для юзера."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM chats WHERE user_id = ? AND closed = 0 ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def has_active_chat(user_id):
    """True, если у юзера есть активный чат."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT 1 FROM chats WHERE user_id = ? AND active = 1 AND closed = 0 LIMIT 1",
            (user_id,)
        )
        return (await cursor.fetchone()) is not None
