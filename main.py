import discord
from discord.ext import commands
import os
import datetime
from flask import Flask
from threading import Thread

# --- ส่วนของ Web Server เพื่อกันหลับ ---
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ----------------------------------

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
active_users = {}

@bot.event
async def on_ready():
    print(f'✅ บอทออนไลน์แล้วในชื่อ: {bot.user}')

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        active_users[member.id] = datetime.datetime.now()
        print(f"📥 {member.name} เข้าห้อง {after.channel.name}")
    elif before.channel is not None and after.channel is None:
        start_time = active_users.pop(member.id, None)
        if start_time:
            duration = datetime.datetime.now() - start_time
            minutes = int(duration.total_seconds() / 60)
            print(f"📤 {member.name} ออกจากห้อง. อยู่ไป {minutes} นาที")

# เรียกใช้ฟังก์ชันกันหลับ
keep_alive()

# รันบอท
token = os.environ.get('MTQ5MzYzMzg4NTE3MzU3OTg3OA.G1TWaR.w87oMfFvpR3mVH-cpLy-OwtkIQ_eIwFrBi4Kno')
if token:
    bot.run(token)
else:
    print("❌ ไม่พบ DISCORD_TOKEN ใน Environment Variables")
