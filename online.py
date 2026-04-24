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

# --- [ ⚡ ชั้นที่ 1: ระบบ Instant Reconnect & Logging ] ---
LOG_CHANNEL_ID = 1497227431462043708 # ห้องส่ง Log

# สร้างความจำชั่วคราวให้บอทเอาไว้จำเวลาหลุด (ใส่ไว้นอกฟังก์ชัน หรือใต้ on_ready ก็ได้)
bot.last_disconnect_time = None
bot.disconnect_reason = ""

# --- [ ⚡ ชั้นที่ 1: ระบบ Instant Reconnect & Pro Logging (English UI) ] ---
LOG_CHANNEL_ID = 1497227431462043708 # ห้องส่ง Log

# เปลี่ยนมาใช้ Dictionary เพื่อเก็บข้อมูลให้ละเอียดขึ้น
bot.disconnect_info = None

@bot.event
async def on_voice_state_update(member, before, after):
    # ทำงานเฉพาะตัวบอท
    if member.id == bot.user.id:
        TARGET_ID = 1069137562213552128
        target_channel = bot.get_channel(TARGET_ID)

        # 🔴 ตรวจจับ 1: สายหลุด หรือ โดนเตะ (Connection Dropped / Kicked)
        if before.channel is not None and after.channel is None:
            bot.disconnect_info = {
                "time": time.time(),
                "type": "drop",
                "reason": "Connection Dropped or Forcefully Kicked",
                "dragged_to": None
            }
            print(f"⚠️ บอทหลุดจากห้องเสียง! กำลังกู้คืน...")
            if target_channel:
                try: await target_channel.connect(reconnect=True, timeout=10)
                except: pass

        # 🟠 ตรวจจับ 2: โดนลากไปห้องอื่น (Forcefully Moved)
        elif after.channel is not None and after.channel.id != TARGET_ID:
            bot.disconnect_info = {
                "time": time.time(),
                "type": "move",
                "reason": "Forcefully Moved by User",
                "dragged_to": after.channel.id
            }
            print(f"⚡ โดนลาก! กำลังวาร์ปกลับ...")
            if target_channel:
                try: await member.move_to(target_channel)
                except: pass

        # 🟢 ตรวจจับ 3: กลับเข้าห้องเป้าหมายสำเร็จ (Recovery Successful)
        elif after.channel is not None and after.channel.id == TARGET_ID:
            # ถ้ามีข้อมูลการหลุดบันทึกไว้ ค่อยสร้าง Log
            if getattr(bot, 'disconnect_info', None) is not None:
                info = bot.disconnect_info
                downtime = round(time.time() - info["time"], 2) # ทศนิยม 2 ตำแหน่งให้ดูโปร
                
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    # เลือกสีและไอคอนตามสาเหตุ
                    embed_color = discord.Color.red() if info["type"] == "drop" else discord.Color.gold()
                    status_icon = "🔴" if info["type"] == "drop" else "🟠"
                    
                    # สร้าง Embed แบบเรียบหรู (Clean Design)
                    embed = discord.Embed(
                        title=f"{status_icon} Voice Connection Restored",
                        color=embed_color,
                        timestamp=datetime.datetime.now()
                    )
                    
                    # ใส่รูปโปรไฟล์บอทไว้ด้านบน
                    avatar_url = member.display_avatar.url if member.display_avatar else None
                    embed.set_author(name=f"System Alert : {member.display_name}", icon_url=avatar_url)
                    
                    # จัดเรียงข้อมูลแบบ Grid
                    embed.add_field(name="Trigger Reason", value=f"`{info['reason']}`", inline=False)
                    embed.add_field(name="Recovery Time", value=f"`{downtime} Seconds`", inline=True)
                    embed.add_field(name="Target Channel", value=f"<#{TARGET_ID}>", inline=True)
                    
                    # ถ้าโดนลาก ให้แฉด้วยว่าลากไปห้องไหน
                    if info["type"] == "move" and info["dragged_to"]:
                        embed.add_field(name="Dragged To", value=f"<#{info['dragged_to']}>", inline=False)
                        
                    embed.set_footer(text="Automated Recovery Service")
                    
                    await log_channel.send(embed=embed)
                
                # เคลียร์ความจำทิ้ง เตรียมรับมือรอบต่อไป
                bot.disconnect_info = None
                
# --- [ 🔄 ชั้นที่ 2: ยามเดินตรวจ (Safety Net) - ปรับเหลือ 2 วินาที ] ---
@tasks.loop(seconds=2) 
async def check_voice_status():
    await bot.wait_until_ready()
    TARGET_ID = 1069137562213552128
    channel = bot.get_channel(TARGET_ID)
    if not channel: return

    vc = channel.guild.voice_client

    # ถ้าชั้นที่ 1 (Event) พลาด หรือเน็ตกระตุกจน Event ไม่มา 
    # ลูปนี้จะช่วยเช็คซ้ำทุก 2 วินาที
    if vc is None or not vc.is_connected() or vc.channel.id != TARGET_ID:
        try:
            if vc and vc.is_connected():
                await vc.move_to(channel)
            else:
                await channel.connect(reconnect=True, timeout=10)
        except Exception as e:
            # ถ้าเน่าหนักมาก ให้ล้าง Session ทิ้งเพื่อรอเชื่อมใหม่รอบหน้า
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


@bot.command()
async def status(ctx):
    # ดึงค่าชื่อบอท
    bot_name = os.getenv('BOT_NAME', 'online_bot')

    # 1. คำนวณ Uptime
    current_time = time.time()
    difference = int(round(current_time - start_time))
    text_uptime = str(datetime.timedelta(seconds=difference))

    # 2. อ่านค่าทรัพยากร
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu = psutil.cpu_percent()
    ping = round(bot.latency * 1000)

    # 3. กำหนดสีกรอบตามสุขภาพเครื่อง (เขียว = ปกติ, ส้ม = เริ่มหนัก, แดง = วิกฤต)
    if cpu > 85 or ram.percent > 90:
        embed_color = discord.Color.red()
        status_text = "🔴 วิกฤต (Critical)"
    elif cpu > 60 or ram.percent > 70:
        embed_color = discord.Color.orange()
        status_text = "🟠 เริ่มหนัก (Warning)"
    else:
        embed_color = discord.Color.green()
        status_text = "🟢 ปกติ (Healthy)"

    # 4. สร้างกรอบ Embed
    embed = discord.Embed(
        title=f"🖥️ System Status : {bot_name.upper()}",
        description=f"**สถานะเครื่อง:** {status_text}",
        color=embed_color,
        timestamp=datetime.datetime.now()
    )

    # 5. ใส่ข้อมูลแบ่งเป็นคอลัมน์ (inline=True คือให้อยู่บรรทัดเดียวกัน)
    embed.add_field(name="⏱️ Uptime", value=f"`{text_uptime}`", inline=True)
    embed.add_field(name="📶 Ping", value=f"`{ping} ms`", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True) # ช่องว่างจัดระเบียบ

    embed.add_field(name="⚙️ CPU Usage", value=f"`{cpu}%`", inline=True)
    embed.add_field(name="🧠 RAM Usage", value=f"`{ram.used // (1024**2)} / {ram.total // (1024**2)} MB`\n(`{ram.percent}%`)", inline=True)
    embed.add_field(name="🔄 Swap Memory", value=f"`{swap.used // (1024**2)} MB`", inline=True)

    # ใส่รูปโปรไฟล์คนสั่งไว้ข้างล่างเท่ๆ
    user_avatar = ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=user_avatar)

    # ส่งข้อความ
    await ctx.send(embed=embed)

bot.run(TOKEN)