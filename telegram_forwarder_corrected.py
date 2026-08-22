#!/usr/bin/env python3
"""
TELEGRAM FORWARDER - SIMPLEST WORKING VERSION
NO complexity, NO fancy features, JUST WORKS
"""

import sys
import os
import asyncio
import logging
import sqlite3
import random
from datetime import datetime, timedelta

# FORCE FLUSH
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("🚀 SIMPLEST VERSION BOOTING...", flush=True)

# INSTALL TELEthon
try:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    from telethon.tl.types import DocumentAttributeFilename
    from telethon.errors import FloodWaitError
    print("✅ Telethon loaded", flush=True)
except ImportError:
    print("📦 Installing Telethon...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "--quiet"])
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    from telethon.tl.types import DocumentAttributeFilename
    from telethon.errors import FloodWaitError
    print("✅ Telethon installed", flush=True)

# ========== CONFIG ==========
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'

SESSION_STRING = '1BVtsOJYBu5lxKgz1X9OPtjrhIi5M4HOR8d25C9XbJU13PU3PUYxFjaMhF4OqjcgHmjZ-m26WJMJe33-C3absPhgKHpic_V5hk4VC5i82kUGHTDwGpt3gcmvo8gPnYGW2VTRzqSMl46hIuMoMbHHU82QndSkasFzJBVe2Y6uqVXz0AjyLw0TttDi1YZV-b6TWLKgpQDXFFzn1jnZ3dwtJ7ZKM96rb4vNxDzeq_DNDg8i_Xk6-PUMmVDQ7r6CYK5R_GCyYaoseYo2GEDoLcAFIqWI_TXSangMrVjiy-r6eD7W6w0pz_DbTefiOEGV2ik_NSmMx8U3_XA0vB-B-KVzDgH2ZKOE0W1A='

CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'
CHECKER_BOT_ID = 8872438487

# ========== SIMPLE DATABASE ==========
class DB:
    def __init__(self):
        self.conn = sqlite3.connect('forwarded.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY)')
        self.conn.commit()
    
    def exists(self, file_id):
        self.cursor.execute('SELECT 1 FROM files WHERE id = ?', (file_id,))
        return self.cursor.fetchone() is not None
    
    def add(self, file_id):
        self.cursor.execute('INSERT INTO files (id) VALUES (?)', (file_id,))
        self.conn.commit()

db = DB()

# ========== MAIN ==========
async def main():
    print("📡 Connecting to Telegram...", flush=True)
    
    # Create user client
    user = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await user.start(phone=lambda: '')
    
    me = await user.get_me()
    print(f"✅ Logged in as: {me.first_name} (@{me.username})", flush=True)
    
    # Create control bot
    print("🤖 Connecting control bot...", flush=True)
    control = TelegramClient('control', API_ID, API_HASH)
    await control.start(bot_token=CONTROL_BOT_TOKEN)
    bot_me = await control.get_me()
    print(f"✅ Control bot connected: @{bot_me.username}", flush=True)
    
    # ========== COMMAND HANDLER ==========
    @control.on(events.NewMessage(pattern='/status'))
    async def status_handler(event):
        print(f"📩 /status command received", flush=True)
        await event.reply(f"✅ Bot is alive!\nTime: {datetime.now()}\nForwarded: {db.cursor.execute('SELECT COUNT(*) FROM files').fetchone()[0]} files")
    
    @control.on(events.NewMessage(pattern='/scan'))
    async def scan_handler(event):
        print(f"📩 /scan command received", flush=True)
        await event.reply("🔍 Scanning...")
        await scan_and_forward(user)
        await event.reply("✅ Scan complete")
    
    @control.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        print(f"📩 /start command received", flush=True)
        await event.reply("✅ Bot started")
    
    @control.on(events.NewMessage(pattern='/help'))
    async def help_handler(event):
        await event.reply("Commands: /status, /scan, /start, /help")
    
    # ========== SCAN FUNCTION ==========
    async def scan_and_forward(user_client):
        print("🔍 Scanning channels...", flush=True)
        try:
            dialogs = await user_client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            print(f"📂 Found {len(channels)} channels", flush=True)
            
            for dialog in channels:
                try:
                    print(f"📂 Checking: {dialog.name}", flush=True)
                    since = datetime.now() - timedelta(minutes=30)
                    count = 0
                    
                    async for msg in user_client.iter_messages(dialog.entity, limit=30, offset_date=since):
                        if not msg.document:
                            continue
                        
                        mime = msg.document.mime_type or ''
                        if not (mime.endswith('txt') or mime.endswith('plain')):
                            continue
                        
                        if msg.document.size > 50 * 1024 * 1024:
                            continue
                        
                        # Get filename
                        file_name = None
                        for attr in msg.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                file_name = attr.file_name
                                break
                        if not file_name:
                            file_name = f"file_{msg.id}.txt"
                        
                        file_id = f"{dialog.id}_{msg.id}_{file_name}"
                        
                        if db.exists(file_id):
                            continue
                        
                        count += 1
                        print(f"📄 Found: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}", flush=True)
                        
                        # Forward to checker bot
                        try:
                            target = await user_client.get_input_entity(CHECKER_BOT_ID)
                            await user_client.forward_messages(target, messages=[msg.id], from_peer=dialog.entity)
                            db.add(file_id)
                            print(f"✅ Forwarded: {file_name} to CHECKER BOT", flush=True)
                        except Exception as e:
                            print(f"❌ Forward failed: {e}", flush=True)
                        
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                    if count > 0:
                        print(f"📤 Forwarded {count} files from {dialog.name}", flush=True)
                        
                except FloodWaitError as e:
                    print(f"⏳ Flood wait: {e.seconds}s", flush=True)
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    print(f"❌ Error on {dialog.name}: {e}", flush=True)
                    
        except Exception as e:
            print(f"💥 Scan error: {e}", flush=True)
    
    # ========== SCANNER LOOP ==========
    async def scanner_loop():
        print("🔄 Scanner loop started", flush=True)
        while True:
            try:
                await scan_and_forward(user)
                delay = random.randint(5, 10)
                print(f"⏳ Next scan in {delay}s", flush=True)
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"💥 Scanner error: {e}", flush=True)
                await asyncio.sleep(10)
    
    # ========== START EVERYTHING ==========
    print("✅ ALL SYSTEMS READY", flush=True)
    print("📤 Files will be forwarded to CHECKER BOT: 8872438487", flush=True)
    print("🎯 Commands go to CONTROL BOT", flush=True)
    print("🔥 Starting eternal loop...", flush=True)
    
    # Start scanner in background
    asyncio.create_task(scanner_loop())
    
    # Keep control bot running
    print("🎧 Listening for commands...", flush=True)
    await control.run_until_disconnected()

# ========== RUN ==========
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
    except Exception as e:
        print(f"💀 Fatal: {e}")
        import traceback
        traceback.print_exc()
