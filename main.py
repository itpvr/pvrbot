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

# --- [ ⚙️ ดึงค่าจาก Environment Variables ] ---
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = "AIzaSyCkrqzxWa0aEWsnPhudtqAQAChgHf2afsM"

if not TOKEN or not GEMINI_API_KEY:
    print(f"❌ Error: ขาด Token หรือ API Key! (เช็คการ export ค่าก่อนรัน)")
    sys.exit()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-lite-latest')

start_time = time.time()
TARGET_CHANNEL_ID = 1069137562213552128 

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- [ ⚡ Database สมองลุงอ๊อด ] ---
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

# --- [ ⚡ ระบบค้นหาข้อมูล (Async) ] ---
def _sync_search(query):
    try:
        with DDGS() as ddgs:
            refined_query = f"{query} ข้อมูลล่าสุดปี 2026"
            return [r for r in ddgs.text(refined_query, max_results=3)]
    except:
        return []

async def pro_search(query):
    results = await asyncio.to_thread(_sync_search, query)
    if not results: return "ไม่พบข้อมูลใหม่ในอินเทอร์เน็ต"
    context = "⚠️ ข้อมูลสดจากเน็ต (2026):\n"
    for res in results:
        context += f"- {res['body']}\n"
    return context

@bot.event
async def on_ready():
    print(f'✅ ออนไลน์: {bot.user} | ฐานข้อมูล: {db_filename}')
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()

@tasks.loop(seconds=10)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel: return
    vc = channel.guild.voice_client
    try:
        if not vc:
            await channel.connect(reconnect=True, timeout=20)
        elif vc.channel.id != TARGET_CHANNEL_ID:
            await vc.move_to(channel)
    except Exception as e:
        if vc:
            try: await vc.disconnect(force=True)
            except: pass

@bot.command(aliases=['ood', 'ลุง'])
@commands.cooldown(1, 5, commands.BucketType.user)
async def ask(ctx, *, question: str = ""):
    async with ctx.typing():
        channel_id = str(ctx.channel.id)
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        current_time_str = now.strftime("%d/%m/%Y %H:%M")

        image_data = None
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if att.content_type.startswith('image/'):
                image_bytes = await att.read()
                image_data = {"mime_type": att.content_type, "data": image_bytes}
                if not question: question = "วิเคราะห์รูปนี้หน่อย"

        if not question and not image_data:
            return await ctx.send("จะถามอะไรก็พิมพ์มาสิโว้ย!")

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
            f"- ถ้ามีรูปภาพส่งมา ให้วิจารณ์รูปภาพนั้นตามสไตล์ลุง\n\n"
            f"🔍 ข้อมูลเน็ต: {search_res}\n\n"
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

            for i in range(0, len(answer), 2000):
                await ctx.send(answer[i:i+2000])
        except Exception as e:
            print(f"Gemini Error: {e}")
            await ctx.send("สมองลุงช็อตว่ะ ลองถามใหม่ซิ!")

# --- [ 🛠️ คำสั่งกลุ่ม PVR ] ---
@bot.group(name="pvr", invoke_without_command=True)
async def pvr(ctx):
    if ctx.author.id == 431421372133277698:
        try:
            await ctx.message.delete()
        except:
            pass

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
    uptime = str(datetime.timedelta(seconds=int(round(time.time() - start_time))))
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    db_size = os.path.getsize(db_filename) / 1024
    
    report = (
        f"**📊 รายงานสุขภาพ: {BOT_NAME.upper()}**\n"
        f"---"
        f"\n⏱️ **เปิดมาแล้ว:** `{uptime}`"
        f"\n🏎️ **ความไว (Ping):** `{round(bot.latency * 1000)}ms`"
        f"\n🖥️ **CPU:** `{psutil.cpu_percent()}%`"
        f"\n🧠 **RAM:** `{ram.used // (1024**2)}MB` / `{ram.total // (1024**2)}MB`"
        f"\n🔄 **Swap:** `{swap.used // (1024**2)}MB`"
        f"\n📖 **สมอง (DB):** `{db_size:.2f} KB`"
        f"\n---"
    )
    await ctx.send(report)

@bot.command()
async def forget(ctx):
    c.execute("DELETE FROM memory WHERE channel_id = ?", (str(ctx.channel.id),))
    conn.commit()
    await ctx.send("🧹 ลุงลืมหมดแล้วว่าคุยอะไรกัน!")

@ask.error
async def ask_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ ใจเย็น! รออีก {round(error.retry_after, 1)} วิ", delete_after=5)

bot.run(TOKEN)