import os
import telebot
import librosa
import soundfile as sf
import numpy as np
from pydub import AudioSegment
from flask import Flask, request
from scipy.signal import correlate

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

BASE_DIR = "sessions"
os.makedirs(BASE_DIR, exist_ok=True)

user_sessions = {}
ALLOWED_FORMATS = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"]

# --------------------------
# AUDIO PROCESSING
# --------------------------

def load_mono(path):
    y, sr = librosa.load(path, mono=True)
    return y, sr

def detect_bpm(path):
    y, sr = load_mono(path)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    return tempo

def detect_key(path):
    y, sr = load_mono(path)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    return int(np.argmax(np.mean(chroma, axis=1)))

def time_stretch(input_path, rate, output_path):
    y, sr = load_mono(input_path)
    stretched = librosa.effects.time_stretch(y, rate)
    sf.write(output_path, stretched, sr)

def pitch_shift(input_path, semitones, output_path):
    y, sr = load_mono(input_path)
    shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)
    sf.write(output_path, shifted, sr)

def align_audio(ref_path, target_path, output_path):
    y_ref, sr = load_mono(ref_path)
    y_tar, _ = load_mono(target_path)

    correlation = correlate(y_ref, y_tar)
    shift = correlation.argmax() - len(y_tar)

    if shift > 0:
        y_tar = np.pad(y_tar, (shift, 0))
    else:
        y_tar = y_tar[-shift:]

    sf.write(output_path, y_tar, sr)

def auto_gain(vocal, instrumental):
    vocal = vocal.apply_gain(-vocal.max_dBFS)
    instrumental = instrumental.apply_gain(-instrumental.max_dBFS - 1)
    return vocal, instrumental

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
    if ext not in ALLOWED_FORMATS:
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
        bot.reply_to(message, "🎛 Profesyonel uyum yapılıyor...")
        process_audio(user_id, message)

# --------------------------
# MAIN PROCESS
# --------------------------

def process_audio(user_id, message):
    try:
        session_path = os.path.join(BASE_DIR, str(user_id))
        vocal_path, instrumental_path = user_sessions[user_id]

        # BPM
        bpm_inst = detect_bpm(instrumental_path)
        bpm_voc = detect_bpm(vocal_path)
        rate = bpm_inst / bpm_voc if bpm_voc != 0 else 1

        stretched = os.path.join(session_path, "stretched.wav")
        time_stretch(vocal_path, rate, stretched)

        # Pitch
        key_inst = detect_key(instrumental_path)
        key_voc = detect_key(stretched)
        semitone_diff = key_inst - key_voc

        pitched = os.path.join(session_path, "pitched.wav")
        pitch_shift(stretched, semitone_diff, pitched)

        # Align
        aligned = os.path.join(session_path, "aligned.wav")
        align_audio(instrumental_path, pitched, aligned)

        # Mix
        inst_audio = AudioSegment.from_file(instrumental_path)
        voc_audio = AudioSegment.from_file(aligned)

        voc_audio, inst_audio = auto_gain(voc_audio, inst_audio)

        final_mix = inst_audio.overlay(voc_audio)

        output_path = os.path.join(session_path, "final_mix.mp3")
        final_mix.export(output_path, format="mp3")

        bot.send_audio(message.chat.id, open(output_path, "rb"))

    except Exception as e:
        bot.reply_to(message, f"❌ Hata:\n{e}")

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
    return "Bot çalışıyor"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    bot.set_webhook(url=f"https://zordomusic.onrender.com/{TOKEN}")
    app.run(host="0.0.0.0", port=port)
