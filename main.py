import os
import sys
import time
import sqlite3
import asyncio
import datetime
import json
import base64
import audioop
import queue

import psutil
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ext import voice_recv
from dotenv import load_dotenv

import websockets
import google.generativeai as genai
from ddgs import DDGS


# =========================
# Load Config
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")

BOT_NAME = os.getenv("BOT_NAME", "gosu")

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
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
voice_sessions = {}


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
# Voice Utilities
# =========================

class PCMQueueAudioSource(discord.AudioSource):
    """
    Discord voice output format:
    48kHz, stereo, signed 16-bit PCM, 20ms frame = 3840 bytes
    """

    FRAME_SIZE = 3840

    def __init__(self):
        self.q = queue.Queue(maxsize=160)
        self.buffer = bytearray()
        self.closed = False

    def is_opus(self):
        return False

    def read(self) -> bytes:
        if self.closed:
            return b""

        while len(self.buffer) < self.FRAME_SIZE:
            try:
                chunk = self.q.get_nowait()
                self.buffer.extend(chunk)
            except queue.Empty:
                break

        if len(self.buffer) >= self.FRAME_SIZE:
            frame = self.buffer[:self.FRAME_SIZE]
            del self.buffer[:self.FRAME_SIZE]
            return bytes(frame)

        return b"\x00" * self.FRAME_SIZE

    def push(self, pcm48_stereo: bytes):
        if not pcm48_stereo:
            return

        try:
            if not self.q.full():
                self.q.put_nowait(pcm48_stereo)
        except queue.Full:
            pass

    def cleanup(self):
        self.closed = True


class AudioResampler:
    """
    ใช้ audioop เพื่อลดภาระเครื่อง:
    - Discord input: 48k stereo PCM16
    - OpenAI input: 24k mono PCM16
    - OpenAI output: 24k mono PCM16
    - Discord output: 48k stereo PCM16
    """

    def __init__(self):
        self.to_ai_state = None
        self.to_discord_state = None

    def discord_to_ai(self, pcm48_stereo: bytes) -> bytes:
        if not pcm48_stereo:
            return b""

        try:
            mono48 = audioop.tomono(pcm48_stereo, 2, 0.5, 0.5)
            mono24, self.to_ai_state = audioop.ratecv(
                mono48,
                2,
                1,
                48000,
                24000,
                self.to_ai_state
            )
            return mono24
        except Exception as e:
            print(f"discord_to_ai resample error: {e}")
            return b""

    def ai_to_discord(self, pcm24_mono: bytes) -> bytes:
        if not pcm24_mono:
            return b""

        try:
            mono48, self.to_discord_state = audioop.ratecv(
                pcm24_mono,
                2,
                1,
                24000,
                48000,
                self.to_discord_state
            )
            stereo48 = audioop.tostereo(mono48, 2, 1.0, 1.0)
            return stereo48
        except Exception as e:
            print(f"ai_to_discord resample error: {e}")
            return b""


class OpenAIRealtimeVoice:
    def __init__(self):
        self.ws = None
        self.recv_task = None
        self.audio_out = queue.Queue(maxsize=160)
        self.connected = False

    async def connect(self):
        if not OPENAI_API_KEY:
            raise RuntimeError("Missing OPENAI_API_KEY")

        url = f"wss://api.openai.com/v1/realtime?model={OPENAI_REALTIME_MODEL}"

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Safety-Identifier": "discord-pvrbot",
        }

        try:
            self.ws = await websockets.connect(
                url,
                additional_headers=headers,
                max_size=2 ** 20,
                ping_interval=20,
                ping_timeout=20,
            )
        except TypeError:
            self.ws = await websockets.connect(
                url,
                extra_headers=headers,
                max_size=2 ** 20,
                ping_interval=20,
                ping_timeout=20,
            )

        self.connected = True

        await self.send({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": (
                    "คุณคือ 'ลุงอ๊อด' ผู้ช่วยเสียงภาษาไทย "
                    "ตอบสั้น กระชับ สุภาพ เป็นกันเอง "
                    "เรียกตัวเองว่า 'ลุง' และเรียกผู้ใช้ว่า 'หลาน'"
                ),
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.55,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 650,
                },
            },
        })

        self.recv_task = asyncio.create_task(self.recv_loop())

    async def send(self, payload: dict):
        if self.ws:
            await self.ws.send(json.dumps(payload))

    async def say_text(self, text: str):
        if not self.connected:
            return

        await self.send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            },
        })

        await self.send({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
            },
        })

    async def send_audio_pcm16(self, pcm24_mono: bytes):
        if not self.connected or not pcm24_mono:
            return

        audio_b64 = base64.b64encode(pcm24_mono).decode("ascii")

        await self.send({
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        })

    async def commit_audio(self):
        if not self.connected:
            return

        await self.send({"type": "input_audio_buffer.commit"})
        await self.send({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
            },
        })

    async def recv_loop(self):
        try:
            async for raw in self.ws:
                event = json.loads(raw)
                event_type = event.get("type")

                if event_type in (
                    "response.audio.delta",
                    "response.output_audio.delta",
                ):
                    delta = event.get("delta")
                    if delta:
                        pcm = base64.b64decode(delta)
                        try:
                            if not self.audio_out.full():
                                self.audio_out.put_nowait(pcm)
                        except queue.Full:
                            pass

                elif event_type == "response.text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        print(delta, end="", flush=True)

                elif event_type == "response.done":
                    print("\n✅ Realtime response done")

                elif event_type == "error":
                    print("❌ OpenAI realtime error:", event)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Realtime recv error: {e}")

    async def close(self):
        self.connected = False

        if self.recv_task:
            self.recv_task.cancel()

        if self.ws:
            await self.ws.close()


class RealtimeAudioSink(voice_recv.AudioSink):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.Member, data):
        if not user or user.bot:
            return

        pcm = getattr(data, "pcm", None)
        if not pcm:
            return

        self.session.feed_user_audio(user.id, pcm)

    def cleanup(self):
        pass


class VoiceSession:
    def __init__(self, bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.voice_client = None

        self.source = PCMQueueAudioSource()
        self.resampler = AudioResampler()
        self.realtime = OpenAIRealtimeVoice()

        self.active_user_id = None
        self.audio_in = queue.Queue(maxsize=100)

        self.last_audio_time = 0
        self.has_audio_since_commit = False
        self.tasks = []

    async def join(self, channel: discord.VoiceChannel):
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect(
                cls=voice_recv.VoiceRecvClient,
                self_deaf=False,
                self_mute=False,
                timeout=20,
                reconnect=True,
            )

        if not self.realtime.connected:
            await self.realtime.connect()

        try:
            self.voice_client.listen(RealtimeAudioSink(self))
        except Exception as e:
            print(f"listen error: {e}")

        if not self.voice_client.is_playing():
            self.voice_client.play(self.source)

        if not self.tasks:
            self.tasks.append(asyncio.create_task(self.audio_to_ai_loop()))
            self.tasks.append(asyncio.create_task(self.ai_to_discord_loop()))

    def feed_user_audio(self, user_id: int, pcm48_stereo: bytes):
        """
        รับทีละ 1 speaker ป้องกันเสียงหลายคนปนกันบน e2-micro
        """
        if self.active_user_id is None:
            self.active_user_id = user_id

        if user_id != self.active_user_id:
            return

        pcm24_mono = self.resampler.discord_to_ai(pcm48_stereo)

        if not pcm24_mono:
            return

        try:
            if not self.audio_in.full():
                self.audio_in.put_nowait(pcm24_mono)
                self.last_audio_time = time.time()
                self.has_audio_since_commit = True
        except queue.Full:
            pass

    async def audio_to_ai_loop(self):
        while True:
            await asyncio.sleep(0.01)

            try:
                pcm24_mono = self.audio_in.get_nowait()
            except queue.Empty:
                if (
                    self.active_user_id is not None
                    and self.has_audio_since_commit
                    and time.time() - self.last_audio_time > 1.0
                ):
                    try:
                        await self.realtime.commit_audio()
                    except Exception as e:
                        print(f"commit audio error: {e}")

                    self.active_user_id = None
                    self.has_audio_since_commit = False

                continue

            try:
                await self.realtime.send_audio_pcm16(pcm24_mono)
            except Exception as e:
                print(f"send audio error: {e}")

    async def ai_to_discord_loop(self):
        while True:
            await asyncio.sleep(0.005)

            try:
                api_pcm24 = self.realtime.audio_out.get_nowait()
            except queue.Empty:
                continue

            pcm48_stereo = self.resampler.ai_to_discord(api_pcm24)

            if pcm48_stereo:
                self.source.push(pcm48_stereo)

    async def say_text(self, text: str):
        await self.realtime.say_text(text)

    async def leave(self):
        for task in self.tasks:
            task.cancel()

        self.tasks.clear()

        try:
            if self.voice_client:
                self.voice_client.stop_listening()
        except Exception:
            pass

        await self.realtime.close()
        self.source.cleanup()

        if self.voice_client:
            await self.voice_client.disconnect(force=True)


# =========================
# Slash Commands: OOD
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
# Slash Commands: Voice
# =========================

class VoiceGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="voice",
            description="คำสั่งโหมดเสียงของลุงอ๊อด"
        )

    @app_commands.command(name="join", description="ให้ลุงอ๊อดเข้าห้องเสียง")
    async def join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                "หลานต้องเข้าห้องเสียงก่อนนะครับ",
                ephemeral=True
            )
            return

        if not OPENAI_API_KEY:
            await interaction.followup.send(
                "ยังไม่ได้ตั้งค่า OPENAI_API_KEY ในไฟล์ .env ครับ",
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel
        guild_id = interaction.guild_id

        session = voice_sessions.get(guild_id)

        if not session:
            session = VoiceSession(interaction.client, guild_id)
            voice_sessions[guild_id] = session

        try:
            await session.join(channel)
            await interaction.followup.send(
                f"✅ ลุงเข้าห้องเสียง `{channel.name}` แล้วครับ",
                ephemeral=True
            )
        except Exception as e:
            print(f"voice join error: {e}")
            await interaction.followup.send(
                f"❌ เข้าห้องเสียงไม่สำเร็จ: `{e}`",
                ephemeral=True
            )

    @app_commands.command(name="leave", description="ให้ลุงอ๊อดออกจากห้องเสียง")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        session = voice_sessions.pop(interaction.guild_id, None)

        if session:
            await session.leave()

        await interaction.followup.send(
            "👋 ลุงออกจากห้องเสียงแล้วครับ",
            ephemeral=True
        )

    @app_commands.command(name="talk", description="ให้ลุงพูดข้อความผ่านเสียง")
    async def talk(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer(ephemeral=True)

        session = voice_sessions.get(interaction.guild_id)

        if not session:
            await interaction.followup.send(
                "ลุงยังไม่ได้อยู่ในห้องเสียงครับ ใช้ `/voice join` ก่อนนะ",
                ephemeral=True
            )
            return

        try:
            await session.say_text(text)
            await interaction.followup.send(
                "✅ ส่งให้ลุงพูดแล้วครับ",
                ephemeral=True
            )
        except Exception as e:
            print(f"voice talk error: {e}")
            await interaction.followup.send(
                f"❌ พูดไม่สำเร็จ: `{e}`",
                ephemeral=True
            )


# =========================
# Bot Setup Low RAM
# =========================

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()

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
        try:
            self.tree.add_command(OodGroup())
        except app_commands.CommandAlreadyRegistered:
            print("⚠️ OodGroup already registered, skip add_command")

        try:
            self.tree.add_command(VoiceGroup())
        except app_commands.CommandAlreadyRegistered:
            print("⚠️ VoiceGroup already registered, skip add_command")

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            synced = await self.tree.sync(guild=guild)
            print(f"✅ Guild Slash Commands Synced: {len(synced)} commands")
        else:
            synced = await self.tree.sync()
            print(f"✅ Global Slash Commands Synced: {len(synced)} commands")


bot = MyBot()


# =========================
# Voice Auto Recovery
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
    await bot.wait_until_ready()

    if not TARGET_VOICE_CHANNEL_ID:
        return

    channel = bot.get_channel(TARGET_VOICE_CHANNEL_ID)

    if not isinstance(channel, discord.VoiceChannel):
        return

    session = voice_sessions.get(channel.guild.id)

    if not session:
        return

    vc = session.voice_client

    if vc is None or not vc.is_connected():
        try:
            await session.join(channel)
            await send_recovery_log(
                "drop",
                "บอทหลุดจากห้องเสียงและเชื่อมต่อกลับอัตโนมัติ"
            )
        except Exception as e:
            print(f"Voice recovery failed: {e}")

    elif vc.channel.id != TARGET_VOICE_CHANNEL_ID:
        try:
            await vc.move_to(channel)
            await send_recovery_log(
                "move",
                "บอทถูกย้ายห้องและดึงกลับห้องเป้าหมายแล้ว"
            )
        except Exception as e:
            print(f"Voice move recovery failed: {e}")


@bot.event
async def on_ready():
    print(f"🚀 บอท {bot.user} ออนไลน์แล้ว")
    print("✅ Low RAM mode enabled")

    if not check_voice_status.is_running():
        check_voice_status.start()


bot.run(TOKEN)