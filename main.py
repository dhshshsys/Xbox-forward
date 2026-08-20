#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TELEGRAM AUTO-FORWARDER v24.0 – RAILWAY DEPLOYABLE (WORKING)
✅ Based on your working v10.0 forwarder
✅ Railway deployment ready
✅ Scans channels every 5-10 seconds
✅ Forwards .txt files under 50MB to Xbox Checker Bot
✅ Human-like behavior with random delays
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
FORWARD_DELAY_MIN = float(os.environ.get('FORWARD_DELAY_MIN', 2.0))
FORWARD_DELAY_MAX = float(os.environ.get('FORWARD_DELAY_MAX', 5.5))
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 5))
BATCH_PAUSE_MIN = float(os.environ.get('BATCH_PAUSE_MIN', 8))
BATCH_PAUSE_MAX = float(os.environ.get('BATCH_PAUSE_MAX', 15))
DAYS_BACK = int(os.environ.get('DAYS_BACK', 1))
PORT = int(os.environ.get('PORT', 8080))

DB_FILE = 'forwarded_files.db'
DEPLOYMENT_FILE = 'deployment_time.json'

# ================================================================
# AUTO-CREATE RAILWAY FILES
# ================================================================

def create_railway_files():
    """Auto-create all required Railway files"""
    try:
        if not os.path.exists('requirements.txt'):
            with open('requirements.txt', 'w') as f:
                f.write('''telethon>=1.34.0
aiohttp>=3.9.0
cryptg>=0.4.0
''')
            print("✅ Created requirements.txt")
        if not os.path.exists('start.sh'):
            with open('start.sh', 'w') as f:
                f.write('''#!/bin/bash
python main.py
''')
            os.chmod('start.sh', 0o755)
            print("✅ Created start.sh")
        if not os.path.exists('nixpacks.toml'):
            with open('nixpacks.toml', 'w') as f:
                f.write('''[phases.setup]
nixPkgs = ["python311"]
[phases.install]
cmds = ["pip install -r requirements.txt"]
[phases.start]
cmd = "python main.py"
''')
            print("✅ Created nixpacks.toml")
        if not os.path.exists('railway.json'):
            with open('railway.json', 'w') as f:
                f.write('''{
  "build": {"builder": "NIXPACKS"},
  "deploy": {
    "startCommand": "python main.py",
    "healthcheckPath": "/health"
  }
}
''')
            print("✅ Created railway.json")
        if not os.path.exists('Procfile'):
            with open('Procfile', 'w') as f:
                f.write('web: python main.py\n')
            print("✅ Created Procfile")
        return True
    except Exception as e:
        print(f"❌ Failed to create files: {str(e)}")
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
    
    def is_after_deployment(self, message_date):
        try:
            return make_aware(message_date) > self.deployment_time
        except:
            return False

deployment = DeploymentManager()

# ================================================================
# DATABASE MANAGER (FROM YOUR WORKING V10.0)
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
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT 1 FROM forwarded_files WHERE file_hash = ?', (file_hash,))
        result = c.fetchone()
        conn.close()
        return result is not None
    
    def mark_forwarded(self, file_hash, channel_id, message_id, file_name, file_size, channel_name):
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
    
    def cleanup_old(self, days=30):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        c.execute('DELETE FROM forwarded_files WHERE forwarded_at < ?', (cutoff.isoformat(),))
        conn.commit()
        conn.close()
        logger.info(f"🧹 Cleaned up records older than {days} days")

db = DatabaseManager()

# ================================================================
# HUMAN MIMICRY ENGINE (FROM YOUR WORKING V10.0)
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
        await asyncio.sleep(random.uniform(FORWARD_DELAY_MIN, FORWARD_DELAY_MAX))
    
    @staticmethod
    async def batch_pause():
        await asyncio.sleep(random.uniform(BATCH_PAUSE_MIN, BATCH_PAUSE_MAX))

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
# MAIN FORWARDER CLASS (FROM YOUR WORKING V10.0)
# ================================================================

class TelegramForwarder:
    def __init__(self):
        self.client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        self.is_running = True
        self.forward_target = None
        self.control_bot = None
    
    async def resolve_bot(self, bot_token, bot_username=None):
        """Resolve a bot entity using multiple methods"""
        bot_id = int(bot_token.split(':')[0])
        
        if bot_username:
            try:
                logger.info(f"   Trying to resolve by username: @{bot_username}")
                entity = await self.client.get_entity(f'@{bot_username}')
                logger.info(f"   ✅ Found by username: {entity.id}")
                return entity
            except Exception as e:
                logger.warning(f"   ⚠️ Username resolution failed: {str(e)}")
        
        try:
            logger.info(f"   Trying to find in dialogs...")
            dialogs = await self.client.get_dialogs()
            for dialog in dialogs:
                if dialog.entity.id == bot_id:
                    logger.info(f"   ✅ Found in dialogs: {dialog.entity.id}")
                    return dialog.entity
        except Exception as e:
            logger.warning(f"   ⚠️ Dialog search failed: {str(e)}")
        
        try:
            logger.info(f"   Trying to resolve by ID: {bot_id}")
            entity = await self.client.get_entity(bot_id)
            logger.info(f"   ✅ Found by ID: {entity.id}")
            return entity
        except Exception as e:
            logger.warning(f"   ⚠️ ID resolution failed: {str(e)}")
        
        try:
            logger.info(f"   Trying to start conversation with bot...")
            await self.client.send_message(bot_id, '/start')
            await asyncio.sleep(1)
            entity = await self.client.get_entity(bot_id)
            logger.info(f"   ✅ Found after sending /start: {entity.id}")
            return entity
        except Exception as e:
            logger.error(f"   ❌ All resolution methods failed: {str(e)}")
            return None
    
    async def authenticate(self):
        """Authenticate and setup bots"""
        try:
            logger.info("🔑 Authenticating with session string...")
            await self.client.start()
            
            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username or 'no username'})")
            logger.info(f"✅ User ID: {me.id}")
            
            logger.info("🔍 Setting up Xbox Checker Bot (forward target)...")
            logger.info("   Using multiple resolution methods...")
            
            self.forward_target = await self.resolve_bot(FORWARD_BOT_TOKEN, FORWARD_BOT_USERNAME)
            
            if not self.forward_target:
                logger.error("❌ Could not find Xbox Checker Bot!")
                return False
            
            logger.info(f"✅ Xbox Checker Bot found: {self.forward_target.id}")
            logger.info(f"✅ All .txt files will be forwarded to Xbox Checker Bot")
            
            logger.info("🔍 Setting up Xbox Control Panel Bot...")
            self.control_bot = await self.resolve_bot(CONTROL_BOT_TOKEN, CONTROL_BOT_USERNAME)
            
            if self.control_bot:
                logger.info(f"✅ Xbox Control Panel Bot found: {self.control_bot.id}")
                try:
                    await self.client.send_message(
                        self.control_bot,
                        f"✅ Auto-Forwarder Started!\n"
                        f"👤 User: {me.first_name} (@{me.username or 'no username'})\n"
                        f"🆔 ID: {me.id}\n"
                        f"📤 Forwarding to: Xbox Checker Bot\n"
                        f"📁 Max file size: 50MB\n"
                        f"⏱️ Scan interval: 5-10 seconds"
                    )
                    logger.info("✅ Startup notification sent to Xbox Control Panel Bot")
                except Exception as e:
                    logger.warning(f"⚠️ Could not send startup notification: {str(e)}")
            else:
                logger.warning("⚠️ Xbox Control Panel Bot not available")
                logger.info("💡 Continuing without control bot...")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {str(e)}")
            return False
    
    async def get_channels(self):
        """Get all channels"""
        try:
            dialogs = await self.client.get_dialogs()
            channels = []
            for dialog in dialogs:
                if dialog.is_channel:
                    channels.append({
                        'id': dialog.id,
                        'name': dialog.name,
                        'title': dialog.title,
                        'entity': dialog.entity
                    })
            logger.info(f"📡 Found {len(channels)} channels")
            return channels
        except Exception as e:
            logger.error(f"❌ Error getting channels: {str(e)}")
            return []
    
    def extract_file_info(self, message):
        """Extract file info"""
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
    
    async def scan_channel(self, channel):
        """Scan a channel – ONLY files AFTER deployment time"""
        try:
            since_time = datetime.now() - timedelta(days=DAYS_BACK)
            messages = await self.client.get_messages(
                channel['entity'],
                limit=100,
                offset_date=since_time
            )
            
            new_files = []
            for msg in messages:
                # Skip files before deployment time
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
                logger.info(f"📄 Found {len(new_files)} new .txt files in {channel['name']}")
            
            return new_files
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s for {channel['name']}")
            await asyncio.sleep(e.seconds)
            return []
        except Exception as e:
            logger.error(f"❌ Error scanning {channel['name']}: {str(e)}")
            return []
    
    async def forward_file(self, file_info):
        """Forward a file to Xbox Checker Bot"""
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
                channel_name=file_info['channel_name']
            )
            
            logger.info(f"✅ Forwarded: {file_info['name']} ({file_info['size']/1024:.1f}KB) → Xbox Checker Bot")
            
            if self.control_bot:
                try:
                    await self.client.send_message(
                        self.control_bot,
                        f"📤 Forwarded: {file_info['name']}\n"
                        f"📁 Size: {file_info['size']/1024:.1f}KB\n"
                        f"📂 From: {file_info['channel_name']}\n"
                        f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
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
        """Process a batch"""
        if not files:
            return
        
        random.shuffle(files)
        logger.info(f"📦 Processing {len(files)} files")
        
        for i, file_info in enumerate(files):
            if i > 0 and i % BATCH_SIZE == 0:
                logger.info(f"⏸️ Batch pause – {i} files processed")
                await HumanMimic.batch_pause()
            
            await self.forward_file(file_info)
    
    async def run_loop(self):
        """Main loop"""
        logger.info("🔄 Starting scan loop...")
        logger.info(f"📊 Scan interval: {SCAN_INTERVAL_MIN}-{SCAN_INTERVAL_MAX}s")
        logger.info(f"📤 Forward target: Xbox Checker Bot")
        logger.info(f"📅 ONLY files AFTER: {deployment.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
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
                    logger.info(f"📦 Total {len(all_files)} new files to forward")
                    await self.process_files(all_files)
                else:
                    logger.info("📭 No new .txt files found")
                
                wait_time = random.uniform(SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX)
                logger.info(f"⏳ Next scan in {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"❌ Loop error: {str(e)}")
                await asyncio.sleep(10)
    
    async def start(self):
        """Start"""
        if not await self.authenticate():
            logger.error("❌ Failed to authenticate")
            return
        
        logger.info("🚀 Starting Xbox Auto-Forwarder...")
        await self.run_loop()
    
    async def stop(self):
        """Stop"""
        self.is_running = False
        await self.client.disconnect()
        logger.info("✅ Disconnected")

# ================================================================
# MAIN
# ================================================================

async def main():
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
        await asyncio.sleep(30)
        os._exit(1)

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 TELEGRAM AUTO-FORWARDER v24.0 – RAILWAY DEPLOYABLE")
    print("=" * 70)
    print(f"✅ Deployment time: {deployment.deployment_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"✅ Forward target: Xbox Checker Bot")
    print(f"✅ Control bot: Xbox Control Panel Bot")
    print(f"✅ Health check on port {PORT}")
    print("=" * 70)
    print("\n📋 How it works:")
    print("   • Scans all your channels every 5-10 seconds")
    print("   • Finds .txt files under 50MB")
    print("   • Forwards them to Xbox Checker Bot")
    print("   • Human-like behavior with random delays")
    print("   • Database tracks forwarded files (no duplicates)")
    print("   • ONLY files AFTER deployment time are forwarded")
    print("\n🎮 Xbox Mode Activated!\n")
    
    asyncio.run(main())
