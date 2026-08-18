#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
TELEGRAM AUTO-FORWARDER v19.0 – RAILWAY DEPLOYMENT (SINGLE FILE)
================================================================================
✅ ALL-IN-ONE – Just upload this ONE file to Railway
✅ Auto-detects Railway environment
✅ Creates all necessary files on first run
✅ Self-contained – no other files needed
✅ Works on Railway free plan
================================================================================
"""

import os
import sys
import json
import asyncio
import random
import sqlite3
import hashlib
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

# ================================================================
# ENVIRONMENT VARIABLES (Set these in Railway dashboard)
# ================================================================

SESSION_STRING = os.environ.get('SESSION_STRING', '1BVtsOLEBuzomCJpipJP4r4UoPd66tglye3cdnHy-O2Gf1jbZRyQSIA5p7cpUpj3D2NPubpNWmGvZ4OgfAFz9gbcw2uGyrkz5iRaH0i8735Vz8H-iFRmsBInTuCZ6mB-KHABExVfZzuzS2XDzxNJVUTbyAZByQQ1gLqKK_UKHC5ShKuB_i2S8ebfWRx4ix1nkjwnTgcP2aPzKLmO_CpdP95VyQWWj2IORoyzrRgj3MaN7fBt52uWKGWoL3DmxJvDnXiWO-wZOkuAgHYFMDzKPDgNYDb2Pbe1VQX-rJxDAoj4d7SMp9SwcxfdeUuFgTrVwgf0CqFe3hTdh71oD14q6rs6EXVXBbME=')
API_ID = int(os.environ.get('API_ID', 37897922))
API_HASH = os.environ.get('API_HASH', '6761ebe743a7389115a99af249cbbae6')
FORWARD_BOT_TOKEN = os.environ.get('FORWARD_BOT_TOKEN', '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI')
CONTROL_BOT_TOKEN = os.environ.get('CONTROL_BOT_TOKEN', '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY')
FORWARD_BOT_USERNAME = os.environ.get('FORWARD_BOT_USERNAME', 'XboxCheckerBot')
CONTROL_BOT_USERNAME = os.environ.get('CONTROL_BOT_USERNAME', 'XboxControlBot')

SCAN_INTERVAL_MIN = int(os.environ.get('SCAN_INTERVAL_MIN', 5))
SCAN_INTERVAL_MAX = int(os.environ.get('SCAN_INTERVAL_MAX', 10))
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 50 * 1024 * 1024))
MAX_MESSAGES_PER_CHANNEL = int(os.environ.get('MAX_MESSAGES_PER_CHANNEL', 20))
PORT = int(os.environ.get('PORT', 8080))

DB_FILE = 'forwarded_files.db'
DEPLOYMENT_FILE = 'deployment_time.json'

# ================================================================
# LOGGING
# ================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('forwarder.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ================================================================
# RAILWAY AUTO-SETUP – Creates required files on first run
# ================================================================

def setup_railway_files():
    """Auto-create all required Railway files on first run"""
    try:
        # Create nixpacks.toml
        if not os.path.exists('nixpacks.toml'):
            with open('nixpacks.toml', 'w') as f:
                f.write('''[phases.setup]
nixPkgs = ["python311"]

[phases.install]
cmds = ["pip install -r requirements.txt"]

[phases.start]
cmd = "python forwarder.py"
''')
            logger.info("✅ Created nixpacks.toml")

        # Create requirements.txt
        if not os.path.exists('requirements.txt'):
            with open('requirements.txt', 'w') as f:
                f.write('''telethon>=1.34.0
aiohttp>=3.9.0
cryptg>=0.4.0
''')
            logger.info("✅ Created requirements.txt")

        # Create start.sh
        if not os.path.exists('start.sh'):
            with open('start.sh', 'w') as f:
                f.write('''#!/bin/bash
echo "🚀 Starting Xbox Forwarder..."
python forwarder.py
''')
            os.chmod('start.sh', 0o755)
            logger.info("✅ Created start.sh")

        # Create railway.json
        if not os.path.exists('railway.json'):
            with open('railway.json', 'w') as f:
                f.write('''{
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r requirements.txt"
  },
  "deploy": {
    "startCommand": "python forwarder.py",
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
''')
            logger.info("✅ Created railway.json")

        # Create Procfile
        if not os.path.exists('Procfile'):
            with open('Procfile', 'w') as f:
                f.write('web: python forwarder.py\n')
            logger.info("✅ Created Procfile")

        return True
    except Exception as e:
        logger.error(f"❌ Failed to create Railway files: {str(e)}")
        return False

# ================================================================
# TIMEZONE HELPERS
# ================================================================

def make_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def make_naive(dt):
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
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
            except Exception as e:
                logger.warning(f"⚠️ Could not load deployment file: {str(e)}")
        
        self.deployment_time = now_aware()
        self._save()
        logger.info(f"📅 New deployment time set: {self.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    def _save(self):
        try:
            naive_time = make_naive(self.deployment_time)
            with open(self.file_path, 'w') as f:
                json.dump({
                    'deployment_time': naive_time.isoformat(),
                    'created_at': make_naive(now_aware()).isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Could not save deployment time: {str(e)}")
    
    def is_after_deployment(self, message_date):
        try:
            msg_date_aware = make_aware(message_date)
            return msg_date_aware > self.deployment_time
        except:
            return False
    
    def get_deployment_time(self):
        return self.deployment_time

deployment = DeploymentManager()

# ================================================================
# DATABASE
# ================================================================

class DatabaseManager:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        try:
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
                    channel_name TEXT,
                    message_date TIMESTAMP
                )
            ''')
            c.execute('CREATE INDEX IF NOT EXISTS idx_channel_msg ON forwarded_files(channel_id, message_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_forwarded_at ON forwarded_files(forwarded_at)')
            conn.commit()
            conn.close()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database init failed: {str(e)}")
    
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
    
    def mark_forwarded(self, file_hash, channel_id, message_id, file_name, file_size, channel_name, message_date):
        try:
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            naive_date = make_naive(message_date)
            c.execute('''
                INSERT OR REPLACE INTO forwarded_files 
                (file_hash, channel_id, message_id, file_name, file_size, forwarded_at, channel_name, message_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (file_hash, channel_id, message_id, file_name, file_size, 
                  make_naive(now_aware()).isoformat(), channel_name, naive_date.isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Database mark failed: {str(e)}")
            return False

db = DatabaseManager()

# ================================================================
# HUMAN MIMICRY
# ================================================================

class HumanMimic:
    @staticmethod
    async def simulate_typing(client, entity):
        try:
            duration = random.uniform(1.5, 4.0)
            async with client.action(entity, 'typing'):
                await asyncio.sleep(duration)
        except:
            pass
    
    @staticmethod
    async def simulate_reading(client, entity):
        try:
            await client.send_read_acknowledge(entity)
            await asyncio.sleep(random.uniform(0.3, 1.0))
        except:
            pass
    
    @staticmethod
    async def delay_between_forwards():
        await asyncio.sleep(random.uniform(2.0, 5.5))

# ================================================================
# HEALTH CHECK SERVER
# ================================================================

async def start_health_server():
    """Start simple HTTP server for Railway health checks"""
    try:
        from aiohttp import web
        app = web.Application()
        app.router.add_get('/', lambda r: web.Response(text="OK", status=200))
        app.router.add_get('/health', lambda r: web.json_response({"status": "ok", "time": datetime.now().isoformat()}))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        logger.info(f"✅ Health check server running on port {PORT}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Health check server failed: {str(e)}")
        return False

# ================================================================
# MAIN FORWARDER
# ================================================================

class TelegramForwarder:
    def __init__(self):
        self.client = None
        self.is_running = True
        self.forward_target = None
        self.control_bot = None
        self.deployment_time = deployment.get_deployment_time()
    
    async def resolve_bot(self, bot_token, bot_username=None):
        bot_id = int(bot_token.split(':')[0])
        
        if bot_username:
            try:
                entity = await self.client.get_entity(f'@{bot_username}')
                return entity
            except:
                pass
        
        try:
            entity = await self.client.get_entity(bot_id)
            return entity
        except:
            pass
        
        try:
            await self.client.send_message(bot_id, '/start')
            await asyncio.sleep(1)
            entity = await self.client.get_entity(bot_id)
            return entity
        except:
            return None
    
    async def connect(self):
        try:
            if self.client is None:
                self.client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                await self.client.start()
            
            return True
        except Exception as e:
            logger.error(f"❌ Connection error: {str(e)}")
            return False
    
    async def authenticate(self):
        try:
            for attempt in range(3):
                if await self.connect():
                    break
                logger.info(f"🔄 Reconnect attempt {attempt + 1}/3")
                await asyncio.sleep(5)
            else:
                logger.error("❌ Failed to connect after 3 attempts")
                return False
            
            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username or 'no username'})")
            logger.info(f"✅ User ID: {me.id}")
            
            self.forward_target = await self.resolve_bot(FORWARD_BOT_TOKEN, FORWARD_BOT_USERNAME)
            if not self.forward_target:
                logger.error("❌ Could not find Xbox Checker Bot!")
                return False
            logger.info(f"✅ Xbox Checker Bot found: {self.forward_target.id}")
            
            self.control_bot = await self.resolve_bot(CONTROL_BOT_TOKEN, CONTROL_BOT_USERNAME)
            if self.control_bot:
                logger.info(f"✅ Xbox Control Panel Bot found: {self.control_bot.id}")
                try:
                    await self.client.send_message(
                        self.control_bot,
                        f"✅ Forwarder Started!\n📅 Deployment: {self.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                except:
                    pass
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {str(e)}")
            return False
    
    async def get_channels(self):
        try:
            dialogs = await self.client.get_dialogs()
            channels = []
            for dialog in dialogs:
                if dialog.is_channel:
                    channels.append({
                        'id': dialog.id,
                        'name': dialog.name,
                        'entity': dialog.entity
                    })
            logger.info(f"📡 Found {len(channels)} channels")
            return channels
        except Exception as e:
            logger.error(f"❌ Error getting channels: {str(e)}")
            return []
    
    def extract_file_info(self, message):
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
    
    async def scan_channel(self, channel):
        try:
            messages = await self.client.get_messages(
                channel['entity'],
                limit=MAX_MESSAGES_PER_CHANNEL
            )
            
            new_files = []
            for msg in messages:
                if not deployment.is_after_deployment(msg.date):
                    continue
                
                file_info = self.extract_file_info(msg)
                if file_info and not db.is_forwarded(file_info['hash']):
                    new_files.append({
                        **file_info,
                        'channel_id': channel['id'],
                        'channel_name': channel['name']
                    })
            
            if new_files:
                logger.info(f"📄 Found {len(new_files)} NEW files in {channel['name']}")
            
            return new_files
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return []
        except Exception as e:
            logger.error(f"❌ Error scanning {channel['name']}: {str(e)}")
            return []
    
    async def forward_file(self, file_info):
        try:
            await HumanMimic.simulate_reading(self.client, file_info['message_obj'].peer_id)
            await HumanMimic.simulate_typing(self.client, self.forward_target)
            
            await self.client.forward_messages(
                self.forward_target,
                messages=file_info['message_obj'],
                drop_author=True
            )
            
            db.mark_forwarded(
                file_hash=file_info['hash'],
                channel_id=file_info['channel_id'],
                message_id=file_info['message_id'],
                file_name=file_info['name'],
                file_size=file_info['size'],
                channel_name=file_info['channel_name'],
                message_date=file_info['date']
            )
            
            logger.info(f"✅ Forwarded: {file_info['name']} ({file_info['size']/1024:.1f}KB)")
            
            if self.control_bot:
                try:
                    await self.client.send_message(
                        self.control_bot,
                        f"📤 {file_info['name']}\n📁 {file_info['size']/1024:.1f}KB\n📂 {file_info['channel_name']}"
                    )
                except:
                    pass
            
            await HumanMimic.delay_between_forwards()
            return True
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error(f"❌ Failed to forward {file_info['name']}: {str(e)}")
            return False
    
    async def process_files(self, files):
        if not files:
            return
        
        random.shuffle(files)
        logger.info(f"📦 Processing {len(files)} new files")
        
        for file_info in files:
            await self.forward_file(file_info)
    
    async def run_loop(self):
        logger.info(f"🔄 Starting scan loop...")
        logger.info(f"📅 ONLY forwarding files posted AFTER: {self.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        while self.is_running:
            try:
                if not self.client or not await self.client.is_user_authorized():
                    if not await self.authenticate():
                        await asyncio.sleep(30)
                        continue
                
                channels = await self.get_channels()
                if not channels:
                    await asyncio.sleep(SCAN_INTERVAL_MIN)
                    continue
                
                all_files = []
                for channel in channels:
                    await asyncio.sleep(random.uniform(0.2, 0.6))
                    files = await self.scan_channel(channel)
                    if files:
                        all_files.extend(files)
                
                if all_files:
                    logger.info(f"📦 Total {len(all_files)} NEW files found")
                    await self.process_files(all_files)
                else:
                    logger.info("📭 No new files")
                
                wait_time = random.uniform(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                logger.info(f"⏳ Next scan in {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"❌ Loop error: {str(e)}")
                await asyncio.sleep(10)
    
    async def start(self):
        if not await self.authenticate():
            logger.error("❌ Failed to authenticate")
            return
        
        logger.info("🚀 Starting forwarder...")
        await self.run_loop()
    
    async def stop(self):
        self.is_running = False
        if self.client:
            await self.client.disconnect()
        logger.info("✅ Disconnected")

# ================================================================
# MAIN
# ================================================================

async def main():
    # Setup Railway files on first run
    setup_railway_files()
    
    # Start health check
    await start_health_server()
    
    # Start forwarder
    forwarder = TelegramForwarder()
    try:
        await forwarder.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping...")
        await forwarder.stop()
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        await forwarder.stop()
        logger.info("🔄 Restarting in 30 seconds...")
        await asyncio.sleep(30)
        os._exit(1)

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 TELEGRAM AUTO-FORWARDER v19.0 – RAILWAY READY")
    print("=" * 70)
    print(f"✅ Deployment time: {deployment.get_deployment_time().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"✅ ONLY files posted AFTER this time will be forwarded")
    print(f"✅ Health check on port {PORT}")
    print(f"✅ Auto-creates all Railway files on first run")
    print("=" * 70)
    print("\n🎮 Xbox Mode Activated – Running Forever!\n")
    
    asyncio.run(main())