import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import psutil
import time
import datetime
import google.generativeai as genai
from ddgs import DDGS

# --- [ 1. Setup Gemini ] ---
GEMINI_API_KEY = 'AIzaSyCkrqzxWa0aEWsnPhudtqAQAChgHf2afsM'
genai.configure(api_key=GEMINI_API_KEY)

# ใช้ชื่อรุ่นนี้ ชัวร์ที่สุดในตอนนี้ครับ
model = genai.GenerativeModel('gemini-flash-lite-latest')


start_time = time.time()
# --- ตั้งค่าพื้นฐาน (เหมือนเดิม) ---
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_CHANNEL_ID = 1069137562213552128

intents = discord.Intents.default()
intents.voice_states = True # Needed for voice check
bot = commands.Bot(command_prefix="!", intents=intents)
intents.message_content = True  # ✅ ต้องมีบรรทัดนี้! (สำคัญมากสำหรับคำสั่ง !)
intents.messages = True


@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user}')
    # 2. 🏠 เริ่มต้นระบบเช็คห้องเสียงอันแสนเสถียรของเรา (ขาดตัวนี้ไม่ได้!)
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
        print("🏠 Voice Check Loop Started")

    text_channel = bot.get_channel(123456789012345678) 
    if text_channel:
        await text_channel.send("🚀 บอท gosu.wav ออนไลน์พร้อมใช้งานแล้ว!")

# --- (โค้ดเช็คห้องเสียง อันเดิมของคุณที่รัน 24 ชม. ห้ามลบนะครับ!) ---
# เช็คทุก 5 วินาทีตามที่คุณตั้งไว้
@tasks.loop(seconds=5)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)

    if channel is None:
        return

    guild = channel.guild
    vc = guild.voice_client

    try:
        if vc is None:
            # print("🔍 ตรวจพบ: บอทไม่อยู่ในห้องเสียง กำลังเข้าร่วม...")
            await channel.connect(reconnect=True, timeout=20)
            # print(f"🏠 เข้าห้อง {channel.name} สำเร็จ")
        elif vc.channel.id != TARGET_CHANNEL_ID:
            # print(f"🔍 ตรวจพบ: บอทอยู่ผิดห้อง กำลังย้ายกลับ...")
            await vc.move_to(channel)
            # print(f"🏠 ย้ายกลับเข้าห้อง {channel.name} เรียบร้อย")
    except Exception as e:
        # 🔥 เปลี่ยนจาก pass เป็นระบบสลายเซสชันที่บูดทิ้ง
        print(f"⚠️ Voice Error: {e} | สั่ง Force Disconnect เพื่อเริ่มใหม่...")
        if vc:
            try:
                await vc.disconnect(force=True)
            except:
                pass

@bot.event
async def on_voice_state_update(member, before, after):
    # Optional logger (harmless to keep)
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        print("ℹ️ บอทหลุดจากห้องเสียง (จะกลับเข้าที่ในรอบตรวจถัดไป)")

# --- คำสั่งกลุ่ม !pvr ---
@bot.group(name="pvr", invoke_without_command=True)
async def pvr(ctx):
    # ถ้าพิมพ์ !pvr เฉยๆ ให้บอทลบข้อความนั้นทิ้งด้วย จะได้ไม่รก
    if ctx.author.id == 431421372133277698:
        await ctx.message.delete()
    pass

# --- คำสั่งย่อย !pvr say ---
@pvr.command(name="say")
async def say(ctx, *, message: str):
    # ID ของคุณที่ได้รับอนุญาต
    ALLOWED_USER_ID = 431421372133277698

    if ctx.author.id == ALLOWED_USER_ID:
        try:
            # 1. 🔥 คำสั่งลบข้อความที่คุณพิมพ์สั่ง (เช่น !pvr say test)
            await ctx.message.delete()

            # 2. 🎤 บอทส่งข้อความตามที่สั่ง
            await ctx.send(message)

            print(f"✅ บอทส่งข้อความแทนคุณแล้ว: {message}")

        except Exception as e:
            # ถ้าลบไม่ได้ (อาจเพราะบอทไม่มีสิทธิ์ Manage Messages) 
            # ให้บอทส่งข้อความไปก่อน แล้วค่อยแจ้ง Error ในหน้า Log
            await ctx.send(message)
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

@bot.command()
async def status(ctx):
    # 1. คำนวณ Uptime (เปิดมานานแค่ไหนแล้ว)
    current_time = time.time()
    difference = int(round(current_time - start_time))
    text_uptime = str(datetime.timedelta(seconds=difference))

    # 2. อ่านค่าทรัพยากรเครื่อง (GCP e2-micro ต้องเฝ้าระวังตัวนี้!)
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage('/')
    cpu = psutil.cpu_percent()

    # 3. เช็กสถานะ SQLite (ดูว่าฐานข้อมูลใหญ่แค่ไหน)
    db_size = os.path.getsize(db_filename) / (1024) # หน่วยเป็น KB

    # 4. สร้างรายงานแบบเน้นอ่านง่าย สไตล์ลุงอ๊อด
    report = (
        f"**📊 รายงานสุขภาพบอท: {BOT_NAME.upper()}**\n"
        f"---"
        f"\n⏱️ **เปิดมาแล้ว:** `{text_uptime}`"
        f"\n🏎️ **ความไวบอท (Ping):** `{round(bot.latency * 1000)}ms`"
        f"\n🖥️ **CPU ที่ใช้:** `{cpu}%`"
        f"\n🧠 **RAM:** `{ram.used // (1024**2)}MB` / `{ram.total // (1024**2)}MB`"
        f"\n🔄 **Swap:** `{swap.used // (1024**2)}MB` / `{swap.total // (1024**2)}MB`"
        f"\n💾 **Disk:** `{disk.percent}% used`"
        f"\n📖 **ขนาดสมอง (DB):** `{db_size:.2f} KB`"
        f"\n---"
    )
    
    # ถ้า RAM หรือ Swap เริ่มวิกฤต ลุงจะเตือนเป็นพิเศษ!
    if ram.percent > 90 or swap.percent > 80:
        report += "\n⚠️ **แจ้งเตือน:** ไอ้หลานเอ๊ย เครื่องจะระเบิดแล้วนะ RAM เต็มกะหร่องเลย!"

    await ctx.send(report)
    
bot.run(TOKEN)

