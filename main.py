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

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        # Slash Command ไม่จำเป็นต้องใช้ message_content แล้ว แต่เปิดไว้เผื่อฟีเจอร์อื่น
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # ทำการ Sync Slash Commands เข้ากับเซิร์ฟเวอร์
        # (ใน Production จริงๆ อาจจะใช้เวลานิดหน่อยในการอัปเดตทั่วโลก)
        await self.tree.sync()
        print(f"✅ Slash Commands Synced for {self.user}")

bot = MyBot()

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

# --- [ 🎤 Voice Check ] ---
@tasks.loop(seconds=10)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel: return
    vc = channel.guild.voice_client
    try:
        if not vc: await channel.connect(reconnect=True, timeout=20)
        elif vc.channel.id != TARGET_CHANNEL_ID: await vc.move_to(channel)
    except Exception as e:
        if vc:
            try: await vc.disconnect(force=True)
            except: pass

@bot.event
async def on_ready():
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
    print(f'🚀 {bot.user} พร้อมลุยในระบบ Slash Command!')

# --- [ 💬 Slash Command: /ask ] ---
@bot.tree.command(name="ask", description="ถามปัญหาชีวิตหรือให้ลุงช่วยหาข้อมูลจากเน็ต")
@app_commands.describe(question="พิมพ์คำถามที่นี่", image="ส่งรูปให้ลุงดู (ถ้ามี)")
async def ask(interaction: discord.Interaction, question: str = "", image: discord.Attachment = None):
    # เนื่องจากการประมวลผล AI นานเกิน 3 วิ ต้องใช้ defer
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
        f"🎯 สไตล์:\n"
        f"- สั้น กระชับ กวนตีนนิดๆ แทนตัวเองกู/มึง แต่มีกาลเทศะ\n"
        f"- ถ้ามีคนถามว่าลุงเป็นใคร ให้ตอบว่า 'PVR เป็นคนสร้างกูขึ้นมาเว้ย เพื่อวิเคราะห์ข้อมูลและค้นหาได้ทุกอย่าง!'\n"
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

        # ใช้ followup.send แทน response.send_message เมื่อใช้ defer
        if len(answer) > 2000:
            for i in range(0, len(answer), 2000):
                await interaction.followup.send(answer[i:i+2000])
        else:
            await interaction.followup.send(answer)
    except Exception as e:
        print(f"Gemini Error: {e}")
        await interaction.followup.send("สมองลุงช็อตว่ะ ลองถามใหม่ซิ!")

# --- [ 📊 Slash Command: /status ] ---
@bot.tree.command(name="status", description="เช็กสุขภาพเครื่องเซิร์ฟเวอร์")
async def status(interaction: discord.Interaction):
    bot_name = os.getenv('BOT_NAME', 'gosu')
    current_time = time.time()
    uptime = str(datetime.timedelta(seconds=int(round(current_time - start_time))))
    
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu = psutil.cpu_percent()
    ping = round(bot.latency * 1000)

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

# --- [ 🛠️ Slash Command Group: /pvr ] ---
class PVRGroup(app_commands.Group, name="pvr", description="คำสั่งสำหรับผู้สร้างเท่านั้น"):
    @app_commands.command(name="say", description="สั่งให้บอทพูดแทน")
    async def say(self, interaction: discord.Interaction, message: str):
        if interaction.user.id == 431421372133277698:
            await interaction.channel.send(message)
            await interaction.response.send_message("ส่งข้อความแล้วโว้ย!", ephemeral=True)
        else:
            await interaction.response.send_message("มึงไม่ใช่ PVR อย่าเนียน!", ephemeral=True)

    @app_commands.command(name="clear", description="ล้างประวัติแชท")
    async def clear(self, interaction: discord.Interaction, amount: int = 5):
        if interaction.user.id == 431421372133277698:
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"🧹 ล้างให้แล้ว {len(deleted)} ข้อความ", ephemeral=True)
        else:
            await interaction.response.send_message("ไม่มีสิทธิ์โว้ย!", ephemeral=True)

# เพิ่มกลุ่มคำสั่ง pvr เข้าไปใน tree
bot.tree.add_command(PVRGroup())

# --- [ 🧹 Slash Command: /forget ] ---
@bot.tree.command(name="forget", description="ล้างสมองลุงอ๊อดในห้องนี้")
async def forget(interaction: discord.Interaction):
    c.execute("DELETE FROM memory WHERE channel_id = ?", (str(interaction.channel_id),))
    conn.commit()
    await interaction.response.send_message("🧹 ลุงลืมหมดแล้วว่าคุยอะไรกัน!")

bot.run(TOKEN)