"""The reference answer to a what if question.

The synthetic patients come from the UVA/Padova based simulator in physiology.py, which is
richer than the twin (two compartment stomach, portal insulin, counter regulation, renal loss,
insulin independent uptake by working muscle). Because it is deterministic, any patient can be
rebuilt exactly and re-run from any minute with one behaviour changed. The twin never sees it.
This module answers: had Ramesh walked after dinner, what would his glucose have done?

Changes are applied to what the patient actually did (the true meal times and sizes), not to the
routine the twin assumes, so the comparison also includes the twin's uncertainty about the meal.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from prativimb import config
from prativimb.data import cohort as cohort_mod
from prativimb.data import physiology, schedule
from prativimb.twin.forecast import MAIN_MEAL_G, SWAPS

WALK_STEPS = 100.0        # steps per minute for a brisk walk; the twin's activity input is steps / 100
WALK_DELAY = 10           # minutes after the meal, as in the twin's scenarios
INPUTS = ("carbs", "absf", "steps", "metformin", "night_work")


@dataclass
class Change:
    walk_minutes: int = 0
    swap: str = "none"
    shift_hours: float = 0.0
    carb_factor: float = 1.0


@lru_cache(maxsize=1)
def cohort() -> dict:
    patients = cohort_mod.make_cohort(config.N_PATIENTS, config.SEED)
    seeds = np.random.SeedSequence(config.SEED + 1).spawn(config.N_PATIENTS)
    return {"patients": {p.id: p for p in patients}, "index": {p.id: i for i, p in enumerate(patients)}, "seeds": seeds}


@lru_cache(maxsize=256)
def patient_inputs(pid: str):
    """Schedule and simulator inputs for one patient, rebuilt with the same random stream as the data."""
    c = cohort()
    p = c["patients"][pid]
    rng = np.random.default_rng(c["seeds"][c["index"][pid]])
    s = schedule.build(p, rng)
    s.sens = schedule.sensitivity_multiplier(p, s, rng)
    strain = np.array([d["strain"] for d in s.days])
    fever = np.array([d["fever"] for d in s.days])
    s.egp = 1 + 0.04 * np.maximum(strain, 0) + 0.08 * fever
    inputs = {k: getattr(s, k)[None, :].astype(float) if k != "night_work" else getattr(s, k)[None, :] for k in INPUTS}
    inputs["sens_day"], inputs["egp_day"] = s.sens[None, :], s.egp[None, :]
    P = physiology.build_params([p])
    return p, s, inputs, P


def states_at(pid: str, minutes: list[int]) -> dict[int, dict]:
    """Simulator state at the start of each minute, from one pass from the beginning."""
    _, _, inputs, P = patient_inputs(pid)
    last = max(minutes)
    cps = {m: None for m in minutes}
    sl = {k: (v[:, :last + 1] if k in INPUTS else v) for k, v in inputs.items()}
    physiology.run(P, sl, physiology.initial_state(P), 0, cps)
    return cps


_STATE_CACHE: dict[tuple[str, int], dict] = {}
CHECKPOINTS = config.ARTIFACT_DIR / "reference_states.npz"


def build_checkpoints(verbose: bool = True) -> None:
    """Simulator state at every midnight for every patient, so any what if starts at most a day back."""
    import time
    t0 = time.time()
    pids = list(cohort()["patients"])
    parts = [patient_inputs(pid) for pid in pids]
    inputs = {k: np.concatenate([x[2][k] for x in parts]) for k in (*INPUTS, "sens_day", "egp_day")}
    P = physiology.build_params([x[0] for x in parts])
    cps = {d * 1440: None for d in range(config.N_DAYS)}
    physiology.run(P, inputs, physiology.initial_state(P), 0, cps)
    np.savez_compressed(CHECKPOINTS, pids=np.array(pids),
                        **{f"{k}__{d}": cps[d * 1440][k] for d in range(config.N_DAYS) for k in physiology.STATE_KEYS})
    _checkpoints.cache_clear()
    if verbose:
        print(f"reference checkpoints for {len(pids)} patients ({time.time() - t0:.0f}s)")


@lru_cache(maxsize=1)
def _checkpoints():
    if not CHECKPOINTS.exists():
        return None
    z = np.load(CHECKPOINTS)
    return {"index": {p: i for i, p in enumerate(z["pids"])}, "z": {k: z[k] for k in z.files if k != "pids"}}


def state_at(pid: str, minute: int) -> dict:
    key = (pid, int(minute))
    if key in _STATE_CACHE:
        return _STATE_CACHE[key]
    if len(_STATE_CACHE) > 128:
        _STATE_CACHE.clear()
    cp = _checkpoints()
    if cp is None:
        st = states_at(pid, [int(minute)])[int(minute)]
    else:
        d = int(minute) // 1440
        i = cp["index"][pid]
        st = {k: cp["z"][f"{k}__{d}"][i: i + 1].copy() for k in physiology.STATE_KEYS}
        _, _, inputs, P = patient_inputs(pid)
        span = int(minute) - d * 1440
        if span:
            sl = {k: (v[:, d * 1440: int(minute)] if k in INPUTS else v) for k, v in inputs.items()}
            physiology.run(P, sl, st, d * 1440)
    _STATE_CACHE[key] = st
    return st


def target_meal(s, t: int, horizon: int) -> tuple[int, float, float] | None:
    """The next main meal the patient really ate after minute t: (minute, carbs, absorption)."""
    for m, g, kind, _name in s.meals:
        if t <= m < t + horizon and g >= MAIN_MEAL_G:
            return int(m), float(g), float(s.absf[m])
    return None


def changed_inputs(pid: str, t: int, horizon: int, ch: Change, scope: str = "next") -> tuple[dict, list[int]]:
    """Inputs from minute t for `horizon` minutes, with the change applied to the next (or every) main meal."""
    _, s, inputs, _ = patient_inputs(pid)
    T = inputs["carbs"].shape[1]
    end = min(t + horizon, T)
    out = {k: inputs[k][:, t:end].copy() for k in INPUTS}
    out["sens_day"], out["egp_day"] = inputs["sens_day"], inputs["egp_day"]
    meals = [(int(m), float(g)) for m, g, _k, _n in s.meals if t <= m < end and g >= MAIN_MEAL_G]
    if scope == "next":
        meals = meals[:1]
    factor, af_new = SWAPS.get(ch.swap, (1.0, None))
    factor *= ch.carb_factor
    shift = int(round(ch.shift_hours * 60))
    changed = []
    for m, g in meals:
        r = m - t
        af = float(out["absf"][0, r])
        out["carbs"][0, r] -= g
        new = int(np.clip(r + shift, 1, end - t - 1))
        out["carbs"][0, new] += g * factor
        out["absf"][0, new] = af_new if af_new is not None else af
        changed.append(t + new)
        if ch.walk_minutes:
            w0 = new + WALK_DELAY
            out["steps"][0, w0: w0 + ch.walk_minutes] = np.maximum(out["steps"][0, w0: w0 + ch.walk_minutes], WALK_STEPS)
    return out, changed


def run_from(pid: str, t: int, inputs: dict) -> np.ndarray:
    """Interstitial glucose (what a noise free CGM would read) every minute from t."""
    _, _, _, P = patient_inputs(pid)
    st = {k: v.copy() for k, v in state_at(pid, t).items()}
    return physiology.run(P, inputs, st, t)["Gs"][0]


def what_if(pid: str, t: int, horizon: int, ch: Change, scope: str = "next") -> dict:
    """Usual against changed, at 5 minute resolution, as the reference simulator sees it."""
    base, _ = changed_inputs(pid, t, horizon, Change(), scope)
    alt, moved = changed_inputs(pid, t, horizon, ch, scope)
    gb, ga = run_from(pid, t, base), run_from(pid, t, alt)
    summary = lambda g: {"peak": float(g.max()), "tar_min": int((g > 180).sum()), "tbr_min": int((g < 70).sum()),
                         "mean": float(g.mean()), "tir_pct": float(np.mean((g >= 70) & (g <= 180)) * 100)}
    b, a = summary(gb), summary(ga)
    _, s, _, _ = patient_inputs(pid)
    tm = target_meal(s, t, horizon)
    return {"minutes": int(len(gb)), "baseline": gb[::5].tolist(), "scenario": ga[::5].tolist(), "baseline_summary": b,
            "scenario_summary": a, "delta": {k: a[k] - b[k] for k in ("peak", "tar_min", "mean", "tir_pct")},
            "meal": {"minute": tm[0], "carbs": tm[1]} if tm else None, "changed_minutes": moved}
