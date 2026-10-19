"""One command synthetic data generation: python -m prativimb.data.generate

Writes:
  data/raw/ehr/<id>.json             FHIR R4 shaped bundle per patient
  data/raw/routines/<id>.json        patient reported routine (meal times, usual carbohydrate)
  data/raw/devices/<id>/...          Apple Health export.xml or Google Fit JSON (hero patients)
  data/processed/*.parquet           canonical wearable and log tables
  data/processed/truth_*.parquet     simulator ground truth (evaluation and audit only)
  data/splits.json                   patient level train / calibration / test split
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from prativimb import config
from prativimb.data import cohort as cohort_mod
from prativimb.data import devices, fhir, physiology, schedule, sensors
from prativimb.data.schedule import STAGE_NAMES


def declared_routine(p: cohort_mod.Patient, rng: np.random.Generator) -> dict:
    """What the patient tells the clinic at enrolment: rounded and a little off from reality."""
    plans = {"normal": p.routine["normal"]}
    if p.lifestyle["observes_ramadan"]:
        plans["ramadan"] = p.routine["ramadan"]
    if p.lifestyle["observes_hindu_fasts"]:
        plans["hindu_fast"] = p.routine["hindu_fast"]
    out = {"patient": p.id, "night_shift": p.night_shift, "night_off_weekday": 3 if p.night_shift else None,
           "observes_ramadan": p.lifestyle["observes_ramadan"],
           "observes_hindu_fasts": p.lifestyle["observes_hindu_fasts"],
           "celebrates_holi": p.lifestyle["celebrates_holi"], "plans": {}}
    for plan, slots in plans.items():
        out["plans"][plan] = [{
            "name": s.name,
            "minute": int(15 * round((s.minute + rng.normal(0, 10)) / 15)) % 1440,
            "carbs": float(5 * round(s.carbs * rng.lognormal(0, 0.15) / 5)),
            "kind": s.kind,
        } for s in slots]
    return out


def run(n_patients: int = config.N_PATIENTS, seed: int = config.SEED, verbose: bool = True) -> None:
    t0 = time.time()
    config.ensure_dirs()
    patients = cohort_mod.make_cohort(n_patients, seed)
    split = cohort_mod.split_of(patients, seed)
    seeds = np.random.SeedSequence(seed + 1).spawn(n_patients)
    rngs = [np.random.default_rng(s) for s in seeds]

    scheds = []
    for p, rng in zip(patients, rngs):
        s = schedule.build(p, rng)
        s.sens = schedule.sensitivity_multiplier(p, s, rng)
        strain = np.array([d["strain"] for d in s.days])
        fever = np.array([d["fever"] for d in s.days])
        s.egp = 1 + 0.04 * np.maximum(strain, 0) + 0.08 * fever
        scheds.append(s)
    if verbose:
        print(f"schedules built ({time.time() - t0:.1f}s)")

    inputs = {k: np.stack([getattr(s, k) for s in scheds]) for k in ("carbs", "absf", "steps", "metformin", "night_work")}
    inputs["sens_day"] = np.stack([s.sens for s in scheds])
    inputs["egp_day"] = np.stack([s.egp for s in scheds])
    sim = physiology.simulate(patients, inputs)
    if verbose:
        print(f"physiology simulated ({time.time() - t0:.1f}s)")

    tables = {k: [] for k in ("cgm", "hr", "sleep_segments", "sleep_nightly", "meals_log", "meals_truth", "doses",
                              "days_truth", "events", "truth_glucose", "routine")}
    raw_ehr = config.RAW_DIR / "ehr"
    raw_routine = config.RAW_DIR / "routines"
    raw_ehr.mkdir(parents=True, exist_ok=True)
    raw_routine.mkdir(parents=True, exist_ok=True)
    five = np.arange(0, config.N_DAYS * 1440, config.CGM_STEP)

    for i, (p, s, rng) in enumerate(zip(patients, scheds, rngs)):
        pid = p.id
        E = p.cardio.get("event_day")
        gap = s.gap  # device removed during the hospital attendance
        if E is not None:
            m = E * 1440 + int(p.cardio["event_hour"] * 60)
            tables["events"].append({"pid": pid, "minute": m, "day": E, "type": "cardiovascular_event",
                                     "description": "ED attendance, acute coronary syndrome (simulated)",
                                     "severity": round(p.cardio["event_severity"], 2)})
        compression = np.zeros(len(five), bool)
        glucose = sensors.cgm(p, sim["Gs"][i, five], s.stage[five], rng, gap, compression)
        hr = sensors.heart_rate(p, s, rng, gap)
        rmssd = sensors.nightly_rmssd(p, s, rng)

        tables["cgm"].append(pd.DataFrame({"pid": pid, "minute": five.astype(np.int32), "glucose": glucose.astype(np.float32)}))
        tables["truth_glucose"].append(pd.DataFrame({"pid": pid, "minute": five.astype(np.int32),
                                                     "bg": sim["G"][i, five], "gs": sim["Gs"][i, five],
                                                     "compression": compression}))
        tables["hr"].append(pd.DataFrame({"pid": pid, "minute": np.arange(len(hr), dtype=np.int32),
                                          "hr": hr.astype(np.float32), "steps": np.round(s.steps).astype(np.int16)}))
        tables["sleep_segments"].append(pd.DataFrame([{"pid": pid, "start": a, "end": b, "stage": STAGE_NAMES[v]}
                                                      for a, b, v in s.sleep_segments]))
        nights = pd.DataFrame(s.nights)
        nights["rmssd"] = nights.night.map(rmssd)
        nights.insert(0, "pid", pid)
        tables["sleep_nightly"].append(nights)
        tables["meals_log"].append(pd.DataFrame([{"pid": pid, "minute": m, "carbs": g, "kind": k, "description": d}
                                                 for m, g, k, d in s.meal_log]))
        tables["meals_truth"].append(pd.DataFrame([{"pid": pid, "minute": m, "carbs": g, "kind": k, "name": n}
                                                   for m, g, k, n in s.meals]))
        tables["doses"].append(pd.DataFrame([{"pid": pid, "minute": m, "drug": k, "dose": d, "taken": t}
                                             for m, k, d, t in s.doses]))
        days = pd.DataFrame(s.days)
        days.insert(0, "pid", pid)
        days["sens_mult"] = s.sens
        tables["days_truth"].append(days)

        (raw_ehr / f"{pid}.json").write_text(json.dumps(fhir.bundle(p), indent=1))
        routine = declared_routine(p, rng)
        (raw_routine / f"{pid}.json").write_text(json.dumps(routine, indent=1))
        for plan, slots in routine["plans"].items():
            for sl in slots:
                tables["routine"].append(pd.DataFrame([{"pid": pid, "plan": plan, **sl}]))

        if p.hero:
            folder = config.RAW_DIR / "devices" / pid
            cgm_df = tables["cgm"][-1][["minute", "glucose"]]
            hr_df = tables["hr"][-1][["minute", "hr", "steps"]]
            sl_df = tables["sleep_segments"][-1][["start", "end", "stage"]]
            hrv_df = pd.DataFrame({"minute": nights.wake_minute, "rmssd": nights.rmssd})
            if p.device == "apple_health":
                devices.write_apple(folder / "apple_health_export.xml", p.given, cgm_df, hr_df, sl_df, hrv_df)
            else:
                devices.write_google(folder / "google_fit", cgm_df, hr_df, sl_df, hrv_df)

    file_names = {"meals_truth": "truth_meals", "days_truth": "truth_days"}
    for name, parts in tables.items():
        if name == "events":
            df = pd.DataFrame(parts, columns=["pid", "minute", "day", "type", "description", "severity"])
        else:
            parts = [x for x in parts if len(x)]
            df = pd.concat(parts, ignore_index=True)
        fname = file_names.get(name, name)
        df.to_parquet(config.PROCESSED_DIR / f"{fname}.parquet", index=False, compression="zstd")
    (config.DATA_DIR / "splits.json").write_text(json.dumps(split, indent=1, sort_keys=True))
    hidden = [{"pid": p.id, "phenotype": p.phenotype, **{k: v for k, v in p.physio.items()},
               "cv_risk": p.cardio["risk_score"], "event_day": p.cardio.get("event_day")} for p in patients]
    pd.DataFrame(hidden).to_parquet(config.PROCESSED_DIR / "truth_patients.parquet", index=False)
    if verbose:
        print(f"files written ({time.time() - t0:.1f}s)")

    from prativimb.data import ingest
    ingest.run(verbose=verbose)
    if verbose:
        print(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    run()
