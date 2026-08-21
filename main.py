#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TELEGRAM FORWARDER - RAILWAY STABLE v4.0
- Fixes AuthKeyDuplicatedError via session exclusivity & auto-regen
- Uses explicit Telethon imports (no telnet collision)
- Implements file-based lock to prevent duplicate workers
- Graceful reconnect with exponential backoff
- Designed for Railway's free tier with ephemeral storage
"""

import asyncio
import logging
import sqlite3
import os
import sys
import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
import fcntl  # For file locking

# CRITICAL: Explicit Telethon imports to avoid 'telnet.py' shadowing
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    AuthKeyDuplicatedError, 
    FloodWaitError, 
    RPCError,
    SessionPasswordNeededError
)
from telethon.tl.types import MessageMediaDocument, Document, InputPeerUser, InputPeerChannel
from telethon.tl.functions import messages

# ========== CONFIGURATION ==========
API_ID = 2040  # REPLACE WITH YOUR ACTUAL API_ID
API_HASH = 'b18441a1ff607e10a989891a5462e627'  # REPLACE WITH YOUR ACTUAL API_HASH
SESSION_STRING = '1BVtsOJYBu8SiM6Fpe8d4HdSK80lEBFECtCwfjMOtR8NfQ59UBGqRjY7xFkOc5xP1dcG9nF0E_sC6yN06fkY_X6_axjKUfefNsOS-ktz_S5KxH5gLQKRvo6sBEfMGOX84ZmPm3ZNTqKjjOwvIqmIxDAwApcGc2s7Z4i3875Wiz-3JYh2MPFjQiQUE618FxrRBrOp8BZBxppI96b2Nr8WD_lKbJ8bb5BnCiVsyPh8Nlmq4uc1ykeAw134cHnUXXlDDMQsPNWa1muwoMrq1pp0ESYse5kPrx8txpvWAZlAbbEFENGNUjAZniODJNrpRq43PJ8YxQEqRdbtJy49R4jE0lIOhADC6Ta0='

CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'
FORWARD_BOT_TOKEN = '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI'
FORWARD_BOT_ID = 8872438487

SCAN_INTERVAL_MIN = 5
SCAN_INTERVAL_MAX = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
DB_FILE = 'forwarder_state.db'
LOCK_FILE = '/tmp/telegram_forwarder.lock'  # Railway writable tmpfs

# ========== LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('RailwayForwarder')

# ========== FILE LOCK ==========
def acquire_lock() -> bool:
    """Prevent multiple Railway instances from running concurrently"""
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        logger.info(f"🔒 Lock acquired (PID: {os.getpid()})")
        return True
    except (IOError, OSError):
        logger.error("❌ Another instance is already running. Exiting.")
        return False

# ========== DATABASE ==========
class StateDB:
    def __init__(self, db_path=DB_FILE):
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.cursor = self.conn.cursor()
        self._init_db()

    def _init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forwarded_files (
                file_id TEXT PRIMARY KEY,
                channel_id INTEGER,
                file_name TEXT,
                file_size INTEGER,
                forwarded_at TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('bot_state', 'running'))
        self.cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('scan_channels', ''))
        self.conn.commit()

    def is_forwarded(self, file_id: str) -> bool:
        self.cursor.execute('SELECT 1 FROM forwarded_files WHERE file_id = ?', (file_id,))
        return self.cursor.fetchone() is not None

    def mark_forwarded(self, file_id: str, channel_id: int, file_name: str, file_size: int):
        self.cursor.execute(
            'INSERT OR REPLACE INTO forwarded_files (file_id, channel_id, file_name, file_size, forwarded_at) VALUES (?, ?, ?, ?, ?)',
            (file_id, channel_id, file_name, file_size, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_state(self) -> str:
        self.cursor.execute('SELECT value FROM config WHERE key = ?', ('bot_state',))
        row = self.cursor.fetchone()
        return row[0] if row else 'running'

    def set_state(self, state: str):
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', (state, 'bot_state'))
        self.conn.commit()

    def get_scan_channels(self) -> List[int]:
        self.cursor.execute('SELECT value FROM config WHERE key = ?', ('scan_channels',))
        row = self.cursor.fetchone()
        if row and row[0]:
            return [int(x.strip()) for x in row[0].split(',') if x.strip()]
        return []

    def set_scan_channels(self, channel_ids: List[int]):
        val = ','.join(str(cid) for cid in channel_ids)
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', (val, 'scan_channels'))
        self.conn.commit()

    def reset_all(self):
        self.cursor.execute('DELETE FROM forwarded_files')
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('running', 'bot_state'))
        self.conn.commit()

    def close(self):
        self.conn.close()

# ========== MAIN FORWARDER ==========
class TeleGodForwarder:
    def __init__(self):
        self.db = StateDB()
        # Use StringSession with explicit error handling
        self.session = StringSession(SESSION_STRING)
        self.client = TelegramClient(
            self.session,
            API_ID,
            API_HASH,
            connection_retries=5,
            retry_delay=3,
            auto_reconnect=True,
            flood_sleep_threshold=60
        )
        self.control_bot = TelegramClient('control_bot', API_ID, API_HASH)
        self.forward_bot = TelegramClient('forward_bot', API_ID, API_HASH)
        self.scan_task: Optional[asyncio.Task] = None
        self.running = False
        self.processing_file_ids: Set[str] = set()
        self.reconnect_attempts = 0

    async def start(self):
        """Initialize all clients with retry logic for AuthKeyDuplicatedError"""
        logger.info("🚀 Initializing Railway-stable Forwarder...")
        
        # Connect main client with retry
        connected = False
        while not connected and self.reconnect_attempts < 5:
            try:
                await self.client.start()
                connected = True
                logger.info("✅ Main client connected successfully.")
            except AuthKeyDuplicatedError:
                self.reconnect_attempts += 1
                logger.warning(f"⚠️ AuthKeyDuplicatedError (attempt {self.reconnect_attempts}/5). Regenerating session...")
                # Force new session by clearing and reinitializing
                self.session = StringSession()  # New empty session
                self.client = TelegramClient(self.session, API_ID, API_HASH)
                await asyncio.sleep(5 * self.reconnect_attempts)
            except Exception as e:
                logger.error(f"🔥 Main client connection error: {e}")
                await asyncio.sleep(10)
        
        if not connected:
            logger.critical("💀 Failed to connect after 5 attempts. Exiting.")
            sys.exit(1)

        # Connect bots
        try:
            await self.control_bot.start(bot_token=CONTROL_BOT_TOKEN)
            await self.forward_bot.start(bot_token=FORWARD_BOT_TOKEN)
            logger.info("✅ Control & Forward bots connected.")
        except Exception as e:
            logger.error(f"❌ Bot connection failed: {e}")
            sys.exit(1)

        self.running = True
        # Start scanner and control listener
        self.scan_task = asyncio.create_task(self._scanner_loop())
        asyncio.create_task(self._control_listener())
        logger.info("📡 All systems operational. Forwarding eternity begins.")

    async def _scanner_loop(self):
        """Scan loop with session health checks"""
        consecutive_errors = 0
        while self.running:
            try:
                if not self.client.is_connected():
                    logger.warning("🔌 Main client disconnected. Reconnecting...")
                    await self.client.reconnect()
                    await asyncio.sleep(2)
                    continue

                state = self.db.get_state()
                if state != 'running':
                    await asyncio.sleep(SCAN_INTERVAL_MAX)
                    continue

                await self._scan_and_forward()
                consecutive_errors = 0  # Reset on success
                delay = random.randint(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                await asyncio.sleep(delay)

            except AuthKeyDuplicatedError:
                consecutive_errors += 1
                logger.error(f"💥 AuthKeyDuplicatedError (count: {consecutive_errors}). Regenerating session...")
                self.session = StringSession()
                self.client = TelegramClient(self.session, API_ID, API_HASH)
                await self.client.start()
                await asyncio.sleep(5)
            except FloodWaitError as e:
                logger.warning(f"⏳ Flood wait: {e.seconds}s")
                await asyncio.sleep(e.seconds + 2)
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"💥 Scanner error (count: {consecutive_errors}): {e}", exc_info=True)
                wait = min(30, 5 * consecutive_errors)
                await asyncio.sleep(wait)

    async def _scan_and_forward(self):
        """Core scanning logic - same as previous but with better error boundaries"""
        try:
            dialogs = await self.client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            target_channel_ids = self.db.get_scan_channels()
            if target_channel_ids:
                channels = [d for d in channels if d.id in target_channel_ids]

            logger.info(f"📂 Scanning {len(channels)} channels/groups")
            for dialog in channels:
                if not self.running or self.db.get_state() != 'running':
                    break
                try:
                    await self._process_channel(dialog)
                except Exception as e:
                    logger.error(f"❌ Channel {dialog.name} error: {e}")
        except Exception as e:
            logger.error(f"🔥 Scan loop error: {e}", exc_info=True)
            raise

    async def _process_channel(self, dialog):
        """Process one channel for .txt files under 50MB"""
        try:
            since = datetime.now() - timedelta(minutes=30)
            async for msg in self.client.iter_messages(dialog.entity, limit=50, offset_date=since):
                if not self.running or self.db.get_state() != 'running':
                    break
                if not msg.document or not msg.document.mime_type or not msg.document.mime_type.endswith('txt'):
                    continue
                if msg.document.size > MAX_FILE_SIZE_BYTES:
                    continue
                file_name = self._get_file_name(msg)
                if not file_name:
                    continue
                file_id = f"{dialog.id}_{msg.id}_{file_name}"
                if file_id in self.processing_file_ids or self.db.is_forwarded(file_id):
                    continue

                logger.info(f"📄 Found new .txt: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}")
                await self._forward_file(msg, dialog, file_id, file_name)
                await asyncio.sleep(random.uniform(1.0, 3.5))
        except FloodWaitError as e:
            logger.warning(f"🐢 Flood wait on {dialog.name}: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"🔥 Process channel {dialog.name} error: {e}", exc_info=True)

    async def _forward_file(self, msg, dialog, file_id, file_name):
        """Forward file with human-like simulation"""
        try:
            self.processing_file_ids.add(file_id)
            await asyncio.sleep(random.uniform(0.8, 2.2))
            target_entity = await self.client.get_input_entity(FORWARD_BOT_ID)
            await self.client.forward_messages(target_entity, messages=[msg.id], from_peer=dialog.entity)
            self.db.mark_forwarded(file_id, dialog.id, file_name, msg.document.size)
            logger.info(f"✅ Forwarded {file_name} to control bot")
            await asyncio.sleep(random.uniform(0.5, 1.5))
        except FloodWaitError as e:
            logger.warning(f"🐢 Forward flood: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"❌ Forward failed {file_name}: {e}", exc_info=True)
        finally:
            self.processing_file_ids.discard(file_id)

    def _get_file_name(self, msg) -> str:
        for attr in msg.document.attributes:
            if isinstance(attr, types.DocumentAttributeFilename):
                return attr.file_name
        return f"file_{msg.id}.txt"

    # ========== CONTROL BOT ==========
    async def _control_listener(self):
        @self.control_bot.on(events.NewMessage(pattern=r'^/(start|stop|reset|scan|force|status)$'))
        async def handler(event):
            cmd = event.pattern_match.group(1)
            logger.info(f"📩 Command /{cmd} from {event.sender_id}")

            if cmd == 'start':
                if self.db.get_state() != 'running':
                    self.db.set_state('running')
                    self.running = True
                    if not self.scan_task or self.scan_task.done():
                        self.scan_task = asyncio.create_task(self._scanner_loop())
                    await event.reply("✅ Bot started.")
                else:
                    await event.reply("ℹ️ Already running.")

            elif cmd == 'stop':
                self.db.set_state('stopped')
                self.running = False
                if self.scan_task and not self.scan_task.done():
                    self.scan_task.cancel()
                await event.reply("⏹️ Bot stopped.")

            elif cmd == 'reset':
                self.db.reset_all()
                self.processing_file_ids.clear()
                await event.reply("🔄 Reset complete. Bot running.")

            elif cmd == 'scan':
                if self.db.get_state() == 'running':
                    asyncio.create_task(self._force_scan(event))
                    await event.reply("🔍 Force scan started.")
                else:
                    await event.reply("⚠️ Bot stopped. Use /start.")

            elif cmd == 'status':
                state = self.db.get_state()
                fwd_count = self.db.cursor.execute('SELECT COUNT(*) FROM forwarded_files').fetchone()[0]
                chs = self.db.get_scan_channels()
                ch_str = ', '.join(str(c) for c in chs) if chs else 'ALL'
                await event.reply(
                    f"📊 **Status**\n"
                    f"State: {state}\n"
                    f"Forwarded: {fwd_count}\n"
                    f"Channels: {ch_str}\n"
                    f"Interval: {SCAN_INTERVAL_MIN}-{SCAN_INTERVAL_MAX}s\n"
                    f"Max size: 50MB"
                )

        await self.control_bot.run_until_disconnected()

    async def _force_scan(self, event):
        try:
            await self._scan_and_forward()
            await event.reply("✅ Force scan done.")
        except Exception as e:
            await event.reply(f"❌ Force scan error: {str(e)[:100]}")

    async def run_forever(self):
        """Eternal loop with health checks"""
        await self.start()
        while True:
            await asyncio.sleep(300)  # Health check every 5 min
            if not self.client.is_connected():
                logger.warning("🔌 Health check: reconnecting main client...")
                await self.client.reconnect()
            if not self.control_bot.is_connected():
                logger.warning("🔌 Health check: reconnecting control bot...")
                await self.control_bot.reconnect()

# ========== MAIN ==========
async def main():
    # Acquire lock to prevent double-run on Railway
    if not acquire_lock():
        sys.exit(1)
    
    forwarder = TeleGodForwarder()
    try:
        await forwarder.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        forwarder.running = False
        if forwarder.scan_task:
            forwarder.scan_task.cancel()
        await forwarder.client.disconnect()
        await forwarder.control_bot.disconnect()
        await forwarder.forward_bot.disconnect()
        forwarder.db.close()
        logger.info("✅ Clean exit.")

if __name__ == '__main__':
    asyncio.run(main())
