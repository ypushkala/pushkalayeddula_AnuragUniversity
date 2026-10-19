"""Forecast windows, the routine prior, and counterfactual scenarios.

A forecast from origin step k uses a 6 hour warm up (k-72 .. k) in which the twin is driven
by logged meals, measured steps and confirmed doses while an observer pulls G toward each
CGM reading. After the origin nothing measured is used: future meals and doses come from
the routine the patient declared (a meal that has not been logged yet is assumed to be on
its way), and activity is assumed to be zero unless a scenario adds some.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from prativimb import config
from prativimb.data.cohort import MEAL_TYPES
from prativimb.twin import bergman
from prativimb.twin.series import N, PER_DAY, STEP, Series, day_plan, works_night

W = 72                       # warm up steps (6 h)
PAD = 9 * PER_DAY            # modifier grids extend past the data for week long scenarios
MAIN_MEAL_G = 30.0
AF = {k: v[1] for k, v in MEAL_TYPES.items()}
SWAPS = {  # carbohydrate factor, absorption factor for the swapped meal
    "none": (1.0, None),
    "millet": (0.85, AF["millet_meal"]),
    "brown_rice": (0.95, 0.80),
    "roti": (0.90, AF["roti_meal"]),
    "half_portion": (0.5, None),
}


def sleep_multiplier(hours: np.ndarray, habitual: float) -> np.ndarray:
    h = np.where(np.isnan(hours), habitual, hours)
    debt = np.maximum(0.0, 7.0 - h)
    out = np.ones(len(h))
    for d in range(len(h)):
        out[d] = np.clip(1 - bergman.POP["sleep_slope"] * debt[max(0, d - 2): d + 1].sum(), 0.75, 1.05)
    return out


def modifier_grids(s: Series, sleep_hours: np.ndarray | None = None, force_night: bool = False):
    """smod and dawn on the 5 minute grid, length N + PAD."""
    L = N + PAD
    k = np.arange(L)
    minute = k * STEP
    hour = (minute % 1440) / 60
    day = np.minimum(minute // 1440, config.N_DAYS - 1)
    hours = s.sleep_hours if sleep_hours is None else sleep_hours
    habitual = float(np.nanmedian(s.sleep_hours)) if np.isfinite(s.sleep_hours).any() else 7.0
    sm = sleep_multiplier(hours, habitual)[day]
    circ = 1 + bergman.POP["circ_amp"] * np.cos(2 * np.pi * (hour - 9) / 24)
    shift_day = np.where(hour < 7, day - 1, day)
    night = (hour >= 22) | (hour < 7)
    works = np.array([works_night(s.declared, int(d)) or force_night for d in range(-1, config.N_DAYS + 2)])
    mis = np.where(night & works[np.clip(shift_day + 1, 0, len(works) - 1)], 0.92, 1.0)
    dawn = np.exp(-0.5 * ((hour - 5.5) / 1.4) ** 2)
    return circ * sm * mis, dawn


@dataclass
class Prepared:
    s: Series
    smod: np.ndarray
    dawn: np.ndarray
    af_ff: np.ndarray
    meal_minutes: np.ndarray
    meal_carbs: np.ndarray
    dose_minutes: np.ndarray
    dose_unit: float
    extra: dict = field(default_factory=dict)


def prepare(s: Series, **kw) -> Prepared:
    smod, dawn = modifier_grids(s, **kw)
    af = np.where(s.meal_af > 0, s.meal_af, np.nan)
    idx = np.where(~np.isnan(af), np.arange(N), 0)
    np.maximum.accumulate(idx, out=idx)
    af_ff = np.where(np.isnan(af[idx]), 1.0, af[idx])
    meals = s.meal_log
    dm = np.flatnonzero((s.met_dose > 0) | (s.met_missed > 0)) * STEP
    unit = float(np.median(s.met_dose[s.met_dose > 0])) if (s.met_dose > 0).any() else 1.0
    return Prepared(s, smod, dawn, af_ff, meals.minute.to_numpy(float), meals.carbs.to_numpy(float), dm, unit)


def expected_meals(pp: Prepared, k0: int, H: int) -> list[tuple[int, float, float, str]]:
    """(step offset from origin, carbs, absorption factor, slot name) for meals not yet eaten.

    A meal the clinician or patient has planned replaces the routine slot within two hours of it.
    """
    s = pp.s
    t = k0 * STEP
    out = []
    planned = pp.extra.get("planned", [])
    for d in range(t // 1440 - 1, (t + H * STEP) // 1440 + 1):
        plan = day_plan(s.declared, int(d)) if 0 <= d < config.N_DAYS else "normal"
        for minute, carbs, kind, name in s.routine.get(plan) or s.routine.get("normal", []):
            if name == "Night snack" and not works_night(s.declared, int(d) - 1):
                continue
            T = d * 1440 + minute
            if T < t - 45 or T > t + H * STEP:
                continue
            if any(abs(T - pm) <= 120 for pm, *_ in planned):
                continue
            lo, hi = np.searchsorted(pp.meal_minutes, [T - 75, t + 0.5])
            if lo < hi and pp.meal_carbs[lo:hi].max() >= 0.4 * carbs:
                continue
            j = int(max(T - t, STEP) // STEP)
            if j < H:
                out.append((j, carbs, AF.get(kind, 1.0), name))
    for m, g, a, name in planned:
        if m < t - 45 or m > t + H * STEP:
            continue
        lo, hi = np.searchsorted(pp.meal_minutes, [m - 75, t + 0.5])
        if lo < hi and pp.meal_carbs[lo:hi].max() >= 0.4 * g:
            continue
        j = int(max(m - t, STEP) // STEP)
        if j < H:
            out.append((j, g, a, name))
    return sorted(out)


def expected_doses(pp: Prepared, k0: int, H: int) -> list[int]:
    s = pp.s
    if not s.on_metformin:
        return []
    t = k0 * STEP
    out = []
    bd = bool(s.ehr.get("t2d", 0))
    for d in range(t // 1440, (t + H * STEP) // 1440 + 1):
        plan = day_plan(s.declared, int(d)) if 0 <= d < config.N_DAYS else "normal"
        for minute, carbs, kind, name in s.routine.get(plan) or s.routine.get("normal", []):
            n = name.lower()
            is_b = "breakfast" in n or "suhoor" in n
            is_d = n.startswith("dinner") or "fasting dinner" in n
            if not (is_d or (is_b and bd)):
                continue
            T = d * 1440 + minute + 5
            if T <= t or T > t + H * STEP:
                continue
            lo, hi = np.searchsorted(pp.dose_minutes, [T - 90, t + 0.5])
            if lo < hi:
                continue
            j = int((T - t) // STEP)
            if j < H:
                out.append(j)
    return out


def _take(arr: np.ndarray, idx: np.ndarray, fill: float) -> np.ndarray:
    ok = (idx >= 0) & (idx < len(arr))
    out = np.full(idx.shape, fill, float)
    out[ok] = arr[idx[ok]]
    return out


def build(pp: Prepared, ks: np.ndarray, H: int, future: str = "routine"):
    """Inputs for windows [k-W, k+H) and the CGM used by the observer.

    future = "routine": the deployable forecast. future = "actual": logged inputs after the
    origin too (system identification during calibration, never used for forecasting).
    """
    s = pp.s
    ks = np.asarray(ks, int)
    B, S = len(ks), W + H
    idx = ks[:, None] + np.arange(-W, H)[None, :]
    carbs = _take(s.carbs, idx, 0.0)
    dose = _take(s.met_dose, idx, 0.0)
    A = np.minimum(_take(s.steps, idx, 0.0) / 100.0, 1.5)
    af = _take(pp.af_ff, idx, 1.0)
    obs = _take(s.cgm, idx, np.nan)
    smod = _take(pp.smod, idx, 1.0)
    dawn = _take(pp.dawn, idx, 0.0)
    if future == "routine":
        carbs[:, W:] = 0.0
        dose[:, W:] = 0.0
        A[:, W:] = 0.0
        af[:, W:] = af[:, W - 1: W]
        for b, k in enumerate(ks):
            for j, g, a, _ in expected_meals(pp, int(k), H):
                carbs[b, W + j] += g
                af[b, W + j:] = a
            for j in expected_doses(pp, int(k), H):
                dose[b, W + j] += pp.dose_unit
    obs[:, W + 1:] = np.nan
    return bergman.Inputs(carbs, af, A, dose, smod, dawn), obs


def initial_state(obs: np.ndarray, on_met: float) -> np.ndarray:
    first = np.where(np.isnan(obs), np.nan, obs)
    G0 = np.array([row[~np.isnan(row)][0] if (~np.isnan(row)).any() else 120.0 for row in first])
    return bergman.steady_state({}, G0, on_met)


def forecast(pp: Prepared, theta: np.ndarray, ks: np.ndarray, H: int, future: str = "routine") -> np.ndarray:
    """Twin glucose from each origin, [B, H+1]; column 0 is the filtered value at the origin."""
    u, obs = build(pp, ks, H, future)
    s = pp.s
    p = bergman.params_dict(np.repeat(np.atleast_2d(theta), len(ks), axis=0), s.bw, float(s.on_metformin))
    x0 = initial_state(obs, float(s.on_metformin))
    G, _ = bergman.run_rk4(p, x0, u, obs=obs, obs_until=W)
    return G[:, W:]


# Counterfactual scenarios --------------------------------------------------------------

@dataclass
class Scenario:
    walk_minutes: int = 0
    swap: str = "none"
    shift_hours: float = 0.0
    missed_dose: bool = False
    sleep_hours: float | None = None
    night_shift: bool = False
    scope: str = "next"   # "next": the next main meal; "all": every main meal in the horizon
    insulin_bolus_units: float = 0.0     # rapid acting insulin with each targeted main meal
    insulin_basal_units: float = 0.0     # long acting insulin per day, assumed at steady state
    metformin_shift_hours: float = 0.0   # move the evening metformin dose

    def is_baseline(self) -> bool:
        return self == Scenario(scope=self.scope)


def _future_meals(u: bergman.Inputs) -> list[list]:
    cols = np.flatnonzero(u.carbs[0, W:] > 0) + W
    return [[int(c), float(u.carbs[0, c]), float(u.af[0, c])] for c in cols]


def _write_future(u: bergman.Inputs, meals: list[list]) -> None:
    base = float(u.af[0, W - 1])
    u.carbs[0, W:] = 0.0
    u.af[0, W:] = base
    for c, g, a in sorted(meals):
        u.carbs[0, c] += g
        u.af[0, c:] = a


# Injected insulin uses population pharmacokinetics (nobody in the synthetic cohort is on insulin):
# distribution volume 0.12 L/kg; rapid acting appearance follows t/tau^2 exp(-t/tau) with a
# 55 minute peak; long acting insulin is taken as a flat appearance at steady state.
INSULIN_VD_ML_PER_KG = 120.0
BOLUS_TAU = 55.0


def insulin_appearance(H: int, bw: float, bolus_steps: list[int], units: float, basal_units: float) -> np.ndarray:
    """uU/mL per minute for each of H future steps."""
    vol = INSULIN_VD_ML_PER_KG * bw
    out = np.full(H, basal_units * 1e6 / vol / 1440.0)
    t = np.arange(H) * STEP + STEP / 2
    for b in bolus_steps:
        tt = t[: H - b]
        out[b:] += units * 1e6 / vol * tt / BOLUS_TAU ** 2 * np.exp(-tt / BOLUS_TAU)
    return out


def apply_scenario(pp: Prepared, k: int, H: int, sc: Scenario):
    """Returns (inputs, obs, x0, info) for the scenario at origin k."""
    s = pp.s
    if sc.sleep_hours is not None or sc.night_shift:
        hours = s.sleep_hours.copy()
        if sc.sleep_hours is not None:
            # "What if the last three nights (and tonight) had been this long": the twin's debt spans three nights.
            last = min((k * STEP) // 1440, config.N_DAYS - 1)
            hours[max(0, last - 2): last + 2] = sc.sleep_hours
        smod, _ = modifier_grids(s, sleep_hours=hours, force_night=sc.night_shift)
        pp = Prepared(**{**pp.__dict__, "smod": smod})
    u, obs = build(pp, np.array([k]), H)
    x0 = initial_state(obs, float(s.on_metformin))
    names = {W + j: name for j, g, a, name in expected_meals(pp, k, H)}
    meals = _future_meals(u)
    main = [m for m in meals if m[1] >= MAIN_MEAL_G]
    info = {"target_step": None, "target_carbs": None, "meals_changed": 0}
    factor, a_new = SWAPS.get(sc.swap, (1.0, None))
    shift = int(round(sc.shift_hours * 60 / STEP))
    walk_starts = []
    if sc.scope == "all":
        targets = main
    else:
        targets = main[:1]
        if not targets:
            past = np.flatnonzero(u.carbs[0, W - 18: W] >= MAIN_MEAL_G)
            if len(past):
                walk_starts.append(W)  # meal already eaten: a walk can still start now
    if targets:
        info.update(target_step=targets[0][0] - W, target_carbs=targets[0][1])
    first = targets[0][0] if targets else None
    for m in targets:
        c0 = m[0]
        is_dinner = names.get(c0, "").lower().startswith(("dinner", "fasting dinner"))
        if shift and (sc.scope == "next" or is_dinner):
            m[0] = int(np.clip(c0 + shift, W + 1, W + H - 1))
        m[1] *= factor
        if a_new is not None:
            m[2] = a_new
        walk_starts.append(max(m[0] + 2, W))
        info["meals_changed"] += 1
        if c0 == first:
            info["meal_step"] = m[0] - W
    _write_future(u, meals)
    if sc.walk_minutes:
        for st in walk_starts:
            u.A[0, st: st + int(np.ceil(sc.walk_minutes / STEP))] = 1.0
    if sc.missed_dose and s.on_metformin:
        u.dose[0, :] = 0.0
        x0[6] = 0.35
    if sc.metformin_shift_hours and s.on_metformin:
        move = int(round(sc.metformin_shift_hours * 60 / STEP))
        for c in np.flatnonzero(u.dose[0, W:] > 0) + W:
            hour = (((k + c - W) * STEP) % 1440) / 60
            if 16 <= hour < 24:
                d = float(u.dose[0, c])
                u.dose[0, c] = 0.0
                u.dose[0, int(np.clip(c + move, W, W + H - 1))] += d
    if sc.insulin_bolus_units or sc.insulin_basal_units:
        steps = sorted({m[0] - W for m in targets}) if sc.insulin_bolus_units else []
        ins = np.zeros_like(u.carbs)
        ins[0, W:] = insulin_appearance(H, float(s.bw), steps, sc.insulin_bolus_units, sc.insulin_basal_units)
        u.ins = ins
        info["insulin_steps"] = steps
    if sc.night_shift and not s.declared.get("night_shift"):
        t = k * STEP
        for j in range(1, H):
            if ((t + j * STEP) % 1440) == 90:
                _write_future(u, _future_meals(u) + [[W + j, 30.0, AF["tea_snack"]]])
                break
    return u, obs, x0, info


def simulate_scenario(pp: Prepared, theta: np.ndarray, k: int, H: int, sc: Scenario, method: str = "ivp") -> tuple[np.ndarray, dict]:
    """Twin trajectory from the origin under a scenario. Warm up uses RK4 with the observer,
    the counterfactual horizon uses solve_ivp so that scenario curves come from an adaptive solver."""
    u, obs, x0, info = apply_scenario(pp, k, H, sc)
    s = pp.s
    p = bergman.params_dict(np.atleast_2d(theta), s.bw, float(s.on_metformin))
    warm = u.window(0, W)
    _, x = bergman.run_rk4(p, x0, warm, obs=obs[:, :W], obs_until=W)
    # The reading at the origin itself corrects G before the horizon starts.
    if not np.isnan(obs[0, W]):
        x[0] += 0.5 * (obs[0, W] - x[0])
    fut = u.window(W)
    if method == "ivp":
        G = bergman.run_ivp(p, x, fut)
    else:
        G = bergman.run_rk4(p, x, fut)[0][0]
    return G, info
