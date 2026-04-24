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
async def on_ready():
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
    print(f'🚀 {bot.user} พร้อมลุยในระบบ /ood !')

bot.run(TOKEN)