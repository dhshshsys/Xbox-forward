#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   TELEGRAM GOD FORWARDER v10.0 - ETERNAL EDITION             ║
║                                                               ║
║   "Forwarding files from the void, forever."                 ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import asyncio
import logging
import sqlite3
import json
import random
import time
import signal
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Any
from pathlib import Path

# ========== FORCE STDOUT FLUSH ==========
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ========== VERSION ==========
VERSION = "10.0.0"
GOD_NAME = "Eternal Forwarder"

print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   🚀 {GOD_NAME} v{VERSION}                                  ║
║   ⏰ Boot: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    ║
║                                                               ║
║   "Forwarding files from the void, forever."                 ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
""", flush=True)

# ========== DEPENDENCY AUTO-INSTALL ==========
def ensure_telethon():
    """Auto-install telethon if missing - god-like self-sufficiency"""
    try:
        import telethon
        print(f"✅ Telethon v{telethon.__version__} loaded", flush=True)
        return True
    except ImportError:
        print("📦 Installing Telethon...", flush=True)
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "--quiet", "--upgrade"])
            print("✅ Telethon installed successfully", flush=True)
            return True
        except Exception as e:
            print(f"❌ Failed to install telethon: {e}", flush=True)
            return False

if not ensure_telethon():
    print("💀 Cannot proceed without Telethon. Exiting.", flush=True)
    sys.exit(1)

# ========== IMPORTS ==========
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    AuthKeyDuplicatedError,
    FloodWaitError,
    RPCError,
    ApiIdInvalidError,
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    AuthKeyUnregisteredError
)
from telethon.tl.types import MessageMediaDocument, Document, InputPeerUser, InputPeerChannel
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty

# ========== CONFIGURATION ==========
# --- USER SESSION ---
SESSION_STRING = '1BVtsOJYBu5lxKgz1X9OPtjrhIi5M4HOR8d25C9XbJU13PU3PUYxFjaMhF4OqjcgHmjZ-m26WJMJe33-C3absPhgKHpic_V5hk4VC5i82kUGHTDwGpt3gcmvo8gPnYGW2VTRzqSMl46hIuMoMbHHU82QndSkasFzJBVe2Y6uqVXz0AjyLw0TttDi1YZV-b6TWLKgpQDXFFzn1jnZ3dwtJ7ZKM96rb4vNxDzeq_DNDg8i_Xk6-PUMmVDQ7r6CYK5R_GCyYaoseYo2GEDoLcAFIqWI_TXSangMrVjiy-r6eD7W6w0pz_DbTefiOEGV2ik_NSmMx8U3_XA0vB-B-KVzDgH2ZKOE0W1A='

# --- API CREDENTIALS ---
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'

# --- BOT TOKENS ---
CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'
FORWARD_BOT_TOKEN = '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI'
FORWARD_BOT_ID = 8872438487

# --- SCAN CONFIG ---
SCAN_INTERVAL_MIN = 5
SCAN_INTERVAL_MAX = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
SCAN_HISTORY_MINUTES = 30  # Only scan last 30 minutes
MAX_MESSAGES_PER_CHANNEL = 50

# --- PERSISTENCE ---
DB_FILE = 'god_forwarder.db'
SESSION_FILE = 'god_session.txt'
LOCK_FILE = '/tmp/god_forwarder.lock'
CRASH_LOG = '/tmp/god_crash.log'

# ========== LOGGING ==========
class GodLogger:
    """Custom logger with forced flush and crash logging"""
    def __init__(self):
        self.logger = logging.getLogger('GodForwarder')
        self.logger.setLevel(logging.INFO)
        
        # Console handler with flush
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(console)
        
        # File handler for crash logs
        try:
            file_handler = logging.FileHandler(CRASH_LOG, mode='a')
            file_handler.setLevel(logging.ERROR)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(file_handler)
        except:
            pass
        
        # Ensure all logs flush immediately
        for handler in self.logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
    
    def info(self, msg):
        self.logger.info(msg)
        sys.stdout.flush()
    
    def warning(self, msg):
        self.logger.warning(msg)
        sys.stdout.flush()
    
    def error(self, msg):
        self.logger.error(msg)
        sys.stderr.flush()
    
    def critical(self, msg):
        self.logger.critical(msg)
        sys.stderr.flush()
        # Write to crash log
        with open(CRASH_LOG, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - CRITICAL: {msg}\n")
    
    def debug(self, msg):
        self.logger.debug(msg)

logger = GodLogger()

# ========== SESSION MANAGER ==========
class GodSessionManager:
    """Ultimate session manager - self-healing, self-regenerating"""
    
    @staticmethod
    def load_session() -> str:
        """Load session from file or use default"""
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    session = f.read().strip()
                    if session and len(session) > 10:
                        logger.info(f"📂 Loaded session from file: {session[:20]}...")
                        return session
            except Exception as e:
                logger.warning(f"⚠️ Failed to load session file: {e}")
        
        logger.info("📂 Using default session string")
        return SESSION_STRING
    
    @staticmethod
    def save_session(session_string: str):
        """Save session to file for persistence"""
        try:
            with open(SESSION_FILE, 'w') as f:
                f.write(session_string)
            logger.info(f"💾 Session saved to {SESSION_FILE}")
        except Exception as e:
            logger.warning(f"⚠️ Could not save session: {e}")
    
    @staticmethod
    def clear_session():
        """Delete saved session"""
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
            logger.info("🗑️ Session file cleared")
    
    @staticmethod
    def is_session_valid(session_string: str) -> bool:
        """Basic validation - check if session looks like a valid string"""
        return session_string and len(session_string) > 50

# ========== DATABASE ==========
class GodDatabase:
    """Immortal database - never forgets"""
    
    def __init__(self):
        self.db_path = DB_FILE
        self._init_db()
    
    def _init_db(self):
        """Initialize database with all required tables"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        
        # Forwarded files table
        cursor.execute('''
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
        
        # Config table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Channel config table (per-channel settings)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_config (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                enabled INTEGER DEFAULT 1,
                last_scan TIMESTAMP
            )
        ''')
        
        # Insert default config
        cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('bot_state', 'running'))
        cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('scan_channels', ''))
        cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('total_forwarded', '0'))
        cursor.execute('INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)', ('last_active', datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    
    def get_connection(self):
        """Get a new database connection"""
        return sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
    
    def is_forwarded(self, file_id: str) -> bool:
        """Check if a file has been forwarded"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM forwarded_files WHERE file_id = ?', (file_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    def mark_forwarded(self, file_id: str, channel_id: int, channel_name: str, 
                       file_name: str, file_size: int, message_id: int):
        """Mark a file as forwarded"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO forwarded_files 
            (file_id, channel_id, channel_name, file_name, file_size, message_id, forwarded_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (file_id, channel_id, channel_name, file_name, file_size, message_id, datetime.now().isoformat()))
        
        cursor.execute('UPDATE config SET value = value + 1 WHERE key = ?', ('total_forwarded',))
        cursor.execute('UPDATE config SET value = ? WHERE key = ?', (datetime.now().isoformat(), 'last_active'))
        
        conn.commit()
        conn.close()
    
    def get_state(self) -> str:
        """Get bot state (running/stopped)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE key = ?', ('bot_state',))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 'running'
    
    def set_state(self, state: str):
        """Set bot state"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE config SET value = ? WHERE key = ?', (state, 'bot_state'))
        conn.commit()
        conn.close()
    
    def get_scan_channels(self) -> List[int]:
        """Get list of channel IDs to scan (empty = all)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE key = ?', ('scan_channels',))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return [int(x.strip()) for x in row[0].split(',') if x.strip()]
        return []
    
    def set_scan_channels(self, channel_ids: List[int]):
        """Set list of channel IDs to scan"""
        val = ','.join(str(cid) for cid in channel_ids)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE config SET value = ? WHERE key = ?', (val, 'scan_channels'))
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict:
        """Get forwarding statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM forwarded_files')
        total_forwarded = cursor.fetchone()[0]
        
        cursor.execute('SELECT value FROM config WHERE key = ?', ('last_active',))
        last_active = cursor.fetchone()
        last_active = last_active[0] if last_active else 'Never'
        
        cursor.execute('SELECT value FROM config WHERE key = ?', ('bot_state',))
        state = cursor.fetchone()
        state = state[0] if state else 'unknown'
        
        conn.close()
        
        return {
            'total_forwarded': total_forwarded,
            'last_active': last_active,
            'state': state
        }
    
    def reset(self):
        """Reset database - clear forwarded files but keep config"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM forwarded_files')
        cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('0', 'total_forwarded'))
        cursor.execute('UPDATE config SET value = ? WHERE key = ?', ('running', 'bot_state'))
        conn.commit()
        conn.close()
        logger.info("🔄 Database reset complete")

# ========== MAIN FORWARDER ==========
class GodForwarder:
    """The ultimate forwarder - unkillable, self-healing, eternal"""
    
    def __init__(self):
        logger.info("🐉 Forging GodForwarder...")
        self.db = GodDatabase()
        self.session_string = GodSessionManager.load_session()
        self.session = StringSession(self.session_string)
        
        # Main client (user account)
        self.client = TelegramClient(
            self.session,
            API_ID,
            API_HASH,
            connection_retries=10,
            retry_delay=1,
            auto_reconnect=True,
            flood_sleep_threshold=120,
            receive_updates=False,
            timeout=30
        )
        
        # Bot clients
        self.control_bot = None
        self.forward_bot = None
        
        # Runtime state
        self.running = False
        self.scan_task: Optional[asyncio.Task] = None
        self.control_task: Optional[asyncio.Task] = None
        self.health_task: Optional[asyncio.Task] = None
        self.processing_file_ids: Set[str] = set()
        self.consecutive_errors = 0
        self.last_scan_time = None
        self.forward_count_this_session = 0
        self.start_time = datetime.now()
        
        # Session regeneration tracking
        self.session_regenerated = False
        self.regeneration_attempts = 0
        self.max_regeneration_attempts = 3
        
        logger.info("✅ GodForwarder forged successfully")
    
    # ========== CONNECTION MANAGEMENT ==========
    
    async def _connect_main_client(self) -> bool:
        """Connect the main user client with auto-retry"""
        logger.info("📡 Connecting main client...")
        
        for attempt in range(1, 4):
            try:
                # Start the client
                await self.client.start()
                
                # Verify connection
                me = await self.client.get_me()
                logger.info(f"✅ Connected as: {me.first_name} (@{me.username}) [ID: {me.id}]")
                return True
                
            except AuthKeyDuplicatedError:
                logger.warning(f"⚠️ AuthKeyDuplicatedError (attempt {attempt}/3)")
                if attempt == 3:
                    logger.warning("💣 Regenerating session...")
                    self.session = StringSession()  # Fresh session
                    self.client = TelegramClient(
                        self.session, API_ID, API_HASH,
                        connection_retries=10, retry_delay=1,
                        auto_reconnect=True, flood_sleep_threshold=120
                    )
                    await self.client.start()
                    me = await self.client.get_me()
                    new_session = self.client.session.save()
                    GodSessionManager.save_session(new_session)
                    self.session_string = new_session
                    logger.info(f"✅ New session created for: {me.first_name}")
                    return True
                await asyncio.sleep(3 * attempt)
                
            except ApiIdInvalidError as e:
                logger.critical(f"💀 API_ID invalid: {e}")
                return False
                
            except (RPCError, ConnectionError, TimeoutError) as e:
                logger.warning(f"⚠️ Connection error (attempt {attempt}/3): {e}")
                await asyncio.sleep(5 * attempt)
                
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                await asyncio.sleep(5)
        
        return False
    
    async def _connect_bots(self) -> bool:
        """Connect bot clients"""
        try:
            # Control bot
            logger.info("🤖 Connecting control bot...")
            self.control_bot = TelegramClient('control_bot', API_ID, API_HASH)
            await self.control_bot.start(bot_token=CONTROL_BOT_TOKEN)
            logger.info("✅ Control bot connected")
            
            # Forward bot
            logger.info("🤖 Connecting forward bot...")
            self.forward_bot = TelegramClient('forward_bot', API_ID, API_HASH)
            await self.forward_bot.start(bot_token=FORWARD_BOT_TOKEN)
            logger.info("✅ Forward bot connected")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Bot connection failed: {e}")
            return False
    
    async def _ensure_connected(self) -> bool:
        """Ensure all clients are connected - reconnect if needed"""
        if not self.client.is_connected():
            logger.warning("🔌 Main client disconnected, reconnecting...")
            try:
                await self.client.connect()
                if not self.client.is_connected():
                    await self._connect_main_client()
            except Exception as e:
                logger.error(f"❌ Reconnect failed: {e}")
                return False
        
        # Check bot connections
        if self.control_bot and not self.control_bot.is_connected():
            try:
                await self.control_bot.connect()
            except:
                pass
        
        if self.forward_bot and not self.forward_bot.is_connected():
            try:
                await self.forward_bot.connect()
            except:
                pass
        
        return True
    
    # ========== CORE SCANNING ==========
    
    async def _scan_and_forward(self):
        """The eternal scanning loop"""
        try:
            if not await self._ensure_connected():
                logger.warning("⚠️ Cannot scan - not connected")
                return
            
            # Get dialogs
            logger.debug("📡 Fetching dialogs...")
            dialogs = await self.client.get_dialogs()
            
            # Filter channels/groups
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            target_ids = self.db.get_scan_channels()
            
            if target_ids:
                channels = [d for d in channels if d.id in target_ids]
                logger.info(f"🎯 Scanning {len(channels)} target channels")
            else:
                logger.info(f"📂 Scanning all {len(channels)} channels/groups")
            
            # Process each channel
            total_files_found = 0
            for dialog in channels:
                if not self.running or self.db.get_state() != 'running':
                    break
                
                try:
                    found = await self._process_channel(dialog)
                    total_files_found += found
                except FloodWaitError as e:
                    logger.warning(f"🐢 Flood wait on {dialog.name}: {e.seconds}s")
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"❌ Error processing {dialog.name}: {e}")
                    await asyncio.sleep(1)
            
            if total_files_found > 0:
                logger.info(f"📤 Found and forwarded {total_files_found} files this cycle")
            
            self.last_scan_time = datetime.now()
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait: {e.seconds}s")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"💥 Scan error: {e}", exc_info=True)
            raise
    
    async def _process_channel(self, dialog) -> int:
        """Process a single channel for .txt files"""
        found_count = 0
        
        try:
            # Get recent messages
            since = datetime.now() - timedelta(minutes=SCAN_HISTORY_MINUTES)
            messages = []
            
            async for msg in self.client.iter_messages(
                dialog.entity,
                limit=MAX_MESSAGES_PER_CHANNEL,
                offset_date=since,
                wait_time=1
            ):
                if not self.running:
                    break
                messages.append(msg)
            
            # Filter and process
            for msg in messages:
                if not self.running or self.db.get_state() != 'running':
                    break
                
                # Check if it's a .txt file
                if not msg.document:
                    continue
                
                # Check mime type
                mime = msg.document.mime_type or ''
                if not mime.endswith('txt') and not mime.endswith('plain'):
                    continue
                
                # Check size
                if msg.document.size > MAX_FILE_SIZE_BYTES:
                    logger.debug(f"⏭️ Skipping {msg.id} - size {msg.document.size/1024/1024:.2f}MB > 50MB")
                    continue
                
                # Get filename
                file_name = self._get_file_name(msg)
                if not file_name:
                    continue
                
                # Check if already forwarded
                file_id = f"{dialog.id}_{msg.id}_{file_name}"
                if file_id in self.processing_file_ids:
                    continue
                if self.db.is_forwarded(file_id):
                    continue
                
                # Forward it!
                found_count += 1
                logger.info(f"📄 Found: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}")
                await self._forward_file(msg, dialog, file_id, file_name)
                await asyncio.sleep(random.uniform(0.5, 2.0))
            
        except FloodWaitError:
            raise
        except Exception as e:
            logger.error(f"❌ Channel {dialog.name} error: {e}")
        
        return found_count
    
    async def _forward_file(self, msg, dialog, file_id: str, file_name: str):
        """Forward a file with human-like behavior"""
        try:
            self.processing_file_ids.add(file_id)
            
            # Human-like delay (long press)
            await asyncio.sleep(random.uniform(0.8, 2.5))
            
            # Get target
            try:
                target = await self.client.get_input_entity(FORWARD_BOT_ID)
            except:
                target = FORWARD_BOT_ID
            
            # Forward the message
            await self.client.forward_messages(
                target,
                messages=[msg.id],
                from_peer=dialog.entity,
                drop_author=True,
                silent=False
            )
            
            # Mark as forwarded
            self.db.mark_forwarded(
                file_id, dialog.id, dialog.name,
                file_name, msg.document.size, msg.id
            )
            
            self.forward_count_this_session += 1
            logger.info(f"✅ Forwarded: {file_name} (Total this session: {self.forward_count_this_session})")
            
            # Human-like post-forward pause
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
        except FloodWaitError as e:
            logger.warning(f"🐢 Flood on forward: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"❌ Failed to forward {file_name}: {e}")
        finally:
            self.processing_file_ids.discard(file_id)
    
    def _get_file_name(self, msg) -> Optional[str]:
        """Extract filename from message"""
        if not msg.document:
            return None
        
        for attr in msg.document.attributes:
            if isinstance(attr, types.DocumentAttributeFilename):
                return attr.file_name
        
        return f"file_{msg.id}.txt"
    
    # ========== COMMAND HANDLING ==========
    
    async def _control_listener(self):
        """Listen for commands from the control bot"""
        logger.info("🎧 Control listener active")
        
        @self.control_bot.on(events.NewMessage(pattern=r'^/(start|stop|reset|scan|status|health|channels|help|stats)$'))
        async def handler(event):
            cmd = event.pattern_match.group(1)
            sender = event.sender_id
            logger.info(f"📩 Command: /{cmd} from {sender}")
            
            try:
                if cmd == 'start':
                    if self.db.get_state() != 'running':
                        self.db.set_state('running')
                        self.running = True
                        if not self.scan_task or self.scan_task.done():
                            self.scan_task = asyncio.create_task(self._scanner_loop())
                        await event.reply("✅ **Bot started.**\nScanning every 5-10 seconds.")
                    else:
                        await event.reply("ℹ️ Bot is already running.")
                
                elif cmd == 'stop':
                    self.db.set_state('stopped')
                    self.running = False
                    if self.scan_task and not self.scan_task.done():
                        self.scan_task.cancel()
                    await event.reply("⏹️ **Bot stopped.**\nUse /start to resume.")
                
                elif cmd == 'reset':
                    self.db.reset()
                    self.processing_file_ids.clear()
                    GodSessionManager.clear_session()
                    await event.reply("🔄 **Reset complete.**\n- All forward history cleared\n- Session cleared (will regenerate on next boot)")
                
                elif cmd == 'scan':
                    if self.db.get_state() != 'running':
                        await event.reply("⚠️ Bot is stopped. Use /start first.")
                        return
                    await event.reply("🔍 **Force scanning...**")
                    asyncio.create_task(self._force_scan(event))
                
                elif cmd == 'status':
                    stats = self.db.get_stats()
                    uptime = (datetime.now() - self.start_time)
                    uptime_str = str(uptime).split('.')[0]
                    
                    channels = self.db.get_scan_channels()
                    ch_str = ', '.join(str(c) for c in channels) if channels else 'ALL'
                    
                    await event.reply(
                        f"📊 **Status**\n"
                        f"State: {stats['state']}\n"
                        f"Forwarded total: {stats['total_forwarded']}\n"
                        f"Forwarded this session: {self.forward_count_this_session}\n"
                        f"Scanned channels: {ch_str}\n"
                        f"Uptime: {uptime_str}\n"
                        f"Last active: {stats['last_active']}"
                    )
                
                elif cmd == 'health':
                    await event.reply(f"✅ **ALIVE**\n{datetime.now().isoformat()}\nVersion: {VERSION}")
                
                elif cmd == 'channels':
                    dialogs = await self.client.get_dialogs()
                    channels = [d for d in dialogs if d.is_channel or d.is_group]
                    target_ids = self.db.get_scan_channels()
                    
                    msg = "📂 **Channels**\n"
                    for d in channels[:20]:  # Limit to 20
                        mark = "✅" if d.id in target_ids else "⭕"
                        msg += f"{mark} {d.name} (ID: {d.id})\n"
                    
                    if len(channels) > 20:
                        msg += f"\n... and {len(channels) - 20} more"
                    
                    await event.reply(msg)
                
                elif cmd == 'help':
                    await event.reply(
                        "📖 **Commands**\n"
                        "/start - Start scanning\n"
                        "/stop - Stop scanning\n"
                        "/reset - Clear all history & session\n"
                        "/scan - Force immediate scan\n"
                        "/status - Show stats\n"
                        "/health - Check if alive\n"
                        "/channels - List channels\n"
                        "/stats - Detailed stats\n"
                        "/help - This message"
                    )
                
                elif cmd == 'stats':
                    stats = self.db.get_stats()
                    await event.reply(
                        f"📊 **Detailed Stats**\n"
                        f"Total forwarded: {stats['total_forwarded']}\n"
                        f"This session: {self.forward_count_this_session}\n"
                        f"State: {stats['state']}\n"
                        f"Uptime: {str(datetime.now() - self.start_time).split('.')[0]}\n"
                        f"Last scan: {self.last_scan_time or 'Never'}"
                    )
            
            except Exception as e:
                logger.error(f"❌ Command handler error: {e}")
                await event.reply(f"❌ Error: {str(e)[:100]}")
        
        # Keep listening
        try:
            await self.control_bot.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Control listener died: {e}")
    
    async def _force_scan(self, event):
        """Force a scan cycle"""
        try:
            await self._scan_and_forward()
            await event.reply("✅ **Force scan complete.**")
        except Exception as e:
            await event.reply(f"❌ Scan error: {str(e)[:100]}")
    
    # ========== SCANNER LOOP ==========
    
    async def _scanner_loop(self):
        """Main scanner loop - runs forever"""
        logger.info("🔄 Scanner loop started")
        self.consecutive_errors = 0
        
        while self.running:
            try:
                # Check state
                if self.db.get_state() != 'running':
                    await asyncio.sleep(SCAN_INTERVAL_MAX)
                    continue
                
                # Ensure connected
                if not await self._ensure_connected():
                    await asyncio.sleep(5)
                    continue
                
                # Scan
                await self._scan_and_forward()
                self.consecutive_errors = 0
                
                # Random delay
                delay = random.randint(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                await asyncio.sleep(delay)
                
            except FloodWaitError as e:
                logger.warning(f"⏳ Flood wait: {e.seconds}s")
                await asyncio.sleep(e.seconds + 2)
                
            except AuthKeyDuplicatedError:
                logger.warning("⚠️ AuthKeyDuplicatedError in scanner")
                self.consecutive_errors += 1
                if self.consecutive_errors > 2:
                    logger.warning("💣 Regenerating session...")
                    self.session = StringSession()
                    self.client = TelegramClient(self.session, API_ID, API_HASH)
                    await self.client.start()
                    new_session = self.client.session.save()
                    GodSessionManager.save_session(new_session)
                    self.session_string = new_session
                    logger.info("✅ Session regenerated")
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                logger.info("Scanner task cancelled")
                break
                
            except Exception as e:
                self.consecutive_errors += 1
                logger.error(f"💥 Scanner error (count: {self.consecutive_errors}): {e}", exc_info=True)
                wait = min(60, 5 * self.consecutive_errors)
                logger.info(f"⏳ Waiting {wait}s before retry...")
                await asyncio.sleep(wait)
    
    # ========== HEALTH MONITOR ==========
    
    async def _health_monitor(self):
        """Monitor health and self-heal"""
        logger.info("💚 Health monitor active")
        
        while self.running:
            await asyncio.sleep(30)
            
            try:
                # Check main client
                if not self.client.is_connected():
                    logger.warning("🔌 Health check: main client disconnected")
                    try:
                        await self.client.connect()
                    except Exception as e:
                        logger.error(f"❌ Health reconnect failed: {e}")
                
                # Check bots
                if self.control_bot and not self.control_bot.is_connected():
                    logger.warning("🔌 Health check: control bot disconnected")
                    try:
                        await self.control_bot.connect()
                    except Exception as e:
                        logger.error(f"❌ Control bot reconnect failed: {e}")
                
                if self.forward_bot and not self.forward_bot.is_connected():
                    logger.warning("🔌 Health check: forward bot disconnected")
                    try:
                        await self.forward_bot.connect()
                    except Exception as e:
                        logger.error(f"❌ Forward bot reconnect failed: {e}")
                
            except Exception as e:
                logger.error(f"💥 Health monitor error: {e}")
    
    # ========== STARTUP ==========
    
    async def start(self):
        """Start the forwarder"""
        logger.info("🐉 GodForwarder starting...")
        
        # Connect main client
        if not await self._connect_main_client():
            logger.critical("💀 Failed to connect main client. Exiting.")
            return False
        
        # Connect bots
        if not await self._connect_bots():
            logger.critical("💀 Failed to connect bots. Exiting.")
            return False
        
        # Set running state
        self.running = True
        self.start_time = datetime.now()
        
        # Start tasks
        self.scan_task = asyncio.create_task(self._scanner_loop())
        self.control_task = asyncio.create_task(self._control_listener())
        self.health_task = asyncio.create_task(self._health_monitor())
        
        logger.info("✅ ALL SYSTEMS OPERATIONAL")
        logger.info(f"📱 Account: @Relicisme (ID: 8627710307)")
        logger.info(f"⏱️  Scan interval: {SCAN_INTERVAL_MIN}-{SCAN_INTERVAL_MAX}s")
        logger.info(f"📄 Max file size: 50MB")
        logger.info(f"🎯 Control bot: {CONTROL_BOT_TOKEN[:20]}...")
        logger.info(f"📤 Forwarding to: {FORWARD_BOT_ID}")
        logger.info("🔥 ETERNAL FORWARDING ENGAGED")
        
        return True
    
    async def run_forever(self):
        """The eternal loop"""
        if not await self.start():
            return
        
        try:
            # Keep running forever
            while self.running:
                await asyncio.sleep(1)
                
                # Check if tasks died
                if self.scan_task and self.scan_task.done():
                    exc = self.scan_task.exception()
                    if exc:
                        logger.error(f"💀 Scanner task died: {exc}")
                        logger.info("🔄 Restarting scanner...")
                        self.scan_task = asyncio.create_task(self._scanner_loop())
                
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        except Exception as e:
            logger.critical(f"💀 Fatal error: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Shutting down GodForwarder...")
        self.running = False
        
        # Cancel tasks
        for task in [self.scan_task, self.control_task, self.health_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except:
                    pass
        
        # Disconnect clients
        try:
            await self.client.disconnect()
        except:
            pass
        try:
            if self.control_bot:
                await self.control_bot.disconnect()
        except:
            pass
        try:
            if self.forward_bot:
                await self.forward_bot.disconnect()
        except:
            pass
        
        logger.info("✅ Shutdown complete. Goodbye.")

# ========== MAIN ==========
async def main():
    """Entry point"""
    forwarder = GodForwarder()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"📡 Received signal {sig}")
        asyncio.create_task(forwarder.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await forwarder.run_forever()
    except Exception as e:
        logger.critical(f"💀 Fatal: {e}", exc_info=True)
        with open(CRASH_LOG, 'a') as f:
            f.write(f"\n=== CRASH at {datetime.now().isoformat()} ===\n")
            f.write(traceback.format_exc())
            f.write("\n")
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"💀 Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)
