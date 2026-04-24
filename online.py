import discord
from discord.ext import commands, tasks
import os
import sys
import psutil
import time
import datetime

# --- [ ⚙️ ดึงเฉพาะ Token ไม่ต้องใช้ API Key ของ AI แล้ว ] ---
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print(f"❌ Error: ขาด Token! (เช็คการ export ค่าก่อนรัน)")
    sys.exit()

start_time = time.time()
TARGET_CHANNEL_ID = 1069137562213552128

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user} | โหมด: สแตนด์บาย (No AI)')
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
        print("🏠 Voice Check Loop Started")

# --- [ 🎤 ระบบเฝ้าห้องเสียง ] ---
@tasks.loop(seconds=10) # ตั้ง 10 วิก็พอ จะได้ไม่กิน CPU เซิร์ฟเวอร์ฟรี
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel is None: return
    
    guild = channel.guild
    vc = guild.voice_client
    try:
        if vc is None:
            await channel.connect(reconnect=True, timeout=20)
        elif vc.channel.id != TARGET_CHANNEL_ID:
            await vc.move_to(channel)
    except Exception as e:
        print(f"⚠️ Voice Error: {e} | สั่ง Force Disconnect...")
        if vc:
            try: await vc.disconnect(force=True)
            except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    pass # ปิดแจ้งเตือนจุกจิก

# --- [ 🛠️ กลุ่มคำสั่ง !pvr (เฉพาะสั่งพูดและลบข้อความ) ] ---
@bot.group(name="pvr", invoke_without_command=True)
async def pvr(ctx):
    if ctx.author.id == 431421372133277698:
        try: await ctx.message.delete()
        except: pass

@pvr.command(name="say")
async def say(ctx, *, message: str):
    if ctx.author.id == 431421372133277698:
        try:
            await ctx.message.delete()
            await ctx.send(message)
        except Exception as e:
            await ctx.send(message)
            print(f"⚠️ Error: {e}")

@pvr.command(name="clear")
async def clear(ctx, amount: int = 5):
    if ctx.author.id == 431421372133277698:
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            await ctx.send(f"🧹 ล้างให้แล้ว {len(deleted)-1} ข้อความ", delete_after=3)
        except Exception as e:
            print(f"❌ Clear error: {e}")

# --- [ 📊 ระบบรายงานสุขภาพ (ตัดส่วน Database ออก) ] ---
@bot.command()
async def status(ctx):
    current_time = time.time()
    difference = int(round(current_time - start_time))
    text_uptime = str(datetime.timedelta(seconds=difference))

    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu = psutil.cpu_percent()

    report = (
        f"**📊 รายงานสุขภาพ (Standby Mode): {BOT_NAME.upper()}**\n"
        f"---"
        f"\n⏱️ **เปิดมาแล้ว:** `{text_uptime}`"
        f"\n🏎️ **ความไว (Ping):** `{round(bot.latency * 1000)}ms`"
        f"\n🖥️ **CPU:** `{cpu}%`"
        f"\n🧠 **RAM:** `{ram.used // (1024**2)}MB` / `{ram.total // (1024**2)}MB`"
        f"\n🔄 **Swap:** `{swap.used // (1024**2)}MB`"
        f"\n---"
    )
    await ctx.send(report)

bot.run(TOKEN)