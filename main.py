import os
import sys
import time
import sqlite3
import asyncio
import datetime

import psutil
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import google.generativeai as genai
from ddgs import DDGS


# =========================
# Load Config
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BOT_NAME = os.getenv("BOT_NAME", "gosu")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
TARGET_VOICE_CHANNEL_ID = int(os.getenv("TARGET_VOICE_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

if not TOKEN:
    print("❌ Missing DISCORD_TOKEN")
    sys.exit(1)

if not GEMINI_API_KEY:
    print("❌ Missing GEMINI_API_KEY")
    sys.exit(1)


# =========================
# AI Setup
# =========================

genai.configure(api_key=GEMINI_API_KEY)
text_model = genai.GenerativeModel("gemini-1.5-flash")


# =========================
# Runtime State
# =========================

start_time = time.time()


# =========================
# SQLite Memory
# =========================

db_filename = f"brain_{BOT_NAME}.db"

conn = sqlite3.connect(db_filename)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS memory (
    channel_id TEXT,
    role TEXT,
    content TEXT,
    created_at INTEGER
)
""")
conn.commit()


def save_to_db(channel_id: int, role: str, content: str):
    """
    Keep memory small for 1GB RAM server.
    Store only latest 8 messages per channel.
    """
    content = content[:1200]

    c.execute(
        "INSERT INTO memory VALUES (?, ?, ?, ?)",
        (str(channel_id), role, content, int(time.time()))
    )
    conn.commit()

    c.execute(
        """
        DELETE FROM memory
        WHERE rowid NOT IN (
            SELECT rowid
            FROM memory
            WHERE channel_id = ?
            ORDER BY rowid DESC
            LIMIT 8
        )
        AND channel_id = ?
        """,
        (str(channel_id), str(channel_id))
    )
    conn.commit()


def load_from_db(channel_id: int):
    c.execute(
        """
        SELECT role, content
        FROM memory
        WHERE channel_id = ?
        ORDER BY rowid ASC
        """,
        (str(channel_id),)
    )
    return c.fetchall()


# =========================
# Web Search
# =========================

def _sync_search(query: str):
    try:
        with DDGS() as ddgs:
            results = ddgs.text(
                f"{query} ข้อมูลล่าสุด",
                max_results=3
            )
            return [r for r in results]
    except Exception as e:
        print(f"Search error: {e}")
        return []


async def pro_search(query: str) -> str:
    if not query.strip():
        return "ไม่มีคำค้นหา"

    results = await asyncio.to_thread(_sync_search, query)

    if not results:
        return "ไม่พบข้อมูลใหม่จากอินเทอร์เน็ต"

    context = "ข้อมูลอ้างอิงจากอินเทอร์เน็ต:\n"

    for res in results:
        title = res.get("title", "")
        body = res.get("body", "")
        href = res.get("href", "")

        context += f"- {title}: {body} ({href})\n"

    return context[:2500]


# =========================
# AI Text Function
# =========================

async def ask_lung_ood(
    question: str,
    channel_id: int,
    image_data=None
) -> str:
    now = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=7))
    )
    current_time_str = now.strftime("%d/%m/%Y %H:%M")

    history = load_from_db(channel_id)
    history_text = ""

    for role, content in history:
        speaker = "ผู้ใช้" if role == "user" else "ลุงอ๊อด"
        history_text += f"{speaker}: {content}\n"

    search_result = await pro_search(question)

    prompt = f"""
คุณคือ 'ลุงอ๊อด' AI ผู้ช่วยอัจฉริยะที่ถูกพัฒนาขึ้นโดย PVR

เวลาปัจจุบัน: {current_time_str}

บุคลิก:
- เป็นผู้เชี่ยวชาญที่ฉลาด วิเคราะห์ดี และตอบตรงประเด็น
- ใช้สรรพนามแทนตัวเองว่า "ลุง"
- เรียกคู่สนทนาว่า "หลาน"
- สุภาพ เป็นกันเอง
- ห้ามใช้คำหยาบ ห้ามประชด ห้ามกวน
- ตอบสั้น กระชับ เหมือนแชทจริง
- ปกติไม่เกิน 2-4 บรรทัด
- ถ้าเป็นโค้ดหรือขั้นตอนซับซ้อน ค่อยตอบเป็นข้อ ๆ

ข้อมูลจากเน็ต:
{search_result}

บริบทก่อนหน้า:
{history_text}

คำถามปัจจุบัน:
{question}
"""

    try:
        content_list = [prompt]

        if image_data:
            content_list.append(image_data)

        response = await text_model.generate_content_async(
            content_list,
            request_options={"timeout": 60}
        )

        if not response or not getattr(response, "text", None):
            return "ลุงยังตอบไม่ได้ตอนนี้ครับ หลานลองถามใหม่อีกทีนะ"

        answer = response.text.strip()

        save_to_db(channel_id, "user", question)
        save_to_db(channel_id, "model", answer)

        return answer[:1900]

    except Exception as e:
        print(f"Gemini error: {e}")
        return "ระบบ AI ขัดข้องชั่วคราวครับ หลานลองใหม่อีกครั้งนะ"


# =========================
# Slash Commands
# =========================

class OodGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="ood",
            description="คำสั่งทั้งหมดของลุงอ๊อด"
        )

    @app_commands.command(
        name="ask",
        description="ถามปัญหาลุงอ๊อด หรือให้วิเคราะห์รูป"
    )
    @app_commands.describe(
        question="พิมพ์คำถามที่นี่",
        image="ส่งรูปให้ลุงดู ถ้ามี"
    )
    async def ask(
        self,
        interaction: discord.Interaction,
        question: str = "",
        image: discord.Attachment = None
    ):
        await interaction.response.defer()

        image_data = None

        if image:
            if not image.content_type or not image.content_type.startswith("image/"):
                await interaction.followup.send("ส่งมาได้เฉพาะรูปภาพนะครับ")
                return

            image_bytes = await image.read()
            image_data = {
                "mime_type": image.content_type,
                "data": image_bytes
            }

            if not question:
                question = "วิเคราะห์รูปนี้ให้หน่อยครับ"

        if not question and not image_data:
            await interaction.followup.send("พิมพ์คำถามมาก่อนได้เลยครับ")
            return

        answer = await ask_lung_ood(
            question=question,
            channel_id=interaction.channel_id,
            image_data=image_data
        )

        if len(answer) > 2000:
            for i in range(0, len(answer), 1900):
                await interaction.followup.send(answer[i:i + 1900])
        else:
            await interaction.followup.send(answer)

    @app_commands.command(
        name="status",
        description="เช็กสุขภาพเครื่องเซิร์ฟเวอร์"
    )
    async def status(self, interaction: discord.Interaction):
        current_time = time.time()
        uptime = str(
            datetime.timedelta(seconds=int(current_time - start_time))
        )

        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        ping = round(interaction.client.latency * 1000)

        try:
            db_size = os.path.getsize(db_filename) / 1024
        except Exception:
            db_size = 0

        if cpu > 85 or ram.percent > 90:
            embed_color = discord.Color.red()
            status_text = "🔴 วิกฤต"
        elif cpu > 60 or ram.percent > 75:
            embed_color = discord.Color.orange()
            status_text = "🟠 เริ่มหนัก"
        else:
            embed_color = discord.Color.green()
            status_text = "🟢 ปกติ"

        embed = discord.Embed(
            title=f"🖥️ System Status : {BOT_NAME.upper()}",
            description=f"**สถานะ:** {status_text}",
            color=embed_color,
            timestamp=datetime.datetime.now()
        )

        embed.add_field(name="⏱️ Uptime", value=f"`{uptime}`", inline=True)
        embed.add_field(name="📶 Ping", value=f"`{ping} ms`", inline=True)
        embed.add_field(name="📖 DB Size", value=f"`{db_size:.2f} KB`", inline=True)
        embed.add_field(name="⚙️ CPU", value=f"`{cpu}%`", inline=True)
        embed.add_field(
            name="🧠 RAM",
            value=f"`{ram.used // (1024 ** 2)} MB` ({ram.percent}%)",
            inline=True
        )
        embed.add_field(
            name="🔄 Swap",
            value=f"`{swap.used // (1024 ** 2)} MB`",
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="forget",
        description="ล้างความจำของลุงในห้องนี้ เฉพาะ PVR"
    )
    async def forget(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "คำสั่งนี้สงวนไว้สำหรับ PVR เท่านั้นครับ",
                ephemeral=True
            )
            return

        c.execute(
            "DELETE FROM memory WHERE channel_id = ?",
            (str(interaction.channel_id),)
        )
        conn.commit()

        await interaction.response.send_message(
            "🧹 ล้างความจำในห้องนี้เรียบร้อยครับ",
            ephemeral=True
        )

    @app_commands.command(
        name="say",
        description="สั่งให้บอทพูดแทน เฉพาะ PVR"
    )
    async def say(self, interaction: discord.Interaction, message: str):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "ไม่มีสิทธิ์ใช้งานครับ",
                ephemeral=True
            )
            return

        await interaction.channel.send(message)
        await interaction.response.send_message(
            "✅ ส่งข้อความสำเร็จ",
            ephemeral=True
        )

    @app_commands.command(
        name="clear",
        description="ล้างประวัติแชท เฉพาะ PVR"
    )
    async def clear(self, interaction: discord.Interaction, amount: int = 5):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "ไม่มีสิทธิ์ใช้งานครับ",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        amount = max(1, min(amount, 50))

        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(
                f"🧹 ล้างให้แล้ว {len(deleted)} ข้อความ",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ ล้างไม่ได้: {e}",
                ephemeral=True
            )


# =========================
# Bot Setup Low RAM
# =========================

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()

        # Low RAM mode for e2-micro
        intents.presences = False
        intents.members = False
        intents.message_content = False
        intents.voice_states = True
        intents.guilds = True

        member_cache_flags = discord.MemberCacheFlags.none()

        super().__init__(
            command_prefix="!",
            intents=intents,
            member_cache_flags=member_cache_flags,
            max_messages=20,
            chunk_guilds_at_startup=False,
            help_command=None
        )

    async def setup_hook(self):
        self.tree.add_command(OodGroup())
        await self.tree.sync()
        print(f"✅ Slash commands synced for {self.user}")


bot = MyBot()


# =========================
# Voice Auto Recovery Placeholder
# =========================

async def send_recovery_log(status_type: str, reason: str):
    if not LOG_CHANNEL_ID:
        return

    try:
        log_channel = bot.get_channel(LOG_CHANNEL_ID) or await bot.fetch_channel(LOG_CHANNEL_ID)
    except Exception as e:
        print(f"⚠️ หาห้อง Log ไม่เจอ: {e}")
        return

    color = discord.Color.red() if status_type == "drop" else discord.Color.gold()

    embed = discord.Embed(
        title="🔄 Auto Recovery",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="📋 สาเหตุ", value=reason, inline=False)

    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"❌ ส่ง Log ไม่สำเร็จ: {e}")


@tasks.loop(seconds=30)
async def check_voice_status():
    """
    ตอนนี้ยังไม่ connect voice อัตโนมัติ
    เดี๋ยวเฟสถัดไปเราจะเพิ่ม /voice join และ realtime voice ตรงนี้
    """
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"🚀 บอท {bot.user} ออนไลน์แล้ว")
    print("✅ Low RAM mode enabled")

    if not check_voice_status.is_running():
        check_voice_status.start()


bot.run(TOKEN)