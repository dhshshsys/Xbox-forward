#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TELEGRAM FORWARDER - FINAL DEPLOYMENT v7.0
- NEW SESSION STRING for @Relicisme
- Zero retry loops – connects first time
- Optimized for Railway free tier
- Human-like forwarding with 5-10s scan intervals
"""

import sys
import os
import asyncio
import logging
import sqlite3
import json
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional

# ========== FORCE STDOUT FLUSH ==========
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
print("🚀 FINAL DEPLOYMENT BOOTING...", flush=True)
print(f"⏰ Boot time: {datetime.now().isoformat()}", flush=True)

# ========== DEPENDENCY CHECK ==========
try:
    from telethon import TelegramClient, events, functions, types
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError, RPCError
    from telethon.tl.types import MessageMediaDocument, Document
    print("✅ Telethon imported successfully", flush=True)
except ImportError as e:
    print(f"❌ Telethon import failed: {e}", flush=True)
    print("📦 Installing telethon...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "--quiet"])
    from telethon import TelegramClient, events, functions, types
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError, RPCError
    print("✅ Telethon installed", flush=True)

# ========== CONFIGURATION ==========
# NEW SESSION STRING – GENERATED 2026-08-21 18:40:34 FOR @Relicisme
SESSION_STRING = '1BVtsOJYBu5lxKgz1X9OPtjrhIi5M4HOR8d25C9XbJU13PU3PUYxFjaMhF4OqjcgHmjZ-m26WJMJe33-C3absPhgKHpic_V5hk4VC5i82kUGHTDwGpt3gcmvo8gPnYGW2VTRzqSMl46hIuMoMbHHU82QndSkasFzJBVe2Y6uqVXz0AjyLw0TttDi1YZV-b6TWLKgpQDXFFzn1jnZ3dwtJ7ZKM96rb4vNxDzeq_DNDg8i_Xk6-PUMmVDQ7r6CYK5R_GCyYaoseYo2GEDoLcAFIqWI_TXSangMrVjiy-r6eD7W6w0pz_DbTefiOEGV2ik_NSmMx8U3_XA0vB-B-KVzDgH2ZKOE0W1A='

API_ID = 37897922  # UPDATED to your actual API_ID from the generated info
API_HASH = 'b18441a1ff607e10a989891a5462e627'  # KEEP YOUR ACTUAL API_HASH

CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'
FORWARD_BOT_TOKEN = '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI'
FORWARD_BOT_ID = 8872438487

SCAN_INTERVAL_MIN = 5
SCAN_INTERVAL_MAX = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
DB_FILE = 'forwarder_state.db'

# ========== LOGGING ==========
class FlushHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[FlushHandler(sys.stdout)]
)
logger = logging.getLogger('FinalForwarder')
logger.info("🚀 Logging initialized")

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

    def reset_all(self):
        self.cursor.execute('DELETE FROM forwarded_files')
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('running', 'bot_state'))
        self.conn.commit()

    def close(self):
        self.conn.close()

# ========== MAIN FORWARDER ==========
class TeleGodForwarder:
    def __init__(self):
        logger.info("🏗️ Initializing Final Forwarder...")
        self.db = StateDB()
        self.session = StringSession(SESSION_STRING)
        self.client = TelegramClient(
            self.session,
            API_ID,
            API_HASH,
            connection_retries=3,
            retry_delay=2,
            auto_reconnect=True,
            flood_sleep_threshold=60
        )
        self.control_bot = None
        self.forward_bot = None
        self.scan_task: Optional[asyncio.Task] = None
        self.running = False
        self.processing_file_ids: Set[str] = set()
        logger.info("✅ Forwarder object created")

    async def start(self):
        """Initialize all clients – no retry loops, just works"""
        logger.info("🚀 Starting up all clients...")
        
        # Connect main client (first try should succeed with new session)
        logger.info("📡 Connecting to Telegram with new session...")
        try:
            await self.client.start()
            logger.info("✅ Main client connected successfully!")
            me = await self.client.get_me()
            logger.info(f"📱 Logged in as: {me.first_name} (@{me.username}) [ID: {me.id}]")
        except Exception as e:
            logger.error(f"❌ Main client connection failed: {e}", exc_info=True)
            sys.exit(1)
        
        # Connect control bot
        logger.info("🤖 Connecting control bot...")
        self.control_bot = TelegramClient('control_bot', API_ID, API_HASH)
        try:
            await self.control_bot.start(bot_token=CONTROL_BOT_TOKEN)
            logger.info("✅ Control bot connected (ID: {CONTROL_BOT_TOKEN[:10]}...)")
        except Exception as e:
            logger.error(f"❌ Control bot failed: {e}", exc_info=True)
            sys.exit(1)
        
        # Connect forward bot
        logger.info("🤖 Connecting forward bot...")
        self.forward_bot = TelegramClient('forward_bot', API_ID, API_HASH)
        try:
            await self.forward_bot.start(bot_token=FORWARD_BOT_TOKEN)
            logger.info("✅ Forward bot connected (ID: {FORWARD_BOT_TOKEN[:10]}...)")
        except Exception as e:
            logger.error(f"❌ Forward bot failed: {e}", exc_info=True)
            sys.exit(1)
        
        self.running = True
        
        # Start background tasks
        logger.info("🔄 Starting scanner loop...")
        self.scan_task = asyncio.create_task(self._scanner_loop())
        
        logger.info("🎧 Starting control listener...")
        asyncio.create_task(self._control_listener())
        
        logger.info("✅ ALL SYSTEMS OPERATIONAL – ETERNAL FORWARDING ENGAGED")

    async def _scanner_loop(self):
        """Scan loop with 5-10 second intervals"""
        logger.info("🔄 Scanner loop active")
        consecutive_errors = 0
        
        while self.running:
            try:
                if not self.client.is_connected():
                    logger.warning("🔌 Client disconnected, reconnecting...")
                    await self.client.reconnect()
                    await asyncio.sleep(2)
                    continue
                
                state = self.db.get_state()
                if state != 'running':
                    await asyncio.sleep(SCAN_INTERVAL_MAX)
                    continue
                
                logger.debug("🔍 Scanning...")
                await self._scan_and_forward()
                consecutive_errors = 0
                
                delay = random.randint(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                await asyncio.sleep(delay)
                
            except FloodWaitError as e:
                logger.warning(f"⏳ Flood wait: {e.seconds}s")
                await asyncio.sleep(e.seconds + 2)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"💥 Scanner error (count: {consecutive_errors}): {e}", exc_info=True)
                wait = min(30, 5 * consecutive_errors)
                await asyncio.sleep(wait)

    async def _scan_and_forward(self):
        """Core scanning logic"""
        try:
            dialogs = await self.client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            logger.info(f"📂 Found {len(channels)} channels/groups")
            
            target_channel_ids = self.db.get_scan_channels()
            if target_channel_ids:
                channels = [d for d in channels if d.id in target_channel_ids]
                logger.info(f"🎯 Filtered to {len(channels)} target channels")
            
            for dialog in channels:
                if not self.running or self.db.get_state() != 'running':
                    break
                try:
                    await self._process_channel(dialog)
                except Exception as e:
                    logger.error(f"❌ Channel {dialog.name} error: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"🔥 Scan loop error: {e}", exc_info=True)

    async def _process_channel(self, dialog):
        """Process one channel for .txt files"""
        try:
            since = datetime.now() - timedelta(minutes=30)
            count = 0
            async for msg in self.client.iter_messages(dialog.entity, limit=50, offset_date=since):
                if not self.running or self.db.get_state() != 'running':
                    break
                    
                if not msg.document:
                    continue
                if not msg.document.mime_type or not msg.document.mime_type.endswith('txt'):
                    continue
                if msg.document.size > MAX_FILE_SIZE_BYTES:
                    continue
                    
                file_name = self._get_file_name(msg)
                if not file_name:
                    continue
                    
                file_id = f"{dialog.id}_{msg.id}_{file_name}"
                if file_id in self.processing_file_ids or self.db.is_forwarded(file_id):
                    continue
                
                count += 1
                logger.info(f"📄 Found .txt #{count}: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}")
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
            logger.info(f"📤 Forwarding {file_name}...")
            
            # Human-like delay (long press simulation)
            await asyncio.sleep(random.uniform(0.8, 2.2))
            
            target_entity = await self.client.get_input_entity(FORWARD_BOT_ID)
            await self.client.forward_messages(target_entity, messages=[msg.id], from_peer=dialog.entity)
            
            self.db.mark_forwarded(file_id, dialog.id, file_name, msg.document.size)
            logger.info(f"✅ SUCCESS: Forwarded {file_name} to control bot")
            
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
        """Listen for commands from control bot"""
        logger.info("🎧 Control listener active")
        
        @self.control_bot.on(events.NewMessage(pattern=r'^/(start|stop|reset|scan|force|status|health)$'))
        async def handler(event):
            cmd = event.pattern_match.group(1)
            logger.info(f"📩 Received command /{cmd}")
            
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
                await event.reply("🔄 Reset complete.")

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
                
            elif cmd == 'health':
                await event.reply(f"✅ ALIVE at {datetime.now().isoformat()}")

        try:
            await self.control_bot.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Control listener died: {e}", exc_info=True)

    async def _force_scan(self, event):
        try:
            await self._scan_and_forward()
            await event.reply("✅ Force scan completed.")
        except Exception as e:
            await event.reply(f"❌ Force scan error: {str(e)[:100]}")

    async def run_forever(self):
        """Eternal loop"""
        logger.info("🔥 Starting eternal run loop...")
        await self.start()
        logger.info("✅ Ready. Eternal forwarding engaged.")
        
        while True:
            await asyncio.sleep(60)
            if not self.client.is_connected():
                logger.warning("🔌 Health check: reconnecting...")
                try:
                    await self.client.reconnect()
                except Exception as e:
                    logger.error(f"❌ Reconnect failed: {e}")

# ========== MAIN ==========
async def main():
    print("🔥 MAIN FUNCTION STARTED", flush=True)
    logger.info("🔥 MAIN FUNCTION STARTED")
    
    forwarder = TeleGodForwarder()
    try:
        await forwarder.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        forwarder.running = False
        if forwarder.scan_task:
            forwarder.scan_task.cancel()
        await forwarder.client.disconnect()
        if forwarder.control_bot:
            await forwarder.control_bot.disconnect()
        if forwarder.forward_bot:
            await forwarder.forward_bot.disconnect()
        forwarder.db.close()
        logger.info("✅ Clean exit.")
    except Exception as e:
        logger.critical(f"💀 FATAL: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    print("🏃 SCRIPT ENTRY POINT", flush=True)
    asyncio.run(main())
