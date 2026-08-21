#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TELEGRAM AUTO-FORWARDER v28.0 – FINAL RAILWAY DEPLOYMENT
✅ Uses your NEW session string
✅ Working bot resolution
✅ Scans channels for .txt files
✅ Forwards to Xbox Checker Bot
"""

import os
import sys
import json
import asyncio
import random
import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

# ================================================================
# ENVIRONMENT VARIABLES (Railway)
# ================================================================

SESSION_STRING = os.environ.get('SESSION_STRING', '1BVtsOJYBu2tXHovwxstEdqlXCXSiKDVy_sqmjJaTgR0DlFA1PuAytlrWLGescZkJ2TX0oMcruuxjMSpUa-dKMlcgYni6yzE2gnBzoax9qJ8JaVFJlORlIPP1faEClynqiLLgwpsQ1OwMPE-mF6dcPT0qEV_7GFsZdj4g0vMupMLlKNoYfJzyxmCk58y1teB1hei3FehjNl5ZeFDC_v6zcplvV2GMQSMQzXDckgU27qM60Ot546Fpvys0geHbxQoK0IyGtIp-pFSJTcne-sFdo-CO2-461eRBFnmWnPsnzRgmYzAcFBeqwl_QfXWFiPUQG2TN4fqayep0hFn6vghnO_s0EnjQ3vo=')
API_ID = int(os.environ.get('API_ID', 37897922))
API_HASH = os.environ.get('API_HASH', '6761ebe743a7389115a99af249cbbae6')
FORWARD_BOT_TOKEN = os.environ.get('FORWARD_BOT_TOKEN', '8872438487:AAHY-mmvGZnrSw9CpI6DJV1PmlQLap19ZiI')
CONTROL_BOT_TOKEN = os.environ.get('CONTROL_BOT_TOKEN', '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY')
FORWARD_BOT_USERNAME = os.environ.get('FORWARD_BOT_USERNAME', 'XboxCheckerBot')
CONTROL_BOT_USERNAME = os.environ.get('CONTROL_BOT_USERNAME', 'XboxControlBot')

SCAN_INTERVAL_MIN = int(os.environ.get('SCAN_INTERVAL_MIN', 10))
SCAN_INTERVAL_MAX = int(os.environ.get('SCAN_INTERVAL_MAX', 20))
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 50 * 1024 * 1024))
PORT = int(os.environ.get('PORT', 8080))

DB_FILE = 'forwarded_files.db'

# ================================================================
# AUTO-CREATE RAILWAY FILES
# ================================================================

def create_railway_files():
    try:
        if not os.path.exists('requirements.txt'):
            with open('requirements.txt', 'w') as f:
                f.write('telethon>=1.34.0\naiohttp>=3.9.0\ncryptg>=0.4.0\n')
        if not os.path.exists('start.sh'):
            with open('start.sh', 'w') as f:
                f.write('#!/bin/bash\npython main.py\n')
            os.chmod('start.sh', 0o755)
        if not os.path.exists('nixpacks.toml'):
            with open('nixpacks.toml', 'w') as f:
                f.write('[phases.setup]\nnixPkgs = ["python311"]\n[phases.install]\ncmds = ["pip install -r requirements.txt"]\n[phases.start]\ncmd = "python main.py"\n')
        if not os.path.exists('railway.json'):
            with open('railway.json', 'w') as f:
                f.write('{"build":{"builder":"NIXPACKS"},"deploy":{"startCommand":"python main.py","healthcheckPath":"/health"}}\n')
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
                    channel_name TEXT
                )
            ''')
            c.execute('CREATE INDEX IF NOT EXISTS idx_channel_id ON forwarded_files(channel_id)')
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
    except Exception as e:
        logger.warning(f"⚠️ Health check failed: {str(e)}")
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
                entity = await self.client.get_entity(f'@{bot_username}')
                logger.info(f"✅ Found bot by username: {entity.id}")
                return entity
            except Exception as e:
                logger.warning(f"⚠️ Username resolution failed: {str(e)}")
        try:
            entity = await self.client.get_entity(bot_id)
            logger.info(f"✅ Found bot by ID: {entity.id}")
            return entity
        except Exception as e:
            logger.warning(f"⚠️ ID resolution failed: {str(e)}")
        try:
            await self.client.send_message(bot_id, '/start')
            await asyncio.sleep(2)
            entity = await self.client.get_entity(bot_id)
            logger.info(f"✅ Found bot after /start: {entity.id}")
            return entity
        except Exception as e:
            logger.error(f"❌ All resolution methods failed: {str(e)}")
            return None

    async def authenticate(self):
        try:
            if not SESSION_STRING:
                logger.error("❌ SESSION_STRING is empty! Set it in Railway variables.")
                return False

            logger.info("🔑 Authenticating with session string...")
            self.client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
            await self.client.start()

            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username or 'no username'})")
            logger.info(f"✅ User ID: {me.id}")

            logger.info("🔍 Resolving forward bot...")
            self.forward_target = await self.resolve_bot(FORWARD_BOT_TOKEN, FORWARD_BOT_USERNAME)
            if not self.forward_target:
                logger.error("❌ Could not find Xbox Checker Bot!")
                return False
            logger.info(f"✅ Forward bot: {self.forward_target.id}")

            logger.info("🔍 Resolving control bot...")
            self.control_bot = await self.resolve_bot(CONTROL_BOT_TOKEN, CONTROL_BOT_USERNAME)
            if self.control_bot:
                logger.info(f"✅ Control bot: {self.control_bot.id}")
                try:
                    await self.client.send_message(
                        self.control_bot,
                        f"✅ Auto-Forwarder Started!\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                except:
                    pass
            else:
                logger.warning("⚠️ Control bot not available")

            return True
        except Exception as e:
            logger.error(f"❌ Auth failed: {str(e)}")
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
        try:
            messages = await self.client.get_messages(
                channel['entity'],
                limit=50
            )

            new_files = []
            for msg in messages:
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
        logger.info(f"📦 Processing {len(files)} files")

        for file_info in files:
            await self.forward_file(file_info)

    async def run_loop(self):
        logger.info("🔄 Starting scan loop...")
        logger.info(f"📊 Scan interval: {SCAN_INTERVAL_MIN}-{SCAN_INTERVAL_MAX}s")

        while self.is_running:
            try:
                if not self.client or not await self.client.is_user_authorized():
                    logger.warning("⚠️ Connection lost, reconnecting...")
                    if not await self.authenticate():
                        await asyncio.sleep(30)
                        continue

                channels = await self.get_channels()
                if not channels:
                    await asyncio.sleep(SCAN_INTERVAL_MIN)
                    continue

                all_files = []
                for channel in channels:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    files = await self.scan_channel(channel)
                    if files:
                        all_files.extend(files)

                if all_files:
                    logger.info(f"📦 Total {len(all_files)} new files")
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
                await asyncio.sleep(30)

    async def start(self):
        if not await self.authenticate():
            logger.error("❌ Failed to authenticate")
            return

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
    await start_health_server()
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

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 TELEGRAM AUTO-FORWARDER v28.0 – FINAL DEPLOYMENT")
    print("=" * 70)
    print(f"✅ Session string loaded")
    print(f"✅ Forward target: Xbox Checker Bot")
    print(f"✅ Control bot: Xbox Control Panel Bot")
    print(f"✅ Health check on port {PORT}")
    print("=" * 70)
    print("\n🎮 Xbox Mode Activated!\n")

    asyncio.run(main())
