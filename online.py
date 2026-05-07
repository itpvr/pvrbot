import discord
from discord.ext import commands, tasks
import os
import sys
import psutil
import time
import datetime
import asyncio

# --- [ ⚙️ Setup ] ---
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print(f"❌ Error: ขาด Token! (เช็คการ export ค่าก่อนรัน)")
    sys.exit()

start_time = time.time()
TARGET_ID = 1461009670029447432 # รหัสห้องหลักที่บอทต้องอยู่
LOG_CHANNEL_ID = 1497227431462043708 # รหัสห้องสำหรับส่ง Log แจ้งเตือน

# สร้าง Bot Class รองรับ Slash Command
class MinimalBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ สตาร์ทเครื่องและ Sync Slash Commands เรียบร้อย!")

bot = MinimalBot()

# --- [ 🚀 กุญแจสตาร์ทเครื่อง ] ---
@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user} | โหมด: Minimalist 30s Loop')
    
    # สั่งให้ยามเดินตรวจ (Loop 30s) เริ่มทำงานทันที
    if not check_voice_status.is_running():
        check_voice_status.start()
        print("🏠 Voice Check Loop 30s Started")

# --- [ 📝 ฟังก์ชันส่งใบรายงาน (ใช้บอทส่ง แบบ Embed จัดเต็มภาษาไทย) ] ---
async def send_recovery_log(status_type, reason, action_start_time=None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel: 
        print("⚠️ หาห้องส่ง Log ไม่เจอ เช็ก LOG_CHANNEL_ID ด้วย!")
        return
    
    # คำนวณเวลาที่ใช้กู้คืน
    recovery_time_text = "ไม่ระบุ"
    if action_start_time:
        downtime = round(time.time() - action_start_time, 2)
        recovery_time_text = f"{downtime} วินาที"

    # ตั้งค่าสีและไอคอนตามประเภทการหลุด
    embed_color = discord.Color.red() if status_type == "drop" else discord.Color.gold()
    status_icon = "🔴" if status_type == "drop" else "🟠"
    title = f"{status_icon} กู้คืนระบบเสียงสำเร็จ" if status_type == "drop" else f"{status_icon} ดึงบอทกลับห้องเป้าหมายสำเร็จ"
    
    embed = discord.Embed(title=title, color=embed_color, timestamp=datetime.datetime.now())
    
    # ดึงรูปและชื่อบอทมาใส่ด้านบน
    avatar = bot.user.display_avatar.url if bot.user.display_avatar else None
    embed.set_author(name=f"ระบบแจ้งเตือนอัตโนมัติ : {bot.user.display_name}", icon_url=avatar)
    
    # ข้อมูลแบบครบๆ
    embed.add_field(name="📋 สาเหตุการแจ้งเตือน", value=f"`{reason}`", inline=False)
    embed.add_field(name="⏱️ ความเร็วในการกู้คืน", value=f"`{recovery_time_text}`", inline=True)
    embed.add_field(name="📍 ห้องเป้าหมายหลัก", value=f"<#{TARGET_ID}>", inline=True)
    
    embed.set_footer(text="Automated Recovery Service (30s Minimal Mode)")
    
    # สั่งบอทส่งข้อความลงห้อง Log
    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"❌ ส่ง Log ไม่สำเร็จ: {e}")

# --- [ 🔄 ระบบยามเดินตรวจเช็กทุก 30 วินาที ] ---
@tasks.loop(seconds=30)
async def check_voice_status():
    await bot.wait_until_ready()
    target_channel = bot.get_channel(TARGET_ID)
    if not target_channel: return

    vc = target_channel.guild.voice_client

    # 🛑 กรณีที่ 1: บอทหลุด หรือ ไม่มี Voice Client เลย
    if vc is None or not vc.is_connected():
        action_start_time = time.time() # เริ่มจับเวลา
        try:
            # ล้างท่อเก่าถ้ามันค้าง
            if vc: 
                try: await vc.disconnect(force=True)
                except: pass
                await asyncio.sleep(1)
            
            await target_channel.connect(timeout=20)
            await send_recovery_log("drop", "เซิร์ฟเวอร์ตัดการเชื่อมต่อ หรือ บอทหลุดจากห้องเสียง", action_start_time)
            print("🔄 [30s Loop] บอทหลุด -> เชื่อมต่อใหม่สำเร็จ")
        except Exception as e:
            print(f"❌ [30s Loop] ต่อใหม่ไม่สำเร็จ: {e}")

    # 🟠 กรณีที่ 2: บอทอยู่ในสาย แต่ "อยู่ผิดห้อง"
    elif vc.channel.id != TARGET_ID:
        action_start_time = time.time() # เริ่มจับเวลา
        try:
            await target_channel.guild.me.move_to(target_channel)
            await send_recovery_log("move", "มีผู้ใช้อื่นดึงบอทไปห้องอื่น (ทำการดึงกลับแล้ว)", action_start_time)
            print("⚡ [30s Loop] บอทอยู่ผิดห้อง -> ย้ายกลับสำเร็จ")
        except Exception as e:
            print(f"❌ [30s Loop] ย้ายห้องไม่สำเร็จ: {e}")

    # 🟢 กรณีที่ 3: อยู่ในห้องเป้าหมายปกติ -> ไม่ต้องทำอะไร นิ่งๆ

# --- [ 📊 คำสั่ง /status (Slash Command) ] ---
@bot.tree.command(name="status", description="เช็กสถานะเครื่องเซิร์ฟเวอร์แบบ Real-time")
async def status(interaction: discord.Interaction):
    bot_name = os.getenv('BOT_NAME', 'Online_Bot')
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
        title=f"🖥️ ข้อมูลสถานะเซิร์ฟเวอร์ : {bot_name.upper()}",
        description=f"**สถานะการทำงาน:** {status_text}",
        color=embed_color,
        timestamp=datetime.datetime.now()
    )

    embed.add_field(name="⏱️ ระยะเวลาออนไลน์ (Uptime)", value=f"`{uptime}`", inline=True)
    embed.add_field(name="📶 ความหน่วง (Ping)", value=f"`{ping} ms`", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True) 

    embed.add_field(name="⚙️ การทำงานของ CPU", value=f"`{cpu}%`", inline=True)
    embed.add_field(name="🧠 การใช้งาน RAM", value=f"`{ram.used // (1024**2)} MB ({ram.percent}%)`", inline=True)
    
    # โชว์รูปโปรไฟล์คนกดคำสั่งนี้ด้วย
    user_avatar = interaction.user.display_avatar.url if interaction.user.display_avatar else None
    embed.set_footer(text=f"เรียกดูข้อมูลโดย {interaction.user.display_name}", icon_url=user_avatar)
    
    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)