"""Alert definitions and their evaluation.

Two tiers for Event A:
  watch  the hybrid point forecast crosses 180 mg/dL within 2 h (early, shown in the patient view)
  alert  the conformal lower bound crosses 180 mg/dL within 2 h (pushed to the ward list)
The alert level is the most sensitive CQR coverage whose false alarm rate on calibration
patients stays within budget. Test patients are never used to choose it.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from prativimb import config
from prativimb.twin.series import PER_DAY

FA_BUDGET = 0.10
LEVELS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def spike_onsets(c: np.ndarray, start: int) -> np.ndarray:
    """Onset of a sustained excursion above 180 mg/dL: three consecutive readings above, after
    at least 30 minutes not above (missing readings count as not above, need 4 valid)."""
    above = np.nan_to_num(c, nan=0) > config.SPIKE_THRESHOLD
    valid = ~np.isnan(c)
    out = []
    for i in range(max(start, 6), len(c) - 2):
        if above[i] and above[i + 1] and above[i + 2] and not above[i - 6:i].any() and valid[i - 6:i].sum() >= 4:
            out.append(i)
    return np.array(out, int)


def low_onsets(c: np.ndarray, start: int) -> np.ndarray:
    below = np.nan_to_num(c, nan=200) < config.LOW_THRESHOLD
    out = []
    for i in range(max(start, 6), len(c) - 2):
        if below[i] and below[i + 1] and below[i + 2] and not below[i - 6:i].any():
            out.append(i)
    return np.array(out, int)


def lower_hits(t: pd.DataFrame, bundle: dict, coverage: float) -> np.ndarray:
    from prativimb.ml.glucose import lower_bound
    below = t.cgm.to_numpy() <= config.SPIKE_THRESHOLD
    hit = np.column_stack([lower_bound(bundle, h, t[f"qlo{h}"].to_numpy(), coverage) > config.SPIKE_THRESHOLD
                           for h in config.HORIZONS]).any(1)
    return hit & below


def alert_policy(t: pd.DataFrame, kind: str) -> np.ndarray:
    below = t.cgm.to_numpy() <= config.SPIKE_THRESHOLD
    if kind == "lower90":
        hit = np.column_stack([t[f"lo{h}"] > config.SPIKE_THRESHOLD for h in config.HORIZONS]).any(1)
    elif kind in ("hyb", "phys", "ml"):
        hit = np.column_stack([t[f"{kind}{h}"] > config.SPIKE_THRESHOLD for h in config.HORIZONS]).any(1)
    else:
        raise ValueError(kind)
    return hit & below


def evaluate_alerts(t: pd.DataFrame, cgm: dict[str, np.ndarray], alerts: np.ndarray, onset_fn=spike_onsets,
                    window: int = 24) -> dict:
    tp_events, n_events, leads, n_alert_eps, n_false = 0, 0, [], 0, 0
    patient_days = 0.0
    start = config.CALIBRATION_DAYS * PER_DAY
    for pid, g in t.assign(alert=alerts).groupby("pid"):
        c = cgm[pid]
        ks = g.k.to_numpy()
        al = ks[g.alert.to_numpy()]
        patient_days += (ks.max() - ks.min()) / PER_DAY
        onsets = onset_fn(c, start + window)
        n_events += len(onsets)
        for i in onsets:
            prior = al[(al >= i - window) & (al < i)]
            if len(prior):
                tp_events += 1
                leads.append((i - prior.min()) * config.CGM_STEP)
        # alert episodes: a new episode starts after 30 minutes without an alert
        if len(al):
            starts = al[np.concatenate([[True], np.diff(al) > 6])]
            n_alert_eps += len(starts)
            for a in starts:
                if not ((onsets > a) & (onsets <= a + window + 3)).any():
                    n_false += 1
    return {
        "events": n_events, "detected": tp_events,
        "sensitivity": tp_events / max(n_events, 1),
        "alert_episodes": n_alert_eps,
        "precision": (n_alert_eps - n_false) / max(n_alert_eps, 1),
        "median_lead_min": float(np.median(leads)) if leads else None,
        "false_alarms_per_patient_day": n_false / max(patient_days, 1e-9),
        "patient_days": patient_days,
    }


def choose_alert_level(preds: pd.DataFrame, bundle: dict, cgm: dict) -> dict:
    cal = preds[preds.split == "calibration"]
    rows = []
    for c in LEVELS:
        r = evaluate_alerts(cal, cgm, lower_hits(cal, bundle, c))
        rows.append({"coverage": c, **r})
    ok = [r for r in rows if r["false_alarms_per_patient_day"] <= FA_BUDGET]
    best = max(ok, key=lambda r: r["sensitivity"]) if ok else rows[-1]
    out = {"alert_coverage": best["coverage"], "fa_budget": FA_BUDGET, "chosen_on": "calibration patients",
           "calibration_scan": rows}
    (config.ARTIFACT_DIR / "alert_config.json").write_text(json.dumps(out, indent=1, default=float))
    return out
