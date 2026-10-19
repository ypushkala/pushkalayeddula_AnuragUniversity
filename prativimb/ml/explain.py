"""Why the twin expects what it expects, in mg/dL and in plain words.

Two sources are combined in one unit (mg/dL of predicted two hour peak):
  * exact Shapley values over six mechanistic inputs of the twin (2^6 = 64 batched runs),
  * TreeSHAP of the residual model at the horizon nearest the peak, grouped into the same
    clinical categories.
The top positive drivers become one sentence a clinician can read at a glance.
"""
from __future__ import annotations

from itertools import combinations
from math import factorial

import numpy as np

from prativimb import config
from prativimb.twin import bergman, forecast
from prativimb.twin.forecast import W, Prepared
from prativimb.twin.series import STEP

PLAYERS = ("meal_upcoming", "meal_recent", "activity", "sleep", "medication", "physiology")
TYPICAL = {"SI": 5.5e-4, "gamma": 0.045, "SG": 0.016}  # a typical adult without diabetes

CATEGORY_OF = {
    "exp_meal_in": "meal_upcoming", "exp_meal_carbs": "meal_upcoming", "exp_meal_af": "meal_upcoming",
    "exp_carbs30": "meal_upcoming", "exp_carbs60": "meal_upcoming", "exp_carbs120": "meal_upcoming",
    "carbs_1h": "meal_recent", "carbs_2h": "meal_recent", "carbs_4h": "meal_recent", "min_since_meal": "meal_recent",
    "last_meal_carbs": "meal_recent", "last_meal_af": "meal_recent",
    "spm_15": "activity", "spm_60": "activity", "steps_3h": "activity", "hr_30": "activity", "hr_delta": "activity",
    "sleep_last": "sleep", "sleep_3n": "sleep", "sleep_debt3": "sleep", "min_since_wake": "sleep", "on_shift": "sleep",
    "met_missed_24h": "medication", "h_since_met": "medication",
    "cgm": "trend", "d5": "trend", "d15": "trend", "d30": "trend", "d60": "trend", "cgm_mean2h": "trend",
    "cgm_sd2h": "trend", "cgm_min2h": "trend", "cgm_max2h": "trend", "cgm_mean6h": "trend",
    "hour_sin": "calendar", "hour_cos": "calendar", "day_ramadan": "calendar", "day_hindu_fast": "calendar",
}


def _variant(pp: Prepared, theta: np.ndarray, k: int, H: int, active: set[str]):
    """Inputs and params with each inactive player switched to its neutral value."""
    s = pp.s
    u, obs = forecast.build(pp, np.array([k]), H)
    x0 = forecast.initial_state(obs, float(s.on_metformin))
    th = theta.copy()
    if "meal_upcoming" not in active:
        u.carbs[0, W:] = 0.0
    if "meal_recent" not in active:
        u.carbs[0, :W] = 0.0
    if "activity" not in active:
        u.A[0, :] = 0.0
    if "sleep" not in active:
        hour = ((k + np.arange(-W, H)) * STEP % 1440) / 60
        u.smod[0, :] = 1 + bergman.POP["circ_amp"] * np.cos(2 * np.pi * (hour - 9) / 24)
    if "medication" not in active and s.on_metformin:
        # Regular dosing: one unit every 12 hours keeps M near its usual level.
        u.dose[0, :] = 0.0
        u.dose[0, ::144] = pp.dose_unit
        x0[6] = 1.2
    if "physiology" not in active:
        names = list(bergman.PARAMS)
        for key, v in TYPICAL.items():
            th[names.index(key)] = v
    return u, obs, x0, th


def twin_shapley(pp: Prepared, theta: np.ndarray, k: int, H: int = 24) -> tuple[dict[str, float], float, float]:
    coalitions = [frozenset(c) for r in range(len(PLAYERS) + 1) for c in combinations(PLAYERS, r)]
    us, obss, x0s, ths = [], [], [], []
    for c in coalitions:
        u, obs, x0, th = _variant(pp, theta, k, H, set(c))
        us.append(u); obss.append(obs); x0s.append(x0); ths.append(th)
    cat = lambda f: np.vstack([getattr(u, f) for u in us])
    U = bergman.Inputs(cat("carbs"), cat("af"), cat("A"), cat("dose"), cat("smod"), cat("dawn"))
    p = bergman.params_dict(np.vstack(ths), pp.s.bw, float(pp.s.on_metformin))
    G, _ = bergman.run_rk4(p, np.hstack(x0s), U, obs=np.vstack(obss), obs_until=W)
    peak = G[:, W + 1: W + H + 1].max(axis=1)
    v = dict(zip(coalitions, peak))
    n = len(PLAYERS)
    phi = {}
    for i in PLAYERS:
        total = 0.0
        for c in coalitions:
            if i in c:
                continue
            w = factorial(len(c)) * factorial(n - len(c) - 1) / factorial(n)
            total += w * (v[c | {i}] - v[c])
        phi[i] = float(total)
    return phi, float(v[frozenset()]), float(v[frozenset(PLAYERS)])


def residual_shap(bundle: dict, X, h: int) -> dict[str, float]:
    model = bundle["models"][h]["hybrid"]
    contrib = model.booster_.predict(X[bundle["features"]], pred_contrib=True)[0][:-1]
    out: dict[str, float] = {}
    for name, val in zip(bundle["features"], contrib):
        if name.startswith("tw"):
            continue  # the twin forecast itself is already decomposed above
        cat = CATEGORY_OF.get(name, "physiology")
        out[cat] = out.get(cat, 0.0) + float(val)
    return out


def describe(pp: Prepared, k: int, feats: dict, cat: str, H: int = 24) -> str:
    s = pp.s
    if cat == "meal_upcoming":
        em = forecast.expected_meals(pp, k, H)
        if em:
            j, g, a, name = max(em, key=lambda e: e[1])
            t = config.minute_to_datetime((k + j) * STEP).strftime("%H:%M")
            label = name.split(" (")[0].lower()
            return f"expected {label} (about {g:.0f} g carbohydrate at {t})"
        return "no meal expected in the next 2 h"
    if cat == "meal_recent":
        if feats.get("carbs_2h", 0) > 0:
            return f"recent meal ({feats['carbs_2h']:.0f} g in the last 2 h, {feats['min_since_meal']:.0f} min ago)"
        return "no meal in the last 2 h"
    if cat == "activity":
        if feats.get("steps_3h", 0) > 1500:
            return f"recent walking ({feats['steps_3h']:,.0f} steps in 3 h)"
        return f"little activity ({feats.get('steps_3h', 0):,.0f} steps in 3 h)"
    if cat == "sleep":
        parts = []
        if np.isfinite(feats.get("sleep_3n", np.nan)) and feats["sleep_3n"] < 6.5:
            parts.append(f"short sleep ({feats['sleep_3n']:.1f} h, last 3 nights)")
        if feats.get("on_shift", 0) or s.declared.get("night_shift"):
            parts.append("night shift")
        return " and ".join(parts) if parts else f"sleep {feats.get('sleep_3n', 7):.1f} h, last 3 nights"
    if cat == "medication":
        if feats.get("met_missed_24h", 0) > 0:
            return "missed metformin dose in the last 24 h"
        return "medication taken as scheduled" if s.on_metformin else "no glucose lowering medication"
    if cat == "physiology":
        return f"reduced insulin sensitivity (HbA1c {s.ehr.get('hba1c', 0):.1f}%, BMI {s.ehr.get('bmi', 0):.1f})"
    if cat == "trend":
        return f"current glucose {feats['cgm']:.0f} mg/dL, {feats.get('d30', 0):+.0f} in 30 min"
    if cat == "calendar":
        if feats.get("day_ramadan"):
            return "Ramadan fasting day pattern"
        return "time of day pattern"
    return cat


def sentence(drivers: list[dict]) -> str:
    # Trend and time of day are context, not causes a clinician can act on; they stay in the bars only.
    # Walking that "raises" a forecast is a learned correlation, not a cause, so it is not named either.
    pos = [d["text"] for d in drivers if d["mgdl"] > 2 and d["category"] not in ("trend", "calendar")
           and not d["text"].startswith("recent walking")][:3]
    if not pos:
        return "No single factor dominates this forecast."
    pos[0] = pos[0][0].upper() + pos[0][1:]
    if len(pos) == 1:
        body = pos[0]
        verb = "is"
    else:
        body = ", ".join(pos[:-1]) + " and " + pos[-1]
        verb = "are"
    return f"{body} {verb} driving this forecast."


def explain(pp: Prepared, theta: np.ndarray, k: int, bundle: dict, X, feats: dict, peak_h: int) -> dict:
    phi, base, full = twin_shapley(pp, theta, k)
    res = residual_shap(bundle, X, peak_h)
    cats = set(phi) | set(res)
    rows = []
    for c in cats:
        val = phi.get(c, 0.0) + res.get(c, 0.0)
        rows.append({"category": c, "mgdl": round(val, 1), "twin": round(phi.get(c, 0.0), 1),
                     "learned": round(res.get(c, 0.0), 1), "text": describe(pp, k, feats, c)})
    rows.sort(key=lambda r: -abs(r["mgdl"]))
    ranked = sorted(rows, key=lambda r: -r["mgdl"])
    return {"drivers": rows, "sentence": sentence(ranked), "twin_baseline_peak": round(base, 1),
            "twin_peak": round(full, 1), "unit": "mg/dL contribution to the predicted 2 hour peak"}
