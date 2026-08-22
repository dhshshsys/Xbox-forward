#!/usr/bin/env python3
"""
TELEGRAM FORWARDER - FINAL DEPLOYMENT
With FRESH session - NO CONFLICTS
"""

import sys
import os
import asyncio
import sqlite3
import random
from datetime import datetime, timedelta

# FORCE FLUSH
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("🚀 FINAL DEPLOYMENT WITH FRESH SESSION...", flush=True)

# ========== INSTALL TELEthon ==========
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

# ========== NEW SESSION STRING (FRESH) ==========
SESSION_STRING = '1BVtsOJYBu5e3_w2tzyQKDivSrxpr_tl4EdFbl4aYy2Y6JNdha62NHJrXi4K5VjSR3wEte_bKK67XIuAIckXGN4z3KtFPlXcr3cX0-AHSYyCixqz7P7uNw2Tmil4keLyVSkgDHFr7rQDxuGol9K2AYUyMDjRvCAaWIZTJQ_1t4Jlcn1pJGDfcS2fcpNTpGrsURCPHGSIs61RsO8JvFb2u3xty_-qoqtSkBnTq6Dc0bWM60FzT4Vg1UsdfgoLEqjaENqqRaDk0QB07v6yEPNA49BB1UP6Bm1hxcy4cgItxcY8UwYsUH1th3tDlvCpe_s9DFi63MePXc7BSKlMmzxvs-6KtMYQS5Ak='

CONTROL_BOT_TOKEN = '8904895394:AAH6rz5AJVIwWIPYMKnIrQkVAf81mSTO6cY'
CHECKER_BOT_ID = 8872438487

# ========== DATABASE ==========
conn = sqlite3.connect('forwarded.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, time TEXT)')
conn.commit()

def is_forwarded(file_id):
    c.execute('SELECT 1 FROM files WHERE id = ?', (file_id,))
    return c.fetchone() is not None

def mark_forwarded(file_id):
    c.execute('INSERT INTO files (id, time) VALUES (?, ?)', (file_id, datetime.now().isoformat()))
    conn.commit()

# ========== MAIN ==========
async def main():
    print("\n📡 Connecting with FRESH session...", flush=True)
    
    # Create client with NEW session
    user = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    
    try:
        await user.start()
        print("✅ Connected successfully!", flush=True)
    except Exception as e:
        print(f"❌ Connection failed: {e}", flush=True)
        return
    
    # Get user info
    me = await user.get_me()
    print(f"✅ Logged in as: {me.first_name} (@{me.username}) [ID: {me.id}]", flush=True)
    
    # Connect control bot
    print("🤖 Connecting control bot...", flush=True)
    control = TelegramClient('control', API_ID, API_HASH)
    await control.start(bot_token=CONTROL_BOT_TOKEN)
    bot_me = await control.get_me()
    print(f"✅ Control bot connected: @{bot_me.username}", flush=True)
    
    # ========== COMMAND HANDLER ==========
    @control.on(events.NewMessage)
    async def handle_commands(event):
        text = event.raw_text
        print(f"📩 Command: {text}", flush=True)
        
        if text == '/status':
            count = c.execute('SELECT COUNT(*) FROM files').fetchone()[0]
            await event.reply(f"✅ ALIVE\nTime: {datetime.now()}\nForwarded: {count} files")
        
        elif text == '/scan':
            await event.reply("🔍 Scanning...")
            await scan_and_forward(user)
            await event.reply("✅ Scan complete")
        
        elif text == '/start':
            await event.reply("✅ Bot running")
        
        elif text == '/help':
            await event.reply("Commands: /status, /scan, /start, /help")
    
    # ========== SCAN FUNCTION ==========
    async def scan_and_forward(user_client):
        print("🔍 Scanning...", flush=True)
        try:
            dialogs = await user_client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            print(f"📂 Found {len(channels)} channels", flush=True)
            
            for dialog in channels:
                try:
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
                        
                        file_name = None
                        for attr in msg.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                file_name = attr.file_name
                                break
                        if not file_name:
                            file_name = f"file_{msg.id}.txt"
                        
                        file_id = f"{dialog.id}_{msg.id}_{file_name}"
                        
                        if is_forwarded(file_id):
                            continue
                        
                        count += 1
                        print(f"📄 Found: {file_name} ({msg.document.size/1024:.1f}KB) from {dialog.name}", flush=True)
                        
                        try:
                            target = await user_client.get_input_entity(CHECKER_BOT_ID)
                            await user_client.forward_messages(target, messages=[msg.id], from_peer=dialog.entity)
                            mark_forwarded(file_id)
                            print(f"✅ Forwarded to CHECKER BOT: {file_name}", flush=True)
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
    
    # ========== START ==========
    print("\n" + "=" * 50, flush=True)
    print("✅ ALL SYSTEMS READY", flush=True)
    print(f"📤 Files → CHECKER BOT: {CHECKER_BOT_ID}", flush=True)
    print(f"🎯 Commands → CONTROL BOT", flush=True)
    print("=" * 50, flush=True)
    
    asyncio.create_task(scanner_loop())
    
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
