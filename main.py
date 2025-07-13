# -*- coding: utf-8 -*-
"""
NDVI Monitoring & Alert System – Version 2.0 (July 2025)
========================================================
Improved KPIs + Flask route for /test + 20 top corn counties
"""
import os
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from flask import Flask, jsonify

app = Flask(__name__)

# 🔐 Environment Variables
CLIENT_ID = os.environ.get("SENTINELHUB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SENTINELHUB_CLIENT_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 📍 Top 20 corn-producing counties with weights (estimates)
counties = [
    {"name": "McLean, IL", "lat": 40.48, "lon": -88.99, "weight": 0.062},
    {"name": "Iroquois, IL", "lat": 40.74, "lon": -87.83, "weight": 0.051},
    {"name": "Livingston, IL", "lat": 40.89, "lon": -88.63, "weight": 0.050},
    {"name": "Champaign, IL", "lat": 40.13, "lon": -88.20, "weight": 0.049},
    {"name": "Story, IA", "lat": 42.04, "lon": -93.46, "weight": 0.045},
    {"name": "Woodbury, IA", "lat": 42.38, "lon": -96.05, "weight": 0.044},
    {"name": "Lancaster, NE", "lat": 40.78, "lon": -96.69, "weight": 0.042},
    {"name": "Polk, IA", "lat": 41.60, "lon": -93.61, "weight": 0.041},
    {"name": "Marshall, IA", "lat": 42.03, "lon": -92.91, "weight": 0.040},
    {"name": "Boone, NE", "lat": 41.70, "lon": -98.00, "weight": 0.038},
    {"name": "Ford, IL", "lat": 40.57, "lon": -88.23, "weight": 0.037},
    {"name": "DeKalb, IL", "lat": 41.89, "lon": -88.76, "weight": 0.036},
    {"name": "Adams, IL", "lat": 39.99, "lon": -91.19, "weight": 0.035},
    {"name": "Hancock, IL", "lat": 40.40, "lon": -91.16, "weight": 0.034},
    {"name": "Plymouth, IA", "lat": 42.74, "lon": -96.22, "weight": 0.033},
    {"name": "Cass, NE", "lat": 40.91, "lon": -96.15, "weight": 0.032},
    {"name": "Otoe, NE", "lat": 40.68, "lon": -96.13, "weight": 0.031},
    {"name": "Washington, IA", "lat": 41.34, "lon": -91.69, "weight": 0.030},
    {"name": "Tama, IA", "lat": 42.08, "lon": -92.58, "weight": 0.029},
    {"name": "Benton, IA", "lat": 42.11, "lon": -91.86, "weight": 0.028},
]

# ➕ Production tier by weight (to label big/medium/small producers)
for county in counties:
    if county["weight"] >= 0.05:
        county["tier"] = "🟢 Gros producteur"
    elif county["weight"] >= 0.035:
        county["tier"] = "🟡 Producteur moyen"
    else:
        county["tier"] = "🔴 Petit producteur"

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

def simulate_ndvi(lat, lon, date):
    np.random.seed(int(datetime.strptime(date, "%Y-%m-%d").timestamp()) + int(lat*1000))
    return round(np.random.uniform(0.2, 0.85), 2)

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, json=payload)

def determine_stage(date):
    doy = date.timetuple().tm_yday
    if doy < 130:
        return "emergence", 0.3
    elif doy < 160:
        return "V8-V12", 0.55
    else:
        return "pre-silking", 0.7

def check_ndvi_drop():
    token = get_access_token()
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    seven_days_ago = today - timedelta(days=7)

    weighted_index = 0
    total_weight = 0

    for county in counties:
        name = county["name"]
        lat, lon = county["lat"], county["lon"]
        weight = county["weight"]
        tier = county["tier"]

        ndvi_today = simulate_ndvi(lat, lon, today.isoformat())
        ndvi_yest = simulate_ndvi(lat, lon, yesterday.isoformat())
        ndvi_week = simulate_ndvi(lat, lon, seven_days_ago.isoformat())

        delta_1d = ndvi_today - ndvi_yest
        delta_7d = ndvi_today - ndvi_week

        stage, threshold = determine_stage(today)

        z = (ndvi_today - 0.6) / 0.15
        percentile = int(np.clip(100 * (1 + z) / 2, 0, 100))

        weighted_index += z * weight
        total_weight += weight

        if ndvi_today < threshold and (z <= -1.5 or delta_7d < -0.1):
            msg = f"🚨 Alerte NDVI - {name} 🚨\n"
            msg += f"{tier}\n"
            msg += f"Stade : {stage} | Seuil : {threshold}\n"
            msg += f"NDVI actuel : {ndvi_today}\n"
            msg += f"Δ sur 7j : {delta_7d:.2f}\nZ-score : {z:.2f}\nPercentile : {percentile}%"
            send_telegram_alert(msg)
            print(msg)

    stress_index = weighted_index / total_weight if total_weight else 0
    send_telegram_alert(f"🌽 Corn-Belt Stress Index : {stress_index:.2f}")

@app.route("/")
def home():
    return "✅ NDVI Alert Bot is running (v2.0)"

@app.route("/test")
def test_alert():
    send_telegram_alert("✅ TEST : Ceci est une alerte Telegram NDVI (v2.0).")
    return jsonify({"message": "Alerte test envoyée avec succès"})

if __name__ == "__main__":
    check_ndvi_drop()
    app.run(host="0.0.0.0", port=10000)
