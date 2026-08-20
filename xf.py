#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TELEGRAM AUTO-FORWARDER v22.0 – FINAL RAILWAY DEPLOYMENT
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
            except:
                pass
        
        self.deployment_time = now_aware()
        self._save()
        logger.info(f"📅 New deployment time set: {self.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    def _save(self):
        try:
            naive_time = make_naive(self.deployment_time)
            with open(self.file_path, 'w') as f:
                json.dump({'deployment_time': naive_time.isoformat()}, f, indent=2)
        except:
            pass
    
    def is_after_deployment(self, message_date):
        try:
            return make_aware(message_date) > self.deployment_time
        except:
            return False

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
            conn.commit()
            conn.close()
            logger.info("✅ Database initialized")
        except:
            pass
    
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
        except:
            return False

db = DatabaseManager()

# ================================================================
# HUMAN MIMICRY
# ================================================================

class HumanMimic:
    @staticmethod
    async def simulate_typing(client, entity):
        try:
            async with client.action(entity, 'typing'):
                await asyncio.sleep(random.uniform(1.5, 4.0))
        except:
            pass
    
    @staticmethod
    async def simulate_reading(client, entity):
        try:
            await client.send_read_acknowledge(entity)
            await asyncio.sleep(random.uniform(0.3, 1.0))
        except:
            pass

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
# MAIN FORWARDER
# ================================================================

class TelegramForwarder:
    def __init__(self):
        self.client = None
        self.is_running = True
        self.forward_target = None
        self.control_bot = None
    
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
            self.client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
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
    
    async def get_channels(self):
        try:
            dialogs = await self.client.get_dialogs()
            return [{'id': d.id, 'name': d.name, 'entity': d.entity} for d in dialogs if d.is_channel]
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
        if message.document.size > MAX_FILE_SIZE:
            return None
        return {
            'hash': hashlib.sha256(f"{message.id}_{file_name}_{message.document.size}".encode()).hexdigest(),
            'name': file_name,
            'size': message.document.size,
            'message_id': message.id,
            'message_obj': message,
            'date': message.date
        }
    
    async def scan_channel(self, channel):
        try:
            messages = await self.client.get_messages(channel['entity'], limit=MAX_MESSAGES_PER_CHANNEL)
            new_files = []
            for msg in messages:
                if not deployment.is_after_deployment(msg.date):
                    continue
                file_info = self.extract_file_info(msg)
                if file_info and not db.is_forwarded(file_info['hash']):
                    new_files.append({**file_info, 'channel_id': channel['id'], 'channel_name': channel['name']})
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
            await self.client.forward_messages(self.forward_target, messages=file_info['message_obj'], drop_author=True)
            db.mark_forwarded(file_info['hash'], file_info['channel_id'], file_info['message_id'],
                             file_info['name'], file_info['size'], file_info['channel_name'], file_info['date'])
            logger.info(f"✅ Forwarded: {file_info['name']} ({file_info['size']/1024:.1f}KB)")
            if self.control_bot:
                try:
                    await self.client.send_message(self.control_bot, f"📤 {file_info['name']}\n📁 {file_info['size']/1024:.1f}KB")
                except:
                    pass
            await asyncio.sleep(random.uniform(2.0, 5.5))
            return True
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return False
        except Exception as e:
            logger.error(f"❌ Failed to forward {file_info['name']}: {str(e)}")
            return False
    
    async def run_loop(self):
        logger.info(f"🔄 Starting scan loop...")
        logger.info(f"📅 ONLY files AFTER: {deployment.get_deployment_time().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        while self.is_running:
            try:
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
                    logger.info(f"📦 Total {len(all_files)} NEW files")
                    random.shuffle(all_files)
                    for file_info in all_files:
                        await self.forward_file(file_info)
                else:
                    logger.info("📭 No new files")
                
                await asyncio.sleep(random.uniform(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX))
            except Exception as e:
                logger.error(f"❌ Loop error: {str(e)}")
                await asyncio.sleep(10)
    
    async def start(self):
        if not await self.authenticate():
            return
        await self.run_loop()

# ================================================================
# MAIN
# ================================================================

async def main():
    await start_health_server()
    forwarder = TelegramForwarder()
    try:
        await forwarder.start()
    except Exception as e:
        logger.error(f"❌ Fatal: {str(e)}")
        await asyncio.sleep(30)
        os._exit(1)

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 TELEGRAM AUTO-FORWARDER v22.0 – RAILWAY DEPLOYMENT")
    print("=" * 70)
    print(f"✅ Deployment time: {deployment.get_deployment_time().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"✅ Health check on port {PORT}")
    print("=" * 70)
    asyncio.run(main())
