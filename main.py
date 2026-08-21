#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TELEGRAM AUTO-FORWARDER v3.0 - GOD MODE
- Session-based login (no OTP)
- Scans all channels for .txt files < 50MB
- Forwards like human (long press + forward simulation)
- Bot control commands: /start, /stop, /reset, /scan, /force, /status
- Designed for Railway free tier & Termux
"""

import asyncio
import logging
import sqlite3
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
import random

from telethon import TelegramClient, events, functions, types
from telethon.tl.types import MessageMediaDocument, Document, InputPeerUser, InputPeerChannel
from telethon.errors import FloodWaitError, RPCError

# ========== CONFIGURATION ==========
API_ID = 2040  # Replace with your actual API ID (from my.telegram.org)
API_HASH = 'b18441a1ff607e10a989891a5462e627'  # Replace with your actual API hash
SESSION_STRING = '1BVtsOJYBu8SiM6Fpe8d4HdSK80lEBFECtCwfjMOtR8NfQ59UBGqRjY7xFkOc5xP1dcG9nF0E_sC6yN06fkY_X6_axjKUfefNsOS-ktz_S5KxH5gLQKRvo6sBEfMGOX84ZmPm3ZNTqKjjOwvIqmIxDAwApcGc2s7Z4i3875Wiz-3JYh2MPFjQiQUE618FxrRBrOp8BZBxppI96b2Nr8WD_lKbJ8bb5BnCiVsyPh8Nlmq4uc1ykeAw134cHnUXXlDDMQsPNWa1muwoMrq1pp0ESYse5kPrx8txpvWAZlAbbEFENGNUjAZniODJNrpRq43PJ8YxQEqRdbtJy49R4jE0lIOhADC6Ta0='

CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'
FORWARD_BOT_TOKEN = '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI'
FORWARD_BOT_ID = 8872438487  # Numeric ID of forward bot

SCAN_INTERVAL_MIN = 5   # seconds
SCAN_INTERVAL_MAX = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DB_FILE = 'forwarder_state.db'

# ========== LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('TeleGodForwarder')

# ========== DATABASE ==========
class StateDB:
    def __init__(self, db_path=DB_FILE):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
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
        # Set default state if not exists
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
        return []  # Empty = scan all channels

    def set_scan_channels(self, channel_ids: List[int]):
        val = ','.join(str(cid) for cid in channel_ids)
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', (val, 'scan_channels'))
        self.conn.commit()

    def reset_all(self):
        self.cursor.execute('DELETE FROM forwarded_files')
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('running', 'bot_state'))
        self.conn.commit()

# ========== MAIN FORWARDER ==========
class TeleGodForwarder:
    def __init__(self):
        self.db = StateDB()
        self.client = TelegramClient(
            StringSession(SESSION_STRING),
            API_ID,
            API_HASH,
            connection_retries=10,
            retry_delay=2,
            auto_reconnect=True
        )
        self.control_bot = TelegramClient('control_bot', API_ID, API_HASH)
        self.forward_bot = TelegramClient('forward_bot', API_ID, API_HASH)
        self.scan_task: Optional[asyncio.Task] = None
        self.running = False
        self.processing_file_ids: Set[str] = set()  # Prevent duplicate processing

    async def start(self):
        """Initialize all clients and start scanning"""
        logger.info("🚀 Initializing God Forwarder...")
        await self.client.start()
        await self.control_bot.start(bot_token=CONTROL_BOT_TOKEN)
        await self.forward_bot.start(bot_token=FORWARD_BOT_TOKEN)
        self.running = True
        logger.info("✅ All clients connected successfully!")

        # Start background scanner
        self.scan_task = asyncio.create_task(self._scanner_loop())
        # Start control bot listener
        asyncio.create_task(self._control_listener())
        logger.info("📡 Scanner and control listener active. Waiting for eternity...")

    async def _scanner_loop(self):
        """Main scan loop every 5-10 seconds"""
        while self.running:
            try:
                state = self.db.get_state()
                if state != 'running':
                    logger.info(f"⏸️ Bot state is '{state}', skipping scan cycle.")
                    await asyncio.sleep(SCAN_INTERVAL_MAX)
                    continue

                logger.info("🔍 Scanning channels for new .txt files...")
                await self._scan_and_forward()
                delay = random.randint(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                logger.debug(f"⏳ Next scan in {delay}s")
                await asyncio.sleep(delay)
            except FloodWaitError as e:
                logger.warning(f"⏳ Rate limited, waiting {e.seconds}s...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.error(f"💥 Scanner loop error: {e}", exc_info=True)
                await asyncio.sleep(10)  # Backoff on errors

    async def _scan_and_forward(self):
        """Fetch dialogs, filter channels, scan for .txt files under 50MB, forward"""
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
                logger.error(f"❌ Error processing channel {dialog.name}: {e}", exc_info=True)

    async def _process_channel(self, dialog):
        """Process one channel: get recent messages with .txt files <50MB"""
        try:
            # Get messages from last 30 minutes (avoid scanning entire history)
            since = datetime.now() - timedelta(minutes=30)
            async for msg in self.client.iter_messages(dialog.entity, limit=50, offset_date=since):
                if not self.running or self.db.get_state() != 'running':
                    break
                if not msg.document or not msg.document.mime_type or not msg.document.mime_type.endswith('txt'):
                    continue
                # Check size
                if msg.document.size > MAX_FILE_SIZE_BYTES:
                    logger.debug(f"⏭️ Skipping {msg.id} - size {msg.document.size/1024/1024:.2f}MB > 50MB")
                    continue
                file_name = self._get_file_name(msg)
                if not file_name:
                    continue
                file_id = f"{dialog.id}_{msg.id}_{file_name}"
                if file_id in self.processing_file_ids:
                    continue
                if self.db.is_forwarded(file_id):
                    continue

                logger.info(f"📄 Found new .txt: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}")
                await self._forward_file(msg, dialog, file_id, file_name)
                # Human-like delay between forwards
                await asyncio.sleep(random.uniform(1.0, 3.5))
        except FloodWaitError as e:
            logger.warning(f"🐢 Flood wait on channel {dialog.name}: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"🔥 Failed processing {dialog.name}: {e}", exc_info=True)

    async def _forward_file(self, msg, dialog, file_id, file_name):
        """Forward a file to the control bot with human-like behavior"""
        try:
            self.processing_file_ids.add(file_id)
            # Simulate human forward: long press delay
            await asyncio.sleep(random.uniform(0.8, 2.2))
            # Forward to the target bot (the bot we control)
            target_entity = await self.client.get_input_entity(FORWARD_BOT_ID)
            await self.client.forward_messages(target_entity, messages=[msg.id], from_peer=dialog.entity)
            # Mark as forwarded
            self.db.mark_forwarded(file_id, dialog.id, file_name, msg.document.size)
            logger.info(f"✅ Forwarded {file_name} to control bot (ID: {FORWARD_BOT_ID})")
            # Extra human-like: random pause after forward
            await asyncio.sleep(random.uniform(0.5, 1.5))
        except FloodWaitError as e:
            logger.warning(f"🐢 Flood wait on forward: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"❌ Forward failed for {file_name}: {e}", exc_info=True)
        finally:
            self.processing_file_ids.discard(file_id)

    def _get_file_name(self, msg) -> str:
        """Extract filename from document attributes"""
        for attr in msg.document.attributes:
            if isinstance(attr, types.DocumentAttributeFilename):
                return attr.file_name
        return f"file_{msg.id}.txt"

    # ========== CONTROL BOT HANDLERS ==========
    async def _control_listener(self):
        """Listen for commands from control bot"""
        @self.control_bot.on(events.NewMessage(pattern=r'^/(start|stop|reset|scan|force|status)$'))
        async def handler(event):
            cmd = event.pattern_match.group(1)
            user_id = event.sender_id
            logger.info(f"📩 Received command /{cmd} from user {user_id}")

            if cmd == 'start':
                if self.db.get_state() != 'running':
                    self.db.set_state('running')
                    self.running = True
                    if self.scan_task is None or self.scan_task.done():
                        self.scan_task = asyncio.create_task(self._scanner_loop())
                    await event.reply("✅ Bot started. Scanning for .txt files every 5-10s.")
                else:
                    await event.reply("ℹ️ Bot is already running.")

            elif cmd == 'stop':
                self.db.set_state('stopped')
                self.running = False
                if self.scan_task and not self.scan_task.done():
                    self.scan_task.cancel()
                    try:
                        await self.scan_task
                    except asyncio.CancelledError:
                        pass
                await event.reply("⏹️ Bot stopped. No further scanning or forwarding.")

            elif cmd == 'reset':
                self.db.reset_all()
                self.processing_file_ids.clear()
                await event.reply("🔄 All state reset. Forward history cleared. Bot set to running.")
                # Restart scanner if not running
                if self.db.get_state() == 'running' and (self.scan_task is None or self.scan_task.done()):
                    self.running = True
                    self.scan_task = asyncio.create_task(self._scanner_loop())

            elif cmd == 'scan':
                # Force immediate scan
                if self.db.get_state() == 'running':
                    asyncio.create_task(self._force_scan(event))
                    await event.reply("🔍 Forced scan initiated. Check logs for details.")
                else:
                    await event.reply("⚠️ Bot is stopped. Use /start to resume.")

            elif cmd == 'force':
                # Force forward specific file (optional: pass file ID)
                await event.reply("📌 Force command: please provide file_id in format: /force <file_id>")
                # Extended logic can be added

            elif cmd == 'status':
                state = self.db.get_state()
                forwarded_count = self.db.cursor.execute('SELECT COUNT(*) FROM forwarded_files').fetchone()[0]
                channels = self.db.get_scan_channels()
                ch_str = ', '.join(str(c) for c in channels) if channels else 'ALL'
                await event.reply(
                    f"📊 **Status**\n"
                    f"State: {state}\n"
                    f"Forwarded files: {forwarded_count}\n"
                    f"Scanned channels: {ch_str}\n"
                    f"Scan interval: {SCAN_INTERVAL_MIN}-{SCAN_INTERVAL_MAX}s\n"
                    f"Max file size: 50MB"
                )

        # Keep control bot running
        await self.control_bot.run_until_disconnected()

    async def _force_scan(self, event):
        """Trigger an immediate scan cycle"""
        try:
            logger.info("⚡ Force scan triggered by command")
            await self._scan_and_forward()
            await event.reply("✅ Force scan completed.")
        except Exception as e:
            logger.error(f"💥 Force scan error: {e}", exc_info=True)
            await event.reply(f"❌ Force scan failed: {str(e)[:100]}")

    async def run_forever(self):
        """Main entry point - runs until interrupted"""
        await self.start()
        # Keep main task alive
        while True:
            await asyncio.sleep(3600)  # Sleep 1 hour, check health

# ========== STRING SESSION HELPER ==========
from telethon.sessions import StringSession

# ========== MAIN ==========
async def main():
    forwarder = TeleGodForwarder()
    try:
        await forwarder.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
        forwarder.running = False
        if forwarder.scan_task and not forwarder.scan_task.done():
            forwarder.scan_task.cancel()
            try:
                await forwarder.scan_task
            except asyncio.CancelledError:
                pass
        await forwarder.client.disconnect()
        await forwarder.control_bot.disconnect()
        await forwarder.forward_bot.disconnect()
        logger.info("✅ All clients disconnected. Goodbye.")

if __name__ == '__main__':
    # Install missing deps: pip install telethon sqlite3 asyncio
    asyncio.run(main())
