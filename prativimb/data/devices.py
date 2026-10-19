"""Device export formats and the adapters that read them back.

Apple Health: the export.xml produced by Health > Export All Health Data (Record elements
with HK type identifiers). Google Fit: the REST API dataset shape (point lists with
startTimeNanos, endTimeNanos and typed values). Google Fit stores blood glucose in mmol/L.

Neither platform has a native nightly RMSSD type (Apple exports SDNN), so nightly RMSSD,
as reported by rings and bands such as Oura or Fitbit, is written under our own namespaced
type and documented in docs/DATA.md.

Health Connect (Android): records in the shape the Health Connect client returns them
(BloodGlucoseRecord, HeartRateRecord with samples, StepsRecord, SleepSessionRecord with
stages, HeartRateVariabilityRmssdRecord), serialised to JSON with ISO 8601 times. Health
Connect has a native RMSSD record, so no custom type is needed there.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from prativimb import config

MGDL_PER_MMOL = 18.0182
APPLE_SLEEP = {"awake": "HKCategoryValueSleepAnalysisAwake", "core": "HKCategoryValueSleepAnalysisAsleepCore",
               "deep": "HKCategoryValueSleepAnalysisAsleepDeep", "rem": "HKCategoryValueSleepAnalysisAsleepREM"}
APPLE_SLEEP_REV = {v: k for k, v in APPLE_SLEEP.items()}
GFIT_SLEEP = {"awake": 1, "core": 4, "deep": 5, "rem": 6}
GFIT_SLEEP_REV = {v: k for k, v in GFIT_SLEEP.items()}
RMSSD_TYPE = "org.prativimb.NightlyRMSSD"


def _apple_time(minutes: np.ndarray) -> list[str]:
    base = config.START.replace(tzinfo=None)
    return [(base + timedelta(minutes=int(m))).strftime("%Y-%m-%d %H:%M:%S +0530") for m in minutes]


def _nanos(minutes: np.ndarray) -> list[str]:
    epoch = int(config.START.timestamp())
    return [str((epoch + int(m) * 60) * 1_000_000_000) for m in minutes]


def write_apple(path: Path, name: str, cgm: pd.DataFrame, hr: pd.DataFrame, sleep: pd.DataFrame,
                hrv: pd.DataFrame) -> None:
    root = ET.Element("HealthData", locale="en_IN")
    ET.SubElement(root, "ExportDate", value=_apple_time(np.array([config.N_DAYS * 1440 - 1]))[0])
    watch, cgm_src = f"Apple Watch ({name})", "Dexcom G7"

    def rec(kind, src, unit, starts, ends, values):
        for s, e, v in zip(_apple_time(starts), _apple_time(ends), values):
            ET.SubElement(root, "Record", type=kind, sourceName=src, unit=unit, creationDate=e, startDate=s,
                          endDate=e, value=str(v))

    h = hr.dropna(subset=["hr"])
    rec("HKQuantityTypeIdentifierHeartRate", watch, "count/min", h.minute.values, h.minute.values,
        h.hr.astype(int).values)
    st = hr[hr.steps > 0]
    rec("HKQuantityTypeIdentifierStepCount", watch, "count", st.minute.values, st.minute.values + 1,
        st.steps.astype(int).values)
    g = cgm.dropna(subset=["glucose"])
    rec("HKQuantityTypeIdentifierBloodGlucose", cgm_src, "mg/dL", g.minute.values, g.minute.values,
        g.glucose.astype(int).values)
    for s, e, stage in zip(_apple_time(sleep.start.values), _apple_time(sleep.end.values), sleep.stage.values):
        ET.SubElement(root, "Record", type="HKCategoryTypeIdentifierSleepAnalysis", sourceName=watch,
                      creationDate=e, startDate=s, endDate=e, value=APPLE_SLEEP[stage])
    rec(RMSSD_TYPE, watch, "ms", hrv.minute.values, hrv.minute.values, hrv.rmssd.values)
    ET.indent(root, space=" ")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)


def _minute(ts: str) -> int:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S %z")
    return int(round((dt - config.START).total_seconds() / 60))


def read_apple(path: Path) -> dict[str, pd.DataFrame]:
    rows = {"hr": [], "steps": [], "cgm": [], "sleep": [], "hrv": []}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != "Record":
            continue
        t, a = el.get("type"), el.attrib
        if t == "HKQuantityTypeIdentifierHeartRate":
            rows["hr"].append((_minute(a["startDate"]), float(a["value"])))
        elif t == "HKQuantityTypeIdentifierStepCount":
            rows["steps"].append((_minute(a["startDate"]), int(a["value"])))
        elif t == "HKQuantityTypeIdentifierBloodGlucose":
            v = float(a["value"]) * (MGDL_PER_MMOL if a.get("unit") == "mmol<180.1558800000541>/L" else 1)
            rows["cgm"].append((_minute(a["startDate"]), v))
        elif t == "HKCategoryTypeIdentifierSleepAnalysis" and a["value"] in APPLE_SLEEP_REV:
            rows["sleep"].append((_minute(a["startDate"]), _minute(a["endDate"]), APPLE_SLEEP_REV[a["value"]]))
        elif t == RMSSD_TYPE:
            rows["hrv"].append((_minute(a["startDate"]), float(a["value"])))
        el.clear()
    return _canonical(rows)


def write_google(folder: Path, cgm: pd.DataFrame, hr: pd.DataFrame, sleep: pd.DataFrame, hrv: pd.DataFrame) -> None:
    folder.mkdir(parents=True, exist_ok=True)

    def dump(fname, source, dtype, starts, ends, values):
        pts = [{"startTimeNanos": s, "endTimeNanos": e, "dataTypeName": dtype, "value": [v]}
               for s, e, v in zip(_nanos(starts), _nanos(ends), values)]
        doc = {"dataSourceId": source, "minStartTimeNs": _nanos(np.array([0]))[0],
               "maxEndTimeNs": _nanos(np.array([config.N_DAYS * 1440]))[0], "point": pts}
        (folder / fname).write_text(json.dumps(doc))

    h = hr.dropna(subset=["hr"])
    dump("heart_rate.json", "derived:com.google.heart_rate.bpm:com.google.android.gms:merge_heart_rate_bpm",
         "com.google.heart_rate.bpm", h.minute.values, h.minute.values, [{"fpVal": float(v)} for v in h.hr.values])
    st = hr[hr.steps > 0]
    dump("step_count.json", "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps",
         "com.google.step_count.delta", st.minute.values, st.minute.values + 1, [{"intVal": int(v)} for v in st.steps.values])
    g = cgm.dropna(subset=["glucose"])
    dump("blood_glucose.json", "raw:com.google.blood_glucose:com.freestylelibre.app:libre",
         "com.google.blood_glucose", g.minute.values, g.minute.values,
         [{"fpVal": round(float(v) / MGDL_PER_MMOL, 3)} for v in g.glucose.values])
    dump("sleep_segment.json", "derived:com.google.sleep.segment:com.google.android.gms:merged",
         "com.google.sleep.segment", sleep.start.values, sleep.end.values, [{"intVal": GFIT_SLEEP[s]} for s in sleep.stage.values])
    dump("hrv_rmssd.json", "raw:com.prativimb.hrv.rmssd.nightly:band", "com.prativimb.hrv.rmssd.nightly",
         hrv.minute.values, hrv.minute.values, [{"fpVal": float(v)} for v in hrv.rmssd.values])


def read_google(folder: Path) -> dict[str, pd.DataFrame]:
    epoch = int(config.START.timestamp())

    def pts(fname):
        doc = json.loads((folder / fname).read_text())
        for pt in doc["point"]:
            s = (int(pt["startTimeNanos"]) // 1_000_000_000 - epoch) // 60
            e = (int(pt["endTimeNanos"]) // 1_000_000_000 - epoch) // 60
            yield s, e, pt["value"][0]

    rows = {
        "hr": [(s, v["fpVal"]) for s, e, v in pts("heart_rate.json")],
        "steps": [(s, v["intVal"]) for s, e, v in pts("step_count.json")],
        "cgm": [(s, round(v["fpVal"] * MGDL_PER_MMOL)) for s, e, v in pts("blood_glucose.json")],
        "sleep": [(s, e, GFIT_SLEEP_REV[v["intVal"]]) for s, e, v in pts("sleep_segment.json")],
        "hrv": [(s, v["fpVal"]) for s, e, v in pts("hrv_rmssd.json")],
    }
    return _canonical(rows)


HC_SLEEP = {"awake": 1, "core": 4, "deep": 5, "rem": 6}  # SleepSessionRecord.STAGE_TYPE_*
HC_SLEEP_REV = {v: k for k, v in HC_SLEEP.items()}


def _iso(minute: float) -> str:
    return (config.START + timedelta(minutes=float(minute))).isoformat()


def write_health_connect(path: Path, cgm: pd.DataFrame, hr: pd.DataFrame, sleep: pd.DataFrame, hrv: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"dataOrigin": "org.prativimb.synthetic", "device": {"type": "WATCH"}}
    g = cgm.dropna(subset=["glucose"])
    h = hr.dropna(subset=["hr"])
    st = hr[hr.steps > 0]
    hr_records = []
    for start in range(0, config.N_DAYS * 1440, 60):  # one HeartRateRecord per hour, as watches batch them
        w = h[(h.minute >= start) & (h.minute < start + 60)]
        if len(w):
            hr_records.append({"startTime": _iso(start), "endTime": _iso(start + 60), "metadata": meta,
                               "samples": [{"time": _iso(m), "beatsPerMinute": float(v)} for m, v in zip(w.minute, w.hr)]})
    doc = {"exportedBy": "Prativimb synthetic generator", "zoneOffset": "+05:30", "records": {
        "BloodGlucoseRecord": [{"time": _iso(m), "level": {"inMilligramsPerDeciliter": float(v)},
                                "specimenSource": 1, "relationToMeal": 0, "metadata": {"dataOrigin": "com.dexcom.g6"}}
                               for m, v in zip(g.minute, g.glucose)],
        "HeartRateRecord": hr_records,
        "StepsRecord": [{"startTime": _iso(m), "endTime": _iso(m + 1), "count": int(v), "metadata": meta}
                        for m, v in zip(st.minute, st.steps)],
        "SleepSessionRecord": [{"startTime": _iso(a), "endTime": _iso(b), "metadata": meta,
                                "stages": [{"startTime": _iso(a), "endTime": _iso(b), "stage": HC_SLEEP[x]}]}
                               for a, b, x in zip(sleep.start, sleep.end, sleep.stage)],
        "HeartRateVariabilityRmssdRecord": [{"time": _iso(m), "heartRateVariabilityMillis": float(v), "metadata": meta}
                                            for m, v in zip(hrv.minute, hrv.rmssd)],
    }}
    path.write_text(json.dumps(doc))


def _hc_minute(ts: str) -> int:
    return int(round((datetime.fromisoformat(ts) - config.START).total_seconds() / 60))


def read_health_connect(path: Path) -> dict[str, pd.DataFrame]:
    r = json.loads(path.read_text())["records"]
    rows = {
        "cgm": [(_hc_minute(x["time"]), x["level"]["inMilligramsPerDeciliter"]) for x in r["BloodGlucoseRecord"]],
        "hr": [(_hc_minute(s["time"]), s["beatsPerMinute"]) for x in r["HeartRateRecord"] for s in x["samples"]],
        "steps": [(_hc_minute(x["startTime"]), x["count"]) for x in r["StepsRecord"]],
        "sleep": [(_hc_minute(st["startTime"]), _hc_minute(st["endTime"]), HC_SLEEP_REV[st["stage"]])
                  for x in r["SleepSessionRecord"] for st in x["stages"]],
        "hrv": [(_hc_minute(x["time"]), x["heartRateVariabilityMillis"]) for x in r["HeartRateVariabilityRmssdRecord"]],
    }
    return _canonical(rows)


def _canonical(rows: dict) -> dict[str, pd.DataFrame]:
    hr = pd.DataFrame(rows["hr"], columns=["minute", "hr"])
    steps = pd.DataFrame(rows["steps"], columns=["minute", "steps"])
    minutes = pd.DataFrame({"minute": np.arange(config.N_DAYS * 1440)})
    hr_all = minutes.merge(hr, on="minute", how="left").merge(steps, on="minute", how="left")
    hr_all["steps"] = hr_all.steps.fillna(0).astype(np.int16)
    grid = pd.DataFrame({"minute": np.arange(0, config.N_DAYS * 1440, config.CGM_STEP)})
    cgm = grid.merge(pd.DataFrame(rows["cgm"], columns=["minute", "glucose"]), on="minute", how="left")
    sleep = pd.DataFrame(rows["sleep"], columns=["start", "end", "stage"])
    hrv = pd.DataFrame(rows["hrv"], columns=["minute", "rmssd"])
    return {"cgm": cgm, "hr": hr_all, "sleep": sleep, "hrv": hrv}
