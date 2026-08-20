#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TELEGRAM AUTO-FORWARDER v25.0 – EVENT-BASED (FINAL)
✅ Uses Telethon events – REAL-TIME forwarding
✅ No polling – instant message detection
✅ Railway deployable
✅ Based on your working v10.0 logic
"""

import os
import sys
import json
import asyncio
import random
import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

# ================================================================
# ENVIRONMENT VARIABLES
# ================================================================

SESSION_STRING = os.environ.get('SESSION_STRING', '1BVtsOLEBuzomCJpipJP4r4UoPd66tglye3cdnHy-O2Gf1jbZRyQSIA5p7cpUpj3D2NPubpNWmGvZ4OgfAFz9gbcw2uGyrkz5iRaH0i8735Vz8H-iFRmsBInTuCZ6mB-KHABExVfZzuzS2XDzxNJVUTbyAZByQQ1gLqKK_UKHC5ShKuB_i2S8ebfWRx4ix1nkjwnTgcP2aPzKLmO_CpdP95VyQWWj2IORoyzrRgj3MaN7fBt52uWKGWoL3DmxJvDnXiWO-wZOkuAgHYFMDzKPDgNYDb2Pbe1VQX-rJxDAoj4d7SMp9SwcxfdeUuFgTrVwgf0CqFe3hTdh71oD14q6rs6EXVXBbME=')
API_ID = int(os.environ.get('API_ID', 37897922))
API_HASH = os.environ.get('API_HASH', '6761ebe743a7389115a99af249cbbae6')
FORWARD_BOT_TOKEN = os.environ.get('FORWARD_BOT_TOKEN', '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI')
CONTROL_BOT_TOKEN = os.environ.get('CONTROL_BOT_TOKEN', '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY')
FORWARD_BOT_USERNAME = os.environ.get('FORWARD_BOT_USERNAME', 'XboxCheckerBot')
CONTROL_BOT_USERNAME = os.environ.get('CONTROL_BOT_USERNAME', 'XboxControlBot')

MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 50 * 1024 * 1024))
PORT = int(os.environ.get('PORT', 8080))

DB_FILE = 'forwarded_files.db'
DEPLOYMENT_FILE = 'deployment_time.json'

# ================================================================
# AUTO-CREATE RAILWAY FILES
# ================================================================

def create_railway_files():
    try:
        if not os.path.exists('requirements.txt'):
            with open('requirements.txt', 'w') as f:
                f.write('''telethon>=1.34.0
aiohttp>=3.9.0
cryptg>=0.4.0
''')
        if not os.path.exists('start.sh'):
            with open('start.sh', 'w') as f:
                f.write('#!/bin/bash\npython main.py\n')
            os.chmod('start.sh', 0o755)
        if not os.path.exists('nixpacks.toml'):
            with open('nixpacks.toml', 'w') as f:
                f.write('''[phases.setup]\nnixPkgs = ["python311"]\n[phases.install]\ncmds = ["pip install -r requirements.txt"]\n[phases.start]\ncmd = "python main.py"\n''')
        if not os.path.exists('railway.json'):
            with open('railway.json', 'w') as f:
                f.write('''{"build":{"builder":"NIXPACKS"},"deploy":{"startCommand":"python main.py","healthcheckPath":"/health"}}\n''')
        if not os.path.exists('Procfile'):
            with open('Procfile', 'w') as f:
                f.write('web: python main.py\n')
        return True
    except:
        return False

create_railway_files()

# ================================================================
# LOGGING
# ================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ================================================================
# TIMEZONE HELPERS
# ================================================================

def make_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def now_aware():
    return datetime.now(timezone.utc)

# ================================================================
# DEPLOYMENT MANAGER
# ================================================================

class DeploymentManager:
    def __init__(self, file_path=DEPLOYMENT_FILE):
        self.file_path = file_path
        self.deployment_time = None
        self._load_or_create()
    
    def _load_or_create(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    dt = datetime.fromisoformat(data['deployment_time'])
                    self.deployment_time = make_aware(dt)
                    logger.info(f"📅 Loaded deployment time: {self.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                    return
            except:
                pass
        self.deployment_time = now_aware()
        self._save()
        logger.info(f"📅 New deployment time set: {self.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    def _save(self):
        try:
            with open(self.file_path, 'w') as f:
                json.dump({'deployment_time': self.deployment_time.isoformat()}, f, indent=2)
        except:
            pass

deployment = DeploymentManager()

# ================================================================
# DATABASE
# ================================================================

class DatabaseManager:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS forwarded_files (
                file_hash TEXT PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER,
                file_name TEXT,
                file_size INTEGER,
                forwarded_at TIMESTAMP,
                channel_name TEXT
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_channel_id ON forwarded_files(channel_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_forwarded_at ON forwarded_files(forwarded_at)')
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    
    def is_forwarded(self, file_hash):
        try:
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            c.execute('SELECT 1 FROM forwarded_files WHERE file_hash = ?', (file_hash,))
            result = c.fetchone()
            conn.close()
            return result is not None
        except:
            return False
    
    def mark_forwarded(self, file_hash, channel_id, message_id, file_name, file_size, channel_name):
        try:
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO forwarded_files 
                (file_hash, channel_id, message_id, file_name, file_size, forwarded_at, channel_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (file_hash, channel_id, message_id, file_name, file_size, 
                  datetime.now().isoformat(), channel_name))
            conn.commit()
            conn.close()
            return True
        except:
            return False

db = DatabaseManager()

# ================================================================
# HEALTH CHECK SERVER
# ================================================================

async def start_health_server():
    try:
        from aiohttp import web
        app = web.Application()
        app.router.add_get('/', lambda r: web.Response(text="OK", status=200))
        app.router.add_get('/health', lambda r: web.json_response({"status": "ok"}))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        logger.info(f"✅ Health check on port {PORT}")
        return True
    except:
        return False

# ================================================================
# MAIN FORWARDER – EVENT-BASED
# ================================================================

class TelegramForwarder:
    def __init__(self):
        self.client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        self.forward_target = None
        self.control_bot = None
        self.is_running = True
    
    async def resolve_bot(self, bot_token, bot_username=None):
        bot_id = int(bot_token.split(':')[0])
        if bot_username:
            try:
                return await self.client.get_entity(f'@{bot_username}')
            except:
                pass
        try:
            return await self.client.get_entity(bot_id)
        except:
            pass
        try:
            await self.client.send_message(bot_id, '/start')
            await asyncio.sleep(1)
            return await self.client.get_entity(bot_id)
        except:
            return None
    
    async def authenticate(self):
        try:
            logger.info("🔑 Authenticating...")
            await self.client.start()
            
            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username or 'no username'})")
            logger.info(f"✅ User ID: {me.id}")
            
            self.forward_target = await self.resolve_bot(FORWARD_BOT_TOKEN, FORWARD_BOT_USERNAME)
            if not self.forward_target:
                logger.error("❌ Xbox Checker Bot not found!")
                return False
            logger.info(f"✅ Xbox Checker Bot found: {self.forward_target.id}")
            
            self.control_bot = await self.resolve_bot(CONTROL_BOT_TOKEN, CONTROL_BOT_USERNAME)
            if self.control_bot:
                logger.info(f"✅ Control bot found: {self.control_bot.id}")
            
            return True
        except Exception as e:
            logger.error(f"❌ Auth failed: {str(e)}")
            return False
    
    def extract_file_info(self, message):
        """Extract file info from message"""
        if not message.document:
            return None
        
        file_name = None
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                file_name = attr.file_name
                break
        
        if not file_name or not file_name.lower().endswith('.txt'):
            return None
        
        file_size = message.document.size
        if file_size > MAX_FILE_SIZE:
            logger.info(f"⏭️ Skipping {file_name} – {file_size/1024/1024:.2f}MB > 50MB")
            return None
        
        hash_input = f"{message.id}_{file_name}_{file_size}"
        file_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        return {
            'hash': file_hash,
            'name': file_name,
            'size': file_size,
            'message_id': message.id,
            'message_obj': message,
            'date': message.date
        }
    
    async def forward_file(self, file_info, channel_name):
        """Forward a file with human-like behavior"""
        try:
            # Human-like delay (2-5 seconds)
            await asyncio.sleep(random.uniform(2.0, 5.5))
            
            # Forward the file
            await self.client.forward_messages(
                self.forward_target,
                messages=file_info['message_obj'],
                drop_author=True
            )
            
            # Mark in database
            db.mark_forwarded(
                file_hash=file_info['hash'],
                channel_id=file_info['message_obj'].chat_id,
                message_id=file_info['message_id'],
                file_name=file_info['name'],
                file_size=file_info['size'],
                channel_name=channel_name
            )
            
            logger.info(f"✅ Forwarded: {file_info['name']} ({file_info['size']/1024:.1f}KB) → Xbox Checker Bot")
            
            # Notify control bot
            if self.control_bot:
                try:
                    await self.client.send_message(
                        self.control_bot,
                        f"📤 {file_info['name']}\n📁 {file_info['size']/1024:.1f}KB\n📂 {channel_name}"
                    )
                except:
                    pass
            
            return True
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error(f"❌ Failed to forward {file_info['name']}: {str(e)}")
            return False
    
    async def handle_new_message(self, event):
        """Event handler – triggered for EVERY new message"""
        try:
            # Skip if not a channel message
            if not event.is_channel:
                return
            
            # Skip messages before deployment time
            if not deployment.is_after_deployment(event.message.date):
                return
            
            # Extract file info
            file_info = self.extract_file_info(event.message)
            if not file_info:
                return
            
            # Skip if already forwarded
            if db.is_forwarded(file_info['hash']):
                return
            
            # Get channel name
            try:
                channel = await event.get_chat()
                channel_name = channel.title or channel.username or str(channel.id)
            except:
                channel_name = str(event.chat_id)
            
            logger.info(f"📄 New .txt file detected: {file_info['name']} from {channel_name}")
            
            # Forward the file
            await self.forward_file(file_info, channel_name)
            
        except Exception as e:
            logger.error(f"❌ Error in event handler: {str(e)}")
    
    async def run(self):
        """Main runner – sets up event handler and keeps running"""
        if not await self.authenticate():
            logger.error("❌ Failed to authenticate")
            return
        
        logger.info("🚀 Starting event-based forwarder...")
        logger.info(f"📅 ONLY files AFTER: {deployment.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info("📡 Listening for new messages...")
        
        # Register event handler
        @self.client.on(events.NewMessage)
        async def handler(event):
            await self.handle_new_message(event)
        
        # Keep running
        try:
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("🛑 Stopping...")
        except Exception as e:
            logger.error(f"❌ Fatal error: {str(e)}")
            await asyncio.sleep(10)
            os._exit(1)

# ================================================================
# MAIN
# ================================================================

async def main():
    await start_health_server()
    forwarder = TelegramForwarder()
    await forwarder.run()

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 TELEGRAM AUTO-FORWARDER v25.0 – EVENT-BASED (FINAL)")
    print("=" * 70)
    print(f"✅ Deployment time: {deployment.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"✅ Forward target: Xbox Checker Bot")
    print(f"✅ Control bot: Xbox Control Panel Bot")
    print(f"✅ Health check on port {PORT}")
    print("=" * 70)
    print("\n📋 How it works:")
    print("   • REAL-TIME event detection (NO polling)")
    print("   • Instantly detects new .txt files")
    print("   • Forwards them to Xbox Checker Bot")
    print("   • Human-like behavior with random delays")
    print("   • Database tracks forwarded files (no duplicates)")
    print("   • ONLY files AFTER deployment time are forwarded")
    print("\n🎮 Xbox Mode Activated – Instant Forwarding!\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
