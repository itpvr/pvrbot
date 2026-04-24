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

# --- [ ⚙️ Global Variables ] ---
TARGET_ID = 1069137562213552128
LOG_CHANNEL_ID = 1497227431462043708
bot.disconnect_info = None
bot.is_reconnecting = False # ตัวแปรใหม่: ล็อกกุญแจกันยามตีกัน

# --- [ ⚡ ชั้นที่ 1: on_voice_state_update (แก้ไข AttributeError) ] ---
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        target_channel = bot.get_channel(TARGET_ID)
        vc = member.guild.voice_client

        # 🛑 ถ้ากำลังอยู่ในขั้นตอน Reconnect (กุญแจล็อกอยู่) ให้ข้ามไปเลย
        if bot.is_reconnecting:
            return

        # 🔴 กรณี 1: ตรวจพบสายหลุด หรือ โดนเตะ
        if before.channel is not None and after.channel is None:
            bot.is_reconnecting = True # ล็อกกุญแจทันที!
            bot.disconnect_info = {
                "time": time.time(),
                "type": "drop",
                "reason": "Connection Dropped or Forcefully Kicked"
            }
            if target_channel:
                try:
                    print(f"⚠️ Connection lost. Recovering...")
                    await target_channel.connect(reconnect=True, timeout=20)
                except Exception as e:
                    print(f"⚠️ Reconnect Error: {e}")
                finally:
                    bot.is_reconnecting = False # ปลดล็อกเมื่อเสร็จงาน

        # 🟠 กรณี 2: ตรวจพบการโดนลาก
        elif after.channel is not None and after.channel.id != TARGET_ID:
            bot.is_reconnecting = True # ล็อกกุญแจ!
            bot.disconnect_info = {
                "time": time.time(),
                "type": "move",
                "reason": "Forcefully Moved by User",
                "dragged_to": after.channel.id
            }
            if target_channel:
                try:
                    print(f"⚡ Dragged detected. Moving back...")
                    await member.move_to(target_channel)
                except Exception as e:
                    print(f"⚠️ Move Error: {e}")
                finally:
                    bot.is_reconnecting = False # ปลดล็อก!

        # 🟢 กรณี 3: กลับเข้าห้องสำเร็จ (ส่ง Log)
        elif after.channel is not None and after.channel.id == TARGET_ID:
            if getattr(bot, 'disconnect_info', None) is not None:
                info = bot.disconnect_info
                downtime = round(time.time() - info["time"], 2)
                
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    embed_color = discord.Color.red() if info.get("type") == "drop" else discord.Color.gold()
                    status_icon = "🔴" if info.get("type") == "drop" else "🟠"
                    
                    embed = discord.Embed(
                        title=f"{status_icon} Voice Connection Restored",
                        color=embed_color,
                        timestamp=datetime.datetime.now()
                    )
                    avatar_url = member.display_avatar.url if member.display_avatar else None
                    embed.set_author(name=f"System Alert : {member.display_name}", icon_url=avatar_url)
                    embed.add_field(name="Trigger Reason", value=f"`{info['reason']}`", inline=False)
                    embed.add_field(name="Recovery Time", value=f"`{downtime} Seconds`", inline=True)
                    embed.add_field(name="Target Channel", value=f"<#{TARGET_ID}>", inline=True)
                    
                    if info.get("dragged_to"):
                        embed.add_field(name="Dragged From", value=f"<#{info['dragged_to']}>", inline=False)
                    
                    embed.set_footer(text="Automated Recovery Service (Fixed)")
                    await log_channel.send(embed=embed)
                
                bot.disconnect_info = None

# --- [ 🔄 ชั้นที่ 2: check_voice_status (แก้ไข AttributeError) ] ---
@tasks.loop(seconds=15)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_ID)
    if not channel: return

    vc = channel.guild.voice_client

    # 🛑 ถ้ากุญแจล็อกอยู่ (ยามหน้าด่านทำงานอยู่) ให้ยามคนนี้ข้ามไปเลย
    if bot.is_reconnecting:
        return

    # เช็กว่าไม่ได้เชื่อมต่อ หรือ อยู่ผิดห้อง
    if vc is None or not vc.is_connected() or vc.channel.id != TARGET_ID:
        bot.is_reconnecting = True # ล็อกกุญแจ!
        try:
            if vc:
                try: await vc.disconnect(force=True)
                except: pass
                await asyncio.sleep(1)

            await channel.connect(reconnect=True, timeout=20)
            print(f"🔄 [Health Check] Recovered successfully.")
        except Exception as e:
            print(f"❌ [Health Check] Recovery failed: {e}")
        finally:
            bot.is_reconnecting = False # ปลดล็อกเมื่อเสร็จงาน
            
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