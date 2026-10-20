"""Everything the API computes, as of the replay clock."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, replace
from datetime import timedelta

import duckdb
import joblib
import numpy as np
import pandas as pd

from prativimb import config
from prativimb.api.store import ClinicalStore
from prativimb.data.cohort import MEAL_TYPES
from prativimb.ml import conformal
from prativimb.ml import explain as explain_mod
from prativimb.ml.features import glucose_features
from prativimb.ml.glucose import lower_bound
from prativimb.twin import bergman, forecast, series
from prativimb.twin.series import PER_DAY, STEP

PARAMS = list(bergman.PARAMS)
SHORT = {"t2d": "T2D", "prediabetes": "Prediabetes", "hypertension": "HTN", "dyslipidemia": "Dyslipidaemia",
         "obesity": "Obesity", "fh_cad": "FH IHD", "shift_work": "Shift work", "tobacco": "Smoker"}


def iso(minute: float) -> str:
    return config.minute_to_datetime(minute).isoformat()


def hhmm(minute: float) -> str:
    return config.minute_to_datetime(minute).strftime("%H:%M")


CARDIO_SHORT = {"rhr": "resting heart rate up", "rmssd": "heart rate variability down", "deep_min": "less deep sleep",
                "rem_min": "less REM sleep", "awake_min": "more time awake", "awakenings": "broken sleep",
                "efficiency": "poor sleep", "sleep_h": "short sleep", "steps": "fewer steps", "z_composite": "away from usual"}
GROUPS = ("low", "high", "heart", "watch")
LEVER_WEEK = {"Walk 15 min after the meal": "Walk 15 min after every main meal",
              "Walk 30 min after the meal": "Walk 30 min after every main meal",
              "Millets instead of white rice": "Millets instead of white rice at main meals",
              "Brown rice instead of white rice": "Brown rice instead of white rice at main meals",
              "Roti instead of rice": "Roti instead of rice at main meals", "Half the portion": "Half portions at main meals",
              "Meal 1 h earlier": "Dinner 1 h earlier every day", "Sleep 7.5 h for three nights": "Sleep 7.5 h every night",
              "Walk 15 min and millets": "Walk 15 min and millets at main meals"}


ACTION_NAMES = {"call": "Called the patient", "review": "Booked a review", "check": "Checked the patient now"}
ALERT_NAMES = {"spike": "high glucose alert", "low": "low glucose alert", "cardio": "heart risk alert"}


def short_reason(ex: dict | None) -> str:
    """Two or three words per driver for the ward list, from the same explanation the patient page shows."""
    if not ex:
        return ""
    out = []
    for d in sorted(ex["drivers"], key=lambda r: -r["mgdl"]):
        t = d["text"]
        if (d["mgdl"] <= 2 or d["category"] in ("trend", "calendar") or t.startswith(("recent walking", "no ", "medication taken"))):
            continue
        if t.startswith("expected "):
            w = t.split(" (")[0].replace("expected ", "")
        elif t.startswith("recent meal"):
            w = "recent meal"
        elif "missed metformin" in t:
            w = "missed metformin"
        elif t.startswith("reduced insulin"):
            w = "low insulin sensitivity"
        elif t.startswith("little activity"):
            w = "little activity"
        elif t.startswith("short sleep"):
            w = "short sleep" + (", night shift" if "night shift" in t else "")
        else:
            w = t.split(" (")[0]
        if w not in out:
            out.append(w)
    # A standing trait does not help tell one patient's alert from another's; name it only if nothing else shows.
    situational = [w for w in out if w != "low insulin sensitivity"]
    return ", ".join((situational or out)[:2])


def abha_number(pid: str) -> str:
    """A synthetic 14 digit number in the ABHA layout; not a real health ID."""
    d = "".join(str(int(c, 16) % 10) for c in hashlib.sha1(pid.encode()).hexdigest())[:12]
    return f"91-{d[:4]}-{d[4:8]}-{d[8:12]}"


def clean(x):
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), 4)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


@dataclass
class Row:
    pid: str
    k: int
    feats: pd.DataFrame
    G: np.ndarray
    hyb: dict
    lo90: dict
    hi90: dict
    lo_alert: dict
    qlo: dict
    low_p: float = 0.0


class AppState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        con = duckdb.connect(str(config.DB_PATH), read_only=True)
        self.S = series.load_all(con)
        q = lambda sql: con.execute(sql).df()
        self.patients = q("SELECT * FROM patients").set_index("pid")
        self.ehr = q("SELECT * FROM ehr_features").set_index("pid")
        self.conditions = q("SELECT * FROM conditions")
        self.meds = q("SELECT * FROM medications")
        self.obs = q("SELECT * FROM observations")
        self.genetics = q("SELECT * FROM genetics")
        self.events = q("SELECT * FROM events")
        self.meals = q("SELECT * FROM meals_log")
        self.doses = q("SELECT * FROM doses")
        self.segments = q("SELECT * FROM sleep_segments")
        self.nightly = q("SELECT * FROM sleep_nightly")
        con.close()
        self.split = json.loads((config.DATA_DIR / "splits.json").read_text())
        self.twins = pd.read_parquet(config.ARTIFACT_DIR / "twins.parquet").set_index("pid")
        self.bundle = joblib.load(config.ARTIFACT_DIR / "glucose_models.joblib")
        self.alert_cov = json.loads((config.ARTIFACT_DIR / "alert_config.json").read_text())["alert_coverage"]
        cm = joblib.load(config.ARTIFACT_DIR / "cardio_model.joblib")
        self.cardio_threshold = cm["threshold"]
        self.cardio_scores = pd.read_parquet(config.ARTIFACT_DIR / "cardio_scores.parquet")
        self.cardio_daily = pd.read_parquet(config.ARTIFACT_DIR / "cardio_daily.parquet")
        self.cardio_windows = pd.read_parquet(config.ARTIFACT_DIR / "cardio_windows.parquet")
        self.metrics = json.loads((config.REPORT_DIR / "metrics.json").read_text())
        self._pp: dict[tuple, forecast.Prepared] = {}
        self._ward_cache: tuple[tuple, list] | None = None
        self.store = ClinicalStore()
        low_path = config.ARTIFACT_DIR / "low_model.joblib"
        self.low = joblib.load(low_path) if low_path.exists() else None
        self._asleep: dict[str, np.ndarray] = {}
        try:
            self.seed_demo_plan()
        except Exception as exc:  # a demo convenience must never stop the service
            print("demo plan not seeded:", exc)

    # basics --------------------------------------------------------------------------
    def theta(self, pid: str, minute: float | None = None) -> np.ndarray:
        """Calibrated parameters, the EHR prior during the first week, or a later refit once one has been made."""
        if minute is not None and self.calibrating(minute):
            return self.twins.loc[pid, [f"prior_{p}" for p in PARAMS]].to_numpy(float)
        if minute is not None:
            r = self.store.refit(pid, minute)
            if r:
                return np.array(r["theta"], float)
        return self.twins.loc[pid, PARAMS].to_numpy(float)

    # walks the patient logged: the replay follows the reference simulator ------------
    def sync(self, minute: float) -> None:
        """Apply patient logged walks to the replayed data, as of the clock. Called before every request.

        The demo replays recorded synthetic data, so a walk a patient logs would otherwise change nothing that
        follows. Here the reference simulator re-runs that patient from the start of the walk with it included,
        and the replayed CGM after that point becomes the reference glucose plus the sensor noise the original
        reading had. Heart rate and steps show the walk too. Removing the walk restores the original data.
        """
        acts = [a for a in self.store.activities if a["entered_minute"] <= minute and a["kind"] == "walk"]
        key = tuple(sorted(a["id"] for a in acts)) + tuple(sorted(r["id"] for r in self.store.refits if r["minute"] <= minute))
        if key == getattr(self, "_sync_key", ()):
            return
        with self.lock:
            orig = self.__dict__.setdefault("_S_orig", {})
            for pid, sr in orig.items():
                self.S[pid] = sr
            orig.clear()
            for pid in sorted({a["pid"] for a in acts}):
                orig[pid] = self.S[pid]
                try:
                    self.S[pid] = self._walked(pid, [a for a in acts if a["pid"] == pid])
                except Exception as exc:  # the replay must never break because of a demo effect
                    print("walk not applied:", exc)
            self._sync_key = key
            self._pp.clear()
            self._ward_cache = None
            self._hist_key = None

    def _walked(self, pid: str, walks: list[dict]):
        from prativimb.data import reference
        s = self.S[pid]
        t_s = min(a["start"] for a in walks)
        end = config.N_DAYS * 1440
        if t_s >= end:
            return s
        base, _ = reference.changed_inputs(pid, t_s, end - t_s, reference.Change())
        alt = {k: (v.copy() if k in reference.INPUTS else v) for k, v in base.items()}
        for a in walks:
            r0 = a["start"] - t_s
            alt["steps"][0, r0: r0 + a["minutes"]] = np.maximum(alt["steps"][0, r0: r0 + a["minutes"]], reference.WALK_STEPS)
        delta = reference.run_from(pid, t_s, alt) - reference.run_from(pid, t_s, base)
        k0 = -(-t_s // STEP)
        idx = np.arange(k0, min(len(s.cgm), end // STEP))
        cgm, steps, hr = s.cgm.copy(), s.steps.copy(), s.hr.copy()
        cgm[idx] = cgm[idx] + delta[idx * STEP - t_s]
        for a in walks:
            w = np.arange(a["start"] // STEP, min(len(steps), (a["start"] + a["minutes"]) // STEP))
            steps[w] = np.maximum(steps[w], reference.WALK_STEPS)
            hr[w] = np.where(np.isnan(hr[w]), hr[w], hr[w] + 22)
        return replace(s, cgm=cgm, steps=steps, hr=hr)

    @staticmethod
    def calibrating(minute: float) -> int | None:
        """Day number (1 to 7) while the twin is still in its calibration week, else None."""
        d = int(minute // 1440)
        return d + 1 if d < config.CALIBRATION_DAYS else None

    def pp(self, pid: str, minute: float | None = None) -> forecast.Prepared:
        """Prepared inputs, including meals entered by a clinician or patient up to the clock time."""
        entries = self.store.meals_for(pid, minute) if minute is not None else []
        walks = [a for a in self.store.activities_for(pid, minute) if a["kind"] == "walk"] if minute is not None else []
        key = (pid, tuple(e["id"] for e in entries), tuple(a["id"] for a in walks))
        if key not in self._pp:
            s = self.S[pid]
            logged = [e for e in entries if e["type"] == "logged"]
            if logged:
                carbs, maf = s.carbs.copy(), s.meal_af.copy()
                for e in logged:
                    i = int(e["minute"]) // STEP
                    carbs[i] += e["carbs"]
                    maf[i] = MEAL_TYPES.get(e["kind"], ("", 1.0))[1]
                extra = pd.DataFrame([{"pid": pid, "minute": e["minute"], "carbs": e["carbs"], "kind": e["kind"],
                                       "description": e["label"]} for e in logged])
                ml = pd.concat([s.meal_log, extra], ignore_index=True).sort_values("minute")
                s = replace(s, carbs=carbs, meal_af=maf, meal_log=ml)
            pp = forecast.prepare(s)
            pp.extra["planned"] = [(e["minute"], e["carbs"], MEAL_TYPES.get(e["kind"], ("", 1.0))[1], e["label"])
                                   for e in entries if e["type"] == "planned"]
            # A walk the patient said they will take enters the forecast at the time the twin expects it.
            pp.extra["walks"] = [(a.get("planned_start", a["start"]), a["minutes"]) for a in walks]
            self._pp[key] = pp
        return self._pp[key]

    def origin(self, pid: str, minute: float) -> int | None:
        """Latest step at or before the clock with a CGM reading in the last 30 minutes."""
        c = self.S[pid].cgm
        k = int(minute // STEP)
        for j in range(k, max(k - 7, -1), -1):
            if j < len(c) and not np.isnan(c[j]):
                return j
        return None

    def problems(self, pid: str) -> list[str]:
        flags = self.conditions[self.conditions.pid == pid].flag.tolist()
        return [SHORT[f] for f in SHORT if f in flags]

    # forecasting ---------------------------------------------------------------------
    def forecast_rows(self, pids: list[str], minute: float) -> dict[str, Row]:
        jobs = []
        for pid in pids:
            if self.store.withdrawn(pid, "cgm", minute):
                continue
            k = self.origin(pid, minute)
            if k is not None and k >= forecast.W:
                jobs.append((pid, k, minute))
        return {r.pid: r for r in self._rows(jobs)}

    def _rows(self, jobs: list[tuple[str, int, float]], theta: np.ndarray | None = None) -> list[Row]:
        """Forecast rows for (patient, origin step, clock minute) jobs, batched per patient (theta: one patient's override)."""
        if not jobs:
            return []
        groups: dict[tuple, list[int]] = {}
        for i, (pid, k, minute) in enumerate(jobs):
            groups.setdefault((pid, self.calibrating(k * STEP) is not None), []).append(i)
        rows: list[Row | None] = [None] * len(jobs)
        frames, order = [], []
        for (pid, _), idx in groups.items():
            minute = jobs[idx[0]][2]
            pp, th = self.pp(pid, minute), (theta if theta is not None else self.theta(pid, jobs[idx[0]][1] * STEP))
            ks = np.array([jobs[i][1] for i in idx])
            G = forecast.forecast(pp, th, ks, 24)
            f = glucose_features(pp, ks, G, th)
            for j, i in enumerate(idx):
                rows[i] = Row(pid, int(ks[j]), None, G[j], {}, {}, {}, {}, {})
            frames.append(f)
            order += idx
        X = pd.concat(frames, ignore_index=True)
        for n, i in enumerate(order):
            rows[i].feats = X.iloc[[n]]
        if self.low is not None:
            lp = self.low["model"].predict_proba(X[self.low["features"]])[:, 1]
            for n, i in enumerate(order):
                rows[i].low_p = float(lp[n])
        b = self.bundle
        for h in config.HORIZONS:
            m = b["models"][h]
            tw = X[f"tw{h}"].to_numpy()
            hyb = tw + m["hybrid"].predict(X[b["features"]])
            qlo = tw + m["q_lo"].predict(X[b["features"]])
            qhi = tw + m["q_hi"].predict(X[b["features"]])
            lo, hi = conformal.cqr_interval(qlo, qhi, m["cqr_q"])
            la = lower_bound(b, h, qlo, self.alert_cov)
            for n, i in enumerate(order):
                r = rows[i]
                r.hyb[h], r.qlo[h] = float(hyb[n]), float(qlo[n])
                r.lo90[h], r.hi90[h] = float(min(lo[n], hyb[n])), float(max(hi[n], hyb[n]))
                r.lo_alert[h] = float(min(la[n], hyb[n]))
        return rows

    def curve(self, r: Row) -> dict:
        """Two hour hybrid curve at 5 minute steps: twin shape plus interpolated residual corrections."""
        hs = np.array([0] + list(config.HORIZONS)) / STEP
        steps = np.arange(25)
        cg = float(r.feats.cgm.iloc[0])
        resid = np.array([cg - r.G[0]] + [r.hyb[h] - r.G[int(h / STEP)] for h in config.HORIZONS])
        mid = r.G + np.interp(steps, hs, resid)
        dlo = np.interp(steps, hs, [8.0] + [r.hyb[h] - r.lo90[h] for h in config.HORIZONS])
        dhi = np.interp(steps, hs, [8.0] + [r.hi90[h] - r.hyb[h] for h in config.HORIZONS])
        dla = np.interp(steps, hs, [4.0] + [r.hyb[h] - r.lo_alert[h] for h in config.HORIZONS])
        return {"steps": steps, "mid": mid, "lo": mid - dlo, "hi": mid + dhi, "lo_alert": mid - dla, "twin": r.G}

    def status(self, r: Row, cv: dict | None = None) -> dict:
        c = self.curve(r)
        cg = float(r.feats.cgm.iloc[0])
        mid = c["mid"]
        j = int(np.argmax(mid[1:])) + 1
        out = {"glucose": cg, "trend30": float(r.feats.d30.iloc[0]) if np.isfinite(r.feats.d30.iloc[0]) else None,
               "peak": float(mid[j]), "peak_minute": (r.k + j) * STEP, "tier": None, "low": None}
        above = np.flatnonzero(mid > config.SPIKE_THRESHOLD)
        conf = np.flatnonzero(c["lo_alert"] > config.SPIKE_THRESHOLD)
        if cg <= config.SPIKE_THRESHOLD and len(conf):
            out["tier"] = "alert"
            out["cross_minute"] = (r.k + int(conf[0])) * STEP
        elif cg <= config.SPIKE_THRESHOLD and len(above):
            out["tier"] = "watch"
            out["cross_minute"] = (r.k + int(above[0])) * STEP
        elif cg > config.SPIKE_THRESHOLD:
            out["tier"] = "high"
        out["in_2h"] = float(mid[-1])
        out["origin_minute"] = r.k * STEP
        cal = self.calibrating(r.k * STEP)
        if cal:
            out["calibrating"] = cal
            if out["tier"] == "alert":
                out["tier"] = "watch"  # first week: the twin is not fitted yet, so nothing is pushed
        out["low_p"] = r.low_p
        if cg < config.LOW_THRESHOLD:
            out["low"] = "artefact" if self.suspect_compression(r.pid, r.k) else "now"
        elif self.low is not None and r.low_p >= self.low["threshold"]:
            out["low"] = "forecast"
            lows = np.flatnonzero(mid < config.LOW_THRESHOLD + 5)
            j = int(lows[0]) if len(lows) else int(np.argmin(mid[:13]))
            out["low_minute"] = (r.k + j) * STEP
            out["low_value"] = float(mid[:13].min())
        return out

    def suspect_compression(self, pid: str, k: int) -> bool:
        from prativimb.ml import hypo
        if pid not in self._asleep:
            self._asleep[pid] = hypo.asleep_mask(self.S[pid])
        return hypo.suspect_now(self.S[pid].cgm, self._asleep[pid], k)

    # ward ----------------------------------------------------------------------------
    def ward(self, minute: float) -> list[dict]:
        step = (int(minute // STEP), self.store.version)
        with self.lock:
            if self._ward_cache and self._ward_cache[0] == step:
                return self._ward_cache[1]
        pids = list(self.patients.index)
        rows = self.forecast_rows(pids, minute)
        health = self.health_all(minute) if not self.calibrating(minute) else {}
        out = []
        for pid in pids:
            p = self.patients.loc[pid]
            e = self.ehr.loc[pid]
            c = self.S[pid].cgm
            k_now = int(minute // STEP)
            spark = c[max(0, k_now - PER_DAY + 1): k_now + 1]
            spark = spark[::3]
            valid = np.flatnonzero(~np.isnan(c[: k_now + 1]))
            last_sync = int(valid[-1]) * STEP if len(valid) else None
            cv = self.cardio_now(pid, minute)
            st = self.status(rows[pid]) if pid in rows else None
            if st and st["tier"] == "alert" and not self.calibrating(minute):
                r = rows[pid]
                feats = r.feats.iloc[0].to_dict()
                hs = list(config.HORIZONS)
                peak_h = hs[int(np.argmin([abs(h - (st["peak_minute"] - r.k * STEP)) for h in hs]))]
                st["reason"] = short_reason(explain_mod.explain(self.pp(pid, minute), self.theta(pid, minute), r.k,
                                                                self.bundle, r.feats, feats, peak_h))
            if st and st["low"] == "forecast":
                st["low_reason"] = f"{st['low_p'] * 100:.0f}% chance"
            elif st and st["low"] == "now":
                st["low_reason"] = f"reading {st['glucose']:.0f}"
            acks = {k: self.store.active_ack(pid, k, minute) for k in ("spike", "low", "cardio")}
            pr = 0
            if st:
                st["ack"] = acks["spike"] if st["tier"] == "alert" else None
                if st["low"] == "artefact":
                    st["low"], st["artefact"] = None, True
                st["low_ack"] = acks["low"] if st["low"] else None
                pr += {"alert": 8 if st["ack"] else 40, "watch": 10, "high": 6}.get(st["tier"], 0)
                pr += (5 if st["low_ack"] else 25) if st["low"] else 0
                pr += max(st["peak"] - 140, 0) / 10
            cv["ack"] = acks["cardio"] if cv["flag"] else None
            if cv["flag"]:
                pr += 6 if cv["ack"] else 30
            group = None
            if st and st["low"] in ("now", "forecast"):
                group = "low"
            elif st and st["tier"] == "alert":
                group = "high"
            elif cv["flag"]:
                group = "heart"
            elif st and st["tier"] == "watch":
                group = "watch"
            seen = bool((group == "low" and st["low_ack"]) or (group == "high" and st["ack"]) or (group == "heart" and cv["ack"]))
            paused = [src for src in ("cgm", "wearable") if self.store.withdrawn(pid, src, minute)]
            pr += cv["risk"] * 20 if cv["risk"] is not None else 0
            out.append(clean({
                "id": pid, "name": f"{p.given} {p.family}", "age": int(e.age), "sex": "M" if p.sex == "male" else "F",
                "problems": self.problems(pid), "hba1c": float(e.hba1c), "glucose": st and st["glucose"],
                "trend30": st and st["trend30"], "sparkline": [None if np.isnan(v) else float(v) for v in spark],
                "event_a": st, "event_b": cv, "last_sync": last_sync and iso(last_sync), "priority": pr,
                "group": group, "seen": seen, "sharing_paused": paused, "calibrating": self.calibrating(minute),
                "twin_fit": health.get(pid),
                "hero": pid in config.HERO_IDS.values(), "split": self.split[pid],
            }))
        rank = {g: i for i, g in enumerate(GROUPS)}
        out.sort(key=lambda r: (rank.get(r["group"], 9), r["seen"], -r["priority"]))
        with self.lock:
            self._ward_cache = (step, out)
        return out

    # cardio --------------------------------------------------------------------------
    def cardio_now(self, pid: str, minute: float) -> dict:
        day = int(minute // 1440) - 1  # last complete day
        sc = self.cardio_scores[(self.cardio_scores.pid == pid) & (self.cardio_scores.day <= day)]
        ev = self.events[(self.events.pid == pid) & (self.events.minute <= minute)]
        if len(ev):
            return {"risk": None, "flag": False, "post_event": True, "event_minute": int(ev.minute.iloc[0]),
                    "event": ev.description.iloc[0], "day": day}
        if not len(sc):
            return {"risk": None, "flag": False, "post_event": False, "day": day}
        if self.store.withdrawn(pid, "wearable", minute):
            return {"risk": None, "flag": False, "post_event": False, "day": day, "paused": True}
        last = sc.sort_values("day").iloc[-1]
        prev = sc[sc.flag].day
        first_flag = None
        if last.flag:
            run = sc.sort_values("day").set_index("day").flag
            d = int(last.day)
            while d - 1 in run.index and run.loc[d - 1]:
                d -= 1
            first_flag = d
        reason = ""
        if last.flag:
            fs = [f["factor"] for f in json.loads(last.factors) if f["factor"] in CARDIO_SHORT][:2]
            reason = ", ".join(CARDIO_SHORT[f] for f in fs)
        return {"risk": float(last.risk), "flag": bool(last.flag), "post_event": False, "day": int(last.day),
                "flag_since": first_flag, "flags_in_window": int(len(prev)), "reason": reason}

    def cardio_view(self, pid: str, minute: float, end_day: int | None = None) -> dict:
        today = int(minute // 1440)
        last_complete = today - 1
        end = min(end_day if end_day is not None else last_complete, last_complete)
        d = self.cardio_daily[self.cardio_daily.pid == pid].set_index("day")
        days = list(range(end - 6, end + 1))
        base = d.loc[: end - 7]
        rows = []
        metrics = ["rhr", "rmssd", "deep_min", "rem_min", "core_min", "awake_min", "awakenings", "efficiency", "sleep_h", "steps"]
        sign = {"rhr": 1, "rmssd": -1, "deep_min": -1, "rem_min": -1, "core_min": 0, "awake_min": 1, "awakenings": 1,
                "efficiency": -1, "sleep_h": -1, "steps": -1}
        for m in metrics:
            mu, sd = base[m].mean(), base[m].std()
            vals = [d[m].get(x, np.nan) if x in d.index else np.nan for x in days]
            z = [(v - mu) / sd * sign[m] if sd and np.isfinite(sd) and sd > 0 and np.isfinite(v) else None for v in vals]
            rows.append({"metric": m, "values": vals, "adverse_z": z, "baseline": mu})
        sc = self.cardio_scores[(self.cardio_scores.pid == pid) & (self.cardio_scores.day <= last_complete)].sort_values("day")
        traj = [{"day": int(r.day), "date": (config.START.date() + timedelta(days=int(r.day))).isoformat(),
                 "risk": None if r.post_event else float(r.risk), "flag": bool(r.flag) and not r.post_event,
                 "post_event": bool(r.post_event)} for r in sc.itertuples()]
        cur = sc[sc.day == end]
        factors = json.loads(cur.factors.iloc[0]) if len(cur) else []
        ev = self.events[(self.events.pid == pid) & (self.events.minute <= minute)]
        return clean({
            "pid": pid, "end_day": end, "dates": [(config.START.date() + timedelta(days=x)).isoformat() for x in days],
            "metrics": rows, "trajectory": traj, "threshold": self.cardio_threshold,
            "risk": float(cur.risk.iloc[0]) if len(cur) and not cur.post_event.iloc[0] else None,
            "flag": bool(cur.flag.iloc[0]) and not bool(cur.post_event.iloc[0]) if len(cur) else False,
            "factors": factors,
            "event": ({"minute": int(ev.minute.iloc[0]), "time": iso(int(ev.minute.iloc[0])), "day": int(ev.day.iloc[0]),
                       "description": ev.description.iloc[0]} if len(ev) else None),
            "summary": self.cardio_now(pid, minute),
        })

    # patient detail ------------------------------------------------------------------
    def detail(self, pid: str, minute: float | None = None) -> dict:
        p, e, tw = self.patients.loc[pid], self.ehr.loc[pid], self.twins.loc[pid]
        cond = self.conditions[self.conditions.pid == pid]
        obs = self.obs[self.obs.pid == pid]
        lab_keys = ["hba1c", "fpg", "ldl", "hdl", "tg", "tc", "creatinine", "egfr"]
        vit_keys = ["sbp", "dbp", "bmi", "weight", "waist"]
        from prativimb.data.fhir import LOINC

        def obs_list(keys):
            out = []
            for key in keys:
                o = obs[obs.key == key].sort_values("date")
                if not len(o):
                    continue
                last = o.iloc[-1]
                prev = o.iloc[-2] if len(o) > 1 else None
                out.append({"code": {"system": "http://loinc.org", "code": last.loinc, "display": LOINC[key][1]},
                            "value": float(last.value), "unit": last.unit, "text": key, "effectiveDateTime": last.date,
                            "previous": float(prev.value) if prev is not None else None,
                            "previousDate": prev.date if prev is not None else None})
            return out
        smoke = obs[obs.key == "smoking"].text
        abdm_off = minute is not None and self.store.withdrawn(pid, "abdm", minute)
        if abdm_off:
            cond, obs = cond.iloc[0:0], obs.iloc[0:0]
        out = {
            "patient": {"id": pid, "name": f"{p.given} {p.family}", "gender": p.sex, "birthDate": p.birth_date,
                        "age": int(e.age), "city": p.city, "occupation": p.occupation, "nightShift": bool(p.night_shift)},
            "conditions": [{"code": {"system": "http://hl7.org/fhir/sid/icd-10", "code": c.code, "display": c.display},
                            "onsetDateTime": c.onset} for c in cond[~cond.code.str.startswith("FH:")].itertuples()],
            "medications": [{"medication": {"system": "http://www.whocc.no/atc", "code": m.atc, "display": m.name},
                             "dosage": m.dosage, "effectiveStart": m.start, "drugClass": m.drug_class}
                            for m in self.meds[self.meds.pid == pid].itertuples()],
            "labs": obs_list(lab_keys), "vitals": obs_list(vit_keys),
            "genetics": [{"gene": g.gene, "rsid": g.rsid, "genotype": g.genotype, "riskAlleles": int(g.risk_alleles)}
                         for g in self.genetics[self.genetics.pid == pid].itertuples()],
            "familyHistory": cond[cond.code.str.startswith("FH:")].display.tolist(),
            "socialHistory": [f"Smoking: {smoke.iloc[0]}" if len(smoke) else "Smoking: not recorded",
                              f"Occupation: {p.occupation}"],
            "consent": "DPDP consent artefact on file: treatment purpose, valid to "
                       f"{(config.START + timedelta(days=365)).strftime('%d %b %Y')}, revocable (synthetic record)",
            "twin": {
                "insulin_sensitivity_pct_typical": float(tw.SI / explain_mod.TYPICAL["SI"] * 100),
                "glucose_effectiveness": float(tw.SG), "basal_glucose": float(tw.Gb),
                "absorption_half_time_min": float(np.log(2) / tw.ka),
                "secretion_pct_typical": float(tw.gamma / explain_mod.TYPICAL["gamma"] * 100),
                "calibration_rmse_prior": float(tw.rmse_prior), "calibration_rmse_fit": float(tw.rmse_fit),
            },
            "device": {"apple_health": "Apple Health", "google_fit": "Google Fit"}.get(p.device, p.device),
            "context": self.context(pid),
            "split": self.split[pid],
            "abha": abha_number(pid),
            "records_withheld": bool(abdm_off),
            "calibrating": self.calibrating(minute) if minute is not None else None,
        }
        if abdm_off:
            out["medications"], out["genetics"], out["familyHistory"] = [], [], []
        return out

    def consent_view(self, pid: str, minute: float) -> list[dict]:
        p = self.patients.loc[pid]
        device = {"apple_health": "Apple Health", "google_fit": "Google Fit"}.get(p.device, p.device)
        names = {"cgm": ("Continuous glucose monitor", "Dexcom G6 readings every 5 minutes"),
                 "wearable": ("Wearable", f"Heart rate, sleep and steps from {device}"),
                 "abdm": ("Health records through ABDM (simulated)",
                          f"Conditions, medicines and lab results linked to ABHA {abha_number(pid)}")}
        out = []
        for src, (name, what) in names.items():
            c = self.store.consent(pid, src, minute)
            out.append({"source": src, "name": name, "what": what, "granted": c["granted"] if c else True,
                        "since": iso(c["minute"]) if c else config.START.isoformat(), "by": c["by"] if c else "Enrolment",
                        "purpose": "Care management by the diabetes clinic", "valid_until": "14 Feb 2027"})
        return clean(out)

    def context(self, pid: str) -> list[str]:
        dec = self.S[pid].declared
        out = []
        if dec.get("night_shift"):
            out.append("Night shifts, Thursday off")
        if dec.get("observes_ramadan"):
            out.append(f"Observing Ramadan fasts since {config.RAMADAN_FIRST_FAST.strftime('%d %b')}")
        if dec.get("observes_hindu_fasts"):
            out.append("Keeps Ekadashi and Shivaratri fasts")
        return out

    def agp(self, pid: str, minute: float, days: int = 14) -> dict:
        """Ambulatory glucose profile and the international consensus CGM metrics (Battelino et al. 2019)."""
        c = self.S[pid].cgm
        k1 = int(minute // STEP) + 1
        k0 = max(0, k1 - days * PER_DAY)
        x = c[k0:k1]
        tod = (np.arange(k0, k1) % PER_DAY) // 3  # 15 minute bins
        rows = []
        for b in range(96):
            v = x[(tod == b) & ~np.isnan(x)]
            if len(v) >= 3:
                q = np.percentile(v, [5, 25, 50, 75, 95])
                rows.append({"minute": b * 15, "p5": q[0], "p25": q[1], "p50": q[2], "p75": q[3], "p95": q[4]})
        v = x[~np.isnan(x)]
        mean = float(v.mean())
        return clean({
            "days": days, "profile": rows, "coverage": float(len(v) / max(len(x), 1) * 100),
            "metrics": {"mean": mean, "gmi": 3.31 + 0.02392 * mean, "cv": float(v.std() / mean * 100),
                        "tir": float(np.mean((v >= 70) & (v <= 180)) * 100), "tar": float(np.mean(v > 180) * 100),
                        "tar250": float(np.mean(v > 250) * 100), "tbr": float(np.mean(v < 70) * 100),
                        "tbr54": float(np.mean(v < 54) * 100)},
        })

    def timeline(self, pid: str, minute: float, hours: int = 12) -> dict:
        s = self.S[pid]
        k1 = int(minute // STEP)
        k0 = max(0, k1 - hours * 12 + 1)
        ks = np.arange(k0, k1 + 1)
        lo_m, hi_m = k0 * STEP, minute
        m = self.meals[(self.meals.pid == pid) & (self.meals.minute >= lo_m) & (self.meals.minute <= hi_m)]
        entered = [e for e in self.store.meals_for(pid, minute) if e["type"] == "logged" and lo_m <= e["minute"] <= hi_m]
        if entered:
            m = pd.concat([m, pd.DataFrame([{"pid": pid, "minute": e["minute"], "carbs": e["carbs"], "kind": e["kind"],
                                             "description": f"{e['label']} (entered by {e['by']})"} for e in entered])],
                          ignore_index=True)
        dz = self.doses[(self.doses.pid == pid) & (self.doses.minute >= lo_m) & (self.doses.minute <= hi_m)]
        sg = self.segments[(self.segments.pid == pid) & (self.segments.end >= lo_m) & (self.segments.start <= hi_m)]
        return clean({
            "start": iso(lo_m), "now": iso(minute),
            "cgm": [{"t": iso(k * STEP), "v": None if np.isnan(s.cgm[k]) else float(s.cgm[k])} for k in ks],
            "hr": [{"t": iso(k * STEP), "v": None if np.isnan(s.hr[k]) else float(s.hr[k])} for k in ks],
            "steps": [{"t": iso(k * STEP), "v": float(s.steps[k] * STEP)} for k in ks],
            "meals": [{"t": iso(r.minute), "carbs": float(r.carbs), "description": r.description, "kind": r.kind}
                      for r in m.itertuples()],
            "doses": [{"t": iso(r.minute), "drug": r.drug, "dose": r.dose, "taken": bool(r.taken)} for r in dz.itertuples()],
            "sleep": [{"start": iso(max(r.start, lo_m)), "end": iso(min(r.end, hi_m)), "stage": r.stage} for r in sg.itertuples()],
        })

    def patient_forecast(self, pid: str, minute: float, explain: bool = True) -> dict:
        w = self.store.withdrawn(pid, "cgm", minute)
        if w:
            return {"available": False, "paused": True, "alerts": [], "entries": [],
                    "reason": f"Glucose sharing withdrawn by {w['by']} at {hhmm(w['minute'])}. No readings are used until it is granted again."}
        rows = self.forecast_rows([pid], minute)
        if pid not in rows:
            return {"available": False, "reason": "No CGM reading in the last 30 minutes.", "alerts": [], "entries": []}
        r = rows[pid]
        c = self.curve(r)
        st = self.status(r)
        out = {
            "available": True, "origin": iso(r.k * STEP),
            "points": [{"t": iso((r.k + j) * STEP), "mid": c["mid"][j], "lo": c["lo"][j], "hi": c["hi"][j],
                        "lo_alert": c["lo_alert"][j], "twin": c["twin"][j]} for j in c["steps"]],
            "horizons": [{"h": h, "mid": r.hyb[h], "lo": r.lo90[h], "hi": r.hi90[h], "lo_alert": r.lo_alert[h]}
                         for h in config.HORIZONS],
            "status": st, "alert_level": self.alert_cov, "interval": 0.9,
        }
        if explain:
            hs = list(config.HORIZONS)
            peak_h = hs[int(np.argmin([abs(h - (st["peak_minute"] - r.k * STEP)) for h in hs]))]
            feats = r.feats.iloc[0].to_dict()
            ex = explain_mod.explain(self.pp(pid, minute), self.theta(pid, minute), r.k, self.bundle, r.feats, feats, peak_h)
            out["explanation"] = ex
        out["alerts"] = self.alert_cards(pid, minute, st, out.get("explanation"))
        out["entries"] = [{**e, "t": iso(e["minute"])} for e in self.store.meals_for(pid, minute)]
        return clean(out)

    def alert_log(self, pid: str, minute: float, hours: int = 6, every: int = 15) -> list[dict]:
        """What the twin said at earlier times today, so a clinician can see an alert was raised in advance."""
        out = []
        for m, st in self.statuses(pid, minute, minute - hours * 60, every):
            if st["tier"] in ("alert", "watch") or st["low"]:
                out.append({"t": iso(m), "glucose": st["glucose"], "tier": st["tier"], "low": st["low"],
                            "peak": st["peak"], "peak_time": hhmm(st["peak_minute"]),
                            "low_value": st.get("low_value"),
                            "cross_time": hhmm(st["cross_minute"]) if "cross_minute" in st else None})
        return clean(out)

    def alert_cards(self, pid: str, minute: float, st: dict, ex: dict | None) -> list[dict]:
        cards = self._alert_cards(pid, minute, st, ex)
        for c in cards:
            a = self.store.active_ack(pid, c["kind"], minute) if c["kind"] in ("spike", "low", "cardio") else None
            c["ack"] = {**a, "t": iso(a["minute"]), "until_t": iso(a["until"])} if a else None
        return cards

    def _alert_cards(self, pid: str, minute: float, st: dict, ex: dict | None) -> list[dict]:
        cards = []
        if st.get("calibrating"):
            cards.append({"kind": "calibrating", "tier": "info", "title": f"First week: day {st['calibrating']} of 7",
                          "detail": "The glucose forecast is still learning this patient. Until day 7 it uses values "
                                    "estimated from the health record (HbA1c, BMI, age, medicines), its ranges are wider, "
                                    "and possible highs are shown as Glucose may go high rather than pushed as alerts.",
                          "reason": ""})
        sent = ex["sentence"] if ex else ""
        if st["tier"] in ("alert", "watch"):
            cards.append({
                "kind": "spike", "tier": st["tier"],
                "title": ("High glucose likely within 2 hours" if st["tier"] == "alert" else "Glucose may go high within 2 hours"),
                "detail": f"Glucose forecast peak {st['peak']:.0f} mg/dL around {hhmm(st['peak_minute'])}; "
                          f"crossing 180 near {hhmm(st['cross_minute'])}."
                          + (f" At least a {(1 + self.alert_cov) / 2:.0%} chance of exceeding 180." if st["tier"] == "alert" else ""),
                "reason": sent,
            })
        if st["tier"] == "high":
            h2 = st.get("in_2h")
            cards.append({
                "kind": "high_now", "tier": "watch", "title": "Glucose above 180 now",
                "detail": f"Reading {st['glucose']:.0f} mg/dL"
                          + (f"; the forecast expects about {h2:.0f} by {hhmm(st['origin_minute'] + 120)}." if h2 else "."),
                "reason": sent,
            })
        if st["low"] in ("now", "forecast"):
            cards.append({
                "kind": "low", "tier": "alert",
                "title": "Low glucose now" if st["low"] == "now" else "Low glucose likely within the hour",
                "detail": (f"Current reading {st['glucose']:.0f} mg/dL." if st["low"] == "now" else
                           f"Low glucose model: {st['low_p'] * 100:.0f}% probability; forecast minimum "
                           f"{st.get('low_value', 0):.0f} mg/dL around {hhmm(st['low_minute'])}."),
                "reason": "",
            })
            if st["peak"] > config.SPIKE_THRESHOLD:
                cards[-1]["detail"] += f" Rebound to {st['peak']:.0f} mg/dL expected after the next meal."
        if st["low"] == "artefact":
            cards.append({
                "kind": "artefact", "tier": "info", "title": "Low reading, probably the sensor",
                "detail": f"{st['glucose']:.0f} mg/dL reached by a fall of more than 1 mg/dL per minute during sleep. "
                          "Pressure on the sensor gives this pattern; check again in 15 minutes or confirm with a fingerstick.",
                "reason": "",
            })
        cv = self.cardio_now(pid, minute)
        if cv.get("paused"):
            cards.append({"kind": "paused", "tier": "info", "title": "Wearable sharing withdrawn",
                          "detail": "Heart risk is not worked out while the patient has withdrawn wearable sharing.", "reason": ""})
        if cv.get("flag"):
            sc = self.cardio_scores[(self.cardio_scores.pid == pid) & (self.cardio_scores.day == cv["day"])]
            f = json.loads(sc.factors.iloc[0]) if len(sc) else []
            since = cv.get("flag_since")
            cards.append({
                "kind": "cardio", "tier": "alert", "title": "Raised heart risk",
                "detail": f"Seven day wearable pattern; estimated {cv['risk'] * 100:.0f}% chance of a heart event within 3 days"
                          + (f", flagged since {(config.START.date() + timedelta(days=since)).strftime('%d %b')}." if since is not None else "."),
                "reason": "; ".join(x["text"] for x in f[:3]),
            })
        if cv.get("post_event"):
            cards.append({"kind": "event", "tier": "info", "title": "Heart event recorded",
                          "detail": f"{cv['event']}, {config.minute_to_datetime(cv['event_minute']).strftime('%d %b %H:%M')}.",
                          "reason": "Risk scoring paused after an event."})
        return cards

    # what if -------------------------------------------------------------------------
    def whatif(self, pid: str, minute: float, req: dict) -> dict:
        req = dict(req)
        horizon_h = int(req.pop("horizon_h", 6) or 6)
        k = self.origin(pid, minute)
        if k is None:
            return {"available": False}
        pp, th = self.pp(pid, minute), self.theta(pid, minute)
        H = horizon_h * 60 // STEP
        scope = req.get("scope", "next")
        method = "rk4" if horizon_h > 24 else "ivp"  # a week of steps: the fixed step integrator (tests check they agree)
        base, info0 = forecast.simulate_scenario(pp, th, k, H, forecast.Scenario(scope=scope), method=method)
        alt, info = forecast.simulate_scenario(pp, th, k, H, forecast.Scenario(**req), method=method)

        def summary(g):
            g = np.asarray(g)[1:]
            j = int(np.argmax(g))
            return {"peak": float(g[j]), "peak_time": hhmm((k + j + 1) * STEP),
                    "tar_min": int((g > 180).sum() * STEP), "tbr_min": int((g < 70).sum() * STEP),
                    "tir_pct": float(np.mean((g >= 70) & (g <= 180)) * 100),
                    "mean": float(g.mean()), "auc_above_180": float(np.maximum(g - 180, 0).sum() * STEP / 60)}
        b, a = summary(base), summary(alt)
        target = None
        if info0.get("target_step") is not None:
            ts = info0["target_step"]
            target = {"time": hhmm((k + ts) * STEP), "carbs": info0["target_carbs"],
                      "new_time": hhmm((k + info.get("meal_step", ts)) * STEP)}
        note = ("Mechanistic twin only. The learned correction is trained for 2 h forecasts and cancels in the difference.")
        if req.get("insulin_bolus_units") or req.get("insulin_basal_units"):
            note += (" Insulin uses population insulin action, not this patient's (nobody in the synthetic cohort is on insulin); "
                     "check the lowest value before reading anything else.")
        if horizon_h > 6:
            note += (" Beyond about 6 hours absolute levels drift (the twin runs high for some patients), so the chart shows "
                     "the change against the usual plan rather than the level.")
        every = 3 if horizon_h > 24 else 1
        js = range(0, H + 1, every)
        days = []
        if horizon_h > 24:
            for d in range(horizon_h // 24):
                gb, ga = np.asarray(base)[1 + d * PER_DAY: 1 + (d + 1) * PER_DAY], np.asarray(alt)[1 + d * PER_DAY: 1 + (d + 1) * PER_DAY]
                days.append({"day": d + 1, "tir_change": float((np.mean((ga >= 70) & (ga <= 180)) - np.mean((gb >= 70) & (gb <= 180))) * 100),
                             "mean_change": float(ga.mean() - gb.mean()), "lowest": float(ga.min())})
        return clean({
            "available": True, "origin": iso(k * STEP), "horizon_h": horizon_h, "scope": scope,
            "solver": "fixed step RK4 (a week of steps)" if horizon_h > 24 else "scipy.integrate.solve_ivp (RK45)",
            "times": [iso((k + j) * STEP) for j in js], "baseline": [base[j] for j in js], "scenario": [alt[j] for j in js],
            "days": days, "insulin_steps": info.get("insulin_steps", []),
            "baseline_summary": b, "scenario_summary": a,
            "delta": {"peak": a["peak"] - b["peak"], "tar_min": a["tar_min"] - b["tar_min"], "mean": a["mean"] - b["mean"],
                      "auc_above_180": a["auc_above_180"] - b["auc_above_180"], "tir_pct": a["tir_pct"] - b["tir_pct"]},
            "target_meal": target, "meals_changed": info.get("meals_changed", 0), "request": {**req, "horizon_h": horizon_h},
            "note": note,
        })

    LEVERS = [
        ("Walk 15 min after the meal", {"walk_minutes": 15}),
        ("Walk 30 min after the meal", {"walk_minutes": 30}),
        ("Millets instead of white rice", {"swap": "millet"}),
        ("Brown rice instead of white rice", {"swap": "brown_rice"}),
        ("Roti instead of rice", {"swap": "roti"}),
        ("Half the portion", {"swap": "half_portion"}),
        ("Meal 1 h earlier", {"shift_hours": -1.0}),
        ("Sleep 7.5 h for three nights", {"sleep_hours": 7.5}),
        ("Walk 15 min and millets", {"walk_minutes": 15, "swap": "millet"}),
    ]

    def rank_levers(self, pid: str, minute: float, horizon_h: int = 6, scope: str = "next") -> dict:
        """Try every lever on this patient's twin and rank by how much each lowers the peak and time above 180."""
        key = (pid, int(minute // STEP), horizon_h, scope, self.store.version)
        cache = self.__dict__.setdefault("_rank_cache", {})
        if key not in cache:
            if len(cache) > 64:
                cache.clear()
            cache[key] = self._rank_levers(pid, minute, horizon_h, scope)
        return cache[key]

    def _rank_levers(self, pid: str, minute: float, horizon_h: int, scope: str) -> dict:
        rows = []
        if horizon_h > 24:
            scope = "all"
        for label, req in self.LEVERS:
            if horizon_h > 24:
                label = LEVER_WEEK.get(label, label)
            r = self.whatif(pid, minute, {**req, "horizon_h": horizon_h, "scope": scope})
            if not r.get("available"):
                return {"available": False, "levers": []}
            d = r["delta"]
            rows.append({"label": label, "request": req, "peak": d["peak"], "tar_min": d["tar_min"],
                         "auc_above_180": d["auc_above_180"], "mean": d["mean"], "tir_pct": d["tir_pct"],
                         "combined": "and" in label})
        if horizon_h > 24:
            key = lambda x: (-x["tir_pct"], x["mean"])
        elif horizon_h > 6:
            key = lambda x: (x["auc_above_180"], x["peak"])
        else:
            key = lambda x: (x["peak"], x["tar_min"])
        rows.sort(key=key)
        return clean({"available": True, "horizon_h": horizon_h, "scope": scope, "levers": rows,
                      "target_meal": r.get("target_meal")})

    # note ----------------------------------------------------------------------------
    def note(self, pid: str, minute: float) -> dict:
        det = self.detail(pid)
        fc = self.patient_forecast(pid, minute)
        cv = self.cardio_view(pid, minute)
        s = self.S[pid]
        k = int(minute // STEP)
        day = s.cgm[max(0, k - PER_DAY + 1): k + 1]
        week = s.cgm[max(0, k - 7 * PER_DAY + 1): k + 1]
        tir = lambda x: (np.nanmean((x >= 70) & (x <= 180)) * 100, np.nanmean(x > 180) * 100, np.nanmean(x < 70) * 100)
        d_tir, w_tir = tir(day[~np.isnan(day)]), tir(week[~np.isnan(week)])
        mean7 = float(np.nanmean(week))
        gmi = 3.31 + 0.02392 * mean7
        nights = self.nightly[(self.nightly.pid == pid) & (self.nightly.wake_minute <= minute)].sort_values("night").tail(3)
        meals_today = self.meals[(self.meals.pid == pid) & (self.meals.minute <= minute) &
                                 (self.meals.minute >= (minute // 1440) * 1440)]
        missed = self.doses[(self.doses.pid == pid) & (self.doses.minute <= minute) &
                            (self.doses.minute >= minute - 1440) & (~self.doses.taken)]
        ranked = self.rank_levers(pid, minute)
        S_ = [
            f"Occupation: {det['patient']['occupation']}.",
            f"Sleep last 3 nights: {', '.join(f'{n / 60:.1f} h' for n in nights.total_sleep_min)}.",
            f"Meals logged today: {len(meals_today)} ({meals_today.carbs.sum():.0f} g carbohydrate)." if len(meals_today)
            else "No meals logged today.",
            f"Missed doses in 24 h: {', '.join(sorted(set(missed.drug)))}." if len(missed) else "No missed doses recorded in 24 h.",
        ]
        if s.declared.get("observes_ramadan") and forecast.day_plan(s.declared, int(minute // 1440)) == "ramadan":
            S_.append("Observing Ramadan fasts (suhoor and iftar pattern).")
        labs = {l["text"]: l for l in det["labs"]}
        O_ = [
            f"CGM now {fc['status']['glucose']:.0f} mg/dL ({fc['status']['trend30'] or 0:+.0f} in 30 min)." if fc.get("available") else "CGM: no recent reading.",
            f"Last 24 h: time in range {d_tir[0]:.0f}%, above 180 {d_tir[1]:.0f}%, below 70 {d_tir[2]:.0f}%.",
            f"Last 7 days: mean {mean7:.0f} mg/dL, GMI {gmi:.1f}%, time in range {w_tir[0]:.0f}%.",
            f"HbA1c {labs['hba1c']['value']:.1f}% ({labs['hba1c']['effectiveDateTime']}); LDL {labs['ldl']['value']:.0f} mg/dL; "
            f"eGFR {labs['egfr']['value']:.0f}.",
        ]
        rm = next((m for m in cv["metrics"] if m["metric"] == "rmssd"), None)
        rh = next((m for m in cv["metrics"] if m["metric"] == "rhr"), None)
        if rm and rh:
            O_.append(f"Wearable 7 days: resting HR {np.nanmean([v for v in rh['values'] if v is not None]):.0f} bpm "
                      f"(baseline {rh['baseline']:.0f}); nightly RMSSD {np.nanmean([v for v in rm['values'] if v is not None]):.0f} ms "
                      f"(baseline {rm['baseline']:.0f}).")
        A_ = [f"{c['title']}. {c['detail']} {c['reason']}".strip() for c in fc.get("alerts", [])] or \
             ["No active glucose or heart risk alerts."]
        tw = det["twin"]
        A_.append(f"Glucose forecast calibration: insulin sensitivity about {tw['insulin_sensitivity_pct_typical']:.0f}% of a typical adult "
                  f"without diabetes; fit error {tw['calibration_rmse_fit']:.0f} mg/dL over the calibration week.")
        P_ = []
        helpful = [r for r in ranked.get("levers", []) if r["peak"] < -5 and not r["combined"]][:3]
        if helpful:
            meal = ranked.get("target_meal") or {}
            P_.append("Simulated changes for the next main meal" + (f" ({meal.get('time')})" if meal else "") + ", ranked: "
                      + "; ".join(f"{r['label'].lower()}: peak {r['peak']:+.0f} mg/dL, time above 180 {r['tar_min']:+.0f} min"
                                  for r in helpful) + ".")
        early = next((r for r in ranked.get("levers", []) if r["request"] == {"shift_hours": -1.0}), None)
        if early and early["peak"] > 3:
            P_.append(f"Simulated: eating that meal earlier does not help tonight (peak {early['peak']:+.0f} mg/dL); "
                      "glucose from the previous meal has not settled.")
        if cv.get("flag"):
            P_.append("Consider clinical review of cardiovascular symptoms, blood pressure and ECG given the raised heart risk.")
        P_.append("Review with the patient; the simulated changes are hypotheses, not prescriptions.")
        return clean({
            "patient": det["patient"], "generated": iso(minute), "problems": self.problems(pid),
            "medications": [m["dosage"] for m in det["medications"]],
            "S": S_, "O": O_, "A": A_, "P": P_,
            "disclaimer": "Decision support only, not a diagnosis. Generated from synthetic data by Prativimb.",
        })

    # history and follow up -----------------------------------------------------------
    def statuses(self, pid: str, minute: float, start: float, every: int = 15) -> list[tuple[float, dict]]:
        """Status at each check time in (start, minute], using what was known then (batched)."""
        start = max(start, forecast.W * STEP)
        ms = np.arange(start - start % every + every, minute + 1, every)
        jobs, keep = [], []
        for m in ms:
            if self.store.withdrawn(pid, "cgm", float(m)):
                continue
            k = self.origin(pid, float(m))
            if k is not None and k >= forecast.W:
                jobs.append((pid, k, minute))
                keep.append(float(m))
        return [(m, self.status(r)) for m, r in zip(keep, self._rows(jobs))]

    def _onset(self, c: np.ndarray, a: int, b: int, above: bool, n: int) -> int | None:
        """First step in [a, b) that starts n consecutive readings above 180 (or below 70)."""
        thr = config.SPIKE_THRESHOLD if above else config.LOW_THRESHOLD
        for j in range(max(a, 0), min(b, len(c) - n + 1)):
            w = c[j: j + n]
            if not np.isnan(w).any() and ((w > thr).all() if above else (w < thr).all()):
                return j
        return None

    def history(self, pid: str, minute: float, days: int = 7) -> dict:
        """Every alert in the last few days, what the forecast said, what happened, and who did what."""
        key = (pid, int(minute // STEP), days, self.store.version)
        if getattr(self, "_hist_key", None) == key:
            return self._hist
        c = self.S[pid].cgm
        sts = self.statuses(pid, minute, minute - days * 1440)
        eps: list[dict] = []
        cur: dict[str, dict] = {}
        for m, st in sts:
            kinds = []
            if st["tier"] == "alert":
                kinds.append("spike")
            if st["low"] in ("now", "forecast"):
                kinds.append("low")
            for kind in ("spike", "low"):
                e = cur.get(kind)
                if kind in kinds:
                    if e and m - e["end"] <= 30:
                        e["end"] = m
                    else:
                        e = {"kind": kind, "start": m, "end": m, "said": st}
                        cur[kind] = e
                        eps.append(e)
        out = []
        lead = None
        acted = self.store.between(minute - days * 1440 - 60, minute, pid)
        for e in eps:
            k0, st = int(e["start"] // STEP), e["said"]
            if e["kind"] == "spike":
                horizon = k0 + 27
                j = self._onset(c, k0, horizon, True, 3)
                seg = c[k0: k0 + 37]
                hi = float(np.nanmax(seg)) if np.isfinite(seg).any() else None
                said = f"Above 180 by {hhmm(st['cross_minute'])}, peak {st['peak']:.0f}"
                lead = (j - k0) * STEP if j is not None else None
                if j is not None:
                    result, what = "happened", f"Went above 180 at {hhmm(j * STEP)}, {lead} min after the alert; highest {hi:.0f}"
                elif horizon * STEP > minute:
                    result, what = "pending", "Too early to tell"
                else:
                    result, what = "did not happen", f"Stayed at or below 180; highest {hi:.0f}" if hi else "No readings"
            else:
                lead = None
                horizon = k0 + 13
                j = self._onset(c, k0, horizon, False, 2)
                seg = c[k0: k0 + 13]
                lo = float(np.nanmin(seg)) if np.isfinite(seg).any() else None
                said = "Below 70 now" if st["low"] == "now" else f"Below 70 likely within the hour ({st['low_p'] * 100:.0f}%)"
                if j is not None:
                    result, what = "happened", f"Went below 70 at {hhmm(j * STEP)}; lowest {lo:.0f}"
                elif horizon * STEP > minute:
                    result, what = "pending", "Too early to tell"
                else:
                    result, what = "did not happen", f"Stayed at or above 70; lowest {lo:.0f}" if lo else "No readings"
            win = lambda r, t="minute": e["start"] - 5 <= r[t] <= e["end"] + 90
            done = ([f"Seen by {a['by']}" + (f": {a['note']}" if a["note"] else "") for a in acted["acks"] if win(a) and a["kind"] == e["kind"]]
                    + [f"{ACTION_NAMES.get(a['kind'], a['kind'])} by {a['by']}" + (f": {a['outcome'] or a['note']}" if (a['outcome'] or a['note']) else "")
                       for a in acted["actions"] if win(a)]
                    + [f"Meal logged: {m['label']} ({m['carbs']:.0f} g)" for m in acted["meals"] if win(m, "entered_minute")])
            after = self.S[pid].steps[k0: k0 + 24].sum() * STEP
            out.append({"kind": e["kind"], "start": iso(e["start"]), "end": iso(e["end"]), "said": said, "result": result,
                        "what_happened": what, "done": done, "steps_after": float(after), "lead_min": lead})
        spikes = [o for o in out if o["kind"] == "spike"]
        decided = [o for o in spikes if o["result"] != "pending"]
        hits = [o for o in decided if o["result"] == "happened"]
        leads = [o["lead_min"] for o in hits if o["lead_min"] is not None]
        # Highs that came with no confident alert in the 2 hours before.
        k_lo, k_hi = int((minute - days * 1440) // STEP), int(minute // STEP)
        starts = [int(pd.Timestamp(o["start"]).timestamp()) for o in spikes]
        missed = 0
        j = k_lo + 6
        while j < k_hi - 2:
            prev = c[j - 6: j]
            if (not np.isnan(c[j: j + 3]).any() and (c[j: j + 3] > config.SPIKE_THRESHOLD).all()
                    and not (prev > config.SPIKE_THRESHOLD).any()):
                t = config.minute_to_datetime(j * STEP).timestamp()
                if not any(0 <= t - x <= 7200 for x in starts):
                    missed += 1
                j += 6
            j += 1
        res = clean({
            "days": days, "episodes": out[::-1],
            "summary": {"alerts": len(spikes), "decided": len(decided), "happened": len(hits),
                        "rate": len(hits) / len(decided) if decided else None,
                        "median_lead": float(np.median(leads)) if leads else None, "missed": missed,
                        "lows": len([o for o in out if o["kind"] == "low"]),
                        "lows_happened": len([o for o in out if o["kind"] == "low" and o["result"] == "happened"])},
        })
        self._hist_key, self._hist = key, res
        return res

    # plans ---------------------------------------------------------------------------
    def tir(self, pid: str, a: float, b: float) -> dict | None:
        c = self.S[pid].cgm[int(a // STEP): int(b // STEP)]
        v = c[~np.isnan(c)]
        if len(v) < 100:
            return None
        return {"tir": float(np.mean((v >= 70) & (v <= 180)) * 100), "mean": float(v.mean()),
                "tar": float(np.mean(v > 180) * 100)}

    def plan_check(self, pid: str, plan: dict, minute: float) -> dict:
        s = self.S[pid]
        t0 = plan["minute"]
        t1 = min(t0 + 7 * 1440, minute)
        days = (minute - t0) / 1440
        req = plan["request"]
        meals = s.meal_log[(s.meal_log.minute > t0) & (s.meal_log.minute <= t1) & (s.meal_log.carbs >= forecast.MAIN_MEAL_G)]
        before = s.meal_log[(s.meal_log.minute > t0 - 7 * 1440) & (s.meal_log.minute <= t0) & (s.meal_log.carbs >= forecast.MAIN_MEAL_G)]
        n, kept, how = len(meals), None, ""
        if req.get("walk_minutes"):
            walked = [s.steps[int(m // STEP) + 2: int(m // STEP) + 18].sum() * STEP >= 900 for m in meals.minute]
            kept, how = sum(walked), "walked after"
        elif req.get("swap") in ("millet", "roti"):
            kept, how = int((meals.kind == f"{req['swap']}_meal").sum()), "had " + {"millet": "millets", "roti": "roti"}[req["swap"]] + " at"
        elif req.get("swap") == "half_portion" and len(before):
            kept, how = int((meals.carbs <= 0.65 * before.carbs.median()).sum()), "ate a smaller portion at"
        elif req.get("sleep_hours"):
            nights = s.sleep_hours[int(t0 // 1440): int(t1 // 1440)]
            nights = nights[~np.isnan(nights)]
            n, kept, how = len(nights), int((nights >= req["sleep_hours"] - 0.5).sum()), "slept long enough on"
        adherence = (f"{kept} of {n} " + ("nights" if req.get("sleep_hours") else "main meals")) if kept is not None else None
        b, a = self.tir(pid, t0 - 7 * 1440, t0), self.tir(pid, t0, t1)
        out = {"days": round(days, 1), "due": iso(t0 + 7 * 1440), "complete": days >= 7, "before": b, "after": a,
               "adherence": adherence, "adherence_how": how, "kept": kept, "of": n}
        if days < 1:
            out["verdict"] = "Started today. The first check is due in 7 days."
        elif a and b:
            dt = a["tir"] - b["tir"]
            pred = plan["predicted"].get("tir_pct")
            followed = kept is None or n == 0 or kept / n >= 0.5
            part = f"Time in range {b['tir']:.0f}% the week before, {a['tir']:.0f}% {'the week after' if days >= 7 else 'so far'}"
            if not followed:
                v = f"{part}. The plan was mostly not followed ({how} {adherence}), so this does not test it yet; ask what got in the way."
            elif pred is not None and dt >= max(pred * 0.5, 2):
                v = f"{part}. It is working: the forecast expected about {pred:+.0f} points."
            else:
                v = f"{part}. No clear benefit yet" + (f" (the forecast expected about {pred:+.0f} points)." if pred is not None else ".")
            out["verdict"] = v
        return clean(out)

    def plans(self, pid: str, minute: float) -> list[dict]:
        rows = [p for p in self.store.plans if p["pid"] == pid and p["minute"] <= minute]
        return clean([{**p, "t": iso(p["minute"]), "check": self.plan_check(pid, p, minute)}
                      for p in sorted(rows, key=lambda p: -p["minute"])])

    def seed_demo_plan(self) -> None:
        """One plan agreed with Ramesh nine days before the demo, so the one week check has something to show."""
        pid = config.HERO_IDS["ramesh"]
        if any(p["pid"] == pid and p.get("seeded") for p in self.store.plans):
            return
        m = 20 * 1440 + 20 * 60
        req = {"walk_minutes": 15, "scope": "all"}
        r = self.whatif(pid, m, {**req, "horizon_h": 168})
        pred = {"tir_pct": r["delta"]["tir_pct"], "mean": r["delta"]["mean"]} if r.get("available") else {}
        self.store.add_plan(pid, "Walk 15 min after every main meal", req, "Dr A. Kulkarni (demo setup)", m, pred, seeded=True)

    # handover and digest -------------------------------------------------------------
    def handover(self, minute: float, hours: int = 12) -> dict:
        names = {pid: f"{p.given} {p.family}" for pid, p in self.patients.iterrows()}
        got = self.store.between(minute - hours * 60, minute)
        rows = []
        for a in got["acks"]:
            rows.append({"t": iso(a["minute"]), "pid": a["pid"], "name": names[a["pid"]], "who": a["by"],
                         "what": f"Marked {ALERT_NAMES.get(a['kind'], a['kind'])} as seen", "note": a["note"]})
        for a in got["actions"]:
            rows.append({"t": iso(a["minute"]), "pid": a["pid"], "name": names[a["pid"]], "who": a["by"],
                         "what": ACTION_NAMES.get(a["kind"], a["kind"]), "note": " ".join(x for x in (a["outcome"], a["note"]) if x)})
        for m in got["meals"]:
            rows.append({"t": iso(m["entered_minute"]), "pid": m["pid"], "name": names[m["pid"]], "who": m["by"],
                         "what": f"{'Planned' if m['type'] == 'planned' else 'Logged'} a meal: {m['label']}, {m['carbs']:.0f} g",
                         "note": "entered by the patient" if m.get("source") == "patient" else ""})
        for p in got["plans"]:
            rows.append({"t": iso(p["minute"]), "pid": p["pid"], "name": names[p["pid"]], "who": p["by"],
                         "what": f"Agreed a plan: {p['label']}", "note": ""})
        for c in got["consents"]:
            rows.append({"t": iso(c["minute"]), "pid": c["pid"], "name": names[c["pid"]], "who": c["by"],
                         "what": f"{'Granted' if c['granted'] else 'Withdrew'} sharing: {c['source']}", "note": ""})
        rows.sort(key=lambda r: r["t"])
        ward = self.ward(minute)
        open_, seen = [], []
        for r in ward:
            if r["group"] in ("low", "high", "heart"):
                item = {"pid": r["id"], "name": r["name"], "group": r["group"], "glucose": r["glucose"],
                        "reason": (r["event_a"] or {}).get("reason") if r["group"] == "high" else
                                  (r["event_b"].get("reason") if r["group"] == "heart" else (r["event_a"] or {}).get("low_reason", ""))}
                (seen if r["seen"] else open_).append(item)
        return clean({"from": iso(minute - hours * 60), "to": iso(minute), "hours": hours, "done": rows,
                      "open": open_, "seen_still_active": seen})

    def digest(self, minute: float) -> dict:
        """The day before the clock time, for the morning email."""
        day_end = (minute // 1440) * 1440
        day_start = day_end - 1440
        key = (int(day_end), self.store.version)
        if getattr(self, "_digest_key", None) == key:
            return self._digest
        jobs, meta = [], []
        for pid in self.patients.index:
            for m in np.arange(day_start + 15, day_end + 1, 15):
                k = self.origin(pid, float(m))
                if k is not None and k >= forecast.W:
                    jobs.append((pid, k, float(m)))
                    meta.append((pid, float(m)))
        sts = [self.status(r) for r in self._rows(jobs)]
        per: dict[str, dict] = {}
        last: dict[str, float] = {}
        for (pid, m), st in zip(meta, sts):
            d = per.setdefault(pid, {"alerts": 0, "lows": 0, "starts": []})
            if st["tier"] == "alert":
                if m - last.get(pid, -1e9) > 30:
                    d["alerts"] += 1
                    d["starts"].append(m)
                last[pid] = m
            if st["low"] in ("now", "forecast"):
                d["lows"] += 1 if m - d.get("low_last", -1e9) > 30 else 0
                d["low_last"] = m
        hits = total = 0
        for pid, d in per.items():
            c = self.S[pid].cgm
            for m in d["starts"]:
                k0 = int(m // STEP)
                total += 1
                hits += self._onset(c, k0, k0 + 27, True, 3) is not None
        names = {pid: f"{p.given} {p.family}" for pid, p in self.patients.iterrows()}
        top = sorted(((pid, d) for pid, d in per.items() if d["alerts"] or d["lows"]), key=lambda x: -(x[1]["alerts"] + 2 * x[1]["lows"]))[:8]
        allc = np.concatenate([self.S[pid].cgm[int(day_start // STEP): int(day_end // STEP)] for pid in self.patients.index])
        allc = allc[~np.isnan(allc)]
        flags = [pid for pid in self.patients.index if self.cardio_now(pid, day_end).get("flag")]
        got = self.store.between(day_start, day_end)
        res = clean({
            "date": config.minute_to_datetime(day_start).strftime("%a %d %b %Y"), "patients": len(self.patients),
            "alerts": sum(d["alerts"] for d in per.values()), "lows": sum(d["lows"] for d in per.values()),
            "alerts_happened": hits, "alerts_total": total,
            "alerts_per_patient": sum(d["alerts"] for d in per.values()) / len(self.patients),
            "tir": float(np.mean((allc >= 70) & (allc <= 180)) * 100),
            "heart_flags": [{"pid": p, "name": names[p]} for p in flags],
            "most_alerts": [{"pid": p, "name": names[p], "alerts": d["alerts"], "lows": d["lows"]} for p, d in top],
            "actions": {"seen": len(got["acks"]), "actions": len(got["actions"]), "meals": len(got["meals"])},
        })
        self._digest_key, self._digest = key, res
        return res

    # check against the reference simulator ------------------------------------------
    def reference_check(self, pid: str, minute: float, req: dict) -> dict:
        """The twin's answer to a what if next to the reference simulator's, for the same moment and change."""
        from prativimb.data import reference
        others = {k: v for k, v in req.items() if k not in ("walk_minutes", "swap", "shift_hours", "scope", "horizon_h") and v}
        if others:
            return {"available": False, "reason": "The reference check covers walks, food swaps, portion size and meal "
                    "timing. Sleep, missed doses, night shifts and insulin act through the whole day in the reference "
                    "simulator, so they cannot be checked for one evening."}
        k = self.origin(pid, minute)
        if k is None:
            return {"available": False, "reason": "No recent glucose reading."}
        t = k * STEP
        window = min(360, config.N_DAYS * 1440 - t - 1)
        if window < 90:
            return {"available": False, "reason": "Too little of the recorded day is left to check."}
        ch = reference.Change(walk_minutes=int(req.get("walk_minutes", 0)), swap=req.get("swap", "none"),
                              shift_hours=float(req.get("shift_hours", 0.0)))
        ref = reference.what_if(pid, t, window, ch)
        tw = self.whatif(pid, minute, {**{k2: req[k2] for k2 in ("walk_minutes", "swap", "shift_hours") if k2 in req}, "horizon_h": 6})
        n = window // STEP + 1
        gb, ga = np.asarray(tw["baseline"][:n])[1:], np.asarray(tw["scenario"][:n])[1:]
        twin = {"peak": float(ga.max() - gb.max()), "tar_min": int(((ga > 180).sum() - (gb > 180).sum()) * STEP)}
        d_ref, d_tw = ref["delta"]["peak"], twin["peak"]
        same_dir = (abs(d_ref) < 2 and abs(d_tw) < 2) or (d_ref * d_tw > 0 and abs(d_ref) >= 2 and abs(d_tw) >= 2)
        s_ = self.S[pid]
        assumed = tw.get("target_meal")
        actual = ref.get("meal")
        return clean({
            "available": True, "window_min": window, "origin": iso(t),
            "times": [iso(t + 5 * j) for j in range(len(ref["baseline"]))],
            "reference": {"baseline": ref["baseline"], "scenario": ref["scenario"], "delta": ref["delta"],
                          "baseline_summary": ref["baseline_summary"], "scenario_summary": ref["scenario_summary"]},
            "twin": twin, "twin_baseline": list(gb[::1]), "agree": same_dir,
            "assumed_meal": assumed, "actual_meal": {"time": hhmm(actual["minute"]), "carbs": actual["carbs"]} if actual else None,
            "note": "The reference simulator is the richer model the synthetic patients come from. It knows what the patient "
                    "really ate; the twin only knows the routine they declared. Synthetic data only.",
        })

    # what would sharpen the forecast --------------------------------------------------
    def sharpen(self, pid: str, minute: float) -> dict:
        """Which missing piece of information would narrow the forecast most, and roughly by how much."""
        fc = self.patient_forecast(pid, minute, explain=False)
        out = []
        if not fc.get("available"):
            return {"items": out}
        st = fc["status"]
        h = next(x for x in fc["horizons"] if x["h"] == 120)
        k = self.origin(pid, minute)
        pp, th = self.pp(pid, minute), self.theta(pid, minute)
        planned = {round(m) for m, *_ in pp.extra.get("planned", [])}
        meals = [m for m in forecast.expected_meals(pp, k, 24) if m[1] >= forecast.MAIN_MEAL_G
                 and not any(abs((k + m[0]) * STEP - p) <= 120 for p in planned)]
        if meals:
            j, carbs, af, name = meals[0]
            slot = ((k + j) * STEP) % 1440
            log = pp.s.meal_log
            past = log[(log.minute < k * STEP) & (log.minute >= k * STEP - 14 * 1440)]
            tod = past.minute % 1440
            near = past[(np.abs(tod - slot) <= 90) & (past.carbs >= 0.4 * carbs)]
            if len(near) >= 4:
                ratio = np.percentile(near.carbs / carbs, [10, 90])
                dt = np.percentile((near.minute % 1440) - slot, [10, 90])
            else:
                ratio, dt = np.array([0.75, 1.25]), np.array([-30.0, 30.0])
            sims = []
            for sc in (forecast.Scenario(carb_factor=float(ratio[0])), forecast.Scenario(carb_factor=float(ratio[1])),
                       forecast.Scenario(shift_hours=float(dt[0]) / 60), forecast.Scenario(shift_hours=float(dt[1]) / 60)):
                g, _ = forecast.simulate_scenario(pp, th, k, 24, sc, method="rk4")
                sims.append(float(np.asarray(g)[24]))
            sd_meal = float(np.hypot((sims[1] - sims[0]) / 2.563, (sims[3] - sims[2]) / 2.563))
            sd_tot = (h["hi"] - h["lo"]) / (2 * 1.645)
            sd_new = float(np.sqrt(max(sd_tot ** 2 - sd_meal ** 2, (0.35 * sd_tot) ** 2)))
            lo, hi = h["mid"] - 1.645 * sd_new, h["mid"] + 1.645 * sd_new
            if (h["hi"] - h["lo"]) - (hi - lo) >= 8:
                label = name.split(" (")[0].lower()
                out.append({"kind": "meal", "action": "Log a meal", "gain": float((h["hi"] - h["lo"]) - (hi - lo)),
                            "text": f"Logging {label} (usually about {hhmm((k + j) * STEP)}, about {carbs:.0f} g) would narrow the "
                                    f"{hhmm(k * STEP + 120)} range from {h['lo']:.0f} to {h['hi']:.0f} to about {lo:.0f} to {hi:.0f}.",
                            "detail": f"Over the last two weeks this meal ranged from {ratio[0] * 100:.0f}% to {ratio[1] * 100:.0f}% "
                                      f"of its usual size and from {dt[0]:+.0f} to {dt[1]:+.0f} minutes from its usual time; "
                                      f"that alone moves the forecast by about {1.645 * sd_meal:.0f} mg/dL either way."})
        if st.get("low") == "artefact" or (self.S[pid].cgm[k] < config.LOW_THRESHOLD and self.suspect_compression(pid, k)):
            out.append({"kind": "fingerstick", "action": "Check the patient now", "gain": 100.0,
                        "text": "A fingerstick would settle whether this low is real.",
                        "detail": "The reading fell more than 1 mg/dL a minute during sleep, the pattern pressure on the sensor gives."})
        elif st.get("low") in ("now", "forecast"):
            out.append({"kind": "fingerstick", "action": "Check the patient now", "gain": 90.0,
                        "text": "A fingerstick now would confirm the low before treating it.",
                        "detail": f"The low glucose model gives {st['low_p'] * 100:.0f}%; sensors read low more often than blood does."})
        hr = self.S[pid].hr[max(0, k - 12): k + 1]
        if len(hr) and np.isnan(hr).all():
            out.append({"kind": "wearable", "action": "", "gain": 20.0,
                        "text": "The watch has not synced for an hour; the forecast assumes no activity since.",
                        "detail": "Ask the patient to open the app on their phone, or log a walk if they have been active."})
        c = self.S[pid].cgm
        last = np.flatnonzero(~np.isnan(c[: int(minute // STEP) + 1]))
        if len(last) and int(minute // STEP) - last[-1] >= 3:
            out.append({"kind": "cgm", "action": "", "gain": 50.0,
                        "text": f"No glucose reading for {(int(minute // STEP) - last[-1]) * STEP} minutes.",
                        "detail": "The sensor may be out of range of the phone, or warming up after a change."})
        out.sort(key=lambda x: -x["gain"])
        return clean({"items": out, "range": {"lo": h["lo"], "hi": h["hi"], "time": hhmm(k * STEP + 120)}})

    # inside the twin -------------------------------------------------------------------
    def inside(self, pid: str, minute: float, req: dict) -> dict:
        k = self.origin(pid, minute)
        if k is None:
            return {"available": False}
        pp, th = self.pp(pid, minute), self.theta(pid, minute)
        H = 72
        sc_req = {kk: v for kk, v in req.items() if kk in forecast.Scenario.__dataclass_fields__}
        a = forecast.trajectory(pp, th, k, H, forecast.Scenario(scope=sc_req.get("scope", "next")))
        b = forecast.trajectory(pp, th, k, H, forecast.Scenario(**sc_req))
        keys = ("G", "stomach_g", "gut_g", "into_blood", "insulin", "action", "activity", "out_of_blood")
        return clean({"available": True, "times": [iso((k + j) * STEP) for j in range(H)],
                      "usual": {x: list(a[x]) for x in keys}, "change": {x: list(b[x]) for x in keys},
                      "meal_step": a["info"].get("target_step"), "units": {"G": "mg/dL", "stomach_g": "g", "gut_g": "g",
                      "into_blood": "mg/dL per min", "insulin": "uU/mL", "action": "per min", "activity": "walking pace",
                      "out_of_blood": "mg/dL per min"}})

    # ward level what if ----------------------------------------------------------------
    def ward_whatif(self, minute: float, include_watch: bool = False) -> dict:
        """Every change for every likely high patient tonight, added up, plus each patient's own best change."""
        key = (int(minute // STEP), self.store.version, include_watch)
        if getattr(self, "_wwi_key", None) == key:
            return self._wwi
        groups = ("high", "watch") if include_watch else ("high",)
        rows = [r for r in self.ward(minute) if r["group"] in groups]
        levers = [(l, q) for l, q in self.LEVERS if "earlier" not in l and "Sleep" not in l]
        pts = []
        for r in rows:
            pid = r["id"]
            k = self.origin(pid, minute)
            if k is None:
                continue
            pp, th = self.pp(pid, minute), self.theta(pid, minute)
            gb = np.asarray(forecast.simulate_scenario(pp, th, k, 72, forecast.Scenario(), method="rk4")[0])[1:]
            by = {}
            for label, req in levers:
                ga = np.asarray(forecast.simulate_scenario(pp, th, k, 72, forecast.Scenario(**req), method="rk4")[0])[1:]
                by[label] = {"peak_after": float(ga.max()), "hours_after": float((ga > 180).sum() * STEP / 60)}
            hb = float((gb > 180).sum() * STEP / 60)
            best = max(by, key=lambda l: (hb - by[l]["hours_after"], gb.max() - by[l]["peak_after"]))
            pts.append({"pid": pid, "name": r["name"], "group": r["group"], "peak": float(gb.max()), "hours_above": hb,
                        "by_lever": by, "best": best, "best_hours_saved": hb - by[best]["hours_after"],
                        "best_peak_drop": float(gb.max() - by[best]["peak_after"])})
        summary = []
        for label, _ in levers:
            saved = sum(x["hours_above"] - x["by_lever"][label]["hours_after"] for x in pts)
            drop = float(np.mean([x["peak"] - x["by_lever"][label]["peak_after"] for x in pts])) if pts else 0.0
            summary.append({"label": label, "hours_saved": saved, "mean_peak_drop": drop})
        summary.sort(key=lambda x: -x["hours_saved"])
        own = {"hours_saved": sum(x["best_hours_saved"] for x in pts),
               "mean_peak_drop": float(np.mean([x["best_peak_drop"] for x in pts])) if pts else 0.0}
        res = clean({"patients": pts, "levers": summary, "own_best": own, "include_watch": include_watch,
                     "hours_above_total": sum(x["hours_above"] for x in pts)})
        self._wwi_key, self._wwi = key, res
        return res

    # twin health -----------------------------------------------------------------------
    def twin_health(self, pid: str, minute: float) -> dict:
        """Is the twin still fitting this patient? Recent 2 hour error against its own first weeks of use."""
        key = (pid, int(minute // 60), self.store.version)
        cache = self.__dict__.setdefault("_health_cache", {})
        if key in cache:
            return cache[key]
        c = self.S[pid].cgm
        def errors(a: float, b: float):
            jobs = []
            for m in np.arange(a, b, 60):
                k = self.origin(pid, float(m))
                if k is not None and k >= forecast.W and k + 24 < len(c) and not np.isnan(c[k + 24]):
                    jobs.append((pid, k, float(m)))
            rows = self._rows(jobs)
            e = np.array([r.hyb[120] - c[r.k + 24] for r in rows])
            return e
        now = float(minute) - 120
        ref_a, ref_b = config.CALIBRATION_DAYS * 1440, (config.CALIBRATION_DAYS + 7) * 1440
        if now < ref_b + 3 * 1440:
            res = {"status": "too early", "text": "The fit can be checked once the twin has been in use for about ten days."}
        else:
            e0, e1 = errors(ref_a, ref_b), errors(max(ref_b, now - 7 * 1440), now)
            r0, r1 = float(np.sqrt(np.mean(e0 ** 2))), float(np.sqrt(np.mean(e1 ** 2)))
            bias = float(np.mean(e1))
            # About the worst few percent of this synthetic cohort; real patients drift more (new medicines, illness).
            drifting = (r1 > 1.3 * r0 and r1 > 20) or abs(bias) > 10
            res = {"status": "drifting" if drifting else "good", "rmse_then": r0, "rmse_now": r1, "bias_now": bias,
                   "text": (f"Typical 2 hour error {r1:.0f} mg/dL over the last 7 days against {r0:.0f} in its first week of use"
                            + (f"; it now reads {abs(bias):.0f} mg/dL {'high' if bias > 0 else 'low'} on average" if abs(bias) > 8 else "")
                            + (". The twin no longer fits as well as it did: refit it on the last week." if drifting else ". Fitting as well as before."))}
        weeks = []
        for a in range(config.CALIBRATION_DAYS, int(now // 1440), 7):
            b = min(a + 7, now / 1440)
            if b - a < 2:
                break
            e = errors(a * 1440, b * 1440)
            if len(e) >= 20:
                weeks.append({"from": (config.START.date() + timedelta(days=a)).isoformat(),
                              "to": (config.START.date() + timedelta(days=int(np.ceil(b)) - 1)).isoformat(),
                              "rmse": float(np.sqrt(np.mean(e ** 2))), "bias": float(np.mean(e))})
        res["weeks"] = weeks
        r = self.store.refit(pid, minute)
        res["refit"] = {"t": iso(r["minute"]), "by": r["by"], "rmse_before": r.get("rmse_before"), "rmse_after": r.get("rmse_after"),
                        "id": r["id"], "backtest": r.get("backtest")} if r else None
        cache[key] = clean(res)
        return cache[key]

    def health_all(self, minute: float) -> dict[str, str]:
        """Twin fit for every patient, worked out in the background once per replay day (it takes a minute or two)."""
        import threading
        day = int(minute // 1440)
        hs = self.__dict__.setdefault("_health_all", {})
        if day in hs:
            return hs[day]
        if not getattr(self, "_health_running", False):
            self._health_running = True

            def work():
                try:
                    hs[day] = {pid: self.twin_health(pid, day * 1440 + 12 * 60)["status"] for pid in self.patients.index}
                finally:
                    self._health_running = False
                    self._ward_cache = None
            threading.Thread(target=work, daemon=True).start()
        return {}

    def _refit(self, pid: str, minute: float, start_day: int, end_day: int):
        from prativimb.twin import calibrate as cal
        s = self.S[pid]
        current = self.theta(pid, start_day * 1440)
        prior = cal.Prior(current, cal.ehr_prior(s.ehr).sd * 0.7)
        return current, *cal.calibrate(s, prior=prior, days=end_day - start_day, start_day=start_day)

    def refit_backtest(self, pid: str, minute: float) -> dict:
        """Would a refit help? Refit on the week that ended three days ago, then compare old and new on those three days.

        The fit error on the week it was fitted on always improves; this asks whether the next days get better."""
        key = (pid, int(minute // 60), self.store.version)
        cache = self.__dict__.setdefault("_backtest_cache", {})
        if key in cache:
            return cache[key]
        d = int(minute // 1440)
        if d - 10 < config.CALIBRATION_DAYS:
            return {"available": False, "reason": "Needs at least ten days of use."}
        old, new, _ = self._refit(pid, minute, d - 10, d - 3)
        c = self.S[pid].cgm
        jobs = []
        for m in np.arange((d - 3) * 1440, minute - 120, 60):
            k = self.origin(pid, float(m))
            if k is not None and k >= forecast.W and k + 24 < len(c) and not np.isnan(c[k + 24]):
                jobs.append((pid, k, float(m)))
        e_old = np.array([r.hyb[120] - c[r.k + 24] for r in self._rows(jobs, old)])
        e_new = np.array([r.hyb[120] - c[r.k + 24] for r in self._rows(jobs, new)])
        r_old, r_new = float(np.sqrt(np.mean(e_old ** 2))), float(np.sqrt(np.mean(e_new ** 2)))
        day = lambda x: (config.START.date() + timedelta(days=x)).strftime("%d %b")
        helps = r_new < r_old - 1.0
        res = clean({"available": True, "fit_on": [day(d - 10), day(d - 4)], "tested_on": [day(d - 3), day(d)], "n": len(jobs),
                     "rmse_old": r_old, "rmse_new": r_new, "helps": helps,
                     "text": (f"A refit on {day(d - 10)} to {day(d - 4)}, tested on the {len(jobs)} forecasts since, changes the typical 2 hour "
                              f"error from {r_old:.0f} to {r_new:.0f} mg/dL. "
                              + ("A refit is likely to help." if helps else "A refit would not clearly help; the current fit is as good."))})
        cache[key] = res
        return res

    def refit_twin(self, pid: str, minute: float, by: str) -> dict:
        d = int(minute // 1440)
        bt = self.refit_backtest(pid, minute)
        _, theta, rep_ = self._refit(pid, minute, max(0, d - 7), d)
        return self.store.add_refit(pid, list(theta), by, int(minute), {"rmse_before": rep_["rmse_prior"],
                                    "rmse_after": rep_["rmse_fit"], "days": [max(0, d - 7), d],
                                    "backtest": {k: bt.get(k) for k in ("rmse_old", "rmse_new", "helps", "text")} if bt.get("available") else None})

    # festival planner --------------------------------------------------------------------
    # The regional new year differs by state; the dish is what the patient is likely to be offered.
    NEW_YEAR = {"Maharashtra": ("Gudi Padwa", "puran poli"), "Karnataka": ("Ugadi", "obbattu (holige)"),
                "Telangana": ("Ugadi", "bobbatlu and ugadi pachadi"), "Andhra Pradesh": ("Ugadi", "bobbatlu and ugadi pachadi")}
    FESTIVALS = [
        {"key": "new_year", "name": "Ugadi and Gudi Padwa", "date": "2026-03-19", "who": "regional",
         "about": "New year in Maharashtra, Karnataka, Telangana and Andhra Pradesh: a festive lunch with a sweet stuffed flatbread."},
        {"key": "navratri", "name": "Chaitra Navratri, first fast", "date": "2026-03-19", "who": "hindu_fasts",
         "about": "Nine days from 19 March; many keep fasts with sabudana, potato and fruit. The first fast day is shown."},
        {"key": "eid", "name": "Eid al-Fitr (expected, depends on the moon)", "date": "2026-03-21", "who": "ramadan",
         "about": "The end of Ramadan: sheer khurma in the morning, biryani and sweets through the day."},
    ]
    TIPS = {"half_sweets": "Half the usual helping of the sweet", "walk": "A 15 minute walk after the festive meal",
            "smaller_fast": "A smaller fast meal, two thirds of the usual"}

    def _festival_for(self, pid: str, fest: dict) -> dict | None:
        """Whether this patient keeps this festival, and what it is called and served where they live."""
        from prativimb.data.cohort import STATE_OF
        dec, city = self.S[pid].declared, self.patients.loc[pid].city
        if fest["who"] == "ramadan":
            return {"name": "Eid al-Fitr", "dish": "sheer khurma"} if dec.get("observes_ramadan") else None
        if fest["who"] == "hindu_fasts":
            return {"name": "Navratri", "dish": "sabudana"} if dec.get("observes_hindu_fasts") else None
        ny = self.NEW_YEAR.get(STATE_OF.get(city, ""))
        return {"name": ny[0], "dish": ny[1]} if ny and not dec.get("observes_ramadan") else None

    def _festival_meals(self, pid: str, fest: dict, day_minute: int, sweet_factor: float = 1.0) -> tuple[list[tuple], int]:
        """Planned meals for the day and the minute of its main festive meal."""
        AF = {k: v[1] for k, v in MEAL_TYPES.items()}
        if fest["key"] == "eid":
            day = [(8 * 60 + 30, 45 * sweet_factor, "sweets", "Sheer khurma"), (13 * 60 + 30, 110, "biryani", "Eid lunch"),
                   (17 * 60, 40 * sweet_factor, "sweets", "Sweets with guests"), (21 * 60, 90, "biryani", "Eid dinner")]
            main = 13 * 60 + 30
        elif fest["key"] == "navratri":
            plan = self.S[pid].routine.get("hindu_fast") or [(11 * 60, 70, "sabudana", "Fast meal"), (19 * 60 + 30, 80, "sabudana", "Fast dinner")]
            day = [(m, g * sweet_factor, kind, name) for m, g, kind, name in plan]
            main = max(day, key=lambda x: x[1])[0]
        else:
            day = [(13 * 60 + 30, 90 + 60 * sweet_factor, "sweets", "Festive lunch"), (17 * 60, 30 * sweet_factor, "sweets", "Sweets")]
            main = 13 * 60 + 30
        return [(day_minute + m, float(g), AF.get(kind, 1.0), name) for m, g, kind, name in day], day_minute + main

    def festivals(self, minute: float) -> dict:
        key = (int(minute // 1440), self.store.version)
        if getattr(self, "_fest_key", None) == key:
            return self._fest
        from datetime import date
        out, per_patient = [], {}
        for fest in self.FESTIVALS:
            d = (date.fromisoformat(fest["date"]) - config.START.date()).days
            day0 = d * 1440
            if day0 + 1440 <= minute:
                continue
            who = {pid: f for pid in self.patients.index if (f := self._festival_for(pid, fest))}
            rows = self._festival_batch(list(who), fest, minute, day0)
            for r in rows:
                r["festival_local"], r["dish"] = who[r["pid"]]["name"], who[r["pid"]]["dish"]
                per_patient.setdefault(r["pid"], []).append({**r, "festival": fest["key"], "date": fest["date"]})
            rows.sort(key=lambda r: -r["extra_hours_above"])
            tip = "smaller_fast" if fest["key"] == "navratri" else "half_sweets"
            out.append({**fest, "day": d, "patients": len(who), "tip_keys": [tip, "walk"],
                        "tips": {tip: self.TIPS[tip], "walk": self.TIPS["walk"]},
                        "most_affected": [r for r in rows if r["extra_hours_above"] >= 0.25][:12],
                        "total_extra_hours": float(sum(max(r["extra_hours_above"], 0) for r in rows)),
                        "total_saved_hours": float(sum(max(r["best_saved_hours"], 0) for r in rows if r["extra_hours_above"] > 0))})
        self._fest_key, self._fest = key, clean({"festivals": out, "by_patient": per_patient})
        return self._fest

    def _festival_batch(self, pids: list[str], fest: dict, minute: float, day0: int) -> list[dict]:
        """Twin runs from now to the end of the festival day, batched: usual, festival, festival with each suggestion."""
        meta, H = [], None
        for pid in pids:
            k = self.origin(pid, minute)
            if k is None or k < forecast.W:
                continue
            Hk = int((day0 + 1440 - k * STEP) // STEP)
            H = Hk if H is None else min(H, Hk)
            meta.append((pid, k))
        if not meta:
            return []
        tip = "smaller_fast" if fest["key"] == "navratri" else "half_sweets"
        variants = ("usual", "festival", tip, "walk")
        U, O, X0, TH, BW, MET = [], [], [], [], [], []
        for pid, k in meta:
            base = self.pp(pid, minute)
            for v in variants:
                if v == "usual":
                    pp = base
                else:
                    meals, main = self._festival_meals(pid, fest, day0, 0.5 if v == "half_sweets" else 0.67 if v == "smaller_fast" else 1.0)
                    walks = base.extra.get("walks", []) + ([(main + 10, 15)] if v == "walk" else [])
                    pp = forecast.Prepared(**{**base.__dict__, "extra": {**base.extra, "planned": base.extra.get("planned", []) + meals,
                                                                         "walks": walks}})
                u, obs, x0, _ = forecast.apply_scenario(pp, k, H, forecast.Scenario())
                U.append(u); O.append(obs); X0.append(x0)
                TH.append(self.theta(pid, minute)); BW.append(float(pp.s.bw)); MET.append(float(pp.s.on_metformin))
        cat = lambda f: np.concatenate([getattr(u, f) for u in U])
        u = bergman.Inputs(*(cat(f) for f in ("carbs", "af", "A", "dose", "smod", "dawn")))
        p = bergman.params_dict(np.array(TH), np.array(BW), np.array(MET))
        G, _ = bergman.run_rk4(p, np.concatenate(X0, axis=1), u, obs=np.concatenate(O), obs_until=forecast.W)
        G = G[:, forecast.W:]
        names = {pid: f"{q.given} {q.family}" for pid, q in self.patients.iterrows()}
        rows, n = [], len(variants)
        for i, (pid, k) in enumerate(meta):
            j0 = max(int((day0 - k * STEP) // STEP), 0)
            g = [G[n * i + v, j0: H] for v in range(n)]
            hrs = [float((x > 180).sum() * STEP / 60) for x in g]
            saved = {variants[v]: hrs[1] - hrs[v] for v in (2, 3)}
            best = max(saved, key=saved.get)
            rows.append({"pid": pid, "name": names[pid], "usual_peak": float(g[0].max()), "festival_peak": float(g[1].max()),
                         "extra_hours_above": hrs[1] - hrs[0], "saved_hours": saved, "best": best, "best_saved_hours": saved[best]})
        return rows
