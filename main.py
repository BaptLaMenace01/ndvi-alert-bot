# -*- coding: utf-8 -*-
"""
NDVI Monitoring & Alert System – Version 2.0 (July 2025)
========================================================
Improved KPIs + Telegram Alerts + Google Sheets Logging + 20 Top Corn Counties
"""
import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, jsonify

app = Flask(__name__)

# 🔐 Environment Variables
CLIENT_ID = os.environ.get("SENTINELHUB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SENTINELHUB_CLIENT_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SHEET = os.environ.get("GOOGLE_SHEETS_WEBHOOK")

# 📍 Top 20 corn-producing counties with weights
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

# ➕ Tier by weight
for c in counties:
    if c["weight"] >= 0.05:
        c["tier"] = "🟢 Gros producteur"
    elif c["weight"] >= 0.035:
        c["tier"] = "🟡 Producteur moyen"
    else:
        c["tier"] = "🔴 Petit producteur"

def get_access_token():
    return "fake-token"

def simulate_ndvi(lat, lon, date):
    np.random.seed(int(datetime.strptime(date, "%Y-%m-%d").timestamp()) + int(lat*1000))
    return round(np.random.uniform(0.2, 0.85), 2)

def send_telegram_alert(msg, image_path=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

    if image_path and os.path.exists(image_path):
        photo_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(image_path, 'rb') as photo:
            requests.post(photo_url, files={"photo": photo}, data={"chat_id": TELEGRAM_CHAT_ID})
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def send_to_google_sheets(entry):
    try:
        requests.post(WEBHOOK_SHEET, json=entry)
    except:
        print("❌ Erreur webhook Google Sheets")

def determine_stage(date):
    doy = date.timetuple().tm_yday
    if doy < 130:
        return "emergence", 0.3
    elif doy < 160:
        return "V8-V12", 0.55
    else:
        return "pre-silking", 0.7

def check_ndvi_drop():
    today = datetime.utcnow().date()
    doy = today.timetuple().tm_yday
    if doy < 120 or doy > 260:
        print(f"⏸️ Période hors pousse (DOY {doy}). Aucune analyse NDVI lancée.")
        return

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

        alert = ndvi_today < threshold and (z <= -1.5 or delta_7d < -0.1)
                if alert:
            # Générer graphique NDVI simple
            import matplotlib.pyplot as plt
            dates = [seven_days_ago, yesterday, today]
            values = [ndvi_week, ndvi_yest, ndvi_today]
            plt.figure()
            plt.plot(dates, values, marker='o')
            plt.title(f"NDVI – {name}")
            plt.ylabel("NDVI")
            plt.grid(True)
            image_path = f"ndvi_{name.replace(',', '').replace(' ', '_')}.png"
            plt.savefig(image_path)
            plt.close()
            msg = f"🚨 Alerte NDVI détectée à {name} 🚨\n"
            msg += f"{tier} | Stade : {stage} (seuil critique : {threshold})\n"
            msg += f"📉 NDVI actuel : {ndvi_today} ➝ {'SOUS seuil' if ndvi_today < threshold else 'OK'}\n"
            msg += f"↘️ Variation sur 7 jours : {delta_7d:.2f} ➝ {'Chute rapide' if delta_7d < -0.1 else 'Variation normale'}\n"
            msg += f"📊 Z-score : {z:.2f} ➝ {'Stress sévère' if z <= -2 else 'Stress modéré' if z <= -1.5 else 'Rien à signaler'}\n"
            msg += f"📈 Percentile : {percentile}% (vs. climatologie)"
            send_telegram_alert(msg, image_path=image_path)
            print(msg)

        send_to_google_sheets({
            "county": name,
            "ndvi": ndvi_today,
            "delta_7d": round(delta_7d, 2),
            "z": round(z, 2),
            "percentile": percentile,
            "stage": stage,
            "threshold": threshold,
            "tier": tier
        })

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
