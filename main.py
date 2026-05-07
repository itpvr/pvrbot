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
TARGET_ID = 1461009670029447432 
LOG_CHANNEL_ID = 1497227431462043708

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
    context = "⚠️ ข้อมูลอ้างอิงจากเน็ต:\n"
    for res in results: context += f"- {res['body']}\n"
    return context

# --- [ 📝 ฟังก์ชันส่งใบรายงาน (ระบบ 30s เจาะเกราะ) ] ---
async def send_recovery_log(status_type, reason, action_start_time=None):
    try:
        log_channel = bot.get_channel(LOG_CHANNEL_ID) or await bot.fetch_channel(LOG_CHANNEL_ID)
    except Exception as e:
        print(f"⚠️ หาห้อง Log ไม่เจอ: {e}")
        return
    
    recovery_time_text = "ไม่ระบุ"
    if action_start_time:
        downtime = round(time.time() - action_start_time, 2)
        recovery_time_text = f"{downtime} วินาที"

    embed_color = discord.Color.red() if status_type == "drop" else discord.Color.gold()
    status_icon = "🔴" if status_type == "drop" else "🟠"
    title = f"{status_icon} กู้คืนระบบเสียงสำเร็จ" if status_type == "drop" else f"{status_icon} ดึงบอทกลับห้องเป้าหมายสำเร็จ"
    
    embed = discord.Embed(title=title, color=embed_color, timestamp=datetime.datetime.now())
    avatar = bot.user.display_avatar.url if bot.user.display_avatar else None
    embed.set_author(name=f"ระบบแจ้งเตือนอัตโนมัติ : {bot.user.display_name}", icon_url=avatar)
    
    embed.add_field(name="📋 สาเหตุ", value=f"`{reason}`", inline=False)
    embed.add_field(name="⏱️ ความเร็วในการกู้คืน", value=f"`{recovery_time_text}`", inline=True)
    embed.add_field(name="📍 ห้องเป้าหมายหลัก", value=f"<#{TARGET_ID}>", inline=True)
    embed.set_footer(text="Auto Recovery (30s Minimal Mode)")
    
    try: await log_channel.send(embed=embed)
    except Exception as e: print(f"❌ ส่ง Log ไม่สำเร็จ: {e}")


# --- [ 💬 OOD Command Group ] ---
class OodGroup(app_commands.Group, name="ood", description="คำสั่งทั้งหมดของลุงอ๊อด"):
    
    @app_commands.command(name="ask", description="ถามปัญหาลุงอ๊อด หรือให้วิเคราะห์รูป")
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
                if not question: question = "วิเคราะห์รูปนี้หน่อยครับ"
            else:
                await interaction.followup.send("ส่งมาได้แค่รูปภาพนะครับ")
                return

        if not question and not image_data:
            await interaction.followup.send("พิมพ์คำถามมาได้เลยครับ")
            return

        search_res = await pro_search(question)
        history = load_from_db(channel_id)
        h_text = ""
        for role, content in history:
            h_text += f"{'ผู้ใช้' if role == 'user' else 'คุณ'}: {content}\n"

        # 🧠 [ ปรับ Prompt ใหม่: ฉลาด, สุภาพ, สั้นกระชับ ]
        prompt = (
            f"คุณคือ 'ลุงอ๊อด' AI ผู้ช่วยอัจฉริยะที่ถูกพัฒนาขึ้นโดย PVR \n"
            f"เวลาปัจจุบัน: {current_time_str}\n\n"
            f"🎯 บุคลิกภาพและสไตล์การสนทนา:\n"
            f"- เป็นผู้เชี่ยวชาญระดับสูงที่รอบรู้ ฉลาดหลักแหลม และวิเคราะห์ข้อมูลได้อย่างเฉียบคม\n"
            f"- มีความเป็นกันเอง สุภาพ (ใช้สรรพนามแทนตัวเองว่า 'ลุง' และเรียกคู่สนทนาว่า 'หลาน')\n"
            f"- 🚫 ห้ามใช้คำหยาบ ห้ามกวนตีน ห้ามประชดประชันเด็ดขาด\n"
            f"- ⚡ **กฎเหล็กเรื่องความยาว:** ตอบให้สั้น กระชับ ตรงประเด็นที่สุด เหมือนมนุษย์พิมพ์แชทคุยกัน ไม่เกิน 2-4 บรรทัด (ยกเว้นกรณีอธิบายโค้ดหรือขั้นตอนที่ซับซ้อน)\n"
            f"- หากใช้ข้อมูลจากเน็ต ให้ย่อยข้อมูลและสรุปใจความสำคัญมาตอบ ไม่ใช่การก๊อปปี้มาวางยาวๆ\n\n"
            f"🔍 ข้อมูลอ้างอิง: {search_res}\n"
            f"📖 บริบทแชทก่อนหน้า: {h_text}\n"
            f"💬 คำถามปัจจุบัน: {question}"
        )

        try:
            content_list = [prompt]
            if image_data: content_list.append(image_data)
            
            custom_safety = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
            
            response = await model.generate_content_async(
                content_list, 
                request_options={'timeout': 60},
                safety_settings=custom_safety
            )
            
            if not response.candidates:
                await interaction.followup.send("⚠️ ข้อมูลในเน็ตมีเนื้อหาสุ่มเสี่ยงสแปม ระบบความปลอดภัยจึงบล็อกไว้ครับ ลองเปลี่ยนคำถามดูนะครับ")
                return

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
            await interaction.followup.send("ระบบ AI ขัดข้องชั่วคราว ลองใหม่อีกครั้งนะครับ")

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

        if cpu > 85 or ram.percent > 90: embed_color, status_text = discord.Color.red(), "🔴 วิกฤต (Critical)"
        elif cpu > 60 or ram.percent > 70: embed_color, status_text = discord.Color.orange(), "🟠 เริ่มหนัก (Warning)"
        else: embed_color, status_text = discord.Color.green(), "🟢 ปกติ (Healthy)"

        embed = discord.Embed(title=f"🖥️ System Status : {bot_name.upper()}", description=f"**สถานะ:** {status_text}", color=embed_color, timestamp=datetime.datetime.now())
        embed.add_field(name="⏱️ Uptime", value=f"`{uptime}`", inline=True)
        embed.add_field(name="📶 Ping", value=f"`{ping} ms`", inline=True)
        embed.add_field(name="📖 DB Size", value=f"`{db_size:.2f} KB`", inline=True)
        embed.add_field(name="⚙️ CPU Usage", value=f"`{cpu}%`", inline=True)
        embed.add_field(name="🧠 RAM Usage", value=f"`{ram.used // (1024**2)} MB` ({ram.percent}%)", inline=True)
        embed.add_field(name="🔄 Swap", value=f"`{swap.used // (1024**2)} MB`", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="forget", description="ล้างความจำของลุงในห้องนี้ (เฉพาะ PVR)")
    async def forget(self, interaction: discord.Interaction):
        if interaction.user.id == 431421372133277698:
            c.execute("DELETE FROM memory WHERE channel_id = ?", (str(interaction.channel_id),))
            conn.commit()
            await interaction.response.send_message("🧹 ล้างความจำในห้องนี้เรียบร้อยครับ!", ephemeral=True)
        else:
            await interaction.response.send_message("คำสั่งนี้สงวนไว้สำหรับ PVR เท่านั้นครับ", ephemeral=True)

    @app_commands.command(name="say", description="สั่งให้บอทพูดแทน (เฉพาะ PVR)")
    async def say(self, interaction: discord.Interaction, message: str):
        if interaction.user.id == 431421372133277698:
            await interaction.channel.send(message)
            await interaction.response.send_message("✅ ส่งข้อความสำเร็จ", ephemeral=True)
        else:
            await interaction.response.send_message("ไม่มีสิทธิ์ใช้งานครับ", ephemeral=True)

    @app_commands.command(name="clear", description="ล้างประวัติแชท (เฉพาะ PVR)")
    async def clear(self, interaction: discord.Interaction, amount: int = 5):
        if interaction.user.id == 431421372133277698:
            await interaction.response.defer(ephemeral=True)
            try:
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.followup.send(f"🧹 ล้างให้แล้ว {len(deleted)} ข้อความ", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ ล้างไม่ได้: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("ไม่มีสิทธิ์ใช้งานครับ", ephemeral=True)

# --- [ 🤖 Bot Setup ] ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.add_command(OodGroup())
        await self.tree.sync()
        print(f"✅ Slash Commands Synced for {self.user}")

bot = MyBot()

# --- [ 🔄 ชั้นที่ 2: check_voice_status (Loop ยามเดินตรวจ 30 วินาที) ] ---
@tasks.loop(seconds=30)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_ID)
    if not channel: return

    vc = channel.guild.voice_client

    if vc is None or not vc.is_connected():
        start_time = time.time()
        try:
            if vc:
                try: await vc.disconnect(force=True)
                except: pass
                await asyncio.sleep(1)

            await channel.connect(timeout=20)
            await send_recovery_log("drop", "เซิร์ฟเวอร์ตัดการเชื่อมต่อ หรือ บอทหลุดจากห้องเสียง", start_time)
            print("🔄 [Loop] Recovered successfully.")
        except Exception as e:
            print(f"❌ [Loop] Recovery failed: {e}")
            
    elif vc.channel.id != TARGET_ID:
        start_time = time.time()
        try:
            await channel.guild.me.move_to(channel)
            await send_recovery_log("move", "มีผู้ใช้อื่นดึงบอทไปห้องอื่น (ดึงกลับอัตโนมัติ)", start_time)
            print("⚡ [Loop] Moved back to target.")
        except Exception as e:
            print(f"❌ [Loop] Move failed: {e}")

# --- [ 🚀 สตาร์ท Loop ] ---
@bot.event
async def on_ready():
    print(f'🚀 บอท {bot.user} ออนไลน์แล้ว!')
    if not check_voice_status.is_running():
        check_voice_status.start()
        print("✅ ระบบตรวจสอบห้องเสียง 30s เริ่มทำงาน")

bot.run(TOKEN)