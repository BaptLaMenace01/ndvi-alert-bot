from dotenv import load_dotenv
load_dotenv()

import datetime
from flask import Flask, send_file
from utils import (
    load_ndvi_history,
    compute_anomaly,
    append_ndvi_record,
    should_trigger_alert,
    plot_ndvi,
    get_ndvi
)
from telegram import send_telegram_message
from config import config

app = Flask(__name__)

def daily_check():
    today = datetime.datetime.today().strftime("%Y-%m-%d")
    history_file = "ndvi_history.csv"
    for zone in config["zones"]:
        zone_name = zone["name"]
        chart_file = f"charts/{zone_name.replace(', ', '_')}_{today}.png"

        print(f"🔍 Vérification NDVI pour {zone_name}...")
        history = load_ndvi_history(history_file, zone_name)
        ndvi = get_ndvi(zone, today, config["sentinelhub_instance_id"])

        if ndvi:
            anomaly, zscore = compute_anomaly(history, ndvi)
            append_ndvi_record(history_file, today, zone_name, ndvi, anomaly, zscore)

            if should_trigger_alert(zone_name, anomaly, zscore, history_file):
                plot_ndvi(zone_name, history + [ndvi], chart_file)
                msg = (
                    f"⚠️ Chute NDVI détectée sur {zone_name} le {today}.\n"
                    f"NDVI: {ndvi:.3f} | Anomalie: {anomaly}% | z-score: {zscore}"
                )
                send_telegram_message(msg, image_path=chart_file)
        else:
            print(f"❌ NDVI non disponible pour {zone_name} le {today}")

@app.route("/")
def run_daily():
    daily_check()
    return "✅ Exécution terminée"

@app.route("/test")
def test_telegram():
    send_telegram_message("✅ Test alerte NDVI envoyé.")
    return "Message test envoyé."

@app.route("/export")
def export_csv():
    return send_file("ndvi_history.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
