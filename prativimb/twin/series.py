"""Per patient time series on the 5 minute grid, built only from what the system can observe.

Observed means: CGM readings, logged meals, wearable steps and heart rate, sleep summaries,
dose confirmations, the EHR and the routine the patient declared at enrolment. Simulator
ground truth never enters here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import duckdb
import numpy as np
import pandas as pd

from prativimb import config

STEP = config.CGM_STEP
N = config.N_DAYS * 1440 // STEP
PER_DAY = 1440 // STEP


@dataclass
class Series:
    pid: str
    ehr: dict
    cgm: np.ndarray          # [N] mg/dL, NaN when missing
    carbs: np.ndarray        # [N] grams logged in the step
    meal_af: np.ndarray      # [N] absorption factor of the meal logged in the step (0 if none)
    steps: np.ndarray        # [N] mean steps per minute over the step
    hr: np.ndarray           # [N] mean heart rate, NaN when off wrist
    met_dose: np.ndarray     # [N] metformin dose units confirmed taken
    met_missed: np.ndarray   # [N] metformin doses confirmed missed
    sleep_hours: np.ndarray  # [D] sleep that ended on day d (NaN if not recorded)
    nightly: pd.DataFrame
    routine: dict            # plan -> list of slots (minute, carbs, kind, name)
    declared: dict
    meal_log: pd.DataFrame = field(repr=False, default=None)

    @property
    def on_metformin(self) -> bool:
        return bool(self.ehr.get("on_metformin", 0))

    @property
    def bw(self) -> float:
        return float(self.ehr.get("weight", 70.0))


def day_plan(declared: dict, d: int) -> str:
    date = config.START.date() + timedelta(days=d)
    if declared.get("observes_ramadan") and date >= config.RAMADAN_FIRST_FAST:
        return "ramadan"
    if declared.get("observes_hindu_fasts") and (date == config.MAHA_SHIVARATRI or date in config.EKADASHI):
        return "hindu_fast"
    return "normal"


def works_night(declared: dict, d: int) -> bool:
    if not declared.get("night_shift"):
        return False
    return (config.START.date() + timedelta(days=d)).weekday() != declared.get("night_off_weekday", 3)


def load_all(con: duckdb.DuckDBPyConnection | None = None, pids: list[str] | None = None) -> dict[str, Series]:
    from prativimb.data.cohort import MEAL_TYPES

    own = con is None
    con = con or duckdb.connect(str(config.DB_PATH), read_only=True)
    where = ""
    if pids:
        where = "WHERE pid IN (" + ",".join(f"'{p}'" for p in pids) + ")"
    ehr = con.execute(f"SELECT * FROM ehr_features {where}").df().set_index("pid")
    cgm = con.execute(f"SELECT pid, minute, glucose FROM cgm {where}").df()
    hr5 = con.execute(f"""SELECT pid, minute // {STEP} AS k, avg(hr) AS hr, sum(steps) / {STEP}.0 AS spm
                          FROM hr {where} GROUP BY 1, 2""").df()
    meals = con.execute(f"SELECT * FROM meals_log {where} ORDER BY pid, minute").df()
    doses = con.execute(f"SELECT * FROM doses {where}").df()
    nightly = con.execute(f"SELECT * FROM sleep_nightly {where}").df()
    routine = con.execute(f"SELECT * FROM routine {where}").df()
    if own:
        con.close()

    import json
    declared_all = {p.stem: json.loads(p.read_text()) for p in (config.RAW_DIR / "routines").glob("*.json")}
    af = {k: v[1] for k, v in MEAL_TYPES.items()}

    out = {}
    cgm_g = dict(tuple(cgm.groupby("pid")))
    hr_g = dict(tuple(hr5.groupby("pid")))
    meal_g = dict(tuple(meals.groupby("pid")))
    dose_g = dict(tuple(doses.groupby("pid")))
    night_g = dict(tuple(nightly.groupby("pid")))
    rout_g = dict(tuple(routine.groupby("pid")))
    for pid in ehr.index:
        c = np.full(N, np.nan)
        g = cgm_g[pid]
        c[(g.minute.to_numpy() // STEP)] = g.glucose.to_numpy()
        h = hr_g[pid]
        k = h.k.to_numpy()
        hr = np.full(N, np.nan)
        hr[k] = h.hr.to_numpy()
        spm = np.zeros(N)
        spm[k] = h.spm.to_numpy()
        carbs, maf = np.zeros(N), np.zeros(N)
        ml = meal_g.get(pid, pd.DataFrame(columns=meals.columns))
        for m, gr, kind in zip(ml.minute.to_numpy(), ml.carbs.to_numpy(), ml.kind.to_numpy()):
            i = int(m) // STEP
            if 0 <= i < N:
                carbs[i] += gr
                maf[i] = af[kind]
        md, mm = np.zeros(N), np.zeros(N)
        ds = dose_g.get(pid, pd.DataFrame(columns=doses.columns))
        ds = ds[ds.drug == "metformin"]
        for m, dose, taken in zip(ds.minute.to_numpy(), ds.dose.to_numpy(), ds.taken.to_numpy()):
            i = int(m) // STEP
            if taken:
                md[i] += 1.0 if str(dose).startswith("1000") else 0.7
            else:
                mm[i] += 1
        sh = np.full(config.N_DAYS, np.nan)
        nt = night_g.get(pid)
        if nt is not None:
            sh[nt.night.to_numpy()] = nt.total_sleep_min.to_numpy() / 60
        r = rout_g.get(pid)
        plans = {}
        if r is not None:
            for plan, grp in r.groupby("plan"):
                plans[plan] = [(int(a), float(b), str(c), str(d)) for a, b, c, d in
                               zip(grp.minute, grp.carbs, grp.kind, grp.name)]
        out[pid] = Series(pid=pid, ehr=ehr.loc[pid].to_dict(), cgm=c, carbs=carbs, meal_af=maf, steps=spm, hr=hr,
                          met_dose=md, met_missed=mm, sleep_hours=sh, nightly=nt, routine=plans,
                          declared=declared_all.get(pid, {}), meal_log=ml)
    return out
