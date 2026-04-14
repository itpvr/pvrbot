import discord
from discord.ext import commands
import os
import datetime
import asyncio
from flask import Flask
from threading import Thread

# --- ส่วนของ Web Server (แก้เรื่อง Port สำหรับ Render) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    # Render จะส่ง Port มาให้ผ่าน Environment Variable ชื่อ PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- ตั้งค่าบอท ---
TARGET_CHANNEL_ID = 1069137562213552128 # ไอดีห้องที่คุณกำหนด

intents = discord.Intents.default()
intents.voice_states = True      # สำคัญ: ต้องเปิดใน Discord Developer Portal ด้วย
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_users = {}

@bot.event
async def on_ready():
    await bot.wait_until_ready() # เพิ่มบรรทัดนี้: รอให้ระบบโหลดข้อมูลเซิร์ฟเวอร์ให้ครบก่อน
    print(f'✅ ออนไลน์แล้ว: {bot.user}')
    
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel:
        try:
            # เช็คว่าบอทอยู่ในห้องอยู่แล้วหรือเปล่า (กันบัคเข้าซ้อน)
            voice_client = discord.utils.get(bot.voice_clients, guild=channel.guild)
            if not voice_client:
                await channel.connect()
                print(f"🏠 บอทเข้าห้อง {channel.name} เรียบร้อยแล้ว")
        except Exception as e:
            print(f"❌ เข้าห้องไม่ได้ Error: {e}")
    else:
        print(f"❌ หาห้อง ID {TARGET_CHANNEL_ID} ไม่เจอ! (เช็คสิทธิ์การมองเห็น)")

@bot.event
async def on_voice_state_update(member, before, after):
    # 1. ตรวจสอบว่า "ตัวบอทเอง" ถูกย้ายห้องหรือไม่
    if member.id == bot.user.id:
        # ถ้าบอทไม่ได้อยู่ในห้อง หรือ อยู่ในห้องที่ไม่ใช่ห้องเป้าหมาย
        if after.channel is None or after.channel.id != TARGET_CHANNEL_ID:
            print(f"⚠️ บอทถูกย้าย! กำลังจะกลับไปห้องเดิมใน 5 วินาที...")
            await asyncio.sleep(5)
            
            channel = bot.get_channel(TARGET_CHANNEL_ID)
            if channel:
                # ตรวจสอบ Voice Client เดิม
                voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
                if voice_client:
                    await voice_client.move_to(channel)
                else:
                    await channel.connect()
                print(f"🏠 กลับเข้าห้องเป้าหมายสำเร็จ")
        return

    # 2. การเก็บสถิติ (เฉพาะห้องเป้าหมายเท่านั้น)
    # กรณี User เข้าห้องเป้าหมาย
    if after.channel and after.channel.id == TARGET_CHANNEL_ID:
        if before.channel is None or before.channel.id != TARGET_CHANNEL_ID:
            active_users[member.id] = datetime.datetime.now()
            print(f"📥 {member.name} เริ่มนับเวลาในห้องเป้าหมาย")

    # กรณี User ออกจากห้องเป้าหมาย
    elif before.channel and before.channel.id == TARGET_CHANNEL_ID:
        if after.channel is None or after.channel.id != TARGET_CHANNEL_ID:
            start_time = active_users.pop(member.id, None)
            if start_time:
                duration = datetime.datetime.now() - start_time
                minutes = round(duration.total_seconds() / 60, 2)
                print(f"📤 {member.name} ออกจากห้องเป้าหมาย. สถิติ: {minutes} นาที")

# เริ่มทำงาน
keep_alive()
token = os.environ.get('DISCORD_TOKEN')
if token:
    bot.run(token)
else:
    print("❌ ไม่พบ DISCORD_TOKEN")