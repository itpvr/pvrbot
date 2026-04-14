import discord
from discord.ext import commands, tasks
import os
import asyncio

# --- ตั้งค่าพื้นฐาน (เหมือนเดิม) ---
TOKEN = os.getenv('DISCORD_TOKEN')
TARGET_CHANNEL_ID = 1069137562213552128 # ID ห้องเสียงที่คุณต้องการให้บอทอยู่

intents = discord.Intents.default()
intents.voice_states = True # Needed for voice check
bot = commands.Bot(command_prefix="!", intents=intents)
intents.message_content = True  # ✅ ต้องมีบรรทัดนี้! (สำคัญมากสำหรับคำสั่ง !)
intents.messages = True

async def set_minimalist_presence():
    MY_APP_ID = 1493633885173579878  # <--- อย่าลืมใส่ ID ของคุณเหมือนเดิม

    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="♫ Listening to GOSU.WAV", # ตรงนี้ต้องใส่ว่า Spotify เพื่อให้มันขึ้น Listening to Spotify
        application_id=MY_APP_ID,
        
        # รายละเอียดเพลง (เหมือน Spotify เป๊ะ)
        details="Kinda miss you ft. flug", # ชื่อเพลง
        assets={
            "large_image": "kinda",        # รูปหน้าปกเพลง
            "large_text": "Kinda miss you", # เอาเมาส์ชี้แล้วขึ้นชื่อเพลง
            "small_image": "spotify_logo", # โลโก้ Spotify เล็กๆ ที่มุมรูป (ถ้าอัปโหลดไว้)
            "small_text": "Verified Artist" 
        },
        buttons=[
            {
                "label": "Play on gosu.wav 🎧", 
                "url": "https://gosuwav.vercel.app/artist/6str?track=86efea40-82d5-4960-86ae-50aeaf86eb25"
            }
        ]
    )

    await bot.change_presence(status=discord.Status.online, activity=activity)
# --- Event เมื่อบอทพร้อม (Setup presence และ tasks) ---
@bot.event
async def on_ready():
    print(f'✅ ออนไลน์แล้วในชื่อ: {bot.user}')
    
    # 1. ตั้งค่าสถานะทีเดียวจบ (ไม่ต้องรัน Loop ให้กวนเครื่อง)
    await set_minimalist_presence()
    print("✨ Minimalist Presence Set")
    
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
        # Silent failure for stability
        pass

@bot.event
async def on_voice_state_update(member, before, after):
    # Optional logger (harmless to keep)
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        print("ℹ️ บอทหลุดจากห้องเสียง (จะกลับเข้าที่ในรอบตรวจถัดไป)")

# --- คำสั่งกลุ่ม !pvr ---
@bot.group()
async def pvr(ctx):
    # ถ้าพิมพ์แค่ !pvr เฉยๆ โดยไม่มีคำสั่งต่อท้าย จะไม่ทำอะไร
    if ctx.invoked_subcommand is None:
        pass

# --- คำสั่งย่อย !pvr say ---
@pvr.command()
async def say(ctx, *, message: str):
    # ตรวจสอบว่าคนสั่งคือคุณ (ID: 431421372133277698) หรือไม่
    ALLOWED_USER_ID = 431421372133277698
    
    if ctx.author.id == ALLOWED_USER_ID:
        # 1. ลบข้อความที่เราพิมพ์สั่ง (!pvr say ...) ทิ้งทันที
        try:
            await ctx.message.delete()
        except Exception as e:
            print(f"ลบข้อความไม่ได้ (อาจขาดสิทธิ์ Manage Messages): {e}")

        # 2. ให้บอทส่งข้อความตามที่สั่ง
        await ctx.send(message)
    else:
        # ถ้าคนอื่นสั่ง บอทจะไม่ตอบโต้ หรือคุณจะให้บอทพิมพ์ด่าก็ได้นะ 555
        print(f"⚠️ มีคนพยายามใช้คำสั่ง: {ctx.author.name} (ID: {ctx.author.id})")

bot.run(TOKEN)