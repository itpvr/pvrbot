import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import psutil
import time
import datetime
import google.generativeai as genai
from ddgs import DDGS

# --- [ 1. Setup Gemini ] ---
GEMINI_API_KEY = 'AIzaSyCkrqzxWa0aEWsnPhudtqAQAChgHf2afsM'
genai.configure(api_key=GEMINI_API_KEY)

# ใช้ชื่อรุ่นนี้ ชัวร์ที่สุดในตอนนี้ครับ
model = genai.GenerativeModel('gemini-flash-lite-latest')


start_time = time.time()
# --- ตั้งค่าพื้นฐาน (เหมือนเดิม) ---
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_CHANNEL_ID = 1069137562213552128

intents = discord.Intents.default()
intents.voice_states = True # Needed for voice check
bot = commands.Bot(command_prefix="!", intents=intents)
intents.message_content = True  # ✅ ต้องมีบรรทัดนี้! (สำคัญมากสำหรับคำสั่ง !)
intents.messages = True


@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user}')
    # 2. 🏠 เริ่มต้นระบบเช็คห้องเสียงอันแสนเสถียรของเรา (ขาดตัวนี้ไม่ได้!)
    if not hasattr(bot, 'voice_check_task') or not bot.voice_check_task.is_running():
        bot.voice_check_task = check_voice_status.start()
        print("🏠 Voice Check Loop Started")

    text_channel = bot.get_channel(123456789012345678) 
    if text_channel:
        await text_channel.send("🚀 บอท gosu.wav ออนไลน์พร้อมใช้งานแล้ว!")

# --- (โค้ดเช็คห้องเสียง อันเดิมของคุณที่รัน 24 ชม. ห้ามลบนะครับ!) ---
# เช็คทุก 5 วินาทีตามที่คุณตั้งไว้
@tasks.loop(seconds=5)
async def check_voice_status():
    await bot.wait_until_ready()
    channel = bot.get_channel(TARGET_CHANNEL_ID)

    if channel is None:
        return

    guild = channel.guild
    vc = guild.voice_client

    try:
        if vc is None:
            # print("🔍 ตรวจพบ: บอทไม่อยู่ในห้องเสียง กำลังเข้าร่วม...")
            await channel.connect(reconnect=True, timeout=20)
            # print(f"🏠 เข้าห้อง {channel.name} สำเร็จ")
        elif vc.channel.id != TARGET_CHANNEL_ID:
            # print(f"🔍 ตรวจพบ: บอทอยู่ผิดห้อง กำลังย้ายกลับ...")
            await vc.move_to(channel)
            # print(f"🏠 ย้ายกลับเข้าห้อง {channel.name} เรียบร้อย")
    except Exception as e:
        # 🔥 เปลี่ยนจาก pass เป็นระบบสลายเซสชันที่บูดทิ้ง
        print(f"⚠️ Voice Error: {e} | สั่ง Force Disconnect เพื่อเริ่มใหม่...")
        if vc:
            try:
                await vc.disconnect(force=True)
            except:
                pass

@bot.event
async def on_voice_state_update(member, before, after):
    # Optional logger (harmless to keep)
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        print("ℹ️ บอทหลุดจากห้องเสียง (จะกลับเข้าที่ในรอบตรวจถัดไป)")

# --- คำสั่งกลุ่ม !pvr ---
@bot.group(name="pvr", invoke_without_command=True)
async def pvr(ctx):
    # ถ้าพิมพ์ !pvr เฉยๆ ให้บอทลบข้อความนั้นทิ้งด้วย จะได้ไม่รก
    if ctx.author.id == 431421372133277698:
        await ctx.message.delete()
    pass

# --- คำสั่งย่อย !pvr say ---
@pvr.command(name="say")
async def say(ctx, *, message: str):
    # ID ของคุณที่ได้รับอนุญาต
    ALLOWED_USER_ID = 431421372133277698

    if ctx.author.id == ALLOWED_USER_ID:
        try:
            # 1. 🔥 คำสั่งลบข้อความที่คุณพิมพ์สั่ง (เช่น !pvr say test)
            await ctx.message.delete()

            # 2. 🎤 บอทส่งข้อความตามที่สั่ง
            await ctx.send(message)

            print(f"✅ บอทส่งข้อความแทนคุณแล้ว: {message}")

        except Exception as e:
            # ถ้าลบไม่ได้ (อาจเพราะบอทไม่มีสิทธิ์ Manage Messages) 
            # ให้บอทส่งข้อความไปก่อน แล้วค่อยแจ้ง Error ในหน้า Log
            await ctx.send(message)
            print(f"⚠️ คำเตือน: บอทลบข้อความไม่ได้ เนื่องจาก: {e}")
    else:
        # ถ้าไม่ใช่คุณสั่ง บอทจะนิ่งเฉย (และไม่ลบข้อความด้วย เพื่อให้เห็นว่าใครมาเนียน)
        print(f"🚫 มีคนพยายามสวมรอย: {ctx.author.name} (ID: {ctx.author.id})")
# --- คำสั่งย่อย !pvr clear [จำนวน] ---
@pvr.command(name="clear")
async def clear(ctx, amount: int = 5):
    # ตรวจสอบ ID คุณคนเดียว
    if ctx.author.id == 431421372133277698:
        try:
            # ลบข้อความ (บวก 1 เพื่อลบตัวคำสั่งออกไปด้วย)
            deleted = await ctx.channel.purge(limit=amount + 1)
            
            # ส่งข้อความบอกสถานะ แล้วลบตัวเองทิ้งใน 3 วินาที (ไม่ให้รกแชท)
            await ctx.send(f"🧹 ล้างประวัติแชทให้แล้ว {len(deleted)-1} ข้อความครับ", delete_after=3)
            
            print(f"✅ Clear success: {len(deleted)-1} messages by {ctx.author.name}")
        except Exception as e:
            print(f"❌ Clear error: {e}")

@bot.command()
async def status(ctx):
    # 1. คำนวณ Uptime
    current_time = time.time()
    difference = int(round(current_time - start_time))
    text_uptime = str(datetime.timedelta(seconds=difference))

    # 2. อ่านค่า RAM
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    # 3. อ่านค่า Disk และ CPU
    disk = psutil.disk_usage('/')
    cpu = psutil.cpu_percent()

    # 4. สร้างข้อความรายงาน
    report = (
        f"**📊 Health Report**\n"
        f"---"
        f"\n⏱️ **Uptime:** `{text_uptime}`"
        f"\n🏎️ **Bot Latency:** `{round(bot.latency * 1000)}ms`"
        f"\n🖥️ **CPU Usage:** `{cpu}%`"
        f"\n🧠 **RAM:** `{ram.used // (1024**2)}MB` / `{ram.total // (1024**2)}MB`"
        f"\n🔄 **Swap:** `{swap.used // (1024**2)}MB` / `{swap.total // (1024**2)}MB`"
        f"\n💾 **Disk:** `{disk.percent}% used`"
        f"\n---"
    )
    
    await ctx.send(report)
# ชื่อไฟล์ที่จะใช้เก็บความจำ
MEMORY_FILE = 'brain.json'

# ฟังก์ชันโหลดความจำจากไฟล์
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {} # ถ้าไฟล์เสียหรือว่าง ให้เริ่มใหม่
    return {}

# ฟังก์ชันบันทึกความจำลงไฟล์
def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        # indent=4 ทำให้ไฟล์อ่านง่าย, ensure_ascii=False ทำให้เซฟภาษาไทยได้
        json.dump(data, f, ensure_ascii=False, indent=4)

# โหลดความจำขึ้นมาเก็บไว้ในตัวแปรทันทีที่เปิดบอท
chat_memory = load_memory()

async def pro_search(query):
    try:
        with DDGS() as ddgs:
            # เพิ่มการค้นหาที่เจาะจงปีปัจจุบัน 2026
            refined_query = f"{query} ข้อมูลล่าสุดปี 2026"
            results = [r for r in ddgs.text(refined_query, max_results=5)]
            
            if not results: return "ไม่พบข้อมูลใหม่ในอินเทอร์เน็ต"
            
            context = "⚠️ ข้อมูลสดจากอินเทอร์เน็ต (Real-time Data 2026):\n"
            for res in results:
                context += f"- {res['body']}\n"
            return context
    except Exception as e:
        return f"ระบบค้นหาขัดข้อง: {e}"

@bot.command(aliases=['ood', 'ถาม'])
async def ask(ctx, *, question: str):
    async with ctx.typing():
        channel_id = str(ctx.channel.id)
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        current_time_str = now.strftime("%d/%m/%Y %H:%M")

        # 🔍 Step 1: ค้นหาข้อมูลก่อน (RAG Process)
        search_results = await pro_search(question)

        # 🧠 Step 2: สร้าง System Instruction ที่แข็งแกร่ง
        # เราส่งข้อมูลเข้าไปใน 'contents' แทนการใช้ system_instruction แยก (เพื่อความเสถียร)
        prompt_context = (
            f"คุณคือผู้ช่วย AI อัจฉริยะ ชื่อลุงอ๊อด ที่มีความรอบรู้ระดับสูงและสุภาพ ตอบเป็นกันเอง\n"
            f"ลุงอ๊อดเป็นคนกวนๆ แต่คุยรู้เรื่อง"
            f"วันนี้คือวันที่: {current_time_str} แต่ไม่ต้องบอกตลอด\n"
            f"คำแนะนำสำคัญ:\n"
            f"1. ใช้ข้อมูลจากอินเทอร์เน็ตนี้เป็นหลักในการตอบ: {search_results}\n"
            f"2. หากข้อมูลในเน็ตระบุราคาหุ้น หรือทองคำ ให้ยึดตามนั้นและบอกแหล่งที่มา\n"
            f"3. ถ้าข้อมูลในเน็ตไม่มี ให้แจ้งหลานตามตรงว่าข้อมูลยังไม่อัปเดต ห้ามมโนตัวเลขเอง\n"
            f"4. ตอบเป็นกันเอง สรุปสั้นๆ เหมือนถามตอบลุงหลาน มีตัวหนา และ bullet points ให้อ่านง่าย\n\n"
            f"คำถามจากหลาน: {question}"
            f"กฎเหล็ก: ห้ามคำนวณหรือเดาราคาหุ้น/ทองเองเด็ดขาด หากข้อมูลในเน็ตเป็นของปี 2024 หรือ 2025 ให้รายงานตามนั้น และระบุปี พ.ศ./ค.ศ. ที่พบในข้อมูลให้ชัดเจน เพื่อให้หลานทราบว่าเป็นข้อมูลล่าสุดเท่าที่หาได้"
            f"หากในเน็ตไม่มีราคา Real-time ของวันปัจจุบัน ให้บอกหลานว่า 'ลุงเช็กให้แล้ว ข้อมูลล่าสุดที่มีคือของปี... ราคาอยู่ที่...' ห้ามเนียนเดาตัวเลขขึ้นมาเอง"
        )

        try:
            # 🚀 เปลี่ยนมาใช้รุ่น ASYNC (generate_content_async)
            # เพื่อไม่ให้บอทหยุดทำงานขณะรอคำตอบ
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]

            # ✨ หัวใจสำคัญคือเติมคำว่า _async และ await ครับ
            response = await model.generate_content_async(
                prompt_context,
                safety_settings=safety_settings,
                request_options={'timeout': 60}
            )

            if not response.candidates or not response.candidates[0].content.parts:
                await ctx.send("📋 ข้อมูลนี้ลุงขอผ่านนะหลาน ระบบมันกรองทิ้ง (หรือลองถามใหม่ซิ)")
                return

            answer = response.text

            # บันทึกความจำ (แบบง่าย)
            if channel_id not in chat_memory:
                chat_memory[channel_id] = []
            chat_memory[channel_id].append({"role": "user", "parts": [question]})
            chat_memory[channel_id].append({"role": "model", "parts": [answer]})

            # คุมขนาดความจำ
            if len(chat_memory[channel_id]) > 10:
                chat_memory[channel_id] = chat_memory[channel_id][-10:]

            save_memory(chat_memory)

            # ส่งคำตอบ (รองรับข้อความยาว)
            if len(answer) > 2000:
                for i in range(0, len(answer), 2000):
                    await ctx.send(answer[i:i+2000])
            else:
                await ctx.send(answer)

        except Exception as e:
            print(f"Gemini Error: {e}")
            await ctx.send("ขออภัยครับหลาน สมองลุงเกิดอาการช็อตนิดหน่อย ลองถามใหม่อีกทีนะ")

# --- [ แถม: คำสั่งล้างสมอง ] ---
@bot.command()
async def forget(ctx):
    channel_id = str(ctx.channel.id)
    if channel_id in chat_memory:
        del chat_memory[channel_id]
        save_memory(chat_memory)
        await ctx.send("🧹 ลุงอ๊อดลืมหมดแล้วว่าเมื่อกี้เราคุยอะไรกัน!")
    else:
        await ctx.send("🤔 เราเคยคุยกันด้วยเรอะ? ลุงจำไม่ได้อยู่แล้ว")

bot.run(TOKEN)

