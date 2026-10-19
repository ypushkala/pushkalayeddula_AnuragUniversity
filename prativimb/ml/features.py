"""Features for the glucose forecaster, computed identically for training and live serving.

Every feature at origin k uses data strictly before the origin, plus the CGM reading at the
origin itself. Sleep counts only once the person has woken up, so a day sleeper's current
sleep is not leaked into a morning forecast.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from prativimb import config
from prativimb.twin import forecast
from prativimb.twin.forecast import Prepared, _take
from prativimb.twin.series import STEP, day_plan, works_night

EHR_COLS = ["hba1c", "bmi", "age", "fpg", "t2d", "prediabetes", "tcf7l2_risk", "t2d_grs", "on_metformin",
            "on_sulfonylurea", "on_sglt2", "on_dpp4", "male", "night_shift"]
TWIN_PARAM_COLS = ["SI", "SG", "Gb", "ka", "gamma", "eE", "cf"]
TWIN_PRED_COLS = ["tw_now", "tw30", "tw60", "tw90", "tw120", "tw_peak", "tw_slope30"]


def _csum(a: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.nan_to_num(a))])


def _window_sum(cs: np.ndarray, ks: np.ndarray, n: int) -> np.ndarray:
    """Sum over steps [k-n, k-1]."""
    lo = np.clip(ks - n, 0, len(cs) - 1)
    return cs[np.clip(ks, 0, len(cs) - 1)] - cs[lo]


def glucose_features(pp: Prepared, ks: np.ndarray, twin_G: np.ndarray | None, theta: np.ndarray | None,
                     H: int = 24) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN windows (sensor gaps) give NaN features
        return _glucose_features(pp, ks, twin_G, theta, H)


def _glucose_features(pp: Prepared, ks: np.ndarray, twin_G, theta, H: int) -> pd.DataFrame:
    s = pp.s
    c = s.cgm
    ks = np.asarray(ks, int)
    f: dict[str, np.ndarray] = {}
    cg = c[ks]
    f["cgm"] = cg
    for j, name in ((1, "d5"), (3, "d15"), (6, "d30"), (12, "d60")):
        f[name] = cg - _take(c, ks - j, np.nan)
    hist2 = _take(c, ks[:, None] - np.arange(24)[None, :], np.nan)
    with np.errstate(all="ignore"):
        f["cgm_mean2h"] = np.nanmean(hist2, axis=1)
        f["cgm_sd2h"] = np.nanstd(hist2, axis=1)
        f["cgm_min2h"] = np.nanmin(hist2, axis=1)
        f["cgm_max2h"] = np.nanmax(hist2, axis=1)
        f["cgm_mean6h"] = np.nanmean(_take(c, ks[:, None] - np.arange(72)[None, :], np.nan), axis=1)

    minute = ks * STEP
    hour = (minute % 1440) / 60
    day = minute // 1440
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    plans = np.array([day_plan(s.declared, int(d)) for d in range(config.N_DAYS)])
    f["day_ramadan"] = (plans[day] == "ramadan").astype(float)
    f["day_hindu_fast"] = (plans[day] == "hindu_fast").astype(float)
    wn = np.array([works_night(s.declared, int(d)) for d in range(-1, config.N_DAYS)])
    f["on_shift"] = np.where(hour < 7, wn[day], np.where(hour >= 22, wn[day + 1], 0)).astype(float)

    cs_carbs = _csum(s.carbs)
    f["carbs_1h"] = _window_sum(cs_carbs, ks, 12)
    f["carbs_2h"] = _window_sum(cs_carbs, ks, 24)
    f["carbs_4h"] = _window_sum(cs_carbs, ks, 48)
    meal_steps = np.flatnonzero(s.carbs > 0)
    if not len(meal_steps):
        meal_steps = np.array([-10_000])
    pos = np.searchsorted(meal_steps, ks) - 1
    has = pos >= 0
    last = np.where(has, meal_steps[np.clip(pos, 0, None)], -10_000)
    f["min_since_meal"] = np.where(has, np.minimum((ks - last) * STEP, 720), 720).astype(float)
    f["last_meal_carbs"] = np.where(has, s.carbs[np.clip(last, 0, None)], 0.0)
    f["last_meal_af"] = np.where(has, s.meal_af[np.clip(last, 0, None)], 1.0)

    exp_next, exp_g, exp_af, exp30, exp60, exp120 = (np.zeros(len(ks)) for _ in range(6))
    for i, k in enumerate(ks):
        em = forecast.expected_meals(pp, int(k), H)
        exp_next[i] = 240.0
        for j, g, a, _ in em:
            t = j * STEP
            if t < exp_next[i]:
                exp_next[i], exp_g[i], exp_af[i] = t, g, a
            exp30[i] += g * (t <= 30)
            exp60[i] += g * (t <= 60)
            exp120[i] += g * (t <= 120)
    f.update(exp_meal_in=exp_next, exp_meal_carbs=exp_g, exp_meal_af=exp_af, exp_carbs30=exp30,
             exp_carbs60=exp60, exp_carbs120=exp120)

    cs_steps = _csum(s.steps)
    f["spm_15"] = _window_sum(cs_steps, ks, 3) / 3
    f["spm_60"] = _window_sum(cs_steps, ks, 12) / 12
    f["steps_3h"] = _window_sum(cs_steps, ks, 36) * STEP
    with np.errstate(all="ignore"):
        f["hr_30"] = np.nanmean(_take(s.hr, ks[:, None] - np.arange(1, 7)[None, :], np.nan), axis=1)
    base = np.nanpercentile(s.hr[: config.CALIBRATION_DAYS * 288], 5)  # resting level from the calibration week
    f["hr_delta"] = f["hr_30"] - base

    nt = s.nightly
    if nt is not None and len(nt):
        wake = nt.wake_minute.to_numpy()
        hrs = nt.total_sleep_min.to_numpy() / 60
        order = np.argsort(wake)
        wake, hrs = wake[order], hrs[order]
        p = np.searchsorted(wake, minute, side="right") - 1
        get = lambda off: np.where(p - off >= 0, hrs[np.clip(p - off, 0, None)], np.nan)
        f["sleep_last"] = get(0)
        with np.errstate(all="ignore"):
            three = np.vstack([get(0), get(1), get(2)])
            f["sleep_3n"] = np.nanmean(three, axis=0)
            f["sleep_debt3"] = np.nansum(np.maximum(7 - three, 0), axis=0)
        f["min_since_wake"] = np.where(p >= 0, minute - wake[np.clip(p, 0, None)], np.nan)
    else:
        f["sleep_last"] = f["sleep_3n"] = f["sleep_debt3"] = f["min_since_wake"] = np.full(len(ks), np.nan)

    cs_miss = _csum(s.met_missed)
    f["met_missed_24h"] = _window_sum(cs_miss, ks, 288)
    dose_steps = np.flatnonzero(s.met_dose > 0)
    if len(dose_steps):
        q = np.searchsorted(dose_steps, ks) - 1
        since = np.where(q >= 0, (ks - dose_steps[np.clip(q, 0, None)]) * STEP / 60, 48.0)
        f["h_since_met"] = np.minimum(since, 48.0)
    else:
        f["h_since_met"] = np.full(len(ks), 48.0)

    for col in EHR_COLS:
        f[col] = np.full(len(ks), float(s.ehr.get(col, np.nan) or 0.0))
    if theta is not None:
        for col, v in zip(("SI", "SG", "Gb", "ka", "gamma", "dawn", "eE", "cf"), theta):
            if col in TWIN_PARAM_COLS:
                f[col] = np.full(len(ks), float(v))
    if twin_G is not None:
        f["tw_now"] = twin_G[:, 0]
        f["tw30"], f["tw60"], f["tw90"], f["tw120"] = twin_G[:, 6], twin_G[:, 12], twin_G[:, 18], twin_G[:, 24]
        f["tw_peak"] = twin_G[:, 1:H + 1].max(axis=1)
        f["tw_slope30"] = twin_G[:, 6] - twin_G[:, 0]
    return pd.DataFrame(f)


def ml_only_columns(cols: list[str]) -> list[str]:
    drop = set(TWIN_PARAM_COLS) | set(TWIN_PRED_COLS)
    return [c for c in cols if c not in drop]
