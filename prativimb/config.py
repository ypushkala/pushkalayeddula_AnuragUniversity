"""Paths, seeds and calendar constants shared by every stage."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PRATIVIMB_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "prativimb.duckdb"
ARTIFACT_DIR = Path(os.environ.get("PRATIVIMB_ARTIFACTS", ROOT / "artifacts"))
REPORT_DIR = ROOT / "reports"
FIGURE_DIR = REPORT_DIR / "figures"
DOCS_DIR = ROOT / "docs"

SEED = 20260315
N_PATIENTS = 200
N_DAYS = 30
IST = timezone(timedelta(hours=5, minutes=30))

# Day 0 is Saturday 14 Feb 2026. All internal times are minutes since this instant (IST).
START = datetime(2026, 2, 14, 0, 0, tzinfo=IST)
END = START + timedelta(days=N_DAYS)
DEMO_NOW = datetime(2026, 3, 15, 19, 45, tzinfo=IST)

CGM_STEP = 5          # minutes between CGM readings
CALIBRATION_DAYS = 7  # days 0..6 calibrate the twin; forecasting uses days 7..29
HORIZONS = (30, 60, 90, 120)
REPORT_HORIZONS = (30, 60, 120)
SPIKE_THRESHOLD = 180.0
LOW_THRESHOLD = 70.0
CONFORMAL_ALPHA = 0.10

# Calendar events inside the window (dates approximate where the observance depends on moon sighting).
MAHA_SHIVARATRI = date(2026, 2, 15)
RAMADAN_FIRST_FAST = date(2026, 2, 19)
HOLI = date(2026, 3, 4)
EKADASHI = (date(2026, 2, 27), date(2026, 3, 15))

HERO_IDS = {"ramesh": "PTV-0001", "fatima": "PTV-0002", "suresh": "PTV-0003"}


def day_index(d: date) -> int:
    return (d - START.date()).days


def minute_to_datetime(m: int | float) -> datetime:
    return START + timedelta(minutes=float(m))


def datetime_to_minute(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return int(round((dt - START).total_seconds() / 60))


def ensure_dirs() -> None:
    for p in (RAW_DIR, PROCESSED_DIR, ARTIFACT_DIR, FIGURE_DIR):
        p.mkdir(parents=True, exist_ok=True)
