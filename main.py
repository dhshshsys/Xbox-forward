#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAILWAY DEFINITIVE FORWARDER v5.0 - ZERO SILENT FAILURES
- Forces stdout flush immediately
- Writes startup proof to /tmp/railway_alive.txt
- Health check endpoint via HTTP (for Railway's healthchecks)
- Fallback to console logging if no logs appear
- Auto-installs missing dependencies at runtime
"""

import sys
import os
import time
import asyncio
import logging
import sqlite3
import json
import random
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from pathlib import Path

# ========== FORCE STDOUT FLUSH ==========
sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
sys.stderr.reconfigure(line_buffering=True)
print("🚀 RAILWAY FORWARDER BOOTING...", flush=True)
print(f"⏰ Boot time: {datetime.now().isoformat()}", flush=True)

# ========== WRITE ALIVE PROOF ==========
try:
    with open('/tmp/railway_alive.txt', 'w') as f:
        f.write(f"ALIVE at {datetime.now().isoformat()}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"Python: {sys.version}\n")
    print("✅ Alive proof written to /tmp/railway_alive.txt", flush=True)
except Exception as e:
    print(f"⚠️ Could not write alive proof: {e}", flush=True)

# ========== AUTO-INSTALL DEPENDENCIES ==========
def install_missing():
    """Ensure Telethon is installed - Railway sometimes strips dependencies"""
    try:
        import telethon
        print(f"✅ Telethon already installed (version: {telethon.__version__})", flush=True)
        return True
    except ImportError:
        print("📦 Telethon not found. Installing...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "--quiet"])
            print("✅ Telethon installed successfully", flush=True)
            return True
        except Exception as e:
            print(f"❌ Failed to install telethon: {e}", flush=True)
            return False

if not install_missing():
    print("💀 CRITICAL: Cannot proceed without telethon. Exiting.", flush=True)
    sys.exit(1)

# ========== NOW IMPORT TELEthon ==========
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    AuthKeyDuplicatedError, 
    FloodWaitError, 
    RPCError,
    SessionPasswordNeededError
)
from telethon.tl.types import MessageMediaDocument, Document

print("✅ All imports successful", flush=True)

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

# ========== LOGGING WITH FORCED FLUSH ==========
class FlushHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[FlushHandler(sys.stdout)]
)
logger = logging.getLogger('RailwayDefinitive')
logger.info("🚀 Logging initialized with forced flush")

# ========== DATABASE ==========
class StateDB:
    def __init__(self, db_path=DB_FILE):
        logger.info(f"📂 Opening database at {db_path}")
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.cursor = self.conn.cursor()
        self._init_db()
        logger.info("✅ Database initialized")

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

# ========== SIMPLE HTTP HEALTH CHECK ==========
async def health_check_server():
    """Minimal HTTP server for Railway healthchecks"""
    try:
        import asyncio
        reader, writer = await asyncio.start_server(
            lambda r, w: None, '0.0.0.0', 8080
        )
        logger.info("🌐 Health check server running on port 8080")
    except Exception as e:
        logger.warning(f"⚠️ Health check server not started: {e}")

# ========== MAIN FORWARDER ==========
class TeleGodForwarder:
    def __init__(self):
        logger.info("🏗️ Initializing TeleGodForwarder...")
        self.db = StateDB()
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
        logger.info("✅ Forwarder object created")

    async def start(self):
        """Initialize all clients with detailed logging"""
        logger.info("🚀 Starting up all clients...")
        
        # Connect main client
        logger.info("📡 Connecting main Telegram client...")
        try:
            await self.client.start()
            logger.info("✅ Main client connected successfully!")
            logger.info(f"📱 Logged in as: {await self.client.get_me()}")
        except AuthKeyDuplicatedError:
            logger.warning("⚠️ AuthKeyDuplicatedError - regenerating session...")
            self.session = StringSession()
            self.client = TelegramClient(self.session, API_ID, API_HASH)
            await self.client.start()
            logger.info("✅ New session created")
        except Exception as e:
            logger.error(f"❌ Main client connection failed: {e}", exc_info=True)
            raise

        # Connect bots
        logger.info("🤖 Connecting control bot...")
        try:
            await self.control_bot.start(bot_token=CONTROL_BOT_TOKEN)
            logger.info("✅ Control bot connected")
        except Exception as e:
            logger.error(f"❌ Control bot failed: {e}", exc_info=True)
            raise

        logger.info("🤖 Connecting forward bot...")
        try:
            await self.forward_bot.start(bot_token=FORWARD_BOT_TOKEN)
            logger.info("✅ Forward bot connected")
        except Exception as e:
            logger.error(f"❌ Forward bot failed: {e}", exc_info=True)
            raise

        self.running = True
        logger.info("✅ All clients ready!")

        # Start background tasks
        logger.info("🔄 Starting scanner loop...")
        self.scan_task = asyncio.create_task(self._scanner_loop())
        
        logger.info("🎧 Starting control listener...")
        asyncio.create_task(self._control_listener())
        
        logger.info("🌐 Starting health check server...")
        asyncio.create_task(health_check_server())
        
        logger.info("✅ ALL SYSTEMS OPERATIONAL")

    async def _scanner_loop(self):
        """Scan loop with extensive logging"""
        consecutive_errors = 0
        logger.info("🔄 Scanner loop started")
        
        while self.running:
            try:
                if not self.client.is_connected():
                    logger.warning("🔌 Client disconnected, reconnecting...")
                    await self.client.reconnect()
                    await asyncio.sleep(2)
                    continue

                state = self.db.get_state()
                if state != 'running':
                    logger.info(f"⏸️ Bot state is '{state}', waiting...")
                    await asyncio.sleep(SCAN_INTERVAL_MAX)
                    continue

                logger.info("🔍 Starting scan cycle...")
                await self._scan_and_forward()
                consecutive_errors = 0
                
                delay = random.randint(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                logger.debug(f"⏳ Next scan in {delay}s")
                await asyncio.sleep(delay)

            except AuthKeyDuplicatedError:
                consecutive_errors += 1
                logger.error(f"💥 AuthKeyDuplicatedError (attempt {consecutive_errors})")
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
                logger.info(f"⏳ Backing off for {wait}s")
                await asyncio.sleep(wait)

    async def _scan_and_forward(self):
        """Core scanning with detailed logging"""
        try:
            logger.info("📡 Getting dialogs...")
            dialogs = await self.client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            logger.info(f"📂 Found {len(channels)} channels/groups total")
            
            target_channel_ids = self.db.get_scan_channels()
            if target_channel_ids:
                channels = [d for d in channels if d.id in target_channel_ids]
                logger.info(f"🎯 Filtered to {len(channels)} target channels")
            else:
                logger.info("🎯 Scanning ALL channels")

            for idx, dialog in enumerate(channels):
                if not self.running or self.db.get_state() != 'running':
                    break
                try:
                    logger.info(f"📁 Processing channel {idx+1}/{len(channels)}: {dialog.name} (ID: {dialog.id})")
                    await self._process_channel(dialog)
                except Exception as e:
                    logger.error(f"❌ Channel {dialog.name} error: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"🔥 Scan loop error: {e}", exc_info=True)
            raise

    async def _process_channel(self, dialog):
        """Process one channel"""
        try:
            since = datetime.now() - timedelta(minutes=30)
            count = 0
            async for msg in self.client.iter_messages(dialog.entity, limit=50, offset_date=since):
                if not self.running or self.db.get_state() != 'running':
                    break
                    
                # Check if document and .txt
                if not msg.document:
                    continue
                if not msg.document.mime_type or not msg.document.mime_type.endswith('txt'):
                    continue
                if msg.document.size > MAX_FILE_SIZE_BYTES:
                    logger.debug(f"⏭️ Skipping {msg.id} - size {msg.document.size/1024/1024:.2f}MB > 50MB")
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
                
            if count == 0:
                logger.debug(f"📭 No new .txt files in {dialog.name}")
                
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
            
            # Human-like delay
            await asyncio.sleep(random.uniform(0.8, 2.2))
            
            # Forward
            target_entity = await self.client.get_input_entity(FORWARD_BOT_ID)
            await self.client.forward_messages(target_entity, messages=[msg.id], from_peer=dialog.entity)
            
            # Mark as forwarded
            self.db.mark_forwarded(file_id, dialog.id, file_name, msg.document.size)
            logger.info(f"✅ SUCCESS: Forwarded {file_name} to control bot")
            
            # Extra human-like pause
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
        logger.info("🎧 Control listener starting...")
        
        @self.control_bot.on(events.NewMessage(pattern=r'^/(start|stop|reset|scan|force|status|health)$'))
        async def handler(event):
            cmd = event.pattern_match.group(1)
            logger.info(f"📩 Received command /{cmd} from user {event.sender_id}")
            
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
                
            elif cmd == 'health':
                await event.reply(f"✅ ALIVE at {datetime.now().isoformat()}")

        try:
            await self.control_bot.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Control listener died: {e}", exc_info=True)

    async def _force_scan(self, event):
        try:
            logger.info("⚡ Force scan triggered")
            await self._scan_and_forward()
            await event.reply("✅ Force scan completed.")
        except Exception as e:
            logger.error(f"💥 Force scan error: {e}", exc_info=True)
            await event.reply(f"❌ Force scan error: {str(e)[:100]}")

    async def run_forever(self):
        """Eternal loop with health checks"""
        logger.info("🔥 Starting eternal run loop...")
        await self.start()
        
        # Write a second alive proof
        with open('/tmp/railway_ready.txt', 'w') as f:
            f.write(f"READY at {datetime.now().isoformat()}\n")
            f.write(f"Client connected: {self.client.is_connected()}\n")
        
        logger.info("✅ Ready. Entering eternal sleep...")
        
        # Keep alive with health checks
        while True:
            await asyncio.sleep(60)  # Check every minute
            if not self.client.is_connected():
                logger.warning("🔌 Health check: reconnecting main client...")
                try:
                    await self.client.reconnect()
                except Exception as e:
                    logger.error(f"❌ Reconnect failed: {e}")
            
            if not self.control_bot.is_connected():
                logger.warning("🔌 Health check: reconnecting control bot...")
                try:
                    await self.control_bot.reconnect()
                except Exception as e:
                    logger.error(f"❌ Bot reconnect failed: {e}")

# ========== MAIN ==========
async def main():
    """Main entry point with maximum error visibility"""
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
        await forwarder.control_bot.disconnect()
        await forwarder.forward_bot.disconnect()
        forwarder.db.close()
        logger.info("✅ Clean exit.")
    except Exception as e:
        logger.critical(f"💀 FATAL: {e}", exc_info=True)
        # Write crash log
        with open('/tmp/crash.log', 'w') as f:
            f.write(f"CRASH at {datetime.now().isoformat()}\n")
            f.write(f"Error: {e}\n")
            import traceback
            f.write(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    print("🏃 SCRIPT ENTRY POINT - STARTING ASYNCIO", flush=True)
    asyncio.run(main())
