import aiosqlite
from datetime import datetime, timedelta

DB_NAME = bot_database.db

# ========== ИНИЦИАЛИЗАЦИЯ ==========
async def init_db()
    async with aiosqlite.connect(DB_NAME) as db
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_username TEXT,
                type TEXT NOT NULL,              -- 'question'  'idea'
                content TEXT,
                media_type TEXT,                 -- 'photo'  'video'  'document'  NULL
                media_file_id TEXT,
                status TEXT DEFAULT 'pending',   -- pending  taken  approved  rejected  answered
                taken_by INTEGER,
                taken_by_username TEXT,
                taken_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()


# ========== СОЗДАНИЕ ТИКЕТА ==========
async def create_ticket(user_id, username, ticket_type, content, media_type=None, media_file_id=None)
    async with aiosqlite.connect(DB_NAME) as db
        cursor = await db.execute(
            INSERT INTO tickets (user_id, user_username, type, content, media_type, media_file_id)
               VALUES (, , , , , ),
            (user_id, username, ticket_type, content or , media_type, media_file_id)
        )
        await db.commit()
        return cursor.lastrowid


# ========== ПОЛУЧЕНИЕ ==========
async def get_ticket(ticket_id)
    async with aiosqlite.connect(DB_NAME) as db
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(SELECT  FROM tickets WHERE id = , (ticket_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_ticket_status(ticket_id)
    async with aiosqlite.connect(DB_NAME) as db
        cursor = await db.execute(SELECT status FROM tickets WHERE id = , (ticket_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_old_pending_tickets(hours=24)
    async with aiosqlite.connect(DB_NAME) as db
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            SELECT  FROM tickets WHERE status = 'pending' AND created_at   ORDER BY created_at ASC,
            (cutoff,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ========== АТОМАРНЫЙ ЗАХВАТ ТИКЕТА ==========
async def take_ticket(ticket_id, admin_id, admin_username)
    Возвращает True, если удалось захватить. False, если уже занятобработан.
    async with aiosqlite.connect(DB_NAME) as db
        cursor = await db.execute(
            UPDATE tickets
               SET status = 'taken', taken_by = , taken_by_username = , taken_at = 
               WHERE id =  AND status = 'pending',
            (admin_id, admin_username, datetime.now().isoformat(), ticket_id)
        )
        await db.commit()
        return cursor.rowcount  0


# ========== ОБНОВЛЕНИЕ СТАТУСА ==========
async def update_status(ticket_id, status)
    async with aiosqlite.connect(DB_NAME) as db
        await db.execute(UPDATE tickets SET status =  WHERE id = , (status, ticket_id))
        await db.commit()