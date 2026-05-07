import discord
from discord.ext import commands, tasks
import os
import sys
import psutil
import time
import datetime

# --- [ ⚙️ Setup ] ---
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print(f"❌ Error: ขาด Token! (เช็คการ export ค่าก่อนรัน)")
    sys.exit()

start_time = time.time()
TARGET_ID = 1461009670029447432 # รหัสห้องใหม่ที่หลานต้องการ
LOG_CHANNEL_ID = 1497227431462043708

# สร้าง Bot Class เพื่อรองรับ Slash Command อย่างสมบูรณ์
class MinimalBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync Slash Commands ตอนเปิดบอท
        await self.tree.sync()
        print("✅ สตาร์ทเครื่องและ Sync Slash Commands เรียบร้อย!")

bot = MinimalBot()

# --- [ 🚀 กุญแจสตาร์ทเครื่อง ] ---
@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user} | โหมด: Minimalist Standby')
    
    # สั่งให้ยามเดินตรวจ (Loop 30s) เริ่มทำงาน
    if not check_voice_status.is_running():
        check_voice_status.start()
        print("🏠 Voice Check Loop 30s Started")

# --- [ 📝 ฟังก์ชันส่งใบรายงาน (Log) ] ---
async def send_log(status_type, reason):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel: return
    
    color = discord.Color.red() if status_type == "drop" else discord.Color.gold()
    icon = "🔴" if status_type == "drop" else "🟠"
    title = f"{icon} Bot Reconnected" if status_type == "drop" else f"{icon} Bot Relocated"
    
    embed = discord.Embed(title=title, color=color, timestamp=datetime.datetime.now())
    embed.add_field(name="สาเหตุ / Action", value=f"`{reason}`", inline=False)
    embed.add_field(name="เป้าหมาย", value=f"<#{TARGET_ID}>", inline=True)
    embed.set_footer(text="Minimalist Recovery Service")
    
    await log_channel.send(embed=embed)

# --- [ 🔄 ระบบยามเดินตรวจเช็กทุก 30 วินาที ] ---
@tasks.loop(seconds=30)
async def check_voice_status():
    await bot.wait_until_ready()
    target_channel = bot.get_channel(TARGET_ID)
    if not target_channel: return

    vc = target_channel.guild.voice_client

    # 🛑 กรณีที่ 1: บอทหลุด หรือ ไม่มี Voice Client เลย
    if vc is None or not vc.is_connected():
        try:
            if vc: # ล้างท่อเก่าถ้ามันค้าง
                await vc.disconnect(force=True)
                await asyncio.sleep(1)
            
            await target_channel.connect(timeout=20)
            await send_log("drop", "ตรวจพบว่าบอทหลุดจากห้องเสียง (ทำการเชื่อมต่อใหม่แล้ว)")
            print("🔄 [30s Loop] บอทหลุด -> เชื่อมต่อใหม่สำเร็จ")
        except Exception as e:
            print(f"❌ [30s Loop] ต่อใหม่ไม่สำเร็จ: {e}")

    # 🟠 กรณีที่ 2: บอทอยู่ในสาย แต่ "อยู่ผิดห้อง"
    elif vc.channel.id != TARGET_ID:
        try:
            await target_channel.guild.me.move_to(target_channel)
            await send_log("move", "ตรวจพบว่าบอทอยู่ผิดห้อง (ทำการย้ายกลับห้องหลักแล้ว)")
            print("⚡ [30s Loop] บอทอยู่ผิดห้อง -> ย้ายกลับสำเร็จ")
        except Exception as e:
            print(f"❌ [30s Loop] ย้ายห้องไม่สำเร็จ: {e}")

    # 🟢 กรณีที่ 3: อยู่ในห้องเป้าหมายปกติ -> ไม่ต้องทำอะไร ปล่อยชิลๆ

# --- [ 📊 คำสั่ง /status (Slash Command) ] ---
@bot.tree.command(name="status", description="เช็กสถานะเครื่องเซิร์ฟเวอร์แบบ Real-time")
async def status(interaction: discord.Interaction):
    bot_name = os.getenv('BOT_NAME', 'Minimal_Bot')
    current_time = time.time()
    uptime = str(datetime.timedelta(seconds=int(round(current_time - start_time))))

    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent()
    ping = round(bot.latency * 1000)

    if cpu > 85 or ram.percent > 90:
        embed_color, status_text = discord.Color.red(), "🔴 วิกฤต (Critical)"
    elif cpu > 60 or ram.percent > 70:
        embed_color, status_text = discord.Color.orange(), "🟠 เริ่มหนัก (Warning)"
    else:
        embed_color, status_text = discord.Color.green(), "🟢 ปกติ (Healthy)"

    embed = discord.Embed(
        title=f"🖥️ System Status : {bot_name.upper()}",
        description=f"**สถานะเครื่อง:** {status_text}",
        color=embed_color,
        timestamp=datetime.datetime.now()
    )

    embed.add_field(name="⏱️ Uptime", value=f"`{uptime}`", inline=True)
    embed.add_field(name="📶 Ping", value=f"`{ping} ms`", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True) 

    embed.add_field(name="⚙️ CPU Usage", value=f"`{cpu}%`", inline=True)
    embed.add_field(name="🧠 RAM Usage", value=f"`{ram.used // (1024**2)} MB ({ram.percent}%)`", inline=True)
    
    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)