import discord
from discord.ext import commands, tasks
import os
import asyncio
import psutil
import time
import datetime
import google.generativeai as genai

# --- [ 1. ตั้งค่า AI และสถานะบอท ] ---
# ⚠️ สำคัญมาก: เปลี่ยน KEY นี้ด้วยนะหลาน เพราะตัวเก่าหลุดไปแล้ว!
GEMINI_API_KEY = 'AIzaSyCkrqzxWa0aEWsnPhudtqAQAChgHf2afsM' 
genai.configure(api_key=GEMINI_API_KEY)
model_ai = genai.GenerativeModel('gemini-1.5-flash')

start_time = time.time()
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_CHANNEL_ID = 1069137562213552128

# --- [ 2. ตั้งค่า Intents (ต้องตั้งก่อนสร้าง bot) ] ---
intents = discord.Intents.default()
intents.voice_states = True 
intents.message_content = True  
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user}')
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
        print("🏠 Voice Check Loop Started")

# --- [ 3. ระบบเช็คห้องเสียง 24 ชม. ] ---
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
        print(f"⚠️ Voice Error: {e} | Force Reconnecting...")
        if vc:
            try: await vc.disconnect(force=True)
            except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        print("ℹ️ บอทหลุดจากห้องเสียง (กำลังรอรอบตรวจถัดไป)")

# --- [ 4. คำสั่งกลุ่ม !pvr ] ---
@bot.group(name="pvr", invoke_without_command=True)
async def pvr(ctx):
    if ctx.author.id == 431421372133277698:
        await ctx.message.delete()

@pvr.command(name="say")
async def say(ctx, *, message: str):
    if ctx.author.id == 431421372133277698:
        try:
            await ctx.message.delete()
            await ctx.send(message)
        except: await ctx.send(message)

@pvr.command(name="clear")
async def clear(ctx, amount: int = 5):
    if ctx.author.id == 431421372133277698:
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            await ctx.send(f"🧹 ล้างให้แล้ว {len(deleted)-1} ข้อความ", delete_after=3)
        except Exception as e: print(f"❌ Clear error: {e}")

# --- [ 5. ระบบ Health Report แบบจัดเต็ม (มาแล้ว!) ] ---
@bot.command()
async def status(ctx):
    # 1. คำนวณ Uptime
    current_time = time.time()
    difference = int(round(current_time - start_time))
    text_uptime = str(datetime.timedelta(seconds=difference))

    # 2. อ่านค่า Resource
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage('/')
    cpu = psutil.cpu_percent()

    report = (
        f"**📊 Health Report (ฉบับเต็ม)**\n"
        f"---"
        f"\n⏱️ **Uptime:** `{text_uptime}`"
        f"\n🏎️ **Bot Latency:** `{round(bot.latency * 1000)}ms`"
        f"\n🖥️ **CPU Usage:** `{cpu}%`"
        f"\n🧠 **RAM:** `{ram.used // (1024**2)}MB` / `{ram.total // (1024**2)}MB`"
        f"\n🔄 **Swap:** `{swap.used // (1024**2)}MB` / `{swap.total // (1024**2)}MB`"
        f"\n💾 **Disk:** `{disk.percent}% used` (`{disk.free // (1024**3)}GB` free)"
        f"\n---"
    )
    await ctx.send(report)

# --- [ 6. ระบบ AI ลุงอ๊อด (Gemini Pro) ] ---
chat_memory = {}

@bot.command(aliases=['ถาม', 'ลุงอ๊อด', 'ood'])
async def ask(ctx, *, question: str):
    async with ctx.typing():
        channel_id = ctx.channel.id
        system_prompt = "คุณคือ 'ลุงอ๊อด' อดีตศาสตราจารย์มหาลัย ตอบคำถามด้วยตรรกะระดับสูงและถูกต้องเสมอ แต่แฝงความกวนประสาทแบบคนแก่ใจดี (ภาษาไทยภาคกลาง)"
        
        if channel_id not in chat_memory:
            chat_memory[channel_id] = [
                {"role": "user", "parts": [{"text": f"คำสั่งระบบ: {system_prompt}"}]},
                {"role": "model", "parts": [{"text": "รับทราบครับหลาน ลุงอ๊อดร่างทองพร้อมตอบแล้ว!"}]}
            ]
        
        chat_memory[channel_id].append({"role": "user", "parts": [{"text": question}]})

        try:
            # ใช้ model_ai ที่ประกาศไว้ด้านบนสุด
            response = model_ai.generate_content(chat_memory[channel_id])
            answer = response.text
            
            chat_memory[channel_id].append({"role": "model", "parts": [{"text": answer}]})
            
            # เก็บความจำ 10 ข้อความล่าสุด
            if len(chat_memory[channel_id]) > 10:
                chat_memory[channel_id] = chat_memory[channel_id][:2] + chat_memory[channel_id][-8:]

            await ctx.send(answer)
            
        except Exception as e:
            print(f"Error AI: {e}")
            await ctx.send("⚠️ ลุงอ๊อดมึนหัว (API อาจมีปัญหาหรือโควตาเต็ม) ลองใหม่อีกทีนะหลาน")

bot.run(TOKEN)