import requests
import os

def send_telegram_message(message, image_path=None):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("❌ Token ou chat_id manquant")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    requests.post(url, data=data)

    if image_path and os.path.exists(image_path):
        photo_url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(image_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id}
            requests.post(photo_url, data=data, files=files)
