"""Device layer: what a CGM, a wrist band and a sleep tracker would actually report.

CGM error uses the simglucose sensor noise model (Johnson SU transformed AR(1) noise,
Dexcom parameter set from Breton and Kovatchev 2008) at a 5 minute sample time, plus a
per session calibration gain, warm up gaps at each sensor change, random signal loss and
occasional overnight compression lows.
"""
from __future__ import annotations

from importlib import resources

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from prativimb import config
from prativimb.data.cohort import Patient
from prativimb.data.schedule import DEEP, IN_BED_AWAKE, LIGHT, REM, WAKE, Schedule

SESSION_DAYS = 14  # FreeStyle Libre and Dexcom G7 style wear periods (10 to 15 days)


def _sensor_params() -> dict:
    sp = pd.read_csv(resources.files("simglucose") / "params" / "sensor_params.csv")
    row = sp[sp.Name == "Dexcom"].iloc[0].to_dict()
    row["sample_time"] = float(config.CGM_STEP)
    return row


def cgm_noise(n: int, seed: int) -> np.ndarray:
    from simglucose.sensor.noise_gen import CGMNoise  # imported lazily: the package pulls in gym

    gen = CGMNoise(_sensor_params(), seed=seed)
    return np.array([next(gen) for _ in range(n)], dtype=float)


def cgm(p: Patient, gs_5min: np.ndarray, stage_5min: np.ndarray, rng: np.random.Generator,
        gap: tuple[int, int] | None, compression: np.ndarray | None = None) -> np.ndarray:
    """gs_5min: true subcutaneous glucose every 5 minutes. Returns readings with NaN gaps.

    If `compression` (bool array) is given, the injected compression artefacts are marked in it
    so the artefact detector can be validated against ground truth.
    """
    n = len(gs_5min)
    per_day = 1440 // config.CGM_STEP
    noise = 0.85 * cgm_noise(n, int(rng.integers(0, 2**31 - 1)))
    gain = np.ones(n)
    starts = list(range(0, n, SESSION_DAYS * per_day))
    for s in starts:
        gain[s: s + SESSION_DAYS * per_day] = rng.normal(1.0, 0.03)
    # Sensor error is a little larger in the first day of a session.
    first_day = np.zeros(n, bool)
    for s in starts:
        first_day[s: s + per_day] = True
    values = gs_5min * gain + noise * np.where(first_day, 1.3, 1.0)

    # Compression lows: lying on the sensor during sleep, a sharp false dip.
    asleep = stage_5min >= LIGHT
    for d in range(config.N_DAYS):
        if rng.random() < 0.06:
            idx = np.flatnonzero(asleep[d * per_day:(d + 1) * per_day]) + d * per_day
            if len(idx) > 12:
                c = int(rng.choice(idx[:-8]))
                depth = rng.uniform(25, 45)
                L = int(rng.integers(4, 9))
                values[c: c + L] -= depth * np.sin(np.linspace(0.3, np.pi - 0.3, len(values[c: c + L])))
                if compression is not None:
                    compression[c: c + L] = True

    out = np.clip(np.round(values), 40, 400).astype(float)
    # Warm up after each sensor change (the first session starts before the window).
    for s in starts[1:]:
        off = s + int(rng.integers(per_day // 3, per_day // 2))
        out[off: off + 12] = np.nan
    # Signal loss: phone out of range, bluetooth drops.
    for d in range(config.N_DAYS):
        for _ in range(rng.poisson(0.35)):
            a = d * per_day + int(rng.integers(0, per_day))
            out[a: a + int(rng.integers(3, 18))] = np.nan
    if gap:
        out[gap[0] // config.CGM_STEP: gap[1] // config.CGM_STEP] = np.nan
    return out


def base_rhr(p: Patient, rng: np.random.Generator) -> float:
    rhr = (64 + 0.05 * (p.age - 50) + 10 * (1 - p.lifestyle["fitness"]) + (3 if p.phenotype == "t2d" else 0)
           + (2 if p.hypertension else 0) + rng.normal(0, 3.5))
    if p.has_drug("metoprolol"):
        rhr -= 8
    return float(rhr)


def base_rmssd(p: Patient, rng: np.random.Generator) -> float:
    v = (54 - 0.55 * (p.age - 30)) * p.lifestyle["fitness"] ** 0.8
    v *= 0.82 if p.phenotype == "t2d" else 1.0
    v *= 0.9 if p.hypertension else 1.0
    return float(max(v * rng.lognormal(0, 0.15), 9))


def heart_rate(p: Patient, sched: Schedule, rng: np.random.Generator, gap: tuple[int, int] | None) -> np.ndarray:
    """Minute heart rate with sleep stages, activity, circadian swing, strain and off wrist gaps."""
    T = len(sched.steps)
    strain = np.array([d["strain"] for d in sched.days])
    fever = np.array([d["fever"] for d in sched.days])
    rhr_day = base_rhr(p, rng) + 5.5 * strain + 5.0 * fever
    day = np.arange(T) // 1440
    hour = (np.arange(T) % 1440) / 60
    rhr = rhr_day[day]

    # Band lags activity by a couple of minutes.
    steps_f = pd.Series(sched.steps).ewm(alpha=0.35).mean().to_numpy()
    ar = lfilter([1.0], [1.0, -0.85], rng.normal(0, 1.2, T))
    stage = sched.stage
    sleep_offset = np.select([stage == DEEP, stage == LIGHT, stage == REM, stage == IN_BED_AWAKE],
                             [-9.0, -5.0, -1.0, 2.0], default=0.0)
    awake = stage == WAKE
    hr = rhr + np.where(awake, 9 + 3 * np.sin(2 * np.pi * (hour - 9) / 24) + 0.32 * steps_f, sleep_offset) + ar
    hr = hr + np.where(awake & sched.night_work, 2.0, 0.0)
    hr = np.clip(hr, 38, 185)

    # Charging: about an hour a day off the wrist.
    for d in range(config.N_DAYS):
        idx = np.flatnonzero(awake[d * 1440:(d + 1) * 1440])
        if len(idx) > 120:
            a = d * 1440 + int(rng.choice(idx[:-90]))
            hr[a: a + int(rng.integers(40, 80))] = np.nan
    if gap:
        hr[gap[0]: gap[1]] = np.nan
    return np.round(hr)


def nightly_rmssd(p: Patient, sched: Schedule, rng: np.random.Generator) -> dict[int, float]:
    base = base_rmssd(p, rng)
    out = {}
    for n in sched.nights:
        d = n["night"]
        prev = max(d - 1, 0)
        a = sched.days[prev]["strain"] * 0.4 + sched.days[d]["strain"] * 0.6
        f = sched.days[prev]["fever"]
        hours = n["total_sleep_min"] / 60
        v = base * np.exp(-0.32 * a - 0.25 * f + 0.05 * (hours - 7)) * rng.lognormal(0, 0.10)
        out[d] = round(float(np.clip(v, 6, 140)), 1)
    return out
