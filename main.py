import discord
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

# --- [ ⚙️ ดึงค่าจาก Environment Variables ทันทีที่รัน ] ---
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = "AIzaSyCkrqzxWa0aEWsnPhudtqAQAChgHf2afsM"
BOT_NAME = os.getenv('BOT_NAME', 'gosu') # รับชื่อบอทมาเพื่อตั้งชื่อไฟล์ฐานข้อมูล ถ้าไม่ใส่จะใช้ชื่อ gosu

if not TOKEN or not GEMINI_API_KEY:
    print(f"❌ Error: ขาด Token หรือ API Key! ตรวจสอบการพ่วงคำสั่งตอนรันด้วย")
    sys.exit()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

start_time = time.time()
TARGET_CHANNEL_ID = 1069137562213552128

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- [ ⚡ Database สมองลุงอ๊อด (แยกตามชื่อบอท) ] ---
db_filename = f'brain_{BOT_NAME}.db'
conn = sqlite3.connect(db_filename)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS memory 
             (channel_id TEXT, role TEXT, content TEXT)''')
conn.commit()

def save_to_db(channel_id, role, content):
    c.execute("INSERT INTO memory VALUES (?, ?, ?)", (str(channel_id), role, content))
    conn.commit()
    c.execute("""
        DELETE FROM memory WHERE rowid NOT IN (
            SELECT rowid FROM memory WHERE channel_id = ? ORDER BY rowid DESC LIMIT 10
        )
    """, (str(channel_id),))
    conn.commit()

def load_from_db(channel_id):
    c.execute("SELECT role, content FROM memory WHERE channel_id = ? ORDER BY rowid ASC", (str(channel_id),))
    return c.fetchall()

# --- [ ⚡ แยก Thread การค้นหาไม่ให้บอทค้าง ] ---
def _sync_search(query):
    try:
        with DDGS() as ddgs:
            refined_query = f"{query} ข้อมูลล่าสุดปี 2026"
            return [r for r in ddgs.text(refined_query, max_results=3)]
    except Exception:
        return []

async def pro_search(query):
    results = await asyncio.to_thread(_sync_search, query)
    if not results: return "ไม่พบข้อมูลใหม่ในอินเทอร์เน็ต"
    context = "⚠️ ข้อมูลสดจากอินเทอร์เน็ต (Real-time Data 2026):\n"
    for res in results:
        context += f"- {res['body']}\n"
    return context

@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user} (ฐานข้อมูล: {db_filename})')
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
        print("🏠 Voice Check Loop Started")

@tasks.loop(seconds=5)
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
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        pass # ปิดแจ้งเตือนจุกจิก

@bot.command(aliases=['ood', 'ลุง'])
@commands.cooldown(1, 5, commands.BucketType.user)
async def ask(ctx, *, question: str = ""):
    async with ctx.typing():
        channel_id = str(ctx.channel.id)
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        current_time_str = now.strftime("%d/%m/%Y %H:%M")

        # ระบบตาดูภาพ
        image_data = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type.startswith('image/'):
                image_bytes = await attachment.read()
                image_data = {"mime_type": attachment.content_type, "data": image_bytes}
                if not question: question = "วิเคราะห์รูปนี้ให้หน่อย"

        if not question and not image_data:
            await ctx.send("จะถามอะไรลุงก็พิมพ์มาด้วยสิโว้ย!")
            return

        search_results = await pro_search(question)

        history = load_from_db(channel_id)
        history_text = "ไม่เคยคุยกันมาก่อน\n" if not history else ""
        for role, content in history:
            speaker = "หลาน" if role == "user" else "ลุง"
            history_text += f"{speaker}: {content}\n"

        prompt_context = (
            f"คุณคือ 'ลุงอ๊อด' ที่ฉลาดระดับกูเกิลแต่ติดดิน \n"
            f"เวลาตอนนี้: {current_time_str}\n\n"
            f"🎯 สไตล์:\n"
            f"- สั้น กระชับ กวนตีนนิดๆ แทนตัวเองกู/มึง แต่มีกาลเทศะ\n"
            f"- ถ้ามีรูปภาพส่งมา ให้วิจารณ์รูปภาพนั้นตามสไตล์ลุง\n\n"
            f"🔍 ข้อมูลดิบจากเน็ต: {search_results}\n\n"
            f"📖 ประวัติการคุย:\n{history_text}\n"
            f"💬 คำถามใหม่จากหลาน: {question}"
        )

        try:
            contents = [prompt_context]
            if image_data: contents.append(image_data)

            response = await model.generate_content_async(contents, request_options={'timeout': 60})

            if not response.candidates or not response.candidates[0].content.parts:
                await ctx.send("📋 ลุงขอผ่านว่ะ ระบบกรองมันบล็อก")
                return

            answer = response.text
            save_to_db(channel_id, "user", question)
            save_to_db(channel_id, "model", answer)

            if len(answer) > 2000:
                for i in range(0, len(answer), 2000):
                    await ctx.send(answer[i:i+2000])
            else:
                await ctx.send(answer)

        except Exception as e:
            print(f"Gemini Error: {e}")
            await ctx.send("สมองลุงช็อตว่ะ ลองถามใหม่อีกทีนะหลาน")

@bot.command()
async def forget(ctx):
    c.execute("DELETE FROM memory WHERE channel_id = ?", (str(ctx.channel.id),))
    conn.commit()
    await ctx.send("🧹 ลุงอ๊อดลืมหมดแล้วว่าเมื่อกี้เราคุยอะไรกัน!")

@ask.error
async def ask_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ ใจเย็นไอ้หลาน! รออีก {round(error.retry_after, 1)} วินาทีค่อยถามใหม่", delete_after=5)

bot.run(TOKEN)