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

# --------------------------
# AUDIO FUNCTIONS
# --------------------------

def convert_to_wav(input_path, output_path):
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "44100",
        "-ac", "2",
        output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def fast_mix(vocal_path, instrumental_path, output_path):
    vocal = AudioSegment.from_file(vocal_path)
    instrumental = AudioSegment.from_file(instrumental_path)

    # Basit gain dengeleme
    vocal = vocal - 3
    instrumental = instrumental - 1

    # Uzunluk eşitleme
    min_len = min(len(vocal), len(instrumental))
    vocal = vocal[:min_len]
    instrumental = instrumental[:min_len]

    final = instrumental.overlay(vocal)
    final.export(output_path, format="mp3")

# --------------------------
# TELEGRAM HANDLERS
# --------------------------

@bot.message_handler(commands=['start'])
def start(message):
    user_sessions[message.from_user.id] = []
    bot.reply_to(message, "🎤 Önce VOCAL gönder.")

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

    user_sessions.setdefault(user_id, []).append(file_path)

    if len(user_sessions[user_id]) == 1:
        bot.reply_to(message, "🎼 Şimdi INSTRUMENTAL gönder.")
    elif len(user_sessions[user_id]) == 2:
        bot.reply_to(message, "⚡ Mix yapılıyor...")
        process_audio(user_id, message)

# --------------------------
# PROCESS AUDIO
# --------------------------

def process_audio(user_id, message):
    try:
        session_path = os.path.join(BASE_DIR, str(user_id))
        vocal_raw, instrumental_raw = user_sessions[user_id]

        vocal_wav = os.path.join(session_path, "vocal.wav")
        inst_wav = os.path.join(session_path, "inst.wav")

        convert_to_wav(vocal_raw, vocal_wav)
        convert_to_wav(instrumental_raw, inst_wav)

        output_path = os.path.join(session_path, "final_mix.mp3")
        fast_mix(vocal_wav, inst_wav, output_path)

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
    bot.set_webhook(url=f"https://YOUR_RENDER_URL.onrender.com/{TOKEN}")
    app.run(host="0.0.0.0", port=port)
