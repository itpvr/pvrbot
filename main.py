import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import sys
import asyncio
import psutil
import time
import datetime
import sqlite3
import google.generativeai as genai
from ddgs import DDGS

# --- [ ⚙️ Setup ] ---
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = "AIzaSyCkrqzxWa0aEWsnPhudtqAQAChgHf2afsM"
BOT_NAME = os.getenv('BOT_NAME', 'gosu')

if not TOKEN or not GEMINI_API_KEY:
    print(f"❌ Error: ขาด Token หรือ API Key!")
    sys.exit()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-lite-latest')

start_time = time.time()
TARGET_CHANNEL_ID = 1069137562213552128 

# --- [ ⚡ Database ] ---
db_filename = f'brain_{BOT_NAME}.db'
conn = sqlite3.connect(db_filename)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS memory (channel_id TEXT, role TEXT, content TEXT)')
conn.commit()

def save_to_db(channel_id, role, content):
    c.execute("INSERT INTO memory VALUES (?, ?, ?)", (str(channel_id), role, content))
    conn.commit()
    c.execute("DELETE FROM memory WHERE rowid NOT IN (SELECT rowid FROM memory WHERE channel_id = ? ORDER BY rowid DESC LIMIT 10)", (str(channel_id),))
    conn.commit()

def load_from_db(channel_id):
    c.execute("SELECT role, content FROM memory WHERE channel_id = ? ORDER BY rowid ASC", (str(channel_id),))
    return c.fetchall()

# --- [ ⚡ Search ] ---
def _sync_search(query):
    try:
        with DDGS() as ddgs:
            return [r for r in ddgs.text(f"{query} ข้อมูลล่าสุดปี 2026", max_results=3)]
    except: return []

async def pro_search(query):
    results = await asyncio.to_thread(_sync_search, query)
    if not results: return "ไม่พบข้อมูลใหม่ในอินเทอร์เน็ต"
    context = "⚠️ ข้อมูลสดจากเน็ต (2026):\n"
    for res in results: context += f"- {res['body']}\n"
    return context

# --- [ 💬 OOD Command Group (รวมศูนย์คำสั่ง /ood) ] ---
class OodGroup(app_commands.Group, name="ood", description="คำสั่งทั้งหมดของลุงอ๊อด"):
    
    # 1. /ood question
    @app_commands.command(name="question", description="ถามปัญหาลุงอ๊อด หรือให้วิเคราะห์รูป")
    @app_commands.describe(question="พิมพ์คำถามที่นี่", image="ส่งรูปให้ลุงดู (ถ้ามี)")
    async def question(self, interaction: discord.Interaction, question: str = "", image: discord.Attachment = None):
        await interaction.response.defer()
        
        channel_id = str(interaction.channel_id)
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        current_time_str = now.strftime("%d/%m/%Y %H:%M")

        image_data = None
        if image:
            if image.content_type.startswith('image/'):
                image_bytes = await image.read()
                image_data = {"mime_type": image.content_type, "data": image_bytes}
                if not question: question = "วิเคราะห์รูปนี้หน่อยลุง"
            else:
                await interaction.followup.send("ไอ้หลาน! ส่งมาได้แค่รูปภาพนะโว้ย")
                return

        if not question and not image_data:
            await interaction.followup.send("จะถามอะไรก็พิมพ์มาสิโว้ย!")
            return

        search_res = await pro_search(question)
        history = load_from_db(channel_id)
        h_text = ""
        for role, content in history:
            h_text += f"{'หลาน' if role == 'user' else 'ลุง'}: {content}\n"

        prompt = (
            f"คุณคือ 'ลุงอ๊อด' AI ที่ฉลาดระดับกูเกิลแต่ติดดิน \n"
            f"เวลาตอนนี้: {current_time_str}\n\n"
            f"🎯 สไตล์: สั้น กระชับ กวนตีนนิดๆ แทนตัวเองกู/มึง แต่มีกาลเทศะ\n"
            f"- ถ้าคนถามว่าลุงเป็นใคร ตอบว่า 'PVR เป็นคนสร้างกูขึ้นมาเว้ย เพื่อวิเคราะห์ข้อมูลและค้นหาได้ทุกอย่าง!'\n"
            f"🔍 ข้อมูลเน็ต: {search_res}\n"
            f"📖 ประวัติ: {h_text}\n"
            f"💬 คำถาม: {question}"
        )

        try:
            content_list = [prompt]
            if image_data: content_list.append(image_data)
            
            response = await model.generate_content_async(content_list, request_options={'timeout': 60})
            answer = response.text
            
            save_to_db(channel_id, "user", question)
            save_to_db(channel_id, "model", answer)

            if len(answer) > 2000:
                for i in range(0, len(answer), 2000):
                    await interaction.followup.send(answer[i:i+2000])
            else:
                await interaction.followup.send(answer)
        except Exception as e:
            print(f"Gemini Error: {e}")
            await interaction.followup.send("สมองลุงช็อตว่ะ ลองถามใหม่ซิ!")

    # 2. /ood status
    @app_commands.command(name="status", description="เช็กสุขภาพเครื่องเซิร์ฟเวอร์")
    async def status(self, interaction: discord.Interaction):
        bot_name = os.getenv('BOT_NAME', 'gosu')
        current_time = time.time()
        uptime = str(datetime.timedelta(seconds=int(round(current_time - start_time))))
        
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent()
        ping = round(interaction.client.latency * 1000)

        try: db_size = os.path.getsize(db_filename) / 1024
        except: db_size = 0

        if cpu > 85 or ram.percent > 90: embed_color = discord.Color.red()
        elif cpu > 60 or ram.percent > 70: embed_color = discord.Color.orange()
        else: embed_color = discord.Color.green()

        embed = discord.Embed(title=f"🖥️ System Status : {bot_name.upper()}", color=embed_color, timestamp=datetime.datetime.now())
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime}`", inline=True)
        embed.add_field(name="📶 Ping", value=f"`{ping} ms`", inline=True)
        embed.add_field(name="📖 DB Size", value=f"`{db_size:.2f} KB`", inline=True)
        embed.add_field(name="⚙️ CPU Usage", value=f"`{cpu}%`", inline=True)
        embed.add_field(name="🧠 RAM Usage", value=f"`{ram.used // (1024**2)} MB` (`{ram.percent}%`)", inline=True)
        embed.add_field(name="🔄 Swap Memory", value=f"`{swap.used // (1024**2)} MB`", inline=True)

        await interaction.response.send_message(embed=embed)

    # 3. /ood forget (เฉพาะ PVR)
    @app_commands.command(name="forget", description="ล้างความจำของลุงในห้องนี้ (เฉพาะ PVR)")
    async def forget(self, interaction: discord.Interaction):
        if interaction.user.id == 431421372133277698:
            c.execute("DELETE FROM memory WHERE channel_id = ?", (str(interaction.channel_id),))
            conn.commit()
            await interaction.response.send_message("🧹 ลุงลืมความจำห้องนี้หมดแล้วโว้ย หลาน PVR!", ephemeral=True)
        else:
            await interaction.response.send_message("มึงไม่ใช่ PVR อย่ามาสั่งล้างสมองกู!", ephemeral=True)

    # 4. /ood say (เฉพาะ PVR)
    @app_commands.command(name="say", description="สั่งให้บอทพูดแทน (เฉพาะ PVR)")
    async def say(self, interaction: discord.Interaction, message: str):
        if interaction.user.id == 431421372133277698:
            await interaction.channel.send(message)
            await interaction.response.send_message("✅ ส่งข้อความแล้วโว้ย!", ephemeral=True)
        else:
            await interaction.response.send_message("มึงไม่ใช่ PVR อย่าเนียน!", ephemeral=True)

    # 5. /ood clear (เฉพาะ PVR)
    @app_commands.command(name="clear", description="ล้างประวัติแชท (เฉพาะ PVR)")
    async def clear(self, interaction: discord.Interaction, amount: int = 5):
        if interaction.user.id == 431421372133277698:
            await interaction.response.defer(ephemeral=True)
            try:
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.followup.send(f"🧹 ล้างให้แล้ว {len(deleted)} ข้อความ", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ ล้างไม่ได้ว่ะ Error: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("ไม่มีสิทธิ์โว้ย! เฉพาะ PVR เท่านั้น", ephemeral=True)

# --- [ 🤖 Bot Setup ] ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # โหลดกลุ่มคำสั่ง /ood เข้าไปในระบบ
        self.tree.add_command(OodGroup())
        await self.tree.sync()
        print(f"✅ Slash Commands Synced for {self.user}")

bot = MyBot()

# --- [ ⚙️ Global Variables & Helper Function ] ---
TARGET_ID = 1069137562213552128
LOG_CHANNEL_ID = 1497227431462043708
bot.is_reconnecting = getattr(bot, 'is_reconnecting', False)

# 📝 ฟังก์ชันส่งใบรายงาน
async def send_recovery_log(member, target_id, info):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel: return
    
    downtime = round(time.time() - info["time"], 2)
    embed_color = discord.Color.red() if info.get("type") == "drop" else discord.Color.gold()
    status_icon = "🔴" if info.get("type") == "drop" else "🟠"
    
    embed = discord.Embed(
        title=f"{status_icon} Voice Connection Restored",
        color=embed_color,
        timestamp=datetime.datetime.now()
    )
    avatar = member.display_avatar.url if member.display_avatar else None
    embed.set_author(name=f"System Alert : {member.display_name}", icon_url=avatar)
    embed.add_field(name="Trigger Reason", value=f"`{info['reason']}`", inline=False)
    embed.add_field(name="Recovery Time", value=f"`{downtime} Seconds`", inline=True)
    embed.add_field(name="Target Channel", value=f"<#{target_id}>", inline=True)
    
    if info.get("dragged_to"):
        embed.add_field(name="Dragged To", value=f"<#{info['dragged_to']}>", inline=False)
        
    embed.set_footer(text="Automated Recovery Service (Fast Mode)")
    await log_channel.send(embed=embed)


# --- [ ⚡ ชั้นที่ 1: on_voice_state_update (Instant Reconnect) ] ---
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        target_channel = bot.get_channel(TARGET_ID)
        vc = member.guild.voice_client

        if bot.is_reconnecting:
            return 

        # 🔴 กรณี 1: ตรวจพบสายหลุด หรือ โดนเตะ
        if before.channel is not None and after.channel is None:
            bot.is_reconnecting = True
            info = {"time": time.time(), "type": "drop", "reason": "Connection Dropped or Forcefully Kicked"}
            if target_channel:
                try:
                    await target_channel.connect(reconnect=True, timeout=20)
                    await send_recovery_log(member, TARGET_ID, info)
                except Exception as e:
                    print(f"⚠️ Reconnect Error: {e}")
                finally:
                    bot.is_reconnecting = False 

        # 🟠 กรณี 2: ตรวจพบการโดนลาก
        elif after.channel is not None and after.channel.id != TARGET_ID:
            bot.is_reconnecting = True
            info = {"time": time.time(), "type": "move", "reason": "Forcefully Moved by User", "dragged_to": after.channel.id}
            if target_channel:
                try:
                    await member.move_to(target_channel)
                    await send_recovery_log(member, TARGET_ID, info)
                except Exception as e:
                    print(f"⚠️ Move Error: {e}")
                finally:
                    bot.is_reconnecting = False 


# --- [ 🔄 ชั้นที่ 2: check_voice_status (Loop ยามเดินตรวจ 2 วินาที) ] ---
@tasks.loop(seconds=2)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_ID)
    if not channel: return

    vc = channel.guild.voice_client

    if bot.is_reconnecting:
        return 

    # 🛑 ถ้าหลุด หรืออยู่ผิดห้อง
    if vc is None or not vc.is_connected() or vc.channel.id != TARGET_ID:
        bot.is_reconnecting = True
        start_time = time.time()
        try:
            if vc:
                try: await vc.disconnect(force=True)
                except: pass
                await asyncio.sleep(1)

            await channel.connect(reconnect=True, timeout=20)
            
            info = {"time": start_time, "type": "drop", "reason": "Recovered by Auto-Heal Loop (Background Check)"}
            await send_recovery_log(channel.guild.me, TARGET_ID, info)
            print(f"🔄 [Loop] Recovered successfully.")
        except Exception as e:
            print(f"❌ [Loop] Recovery failed: {e}")
        finally:
            bot.is_reconnecting = False

# --- [ 🚀 กุญแจสตาร์ทเครื่อง (ที่หายไป!) ] ---
@bot.event
async def on_ready():
    print(f'🚀 บอท {bot.user} ออนไลน์แล้วโว้ย!')
    # สั่งให้ยามเดินตรวจเริ่มทำงานทันทีที่เปิดบอท
    if not check_voice_status.is_running():
        check_voice_status.start()
        print("✅ ระบบยามเดินตรวจ (Loop) เริ่มทำงานแล้ว!")

bot.run(TOKEN)