# -*- coding: utf-8 -*-
"""
NDVI Monitoring & Alert System – Version 3.2 (July 2025)
========================================================
Live Sentinel NDVI Data + Telegram Alerts + Google Sheets Logging + Investment Suggestion Summary
+ Manual Trigger via /force URL (+ debug test alerts) + Exportable CSV history + Visual Report
"""
import os
import requests
import numpy as np
import csv
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_file, request
import matplotlib.pyplot as plt
from telegram import send_telegram_message

app = Flask(__name__)

CLIENT_ID    = os.environ.get("SENTINELHUB_CLIENT_ID")
CLIENT_SECRET= os.environ.get("SENTINELHUB_CLIENT_SECRET")
WEBHOOK_SHEET= os.environ.get("GOOGLE_SHEETS_WEBHOOK")
HISTORY_FILE = "ndvi_history.csv"
REPORT_IMAGE = "report.png"

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
    # Simulation : remplace par ta vraie extraction Sentinel Hub
    return round(np.random.uniform(0.2, 0.85), 2)

def send_to_google_sheets(entry):
    try:
        requests.post(WEBHOOK_SHEET, json=entry, timeout=5)
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

def generate_daily_report(data):
    fig, ax = plt.subplots(figsize=(12, 6))
    names = [d["county"] for d in data]
    ndvi = [d["ndvi"] for d in data]
    colors = ["green" if v > d["threshold"] else "red" for v, d in zip(ndvi, data)]
    ax.bar(names, ndvi, color=colors)
    ax.set_title(f"NDVI Report - {datetime.utcnow().date()} (Red = sous seuil)")
    ax.set_ylabel("NDVI")
    ax.tick_params(axis='x', rotation=90)
    plt.tight_layout()
    plt.savefig(REPORT_IMAGE)
    plt.close()
    return REPORT_IMAGE

def check_ndvi_drop(force_alert=False):
    today = datetime.utcnow().date()
    doy   = today.timetuple().tm_yday
    if doy < 120 or doy > 260:
        print(f"⏸️ Période hors pousse (DOY {doy}).")
        return

    token    = get_access_token()
    week_ago = today - timedelta(days=7)
    weighted_index = total_weight = 0
    investment_signals = []
    report_data = []

    for c in counties:
        ndvi_today = get_ndvi(c["lat"], c["lon"], today.isoformat(), token)
        ndvi_week  = get_ndvi(c["lat"], c["lon"], week_ago.isoformat(), token)
        if ndvi_today is None or ndvi_week is None:
            continue

        delta_7d = ndvi_today - ndvi_week
        z = (ndvi_today - 0.6) / 0.15
        pct = int(np.clip(100 * (1 + z) / 2, 0, 100))
        stage, threshold = determine_stage(today)
        weighted_index += z * c["weight"]
        total_weight   += c["weight"]

        alert = ndvi_today < threshold and (z <= -1.5 or delta_7d < -0.1)
        if alert or force_alert:
            msg = (
                f"{'⚠️ FAKE ALERT TEST' if force_alert else '🚨 Alerte NDVI à ' + c['name']} 🚨\n"
                f"{c['tier']} | Stade : {stage} (seuil : {threshold})\n"
                f"📉 NDVI actuel : {ndvi_today} → {'SOUS seuil' if ndvi_today < threshold else 'OK'}\n"
                f"↘️ Variation sur 7j : {delta_7d:+.2f}\n"
                f"📊 Z-score : {z:+.2f}\n"
                f"📈 Percentile : {pct}%\n"
                f"💡 Reco : {'📉 Baisse possible → Attendre' if z < -2 else '📈 Stress modéré → Surveiller'}"
            )
            send_telegram_message(msg)
            investment_signals.append(z)

        entry = [
            today.isoformat(), c["name"], ndvi_today, round(delta_7d, 2),
            round(z, 2), pct, stage, threshold, c["tier"]
        ]
        write_to_csv(entry)
        send_to_google_sheets({
            "county": c["name"], "ndvi": ndvi_today, "delta_7d": round(delta_7d, 2),
            "z": round(z, 2), "percentile": pct, "stage": stage,
            "threshold": threshold, "tier": c["tier"]
        })
        report_data.append({
            "county": c["name"], "ndvi": ndvi_today, "threshold": threshold
        })

    stress_index = (weighted_index / total_weight) if total_weight else 0
    summary = f"🌽 Corn-Belt Stress Index : {stress_index:.2f}"
    if len(investment_signals) >= 5 and stress_index < -0.5:
        summary += "\n📈 Signal d’opportunité potentielle (stress agrégé élevé)"
    send_telegram_message(summary)

    path = generate_daily_report(report_data)
    send_telegram_message("🖼️ Rapport visuel du jour", image_path=path)

@app.route("/")
def home():
    return "✅ NDVI Alert Bot (v3.2)"

@app.route("/test")
def test():
    result = send_telegram_message("✅ TEST – NDVI Bot opérationnel ✅")
    return jsonify({
        "status": "ok" if result else "error",
        "message": "Message Telegram de test envoyé." if result else "Échec envoi."
    }), (200 if result else 500)

@app.route("/debug")
def debug():
    token   = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    info = {
        "token_present": bool(token),
        "chat_id_present": bool(chat_id),
        "token_preview": token[:10] + "…" if token else None
    }
    if token and chat_id:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "🔍 Test diag NDVI"}
            )
            info.update({"api_status": resp.status_code, "api_ok": resp.json().get("ok")})
        except Exception as e:
            info["error"] = str(e)
    return jsonify(info)

@app.route("/force")
def force():
    debug = request.args.get("debug", "false").lower() == "true"
    check_ndvi_drop(force_alert=debug)
    return jsonify({"status": "ok", "debug": debug})

@app.route("/export")
def export():
    return send_file(HISTORY_FILE, as_attachment=True)

if __name__ == "__main__":
    # Exécution initiale
    check_ndvi_drop()
    # Démarrage sur le port fourni par Render (variable d'env PORT)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
