import os
import requests
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
        print("Telegram status:", r.status_code, r.text)
    except Exception as e:
        print("❌ Telegram error:", e)

@app.route("/")
def home():
    return "✅ Bot NDVI test basique OK"

@app.route("/test")
def test():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    send_telegram_alert(f"🛰️ Test NDVI Bot lancé à {now} UTC")
    return jsonify({"status": "ok", "message": "Message Telegram envoyé."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
