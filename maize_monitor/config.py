
import os

# 📁 Étape 1 : Configuration initiale
config = {
    "telegram_token": os.getenv("TELEGRAM_TOKEN"),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
    "sentinelhub_instance_id": os.getenv("SENTINELHUB_INSTANCE_ID"),
    "threshold_drop_pct": -15,
    "threshold_zscore": -1.0,
    "min_days_between_signals": 7,
    "zones": [
        {"name": "McLean, IL", "lat": 40.45, "lon": -88.95, "polygon_id": "zone_mclean", "weight": 0.12},
        {"name": "Story, IA", "lat": 42.04, "lon": -93.45, "polygon_id": "zone_story", "weight": 0.10},
        {"name": "Lancaster, NE", "lat": 40.78, "lon": -96.70, "polygon_id": "zone_lancaster", "weight": 0.08},
        {"name": "Champaign, IL", "lat": 40.14, "lon": -88.19, "polygon_id": "zone_champaign", "weight": 0.06},
        {"name": "Woodbury, IA", "lat": 42.38, "lon": -96.03, "polygon_id": "zone_woodbury", "weight": 0.05},
        {"name": "Polk, IA", "lat": 41.60, "lon": -93.61, "polygon_id": "zone_polk", "weight": 0.05},
        {"name": "Ford, IL", "lat": 40.60, "lon": -88.00, "polygon_id": "zone_ford", "weight": 0.04},
        {"name": "Boone, NE", "lat": 41.69, "lon": -98.06, "polygon_id": "zone_boone", "weight": 0.03}
    ]
}

# 📁 Étape 2 : Structure des fichiers attendus
# - ndvi_history.csv : colonnes ['date', 'zone', 'ndvi', 'anomaly', 'zscore']
# - cornhistory.csv : cours de l'ETF CORN (optionnel pour le backtest)
# - charts/ : dossier pour sauvegarder les PNG générés

# === Étape 10 : Routine quotidienne principale ===
def daily_check():
    import datetime
    from utils import load_ndvi_history, compute_anomaly, append_ndvi_record, should_trigger_alert, plot_ndvi, get_ndvi
    from telegram import send_telegram_message

    today = datetime.datetime.today().strftime("%Y-%m-%d")
    history_file = "ndvi_history.csv"
    global_alert_score = 0

    for zone in config["zones"]:
        zone_name = zone["name"]
        weight = zone.get("weight", 0)
        chart_file = f"charts/{zone_name.replace(', ', '_')}_{today}.png"

        print(f"🔍 Vérification NDVI pour {zone_name}...")
        history = load_ndvi_history(history_file, zone_name)
        ndvi = get_ndvi(zone, today, config["sentinelhub_instance_id"])

        if ndvi:
            anomaly, zscore = compute_anomaly(history, ndvi)
            append_ndvi_record(history_file, today, zone_name, ndvi, anomaly, zscore)

            # 💡 Alarme individuelle immédiate si la zone est critique
            if should_trigger_alert(zone_name, anomaly, zscore, history_file):
                plot_ndvi(zone_name, history + [{
                    'date': today,
                    'ndvi': ndvi,
                    'anomaly': anomaly,
                    'zscore': zscore
                }], chart_file)
                msg = (
                    f"⚠️ Chute NDVI détectée sur {zone_name} le {today}.\n"
                    f"NDVI: {ndvi:.3f} | Anomalie: {anomaly}% | z-score: {zscore} | Poids: {weight*100:.1f}%"
                )
                if weight >= 0.1:
                    msg += "\n⭐ Zone très importante"
                elif weight >= 0.05:
                    msg += "\n⚡ Zone modérément importante"
                else:
                    msg += "\n📉 Zone secondaire"
                send_telegram_message(msg, image_path=chart_file)

            # 🧲 Ajout pondéré à l'alerte globale
            if anomaly <= config["threshold_drop_pct"] and zscore <= config["threshold_zscore"]:
                global_alert_score += weight

        else:
            print(f"❌ NDVI non disponible pour {zone_name} le {today}")

    # ✅ Déclenchement alerte globale si >10% du poids total est en alerte
    if global_alert_score >= 0.10:
        msg = f"🚨 ALERTE GLOBALE NDVI : {global_alert_score*100:.1f}% de la production est en stress végétatif"
        send_telegram_message(msg)

# 🔁 Appel direct pour test
if __name__ == "__main__":
    daily_check()
