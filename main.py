import discord
from discord.ext import commands, tasks
import os
import asyncio

# --- ตั้งค่าพื้นฐาน ---
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_CHANNEL_ID = 1069137562213552128  # ID ห้องที่คุณต้องการให้บอทอยู่

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- ระบบตรวจเช็คห้องเสียงทุก 5 นาที ---
@tasks.loop(seconds=5)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    
    if channel is None:
        print(f"❌ ไม่พบห้อง ID {TARGET_CHANNEL_ID} กรุณาเช็ค ID อีกครั้ง")
        return

    # หา voice_client ของ Server นี้
    guild = channel.guild
    vc = guild.voice_client

    try:
        if vc is None:
            # กรณีที่ 1: บอทไม่ได้อยู่ในห้องไหนเลย
            print("🔍 ตรวจพบ: บอทไม่อยู่ในห้องเสียง กำลังเข้าร่วม...")
            await channel.connect(reconnect=True, timeout=20)
            print(f"🏠 เข้าห้อง {channel.name} สำเร็จ")
        
        elif vc.channel.id != TARGET_CHANNEL_ID:
            # กรณีที่ 2: บอทอยู่ผิดห้อง (โดนลากไป)
            print(f"🔍 ตรวจพบ: บอทอยู่ผิดห้อง ({vc.channel.name}) กำลังย้ายกลับ...")
            await vc.move_to(channel)
            print(f"🏠 ย้ายกลับเข้าห้อง {channel.name} เรียบร้อย")
            
        else:
            # กรณีปกติ: อยู่ในห้องถูกต้องแล้ว
            # print("✅ บอทยังอยู่ในห้องปกติ")
            pass

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดขณะเข้าห้องเสียง: {e}")

# --- Event เมื่อบอทพร้อมทำงาน ---
@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user}')
    # เริ่มต้นระบบเช็คห้องอัตโนมัติ
    if not check_voice_status.is_running():
        check_voice_status.start()

# --- ลบ on_voice_state_update ของเก่าออก ---
# เราจะไม่ใช้ระบบ Event เพื่อป้องกัน Loop นรก 4006 อีกต่อไป
# แต่ถ้าอยากให้มี Log ไว้ดู ก็เขียนสั้นๆ พอครับ
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        if before.channel is not None and after.channel is None:
            print("ℹ️ บอทออกจากห้องเสียง (จะกลับเข้าที่ในรอบตรวจถัดไป)")

bot.run(TOKEN)