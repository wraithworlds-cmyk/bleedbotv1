import os
import aiosqlite
from pathlib import Path
from discord.ext import commands

# Railway volumes expose RAILWAY_VOLUME_MOUNT_PATH automatically.
# Locally, this falls back to ./data/bot.db.
DB_PATH = Path(os.getenv("DB_PATH", Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "data")) / "bot.db"))

class Database(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        DB_PATH.parent.mkdir(exist_ok=True)
        self.bot.db = None

    async def cog_load(self):
        self.bot.db = await aiosqlite.connect(DB_PATH)
        self.bot.db.row_factory = aiosqlite.Row
        await self.bot.db.executescript("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            welcome_dm_enabled INTEGER NOT NULL DEFAULT 0,
            welcome_dm_message TEXT NOT NULL DEFAULT 'Welcome to {server}, {user}! 🎉',
            ticket_category_id INTEGER,
            ticket_log_channel_id INTEGER,
            ticket_reminders_enabled INTEGER NOT NULL DEFAULT 0,
            ticket_reminder_minutes INTEGER NOT NULL DEFAULT 120,
            ticket_reminder_message TEXT NOT NULL DEFAULT '🎫 Reminder: staff is waiting for your response in {server}. Your ticket is {channel}.'
        );

        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_user_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_staff_activity_at TEXT,
            last_reminder_at TEXT,
            claimed_by INTEGER
        );
        """)

        # Safe migration for databases created by V1.
        migrations = [
            ("guild_settings", "ticket_reminder_message", "TEXT NOT NULL DEFAULT '🎫 Reminder: staff is waiting for your response in {server}. Your ticket is {channel}.'"),
            ("tickets", "last_activity_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("tickets", "last_user_activity_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("tickets", "last_staff_activity_at", "TEXT"),
            ("tickets", "last_reminder_at", "TEXT"),
            ("tickets", "claimed_by", "INTEGER"),
        ]
        for table, column, definition in migrations:
            try:
                await self.bot.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except Exception as e:
                if "duplicate column name" not in str(e).lower():
                    raise

        await self.bot.db.commit()

    async def cog_unload(self):
        if self.bot.db:
            await self.bot.db.close()

async def ensure_guild(db, guild_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
        (guild_id,)
    )
    await db.commit()

async def get_settings(db, guild_id: int):
    await ensure_guild(db, guild_id)
    cursor = await db.execute(
        "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
    )
    return await cursor.fetchone()

async def update_setting(db, guild_id: int, column: str, value):
    allowed = {
        "welcome_dm_enabled",
        "welcome_dm_message",
        "ticket_category_id",
        "ticket_log_channel_id",
        "ticket_reminders_enabled",
        "ticket_reminder_minutes",
        "ticket_reminder_message",
    }
    if column not in allowed:
        raise ValueError("Invalid setting")
    await ensure_guild(db, guild_id)
    await db.execute(
        f"UPDATE guild_settings SET {column} = ? WHERE guild_id = ?",
        (value, guild_id)
    )
    await db.commit()

async def setup(bot):
    await bot.add_cog(Database(bot))
