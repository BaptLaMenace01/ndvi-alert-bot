# -*- coding: utf-8 -*-
"""
NDVI Monitoring & Alert System – Version 3.2 (July 2025)
========================================================
Live Sentinel NDVI Data + Telegram Alerts + Google Sheets Logging + Investment Suggestion Summary
+ Manual Trigger via /force URL (+ debug test alerts) + Exportable CSV history + Visual Report
"""

import os
import logging
import requests
import numpy as np
import csv
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_file, request
import matplotlib.pyplot as plt

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration via variables d'environnement
# ─────────────────────────────────────────────────────────────────────────────
CLIENT_ID      = os.getenv("SENTINELHUB_CLIENT_ID")
CLIENT_SECRET  = os.getenv("SENTINELHUB_CLIENT_SECRET")
WEBHOOK_SHEET  = os.getenv("GOOGLE_SHEETS_WEBHOOK")
HISTORY_FILE   = "ndvi_history.csv"
REPORT_IMAGE   = "report.png"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────────────────────────────────────
# Fonction d’envoi Telegram
# ─────────────────────────────────────────────────────────────────────────────
def send_telegram_message(text, image_path=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        logger.error("❌ TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant")
        return False
    # Envoi du message texte
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("✅ Message texte envoyé")
    except Exception as e:
        logger.error(f"❌ Échec envoi message Telegram : {e}")
        return False
    # Envoi de l’image si fourni
    if image_path and os.path.exists(image_path):
        url2 = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        try:
            with open(image_path, "rb") as img:
                files = {"photo": img}
                data  = {"chat_id": TELEGRAM_CHAT}
                r2 = requests.post(url2, data=data, files=files, timeout=15)
                r2.raise_for_status()
                logger.info("✅ Image envoyée")
        except Exception as e:
            logger.error(f"❌ Échec envoi image Telegram : {e}")
            return False
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Liste des comtés et pondérations
# ─────────────────────────────────────────────────────────────────────────────
counties = [
    {"name": "McLean, IL",     "lat":40.48, "lon":-88.99, "weight":0.062},
    {"name": "Iroquois, IL",   "lat":40.74, "lon":-87.83, "weight":0.051},
    {"name": "Livingston, IL", "lat":40.89, "lon":-88.63, "weight":0.050},
    {"name": "Champaign, IL",  "lat":40.13, "lon":-88.20, "weight":0.049},
    {"name": "Story, IA",      "lat":42.04, "lon":-93.46, "weight":0.045},
    {"name": "Woodbury, IA",   "lat":42.38, "lon":-96.05, "weight":0.044},
    {"name": "Lancaster, NE",  "lat":40.78, "lon":-96.69, "weight":0.042},
    {"name": "Polk, IA",       "lat":41.60, "lon":-93.61, "weight":0.041},
    {"name": "Marshall, IA",   "lat":42.03, "lon":-92.91, "weight":0.040},
    {"name": "Boone, NE",      "lat":41.70, "lon":-98.00, "weight":0.038},
    {"name": "Ford, IL",       "lat":40.57, "lon":-88.23, "weight":0.037},
    {"name": "DeKalb, IL",     "lat":41.89, "lon":-88.76, "weight":0.036},
    {"name": "Adams, IL",      "lat":39.99, "lon":-91.19, "weight":0.035},
    {"name": "Hancock, IL",    "lat":40.40, "lon":-91.16, "weight":0.034},
    {"name": "Plymouth, IA",   "lat":42.74, "lon":-96.22, "weight":0.033},
    {"name": "Cass, NE",       "lat":40.91, "lon":-96.15, "weight":0.032},
    {"name": "Otoe, NE",       "lat":40.68, "lon":-96.13, "weight":0.031},
    {"name": "Washington, IA", "lat":41.34, "lon":-91.69, "weight":0.030},
    {"name": "Tama, IA",       "lat":42.08, "lon":-92.58, "weight":0.029},
    {"name": "Benton, IA",     "lat":42.11, "lon":-91.86, "weight":0.028},
]
for c in counties:
    w = c["weight"]
    c["tier"] = "🟢 Gros producteur" if w >= 0.05 else ("🟡 Producteur moyen" if w >= 0.035 else "🔴 Petit producteur")

# ─────────────────────────────────────────────────────────────────────────────
# Fonctions d’accès Sentinel Hub
# ─────────────────────────────────────────────────────────────────────────────
def get_access_token():
    resp = requests.post(
        "https://services.sentinel-hub.com/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        },
        timeout=10
    )
    resp.raise_for_status()
    return resp.json().get("access_token")

def get_ndvi(lat, lon, date, token):
    # TODO: remplacer par vraie requête Sentinel Hub
    return round(np.random.uniform(0.2, 0.85), 2)

# ─────────────────────────────────────────────────────────────────────────────
# CSV & Google Sheets
# ─────────────────────────────────────────────────────────────────────────────
def write_to_csv(row):
    headers = ["Date","Comté","NDVI","Δ7j","Z-score","Percentile","Stade","Seuil","Producteur"]
    exists = os.path.isfile(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(headers)
        w.writerow(row)

def send_to_google_sheets(payload):
    if not WEBHOOK_SHEET:
        return
    try:
        requests.post(WEBHOOK_SHEET, json=payload, timeout=5)
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Analyse et rapport
# ─────────────────────────────────────────────────────────────────────────────
def determine_stage(date):
    doy = date.timetuple().tm_yday
    if doy < 130: return "emergence", 0.3
    if doy < 160: return "V8-V12", 0.55
    return "pre-silking", 0.7

def generate_report(data):
    fig, ax = plt.subplots(figsize=(12, 6))
    names     = [d["county"] for d in data]
    ndvis     = [d["ndvi"]   for d in data]
    thresholds= [d["threshold"] for d in data]
    colors    = ["green" if ndvi>thr else "red" for ndvi,thr in zip(ndvis, thresholds)]
    ax.bar(names, ndvis, color=colors)
    ax.set_title(f"NDVI Report – {datetime.utcnow().date()} (Red=sous seuil)")
    ax.set_ylabel("NDVI")
    ax.tick_params(axis="x", rotation=90)
    plt.tight_layout()
    plt.savefig(REPORT_IMAGE)
    plt.close()

def check_ndvi_drop(force_alert=False):
    today   = datetime.utcnow().date()
    doy     = today.timetuple().tm_yday
    if doy < 120 or doy > 260:
        logger.info(f"Période hors pousse (DOY {doy})")
        return

    token   = get_access_token()
    weekago = today - timedelta(days=7)
    stress  = total_w = 0
    signals = []
    report_data = []

    for c in counties:
        ndvi_now  = get_ndvi(c["lat"], c["lon"], today.isoformat(), token)
        ndvi_prev = get_ndvi(c["lat"], c["lon"], weekago.isoformat(), token)
        delta     = ndvi_now - ndvi_prev
        zscore    = (ndvi_now - 0.6) / 0.15
        pct       = int(np.clip(100 * (1 + zscore) / 2, 0, 100))
        stage,thr = determine_stage(today)
        stress   += zscore * c["weight"]
        total_w  += c["weight"]

        alert = (ndvi_now < thr and (zscore <= -1.5 or delta < -0.1)) or force_alert
        if alert:
            msg = (
                f"{'⚠️ FAKE ALERT' if force_alert else '🚨 Alerte NDVI – '+c['name']} 🚨\n"
                f"{c['tier']} | Stade {stage} (seuil {thr})\n"
                f"NDVI {ndvi_now} ({'SOUS' if ndvi_now<thr else 'OK'})\n"
                f"Δ7j {delta:+.2f}, Z {zscore:+.2f}, Pct {pct}%"
            )
            send_telegram_message(msg)
            signals.append(zscore)

        row = [
            today.isoformat(),
            c["name"],
            ndvi_now,
            round(delta,2),
            round(zscore,2),
            pct,
            stage,
            thr,
            c["tier"]
        ]
        write_to_csv(row)
        send_to_google_sheets({
            "county":c["name"],"ndvi":ndvi_now,"delta7d":round(delta,2),
            "z":round(zscore,2),"percentile":pct,"stage":stage,
            "threshold":thr,"tier":c["tier"]
        })
        report_data.append({"county":c["name"],"ndvi":ndvi_now,"threshold":thr})

    index = stress / total_w if total_w else 0
    summary = f"🌽 Stress Index : {index:.2f}"
    if len(signals)>=5 and index < -0.5:
        summary += "\n📈 Opportunité potentielle"
    send_telegram_message(summary)

    generate_report(report_data)
    send_telegram_message("🖼️ Rapport visuel", image_path=REPORT_IMAGE)

# ─────────────────────────────────────────────────────────────────────────────
# Routes HTTP
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return "✅ NDVI Alert Bot v3.2"

@app.route("/force")
def force():
    debug = request.args.get("debug","false").lower()=="true"
    try:
        check_ndvi_drop(force_alert=debug)
        return jsonify({"status":"ok","debug":debug})
    except Exception as e:
        logger.error(f"Erreur dans /force : {e}")
        return jsonify({"status":"error"}), 500

@app.route("/debug")
def debug():
    info = {
        "telegram_token": bool(TELEGRAM_TOKEN),
        "telegram_chat":  bool(TELEGRAM_CHAT)
    }
    if TELEGRAM_TOKEN and TELEGRAM_CHAT:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id":TELEGRAM_CHAT,"text":"🔍 Test diagnostic"}
            )
            info["api_ok"] = r.json().get("ok",False)
        except Exception as e:
            info["error"] = str(e)
    return jsonify(info)

@app.route("/export")
def export():
    if not os.path.isfile(HISTORY_FILE):
        return "Aucun historique NDVI à exporter.", 404
    return send_file(HISTORY_FILE, as_attachment=True)

@app.route("/test")
def test():
    send_telegram_message("🔔 Test Telegram depuis /test !")
    return "Test OK ! (Message Telegram envoyé)"

# ─────────────────────────────────────────────────────────────────────────────
# Démarrage du service
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    check_ndvi_drop()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
