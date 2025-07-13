import csv
import os
import matplotlib.pyplot as plt
from datetime import datetime
import statistics
import requests

# === 1. Charger l'historique NDVI ===
def load_ndvi_history(filename, zone_name):
    history = []
    if not os.path.exists(filename):
        return history
    with open(filename, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['zone'] == zone_name:
                history.append({
                    'date': row['date'],
                    'ndvi': float(row['ndvi']),
                    'anomaly': float(row['anomaly']),
                    'zscore': float(row['zscore'])
                })
    return history

# === 2. Calcul de l'anomalie et du z-score ===
def compute_anomaly(history, current_ndvi):
    if len(history) < 5:
        return 0, 0
    values = [entry['ndvi'] for entry in history]
    avg = statistics.mean(values)
    std = statistics.stdev(values)
    if std == 0:
        return 0, 0
    anomaly = ((current_ndvi - avg) / avg) * 100
    zscore = (current_ndvi - avg) / std
    return round(anomaly, 2), round(zscore, 2)

# === 3. Ajouter une ligne dans l'historique ===
def append_ndvi_record(filename, date, zone, ndvi, anomaly, zscore):
    new_row = {
        'date': date,
        'zone': zone,
        'ndvi': ndvi,
        'anomaly': anomaly,
        'zscore': zscore
    }
    file_exists = os.path.exists(filename)
    with open(filename, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=new_row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(new_row)

# === 4. Vérifie si une alerte doit être déclenchée ===
def should_trigger_alert(zone_name, anomaly, zscore, filename, threshold_pct=-15, threshold_z=-1.0):
    history = load_ndvi_history(filename, zone_name)
    if not history:
        return False
    last_entry = history[-1]
    last_date = datetime.strptime(last_entry['date'], "%Y-%m-%d")
    days_since = (datetime.today() - last_date).days
    return (anomaly <= threshold_pct and zscore <= threshold_z and days_since >= 7)

# === 5. Génère un graphique NDVI ===
def plot_ndvi(zone_name, history, output_file):
    dates = [entry['date'] for entry in history]
    ndvis = [entry['ndvi'] for entry in history]
    plt.figure(figsize=(8, 4))
    plt.plot(dates, ndvis, marker='o')
    plt.title(f"NDVI - {zone_name}")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_file)
    plt.close()

# === 6. Récupère la donnée NDVI via l'API Sentinel Hub ===
def get_ndvi(zone, date_str, instance_id):
    """
    Appelle l'API SentinelHub pour récupérer la valeur NDVI d'une zone carrée autour du point (lat, lon).
    """
    client_id = os.getenv("SENTINELHUB_CLIENT_ID")
    client_secret = os.getenv("SENTINELHUB_CLIENT_SECRET")

    # 🔐 Authentification OAuth2
    token_url = "https://services.sentinel-hub.com/oauth/token"
    response = requests.post(token_url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    })

    if response.status_code != 200:
        print("❌ Authentification échouée :", response.text)
        return None

    access_token = response.json().get("access_token")

    # 📦 Création du carré (2 km x 2 km env.) autour du point
    lon = zone["lon"]
    lat = zone["lat"]
    delta = 0.01  # ~1 km

    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [lon - delta, lat - delta],
            [lon - delta, lat + delta],
            [lon + delta, lat + delta],
            [lon + delta, lat - delta],
            [lon - delta, lat - delta]
        ]]
    }

    # 📡 Requête NDVI via SentinelHub Process API
    api_url = "https://services.sentinel-hub.com/api/v1/process"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "input": {
            "bounds": {
                "geometry": polygon,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                }
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{date_str}T00:00:00Z",
                        "to": f"{date_str}T23:59:59Z"
                    },
                    "maxCloudCoverage": 20
                }
            }]
        },
        "output": {
            "responses": [{"identifier": "ndvi", "format": {"type": "image/tiff"}}]
        },
        "evalscript": """
        //VERSION=3
        function setup() {
            return {
                input: ["B04", "B08"],
                output: [
                    {
                        id: "ndvi",
                        bands: 1,
                        sampleType: "FLOAT32"
                    }
                ]
            };
        }

        function evaluatePixel(sample) {
            let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
            return { ndvi: [ndvi] };
        }
        """
    }

    r = requests.post(api_url, headers=headers, json=payload)

    if r.status_code == 200:
        print(f"✅ Requête NDVI réussie pour {zone['name']}")
        # 🚧 Pour l’instant, retourne une valeur simulée
        return round(0.6 + 0.05 * (hash(zone["name"] + date_str) % 10) / 10, 3)
    else:
        print(f"❌ Erreur NDVI API: {r.status_code} - {r.text}")
        return None
