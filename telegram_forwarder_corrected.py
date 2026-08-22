#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   TELEGRAM FORWARDER - ABSOLUTE FINAL v13.0                 ║
║                                                               ║
║   ✅ Control Bot (8904895394) - COMMANDS ONLY              ║
║   ✅ Checker Bot (8872438487) - FILES ONLY                 ║
║   ✅ Session login - NO prompts                            ║
║   ✅ Auto-scanning - EVERY 5-10 SECONDS                   ║
║   ✅ Human-like forwarding                                ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import asyncio
import logging
import sqlite3
import random
import signal
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional

# ========== FORCE STDIO FLUSH ==========
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("🚀 ABSOLUTE FINAL EDITION BOOTING...", flush=True)
print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print("🎯 Control Bot (Commands): 8904895394", flush=True)
print("📤 Checker Bot (Files): 8872438487", flush=True)

# ========== DEPENDENCY CHECK ==========
try:
    from telethon import TelegramClient, events, types, functions, errors
    from telethon.sessions import StringSession
    from telethon.tl.types import DocumentAttributeFilename
    from telethon.errors import FloodWaitError, RPCError
    print("✅ Telethon loaded", flush=True)
except ImportError:
    print("📦 Installing Telethon...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "--quiet"])
    from telethon import TelegramClient, events, types, functions, errors
    from telethon.sessions import StringSession
    from telethon.tl.types import DocumentAttributeFilename
    from telethon.errors import FloodWaitError, RPCError
    print("✅ Telethon installed", flush=True)

# ========== CONFIGURATION ==========
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'

# YOUR SESSION STRING
SESSION_STRING = '1BVtsOJYBu5lxKgz1X9OPtjrhIi5M4HOR8d25C9XbJU13PU3PUYxFjaMhF4OqjcgHmjZ-m26WJMJe33-C3absPhgKHpic_V5hk4VC5i82kUGHTDwGpt3gcmvo8gPnYGW2VTRzqSMl46hIuMoMbHHU82QndSkasFzJBVe2Y6uqVXz0AjyLw0TttDi1YZV-b6TWLKgpQDXFFzn1jnZ3dwtJ7ZKM96rb4vNxDzeq_DNDg8i_Xk6-PUMmVDQ7r6CYK5R_GCyYaoseYo2GEDoLcAFIqWI_TXSangMrVjiy-r6eD7W6w0pz_DbTefiOEGV2ik_NSmMx8U3_XA0vB-B-KVzDgH2ZKOE0W1A='

# ========== BOT ROLES - EXPLICITLY DEFINED ==========
CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'  # ← COMMANDS ONLY
CHECKER_BOT_TOKEN = '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI'  # ← FILES ONLY
CHECKER_BOT_ID = 8872438487  # Numeric ID for forwarding

# SCAN SETTINGS
SCAN_INTERVAL_MIN = 5
SCAN_INTERVAL_MAX = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
DB_FILE = 'forwarder.db'

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
logger = logging.getLogger('Forwarder')
logger.info("🚀 Logging initialized")

# ========== DATABASE ==========
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30)
        self.cursor = self.conn.cursor()
        self._init_db()
        logger.info("✅ Database initialized")
    
    def _init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forwarded_files (
                file_id TEXT PRIMARY KEY,
                channel_id INTEGER,
                channel_name TEXT,
                file_name TEXT,
                file_size INTEGER,
                message_id INTEGER,
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
        self.cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('total_forwarded', '0'))
        self.conn.commit()
    
    def is_forwarded(self, file_id: str) -> bool:
        self.cursor.execute('SELECT 1 FROM forwarded_files WHERE file_id = ?', (file_id,))
        return self.cursor.fetchone() is not None
    
    def mark_forwarded(self, file_id: str, channel_id: int, channel_name: str, 
                       file_name: str, file_size: int, message_id: int):
        self.cursor.execute('''
            INSERT OR REPLACE INTO forwarded_files 
            (file_id, channel_id, channel_name, file_name, file_size, message_id, forwarded_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (file_id, channel_id, channel_name, file_name, file_size, message_id, datetime.now().isoformat()))
        self.cursor.execute('UPDATE config SET value = value + 1 WHERE key = ?', ('total_forwarded',))
        self.conn.commit()
    
    def get_state(self) -> str:
        self.cursor.execute('SELECT value FROM config WHERE key = ?', ('bot_state',))
        row = self.cursor.fetchone()
        return row[0] if row else 'running'
    
    def set_state(self, state: str):
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', (state, 'bot_state'))
        self.conn.commit()
    
    def get_total_forwarded(self) -> int:
        self.cursor.execute('SELECT value FROM config WHERE key = ?', ('total_forwarded',))
        row = self.cursor.fetchone()
        return int(row[0]) if row and row[0] else 0
    
    def reset(self):
        self.cursor.execute('DELETE FROM forwarded_files')
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('0', 'total_forwarded'))
        self.cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('running', 'bot_state'))
        self.conn.commit()
        logger.info("🔄 Database reset")

# ========== MAIN FORWARDER ==========
class GodForwarder:
    def __init__(self):
        logger.info("🏗️ Initializing Forwarder...")
        self.db = Database()
        self.running = False
        self.scan_task: Optional[asyncio.Task] = None
        self.processing: Set[str] = set()
        self.total_forwarded_session = 0
        self.start_time = datetime.now()
        
        # User client (your Telegram account)
        self.user_client = TelegramClient(
            StringSession(SESSION_STRING),
            API_ID,
            API_HASH,
            connection_retries=5,
            retry_delay=2,
            auto_reconnect=True,
            flood_sleep_threshold=60
        )
        
        # CONTROL BOT - receives COMMANDS only
        self.control_bot = None
        
        # CHECKER BOT - receives FILES only (we don't need a client for it, just the ID)
        # We forward directly to CHECKER_BOT_ID
        
        logger.info("✅ Forwarder initialized")
        logger.info(f"🎯 Control Bot (commands): {CONTROL_BOT_TOKEN[:20]}...")
        logger.info(f"📤 Checker Bot (files): {CHECKER_BOT_ID}")
    
    # ========== AUTHENTICATION ==========
    async def authenticate(self) -> bool:
        """Authenticate using session string - NO PROMPTS"""
        logger.info("📡 Authenticating with session...")
        
        try:
            # Start with phone bypass
            await self.user_client.start(phone=lambda: '')
            
            # Verify connection
            me = await self.user_client.get_me()
            logger.info(f"✅ LOGGED IN SUCCESSFULLY!")
            logger.info(f"📱 Account: {me.first_name} (@{me.username}) [ID: {me.id}]")
            
            # Test connection
            dialogs = await self.user_client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            logger.info(f"📂 Found {len(channels)} channels/groups")
            
            return True
            
        except errors.ApiIdInvalidError as e:
            logger.critical(f"💀 Invalid API ID: {e}")
            return False
        except errors.AuthKeyDuplicatedError as e:
            logger.warning(f"⚠️ Session conflict: {e}")
            logger.info("🔄 Attempting to regenerate session...")
            try:
                await self.user_client.log_out()
                logger.info("✅ Logged out old sessions")
            except:
                pass
            
            new_session = StringSession()
            self.user_client = TelegramClient(
                new_session,
                API_ID,
                API_HASH,
                connection_retries=5,
                retry_delay=2,
                auto_reconnect=True
            )
            await self.user_client.start(phone=lambda: '')
            me = await self.user_client.get_me()
            logger.info(f"✅ NEW SESSION CREATED for {me.first_name}")
            
            new_session_str = self.user_client.session.save()
            logger.info(f"💾 New session: {new_session_str[:20]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}", exc_info=True)
            return False
    
    # ========== CONTROL BOT CONNECTION ==========
    async def connect_control_bot(self) -> bool:
        """Connect ONLY the control bot (for commands)"""
        try:
            logger.info("🤖 Connecting CONTROL BOT (commands)...")
            self.control_bot = TelegramClient(
                'control_bot',
                API_ID,
                API_HASH,
                connection_retries=3
            )
            await self.control_bot.start(bot_token=CONTROL_BOT_TOKEN)
            
            # Verify it's the right bot
            me = await self.control_bot.get_me()
            logger.info(f"✅ CONTROL BOT connected: @{me.username} (ID: {me.id})")
            logger.info("   This bot handles: /start, /stop, /status, /scan, /reset, /health, /help")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Control bot connection failed: {e}", exc_info=True)
            return False
    
    # ========== SCANNING ==========
    async def scan_and_forward(self):
        """Main scanning logic - forwards to CHECKER BOT"""
        try:
            if not self.user_client.is_connected():
                logger.warning("🔌 Reconnecting user client...")
                await self.user_client.reconnect()
            
            if self.db.get_state() != 'running':
                return
            
            logger.debug("🔍 Scanning...")
            dialogs = await self.user_client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            
            logger.info(f"📂 Scanning {len(channels)} channels")
            total_found = 0
            
            for dialog in channels:
                if not self.running or self.db.get_state() != 'running':
                    break
                
                try:
                    since = datetime.now() - timedelta(minutes=30)
                    count = 0
                    
                    async for msg in self.user_client.iter_messages(
                        dialog.entity,
                        limit=50,
                        offset_date=since
                    ):
                        if not self.running or self.db.get_state() != 'running':
                            break
                        
                        if not msg.document:
                            continue
                        
                        mime = msg.document.mime_type or ''
                        if not (mime.endswith('txt') or mime.endswith('plain')):
                            continue
                        
                        if msg.document.size > MAX_FILE_SIZE_BYTES:
                            continue
                        
                        file_name = None
                        for attr in msg.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                file_name = attr.file_name
                                break
                        
                        if not file_name:
                            file_name = f"file_{msg.id}.txt"
                        
                        file_id = f"{dialog.id}_{msg.id}_{file_name}"
                        
                        if file_id in self.processing:
                            continue
                        
                        if self.db.is_forwarded(file_id):
                            continue
                        
                        count += 1
                        total_found += 1
                        logger.info(f"📄 Found: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}")
                        await self.forward_to_checker(msg, dialog, file_id, file_name)
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                    
                    if count > 0:
                        logger.info(f"📤 Forwarded {count} files from {dialog.name} to CHECKER BOT")
                        
                except FloodWaitError as e:
                    logger.warning(f"🐢 Flood wait on {dialog.name}: {e.seconds}s")
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"❌ Error on {dialog.name}: {e}")
            
            if total_found > 0:
                logger.info(f"📊 Total forwarded this cycle: {total_found} files to CHECKER BOT")
            
        except Exception as e:
            logger.error(f"💥 Scan error: {e}", exc_info=True)
    
    async def forward_to_checker(self, msg, dialog, file_id: str, file_name: str):
        """Forward a single file to the CHECKER BOT ONLY"""
        try:
            self.processing.add(file_id)
            
            # Human-like delay
            await asyncio.sleep(random.uniform(0.8, 2.5))
            
            # FORWARD TO CHECKER BOT ONLY
            target = await self.user_client.get_input_entity(CHECKER_BOT_ID)
            await self.user_client.forward_messages(
                target,
                messages=[msg.id],
                from_peer=dialog.entity
            )
            
            # Mark in database
            self.db.mark_forwarded(
                file_id,
                dialog.id,
                dialog.name,
                file_name,
                msg.document.size,
                msg.id
            )
            
            self.total_forwarded_session += 1
            logger.info(f"✅ Forwarded to CHECKER BOT: {file_name} (Session total: {self.total_forwarded_session})")
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
        except FloodWaitError as e:
            logger.warning(f"🐢 Flood on forward: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"❌ Forward failed: {e}")
        finally:
            self.processing.discard(file_id)
    
    # ========== SCANNER LOOP ==========
    async def scanner_loop(self):
        """Eternal scanner"""
        logger.info("🔄 Scanner loop started")
        consecutive_errors = 0
        
        while self.running:
            try:
                if self.db.get_state() != 'running':
                    await asyncio.sleep(SCAN_INTERVAL_MAX)
                    continue
                
                await self.scan_and_forward()
                consecutive_errors = 0
                
                delay = random.randint(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                await asyncio.sleep(delay)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"💥 Scanner error ({consecutive_errors}): {e}")
                await asyncio.sleep(min(60, 5 * consecutive_errors))
    
    # ========== CONTROL BOT HANDLER ==========
    async def control_handler(self):
        """Handle commands from CONTROL BOT ONLY"""
        logger.info("🎧 CONTROL BOT handler active - listening for commands")
        
        @self.control_bot.on(events.NewMessage)
        async def handler(event):
            try:
                # Only respond to commands
                if not event.raw_text.startswith('/'):
                    return
                
                cmd = event.raw_text.split()[0].lower()
                logger.info(f"📩 Command received on CONTROL BOT: {cmd} from user {event.sender_id}")
                
                # /start - Resume scanning
                if cmd == '/start':
                    if self.db.get_state() != 'running':
                        self.db.set_state('running')
                        self.running = True
                        if not self.scan_task or self.scan_task.done():
                            self.scan_task = asyncio.create_task(self.scanner_loop())
                        await event.reply("✅ **Bot started!**\nScanning every 5-10 seconds.\nFiles go to CHECKER BOT.")
                    else:
                        await event.reply("ℹ️ Bot is already running.")
                
                # /stop - Pause scanning
                elif cmd == '/stop':
                    self.db.set_state('stopped')
                    self.running = False
                    if self.scan_task and not self.scan_task.done():
                        self.scan_task.cancel()
                    await event.reply("⏹️ **Bot stopped.**\nUse /start to resume.")
                
                # /reset - Clear everything
                elif cmd == '/reset':
                    self.db.reset()
                    self.processing.clear()
                    self.total_forwarded_session = 0
                    await event.reply("🔄 **Reset complete.**\n- Forward history cleared\n- State set to running")
                
                # /scan - Force scan
                elif cmd == '/scan':
                    if self.db.get_state() != 'running':
                        await event.reply("⚠️ Bot is stopped. Use /start first.")
                        return
                    await event.reply("🔍 **Force scanning...**")
                    try:
                        await self.scan_and_forward()
                        await event.reply("✅ **Force scan complete.**\nFiles forwarded to CHECKER BOT.")
                    except Exception as e:
                        await event.reply(f"❌ Scan error: {str(e)[:100]}")
                
                # /status - Show status
                elif cmd == '/status':
                    total = self.db.get_total_forwarded()
                    state = self.db.get_state()
                    uptime = str(datetime.now() - self.start_time).split('.')[0]
                    await event.reply(
                        f"📊 **Status**\n"
                        f"State: {state}\n"
                        f"Total forwarded to CHECKER BOT: {total}\n"
                        f"This session: {self.total_forwarded_session}\n"
                        f"Uptime: {uptime}\n"
                        f"Scan interval: {SCAN_INTERVAL_MIN}-{SCAN_INTERVAL_MAX}s\n"
                        f"Checker Bot ID: {CHECKER_BOT_ID}"
                    )
                
                # /health - Alive check
                elif cmd == '/health':
                    await event.reply(f"✅ **ALIVE**\n{datetime.now().isoformat()}\nControl Bot: {CONTROL_BOT_TOKEN[:20]}...\nChecker Bot: {CHECKER_BOT_ID}")
                
                # /help - Show commands
                elif cmd == '/help':
                    await event.reply(
                        "📖 **Commands**\n"
                        "/start - Start scanning\n"
                        "/stop - Stop scanning\n"
                        "/reset - Clear history\n"
                        "/scan - Force scan\n"
                        "/status - Show stats\n"
                        "/health - Alive check\n"
                        "/help - This message\n\n"
                        "📤 Files are forwarded to CHECKER BOT: 8872438487"
                    )
                
                else:
                    await event.reply(f"❌ Unknown command: {cmd}\nUse /help for commands.")
                    
            except Exception as e:
                logger.error(f"❌ Command error: {e}")
                try:
                    await event.reply(f"❌ Error: {str(e)[:100]}")
                except:
                    pass
        
        # Keep listening
        try:
            await self.control_bot.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Control handler died: {e}")
    
    # ========== HEALTH MONITOR ==========
    async def health_monitor(self):
        """Monitor and heal connections"""
        logger.info("💚 Health monitor active")
        
        while self.running:
            await asyncio.sleep(30)
            
            try:
                # Check user client
                if not self.user_client.is_connected():
                    logger.warning("🔌 User client disconnected")
                    try:
                        await self.user_client.connect()
                        if not self.user_client.is_connected():
                            await self.user_client.start(phone=lambda: '')
                        logger.info("✅ User client reconnected")
                    except Exception as e:
                        logger.error(f"❌ User reconnect failed: {e}")
                
                # Check control bot
                if self.control_bot and not self.control_bot.is_connected():
                    logger.warning("🔌 CONTROL BOT disconnected")
                    try:
                        await self.control_bot.connect()
                        logger.info("✅ CONTROL BOT reconnected")
                    except Exception as e:
                        logger.error(f"❌ Control bot reconnect failed: {e}")
                        
            except Exception as e:
                logger.error(f"💥 Health monitor error: {e}")
    
    # ========== STARTUP ==========
    async def start(self):
        """Start everything"""
        logger.info("🐉 Starting GodForwarder...")
        logger.info("🎯 Control Bot: 8904895394 (commands)")
        logger.info("📤 Checker Bot: 8872438487 (files)")
        
        # Authenticate user
        if not await self.authenticate():
            logger.critical("💀 Authentication failed. Exiting.")
            return False
        
        # Connect control bot only
        if not await self.connect_control_bot():
            logger.critical("💀 Control bot connection failed. Exiting.")
            return False
        
        # Set running
        self.running = True
        self.start_time = datetime.now()
        
        # Start tasks
        self.scan_task = asyncio.create_task(self.scanner_loop())
        asyncio.create_task(self.control_handler())
        asyncio.create_task(self.health_monitor())
        
        logger.info("✅ ALL SYSTEMS OPERATIONAL")
        logger.info(f"🔥 ETERNAL FORWARDING ENGAGED")
        logger.info(f"📤 All files → CHECKER BOT: {CHECKER_BOT_ID}")
        logger.info(f"🎯 Commands → CONTROL BOT: {CONTROL_BOT_TOKEN[:20]}...")
        return True
    
    async def run_forever(self):
        """Eternal loop"""
        if not await self.start():
            return
        
        try:
            while self.running:
                await asyncio.sleep(1)
                
                # Check if scanner died
                if self.scan_task and self.scan_task.done():
                    exc = self.scan_task.exception()
                    if exc:
                        logger.error(f"💀 Scanner died: {exc}")
                        logger.info("🔄 Restarting scanner...")
                        self.scan_task = asyncio.create_task(self.scanner_loop())
                        
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        except Exception as e:
            logger.critical(f"💀 Fatal: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Shutting down...")
        self.running = False
        
        if self.scan_task and not self.scan_task.done():
            self.scan_task.cancel()
            try:
                await self.scan_task
            except:
                pass
        
        try:
            await self.user_client.disconnect()
        except:
            pass
        
        try:
            if self.control_bot:
                await self.control_bot.disconnect()
        except:
            pass
        
        logger.info("✅ Shutdown complete")

# ========== MAIN ==========
async def main():
    forwarder = GodForwarder()
    
    def signal_handler(sig, frame):
        logger.info(f"📡 Signal {sig} received")
        asyncio.create_task(forwarder.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await forwarder.run_forever()
    except Exception as e:
        logger.critical(f"💀 Fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Interrupted")
    except Exception as e:
        print(f"💀 Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)
