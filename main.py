import os
import requests
from flask import Flask, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# 🔐 Variables d'environnement
CLIENT_ID = os.environ.get("SENTINELHUB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SENTINELHUB_CLIENT_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 📍 Comtés à surveiller
counties = [
    {"name": "McLean, IL", "lat": 40.48, "lon": -88.99},
    {"name": "Story, IA", "lat": 42.04, "lon": -93.46},
    {"name": "Lancaster, NE", "lat": 40.78, "lon": -96.69},
    {"name": "Champaign, IL", "lat": 40.13, "lon": -88.20},
    {"name": "Woodbury, IA", "lat": 42.38, "lon": -96.05},
    {"name": "Polk, IA", "lat": 41.60, "lon": -93.61},
    {"name": "Ford, IL", "lat": 40.57, "lon": -88.23},
    {"name": "Boone, NE", "lat": 41.70, "lon": -98.00},
]

def get_access_token():
    response = requests.post(
        "https://services.sentinel-hub.com/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
    )
    return response.json().get("access_token")

def get_ndvi(lat, lon, date, token):
    url = "https://services.sentinel-hub.com/api/v1/process"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "input": {
            "bounds": {
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                },
                "bbox": [lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01]
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{date}T00:00:00Z",
                        "to": f"{date}T23:59:59Z"
                    }
                }
            }]
        },
        "output": {
            "width": 50,
            "height": 50,
            "responses": [{
                "identifier": "default",
                "format": {"type": "image/tiff"}
            }]
        },
        "evalscript": """
        //VERSION=3
        function setup() {
          return {
            input: ["B08", "B04"],
            output: { bands: 1 }
          };
        }
        function evaluatePixel(sample) {
          let ndvi = index(sample.B08, sample.B04);
          return [ndvi];
        }
        """
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.ok:
        # Simulons un NDVI moyen (car l’image réelle est un GeoTIFF)
        import random
        return round(random.uniform(0.2, 0.8), 2)
    return None

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    requests.post(url, json=payload)

def check_ndvi_drop():
    token = get_access_token()
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    for county in counties:
        lat, lon = county["lat"], county["lon"]
        name = county["name"]

        ndvi_today = get_ndvi(lat, lon, today.isoformat(), token)
        ndvi_yesterday = get_ndvi(lat, lon, yesterday.isoformat(), token)

        print(f"📍 {name}: NDVI {today} = {ndvi_today}, {yesterday} = {ndvi_yesterday}")

        if ndvi_today and ndvi_yesterday:
            drop = (ndvi_yesterday - ndvi_today) / ndvi_yesterday
            if drop > 0.2:
                message = f"⚠️ Forte baisse de NDVI à {name} !\nHier: {ndvi_yesterday}, Aujourd'hui: {ndvi_today}"
                print(message)
                send_telegram_alert(message)

@app.route("/")
def home():
    return "✅ NDVI Alert Bot is running"

@app.route("/test")
def test_alert():
    send_telegram_alert("✅ TEST : Ceci est une alerte Telegram NDVI.")
    return jsonify({"message": "Alerte Telegram envoyée avec succès"})

if __name__ == "__main__":
    check_ndvi_drop()
    app.run(host="0.0.0.0", port=10000)
