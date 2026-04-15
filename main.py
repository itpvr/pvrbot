import discord
from discord.ext import commands, tasks
import os
import asyncio
from flask import Flask
from threading import Thread

# ==========================================
# 🌐 1. ระบบ Keep-Alive (สำหรับ Render & Cronjob)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    # หน้าเว็บเล็กๆ ไว้บอกว่าบอททำงานอยู่
    return "🚀 GOSU.WAV Bot is Alive and Running!"

def run_web():
    # Render จะแจกพอร์ตมาให้ทางตัวแปร PORT (ค่าเริ่มต้น 8080)
    port = int(os.environ.get("PORT", 8080))
    # ปิดข้อความ Log รกๆ ของ Flask ไม่ให้กวนหน้าจอ tmux
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True # ให้ Thread ปิดตัวเองเมื่อบอทดับ
    t.start()
    print("🌐 เริ่มระบบ Web Server สำหรับรับ Cronjob แล้ว")

# ==========================================
# 🤖 2. ระบบ Bot พื้นฐาน
# ==========================================
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_CHANNEL_ID = 1069137562213552128 

intents = discord.Intents.default()
intents.voice_states = True 
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. ฟังก์ชันสถานะ (Spotify) ---
async def set_minimalist_presence():
    MY_APP_ID = 1493633885173579878 

    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="don't know whyyy", 
        application_id=MY_APP_ID,
        details="Kinda miss you ft. flug", 
        assets={
            "large_image": "kinda",        
            "large_text": "Kinda miss you", 
            "small_image": "spotify_logo", 
            "small_text": "Verified Artist" 
        },
        buttons=[
            {
                "label": "Play on gosu.wav 🎧", 
                "url": "https://gosuwav.vercel.app/artist/6str?track=86efea40-82d5-4960-86ae-50aeaf86eb25"
            }
        ]
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

@tasks.loop(seconds=5)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel is None: return

    guild = channel.guild
    vc = guild.voice_client

    try:
        if vc is None:
            # ถ้าไม่อยู่ในห้องเลย ให้ลองเข้า
            await channel.connect(reconnect=True, timeout=20)
        elif vc.channel.id != TARGET_CHANNEL_ID:
            # อยู่ผิดห้อง ให้ย้าย
            await vc.move_to(channel)
            
    except Exception as e:
        # 🔥 นี่คือจุดแก้ 4006: ถ้าพัง ให้สั่งตัดการเชื่อมต่อแบบรุนแรงทันที
        print(f"⚠️ Voice Error: {e} | กำลังล้าง Session...")
        if vc:
            try:
                await vc.disconnect(force=True) # ล้าง Session ที่บูดทิ้ง
            except:
                pass
        # พักสักครู่ให้ Discord ลืมเซสชันเก่า
        await asyncio.sleep(2)
        
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        print("ℹ️ บอทหลุดจากห้องเสียง (จะกลับเข้าที่ในรอบตรวจถัดไป)")

# ==========================================
# 💻 5. ระบบคำสั่ง (!pvr)
# ==========================================
@bot.group(name="pvr", invoke_without_command=True)
async def pvr(ctx):
    if ctx.author.id == 431421372133277698:
        await ctx.message.delete()
    pass

# คำสั่ง: !pvr say
@pvr.command(name="say")
async def say(ctx, *, message: str):
    ALLOWED_USER_ID = 431421372133277698
    
    if ctx.author.id == ALLOWED_USER_ID:
        await ctx.send(message)
        # หน่วงเวลา 0.5 วิ แก้บัคข้อความผี (Ghost Message) ในคอม
        await asyncio.sleep(0.5)
        try:
            await ctx.message.delete()
        except Exception as e:
            print(f"⚠️ คำเตือน: บอทลบข้อความไม่ได้ เนื่องจาก: {e}")
    else:
        # ถ้าไม่ใช่คุณสั่ง บอทจะนิ่งเฉย (และไม่ลบข้อความด้วย เพื่อให้เห็นว่าใครมาเนียน)
        print(f"🚫 มีคนพยายามสวมรอย: {ctx.author.name} (ID: {ctx.author.id})")
# --- คำสั่งย่อย !pvr clear [จำนวน] ---
@pvr.command(name="clear")
async def clear(ctx, amount: int = 5):
    # ตรวจสอบ ID คุณคนเดียว
    if ctx.author.id == 431421372133277698:
        try:
            # ลบข้อความ (บวก 1 เพื่อลบตัวคำสั่งออกไปด้วย)
            deleted = await ctx.channel.purge(limit=amount + 1)
            
            # ส่งข้อความบอกสถานะ แล้วลบตัวเองทิ้งใน 3 วินาที (ไม่ให้รกแชท)
            await ctx.send(f"🧹 ล้างประวัติแชทให้แล้ว {len(deleted)-1} ข้อความครับ", delete_after=3)
            
            print(f"✅ Clear success: {len(deleted)-1} messages by {ctx.author.name}")
        except Exception as e:
            print(f"❌ Clear error: {e}")
bot.run(TOKEN)