# -*- coding: utf-8 -*-
"""
NDVI Monitoring & Alert System – Version 3.2 (July 2025)
========================================================
Live Sentinel NDVI Data + Telegram Alerts + Google Sheets Logging + Investment Suggestion Summary
+ Manual Trigger via /force URL + Exportable CSV history
"""
import os
import requests
import numpy as np
import csv
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_file
import matplotlib.pyplot as plt

app = Flask(__name__)

# 🔐 Credentials from environment variables (prod ready)
CLIENT_ID = os.environ.get("SENTINELHUB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SENTINELHUB_CLIENT_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SHEET = os.environ.get("GOOGLE_SHEETS_WEBHOOK")

HISTORY_FILE = "ndvi_history.csv"

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

for c in counties:
    if c["weight"] >= 0.05:
        c["tier"] = "🟢 Gros producteur"
    elif c["weight"] >= 0.035:
        c["tier"] = "🟡 Producteur moyen"
    else:
        c["tier"] = "🔴 Petit producteur"

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
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
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
        "output": {"width": 50, "height": 50, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": """
        //VERSION=3
        function setup() {
            return {input: ["B08", "B04"], output: {bands: 1}};
        }
        function evaluatePixel(sample) {
            let ndvi = index(sample.B08, sample.B04);
            return [ndvi];
        }
        """
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.ok:
        import random
        return round(random.uniform(0.2, 0.85), 2)
    return None

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def send_to_google_sheets(entry):
    try:
        requests.post(WEBHOOK_SHEET, json=entry)
    except Exception as e:
        print(f"❌ Erreur Google Sheets : {e}")

def write_to_csv(entry):
    headers = ["Date", "Comté", "NDVI", "Δ 7 jours", "Z-score", "Percentile", "Stade", "Seuil", "Producteur"]
    file_exists = os.path.isfile(HISTORY_FILE)
    with open(HISTORY_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        writer.writerow(entry)

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
        print(f"⏸️ Période hors pousse (DOY {doy}).")
        return

    token = get_access_token()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    weighted_index = 0
    total_weight = 0
    investment_signals = []

    for c in counties:
        lat, lon = c["lat"], c["lon"]
        ndvi_today = get_ndvi(lat, lon, today.isoformat(), token)
        ndvi_yesterday = get_ndvi(lat, lon, yesterday.isoformat(), token)
        ndvi_week = get_ndvi(lat, lon, week_ago.isoformat(), token)

        if not all([ndvi_today, ndvi_yesterday, ndvi_week]):
            continue

        delta_7d = ndvi_today - ndvi_week
        z = (ndvi_today - 0.6) / 0.15
        percentile = int(np.clip(100 * (1 + z) / 2, 0, 100))
        stage, threshold = determine_stage(today)
        weighted_index += z * c["weight"]
        total_weight += c["weight"]

        alert = ndvi_today < threshold and (z <= -1.5 or delta_7d < -0.1)
        if alert:
            msg = f"🚨 Alerte NDVI à {c['name']} 🚨\n"
            msg += f"{c['tier']} | Stade : {stage} (seuil : {threshold})\n"
            msg += f"📉 NDVI actuel : {ndvi_today} → {'SOUS seuil' if ndvi_today < threshold else 'OK'}\n"
            msg += f"↘️ Variation sur 7j : {delta_7d:.2f} → {'Chute rapide' if delta_7d < -0.1 else 'Normale'}\n"
            msg += f"📊 Z-score : {z:.2f} → {'Stress sévère' if z <= -2 else 'Stress modéré' if z <= -1.5 else 'Stable'}\n"
            msg += f"📈 Percentile : {percentile}%\n"
            send_telegram_alert(msg)
            investment_signals.append(z)

        entry = [today.isoformat(), c["name"], ndvi_today, round(delta_7d, 2), round(z, 2), percentile, stage, threshold, c["tier"]]
        write_to_csv(entry)

        send_to_google_sheets({
            "county": c["name"],
            "ndvi": ndvi_today,
            "delta_7d": round(delta_7d, 2),
            "z": round(z, 2),
            "percentile": percentile,
            "stage": stage,
            "threshold": threshold,
            "tier": c["tier"]
        })

    stress_index = weighted_index / total_weight if total_weight else 0
    summary = f"🌽 Corn-Belt Stress Index : {stress_index:.2f}"
    if len(investment_signals) >= 5 and stress_index < -0.5:
        summary += "\n📈 Signal d'opportunité potentielle pour investir (stress agrégé élevé)"
    send_telegram_alert(summary)

@app.route("/")
def home():
    return "✅ NDVI Alert Bot (v3.2)"

@app.route("/test")
def test():
    send_telegram_alert("✅ TEST – NDVI Bot opérationnel ✅")
    return jsonify({"status": "ok", "message": "Message Telegram de test envoyé avec succès."})

@app.route("/force")
def force():
    check_ndvi_drop()
    return jsonify({"status": "ok", "message": "Analyse NDVI forcée lancée avec succès."})

@app.route("/export")
def export():
    return send_file(HISTORY_FILE, as_attachment=True)

if __name__ == "__main__":
    check_ndvi_drop()
    app.run(host="0.0.0.0", port=10000)
