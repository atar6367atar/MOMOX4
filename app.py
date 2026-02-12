import os
import telebot
from flask import Flask, request
from pydub import AudioSegment
import subprocess

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

BASE_DIR = "sessions"
os.makedirs(BASE_DIR, exist_ok=True)
user_sessions = {}

ALLOWED = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"]
MAX_DURATION_MS = 3 * 60 * 1000  # 3 dakika = 180.000 ms

# --------------------------
# AUDIO FUNCTIONS
# --------------------------

def check_duration(path):
    audio = AudioSegment.from_file(path)
    return len(audio) <= MAX_DURATION_MS

def fast_mix_ffmpeg(vocal_path, instrumental_path, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-i", instrumental_path,
        "-i", vocal_path,
        "-filter_complex",
        "[1:a]volume=0.8[a1];[0:a][a1]amix=inputs=2:duration=longest",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --------------------------
# TELEGRAM HANDLERS
# --------------------------

@bot.message_handler(commands=['start'])
def start(message):
    user_sessions[message.from_user.id] = []
    bot.reply_to(message, "🎤 Önce VOCAL gönder (max 3dk).")

@bot.message_handler(content_types=['audio', 'document'])
def handle_audio(message):
    user_id = message.from_user.id
    session_path = os.path.join(BASE_DIR, str(user_id))
    os.makedirs(session_path, exist_ok=True)

    if message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
    else:
        file_id = message.document.file_id
        file_name = message.document.file_name or "audio.mp3"

    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED:
        bot.reply_to(message, "❌ Desteklenmeyen format.")
        return

    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    count = len(user_sessions.get(user_id, []))
    file_path = os.path.join(session_path, f"input_{count}{ext}")

    with open(file_path, "wb") as f:
        f.write(downloaded)

    if not check_duration(file_path):
        bot.reply_to(message, "❌ Maksimum şarkı süresi 3 dakika!")
        return

    user_sessions.setdefault(user_id, []).append(file_path)

    if len(user_sessions[user_id]) == 1:
        bot.reply_to(message, "🎼 Şimdi INSTRUMENTAL gönder (max 3dk).")
    elif len(user_sessions[user_id]) == 2:
        bot.reply_to(message, "⚡ Hızlı mix yapılıyor...")
        process_audio(user_id, message)

# --------------------------
# PROCESS AUDIO
# --------------------------

def process_audio(user_id, message):
    try:
        session_path = os.path.join(BASE_DIR, str(user_id))
        vocal_path, inst_path = user_sessions[user_id]
        output_path = os.path.join(session_path, "final_mix.mp3")

        fast_mix_ffmpeg(vocal_path, inst_path, output_path)

        bot.send_audio(message.chat.id, open(output_path, "rb"))

    finally:
        user_sessions[user_id] = []

# --------------------------
# WEBHOOK
# --------------------------

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def home():
    return "Bot aktif"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    bot.set_webhook(url=f"https://zordomusic.onrender.com/{TOKEN}")
    app.run(host="0.0.0.0", port=port)
