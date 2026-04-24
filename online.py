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

# --- [ 🎤 ระบบยามเฝ้าห้อง 24 ชม. (เวอร์ชันดื้อแพ่ง ไม่ยอมหลุด) ] ---
@tasks.loop(seconds=5) # เช็คทุก 5 วินาที ตามสั่ง!
async def check_voice_status():
    await bot.wait_until_ready()
    
    # ID ห้องที่หลานสั่งให้เฝ้าตายตัว
    TARGET_ID = 1069137562213552128
    channel = bot.get_channel(TARGET_ID)
    
    if not channel:
        print(f"⚠️ Error: หาห้อง ID {TARGET_ID} ไม่เจอว่ะหลาน!")
        return
    
    guild = channel.guild
    vc = guild.voice_client # เช็คว่าตอนนี้บอทต่ออยู่กับเสียงใน Server นี้ไหม

    try:
        # กรณีที่ 1: บอทไม่ได้ต่อสายอยู่เลย (เช่น เพิ่งเปิดบอท หรือโดนเตะหลุด)
        if vc is None:
            await channel.connect(reconnect=True, timeout=20)
            print(f"🏠 ลุงกลับเข้าห้อง {channel.name} แล้วโว้ย")

        # กรณีที่ 2: บอทต่อสายอยู่ แต่ "อยู่ผิดห้อง" (โดนคนลากไป หรือเผลอไปกดเข้าห้องอื่น)
        elif vc.channel.id != TARGET_ID:
            # ใช้ move_to เพื่อย้ายห้องทันทีโดยไม่ Disconnect
            await vc.move_to(channel)
            print(f"🏃 ใครลากกู! ลุงรีบวิ่งกลับเข้าห้อง {channel.name} ทันที")

    except Exception as e:
        # ถ้าพยายามย้ายแล้ว Error (เช่น ห้องเต็ม หรือติด Permission)
        # ลุงจะลองล้าง Session แล้วต่อใหม่ในรอบหน้า
        print(f"⚠️ ระบบ Reconnect เอ๋อ: {e}")
        if vc:
            try:
                await vc.disconnect(force=True)
            except:
                pass

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