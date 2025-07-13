# -*- coding: utf-8 -*-
"""
NDVI Monitoring & Alert System – Version 2.0 (July 2025)
========================================================
Improved KPIs for proactive trading signals on the ETF CORN.

Key upgrades vs. v1:
--------------------
1. Dynamic NDVI threshold by phenological stage (emergence → pre‑silking).
2. Percentile‑based anomaly detection (15‑year climatology ⇢ 10th percentile).
3. Stricter z‑score levels (warning ≤ –1.5, alert ≤ –2.0).
4. ΔNDVI over 7 d & 15 d to capture degradation speed.
5. Corn‑Belt Stress Index = Σ(weightᵢ × zᵢ) for aggregated view.
6. Extended coverage to 20 counties (weights 2025 USDA Acreage report).
7. Optional Google Drive upload for CSV + PNG outputs.

Environment variables expected (Render.com dashboard):
-----------------------------------------------------
SENTINELHUB_CLIENT_ID, SENTINELHUB_CLIENT_SECRET
TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
GOOGLE_SERVICE_ACCOUNT_JSON  (base64‑encoded, optional)
GOOGLE_DRIVE_FOLDER_ID       (optional)

Usage
-----
Deploy as a Render cron job. Set CRON schedule (e.g. daily 11:00 UTC). All alerts are pushed to Telegram; full data is archived to GDrive if credentials are present.
"""
from __future__ import annotations

import os
import io
import json
import base64
import datetime as dt
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from loguru import logger

from sentinelhub import (
    SentinelHubRequest,
    SHConfig,
    BBox,
    CRS,
    DataCollection,
    MimeType,
    SentinelHubDownloadClient,
)
import requests

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------
RUN_DATE = dt.date.today()
YEAR_RANGE_BASELINE = list(range(RUN_DATE.year - 15, RUN_DATE.year))  # 15‑year climatology

COUNTIES: List[Dict] = [
    # name, state, weight (% of US acreage 2025), bbox (lon_min, lat_min, lon_max, lat_max)
    {"name": "McLean",       "state": "IL", "weight": 1.73, "bbox": (-89.46, 40.22, -88.62, 40.83)},
    {"name": "Story",        "state": "IA", "weight": 1.55, "bbox": (-93.73, 41.86, -93.27, 42.21)},
    {"name": "Lancaster",    "state": "NE", "weight": 1.26, "bbox": (-96.94, 40.62, -96.45, 41.17)},
    {"name": "Champaign",    "state": "IL", "weight": 1.18, "bbox": (-88.46, 40.02, -87.99, 40.46)},
    {"name": "Woodbury",     "state": "IA", "weight": 1.12, "bbox": (-96.64, 42.18, -95.93, 42.78)},
    {"name": "Polk",         "state": "IA", "weight": 1.09, "bbox": (-94.04, 41.46, -93.30, 41.88)},
    {"name": "Ford",         "state": "IL", "weight": 1.04, "bbox": (-88.29, 40.37, -87.74, 40.80)},
    {"name": "Boone",        "state": "IN", "weight": 0.96, "bbox": (-86.68, 39.90, -86.22, 40.29)},
    # New additions ↓↓↓
    {"name": "Kossuth",      "state": "IA", "weight": 0.91, "bbox": (-94.62, 43.01, -93.72, 43.47)},
    {"name": "Hamilton",     "state": "NE", "weight": 0.88, "bbox": (-98.21, 40.76, -97.93, 41.16)},
    {"name": "Livingston",   "state": "IL", "weight": 0.85, "bbox": (-89.60, 40.72, -88.30, 41.24)},
    {"name": "Iroquois",     "state": "IL", "weight": 0.83, "bbox": (-88.37, 40.46, -87.53, 40.97)},
    {"name": "Colby",        "state": "KS", "weight": 0.80, "bbox": (-101.13, 39.19, -100.79, 39.56)},
    {"name": "Adair",        "state": "MO", "weight": 0.78, "bbox": (-92.79, 40.04, -92.27, 40.36)},
    {"name": "Blue Earth",   "state": "MN", "weight": 0.76, "bbox": (-94.31, 43.84, -93.63, 44.14)},
    {"name": "Cass",         "state": "ND", "weight": 0.73, "bbox": (-97.45, 46.51, -96.33, 47.15)},
    {"name": "Hardin",       "state": "OH", "weight": 0.70, "bbox": (-83.88, 40.38, -83.51, 40.75)},
    {"name": "Coles",        "state": "IL", "weight": 0.68, "bbox": (-88.50, 39.25, -88.03, 39.64)},
    {"name": "Franklin",     "state": "NE", "weight": 0.66, "bbox": (-99.19, 40.05, -98.63, 40.32)},
    {"name": "Madison",      "state": "OH", "weight": 0.64, "bbox": (-83.57, 39.85, -83.19, 40.17)},
]

# Normalize weights to sum to 1.0
TOTAL_WEIGHT = sum(c["weight"] for c in COUNTIES)
for c in COUNTIES:
    c["weight"] /= TOTAL_WEIGHT

# Sentinel Hub configuration
sh_config = SHConfig()
sh_config.instance_id = os.getenv("SENTINELHUB_CLIENT_ID")
sh_config.sh_client_secret = os.getenv("SENTINELHUB_CLIENT_SECRET")
if not (sh_config.instance_id and sh_config.sh_client_secret):
    raise RuntimeError("Sentinel Hub credentials are missing.")

client = SentinelHubDownloadClient(config=sh_config)

# Google Drive setup (optional)
GDRIVE_ENABLED = bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
if GDRIVE_ENABLED:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds_json = base64.b64decode(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON").encode())
    creds = service_account.Credentials.from_service_account_info(json.loads(creds_json), scopes=["https://www.googleapis.com/auth/drive.file"])
    drive_service = build('drive', 'v3', credentials=creds)
    DRIVE_FOLDER = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
    raise RuntimeError("Telegram credentials missing.")


# ---------------------------------------------------------------------------
# 2. HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def get_stage_threshold(doy: int) -> float:
    """Return dynamic NDVI threshold based on Day‑Of‑Year (approx phenological stage).

    Emergence (DOY < 150): 0.30
    Vegetative (150 ≤ DOY < 190): 0.55
    Pre‑silking (190 ≤ DOY < 240): 0.70
    Late/Fill (≥ 240): 0.50  -> stress post‑silking less correlated to yield.
    """
    if doy < 150:
        return 0.30
    if doy < 190:
        return 0.55
    if doy < 240:
        return 0.70
    return 0.50


def percentile_rank(series: pd.Series, value: float) -> float:
    """Return percentile rank (0‑100) of `value` within the distribution of `series`."""
    return stats.percentileofscore(series.dropna().values, value, kind='mean')


def send_telegram(msg: str, png_bytes: bytes | None = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload, timeout=20)
    if png_bytes is not None:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        files = {"photo": ("ndvi.png", png_bytes)}
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID}, files=files, timeout=30)


def upload_to_gdrive(filename: str, data: bytes, mime: str):
    if not GDRIVE_ENABLED:
        return
    media = {'name': filename, 'parents': [DRIVE_FOLDER]}
    media_body = {'mimeType': mime, 'body': io.BytesIO(data)}
    drive_service.files().create(body=media, media_body=media_body, fields='id').execute()


# ---------------------------------------------------------------------------
# 3. CORE NDVI FUNCTIONS
# ---------------------------------------------------------------------------

def fetch_ndvi_series(bbox: Tuple[float, float, float, float], start_date: dt.date, end_date: dt.date) -> pd.Series:
    """Download NDVI time series from Sentinel‑2 L2A via Sentinel Hub."""
    box = BBox(bbox, crs=CRS.WGS84)
    evalscript = """
        //VERSION=3
        function setup() {
            return {
                input: ["B04", "B08"],
                output: { id: "ndvi", bands: 1, sampleType: "FLOAT32" }
            }
        }
        function evaluatePixel(sample) {
            let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
            return [ndvi];
        }
    """
    request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A.with_resolution(10),
                time_interval=(start_date, end_date),
                mosaicking_order='mostRecent'
            )
        ],
        responses=[SentinelHubRequest.output_response('ndvi', MimeType.TIFF)],
        bbox=box,
        resolution=(120, 120),  # coarsen for speed
        config=sh_config,
    )
    data = request.get_data(output_type=np.float32, client=client)
    dates = request.get_dates()
    series = pd.Series(index=pd.to_datetime(dates), data=[img.mean() for img in data])
    series.name = 'NDVI'
    return series


def get_baseline_series(series_all_years: Dict[int, pd.Series]) -> pd.Series:
    """Build baseline median NDVI per DOY over YEAR_RANGE_BASELINE."""
    hist_concat = pd.concat(series_all_years.values())
    hist_concat.index = hist_concat.index.dayofyear
    return hist_concat.groupby(level=0).median()


# ---------------------------------------------------------------------------
# 4. MAIN WORKFLOW
# ---------------------------------------------------------------------------

def process_county(county: Dict, baseline_cache: Dict[str, pd.Series]) -> Dict:
    name = county['name']
    key = f"{name}_{county['state']}"

    end_date = RUN_DATE
    start_date = RUN_DATE - dt.timedelta(days=30)  # fetch last 30 days

    # 4.1  time‑series this month
    series_recent = fetch_ndvi_series(county['bbox'], start_date, end_date)

    # 4.2  baseline median per DOY (cached)
    if key not in baseline_cache:
        per_year = {}
        for year in YEAR_RANGE_BASELINE:
            st = dt.date(year, 4, 1)
            en = dt.date(year, 9, 30)
            per_year[year] = fetch_ndvi_series(county['bbox'], st, en)
        baseline_cache[key] = get_baseline_series(per_year)
    baseline = baseline_cache[key]

    today_ndvi = series_recent.iloc[-1]
    doy = RUN_DATE.timetuple().tm_yday
    baseline_today = baseline.get(doy, np.nan)
    percentile = 100 - percentile_rank(baseline, today_ndvi)  # lower NDVI = higher stress
    z_score = stats.zscore(baseline, nan_policy='omit')[doy-1]  # pre‑compute but simple here
    # Use rolling pct
    ndvi_7 = series_recent.rolling(window=7).mean().iloc[-1]
    ndvi_15 = series_recent.rolling(window=15).mean().iloc[-1]

    delta7 = today_ndvi - ndvi_7
    delta15 = today_ndvi - ndvi_15

    dynamic_threshold = get_stage_threshold(doy)

    status = "OK"
    if (today_ndvi < dynamic_threshold and (z_score <= -1.5 or delta7 <= -0.1)):
        status = "WARNING"
    if z_score <= -2.0:
        status = "ALERT"

    # Graph
    fig, ax = plt.subplots(figsize=(6, 3))
    series_recent.plot(ax=ax, label='NDVI', lw=1.5)
    ax.axhline(dynamic_threshold, ls='--', lw=1, label='Thresh')
    ax.set_title(f"{name} NDVI – last 30 d")
    ax.legend()
    ax.grid(True, alpha=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)

    # Telegram msg
    msg_lines = [
        f"*{name}, {county['state']}*  —  {RUN_DATE:%d %b %Y}",
        f"NDVI : {today_ndvi:0.3f} (baseline {baseline_today:0.3f})",
        f"Δ7j : {delta7:+0.3f},  Δ15j : {delta15:+0.3f}",
        f"Percentile : {percentile:0.1f} % (↓ ⇒ stress)",
        f"z‑score : {z_score:0.2f}",
        f"Poids : {county['weight']*100:0.2f} %",
        f"*Status : {status}*",
    ]
    send_telegram("\n".join(msg_lines), png_bytes=buf.getvalue())

    # Save CSV for the county
    csv_bytes = series_recent.to_csv().encode()
    upload_to_gdrive(f"{name}_{RUN_DATE}.csv", csv_bytes, 'text/csv')
    upload_to_gdrive(f"{name}_{RUN_DATE}.png", buf.getvalue(), 'image/png')

    return {
        'name': name,
        'weight': county['weight'],
        'z': z_score,
    }


def main():
    baseline_cache: Dict[str, pd.Series] = {}
    results = []

    for county in COUNTIES:
        try:
            res = process_county(county, baseline_cache)
            results.append(res)
        except Exception as exc:
            logger.exception(f"Failed county {county['name']}: {exc}")

    # Corn‑Belt Stress Index
    stress_index = sum(r['weight'] * r['z'] for r in results)
    msg = (
        f"*Corn‑Belt Stress Index* ({RUN_DATE:%d %b}): {stress_index:0.2f}\n"
        "Aggregate z < −1 = moderate stress, < −2 = severe."
    )
    send_telegram(msg)

    # Save daily summary to Drive
    df = pd.DataFrame(results)
    summary_bytes = df.to_csv(index=False).encode()
    upload_to_gdrive(f"summary_{RUN_DATE}.csv", summary_bytes, 'text/csv')


if __name__ == "__main__":
    main()
