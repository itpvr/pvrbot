import discord
from discord.ext import commands
import os
import datetime

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ตัวแปรชั่วคราวสำหรับเก็บเวลาตอนคนกำลังอยู่ในห้อง
active_users = {}

@bot.event
async def on_ready():
    print(f'✅ Bot is online! Logged in as {bot.user}')

@bot.event
async def on_voice_state_update(member, before, after):
    # กรณีเข้าห้องเสียง (Join)
    if before.channel is None and after.channel is not None:
        active_users[member.id] = datetime.datetime.now()
        print(f"📥 {member.name} joined {after.channel.name}")

    # กรณีออกจากห้องเสียง (Leave)
    elif before.channel is not None and after.channel is None:
        start_time = active_users.pop(member.id, None)
        if start_time:
            duration = datetime.datetime.now() - start_time
            minutes = int(duration.total_seconds() / 60)
            print(f"📤 {member.name} left {before.channel.name}. Time spent: {minutes} minutes")
            # เดี๋ยวเราจะเอาเวลาที่ได้ไปอัปเดตลงฐานข้อมูลอีกที
            # หลักการทำงานจะคล้ายๆ กับเวลาที่เราซิงค์ข้อมูลอัปเกรดหรือการปรับแต่งยานพาหนะเข้า Database ฝั่งเซิร์ฟเวอร์เลยครับ

# รันบอทโดยใช้ Token จาก Environment Variable ของ Host
bot.run(os.environ.get('MTQ5MzYzMzg4NTE3MzU3OTg3OA.G1TWaR.w87oMfFvpR3mVH-cpLy-OwtkIQ_eIwFrBi4Kno'))
