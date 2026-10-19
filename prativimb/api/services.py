"""Everything the API computes, as of the replay clock."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import timedelta

import duckdb
import joblib
import numpy as np
import pandas as pd

from prativimb import config
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


def clean(x):
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), 2)
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
        self._pp: dict[str, forecast.Prepared] = {}
        self._ward_cache: tuple[int, list] | None = None

    # basics --------------------------------------------------------------------------
    def theta(self, pid: str) -> np.ndarray:
        return self.twins.loc[pid, PARAMS].to_numpy(float)

    def pp(self, pid: str) -> forecast.Prepared:
        if pid not in self._pp:
            self._pp[pid] = forecast.prepare(self.S[pid])
        return self._pp[pid]

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
        rows, frames = {}, []
        for pid in pids:
            k = self.origin(pid, minute)
            if k is None or k < forecast.W:
                continue
            pp, th = self.pp(pid), self.theta(pid)
            G = forecast.forecast(pp, th, np.array([k]), 24)
            f = glucose_features(pp, np.array([k]), G, th)
            rows[pid] = Row(pid, k, f, G[0], {}, {}, {}, {}, {})
            frames.append(f)
        if not frames:
            return rows
        X = pd.concat(frames, ignore_index=True)
        b = self.bundle
        for h in config.HORIZONS:
            m = b["models"][h]
            tw = X[f"tw{h}"].to_numpy()
            hyb = tw + m["hybrid"].predict(X[b["features"]])
            qlo = tw + m["q_lo"].predict(X[b["features"]])
            qhi = tw + m["q_hi"].predict(X[b["features"]])
            lo, hi = conformal.cqr_interval(qlo, qhi, m["cqr_q"])
            la = lower_bound(b, h, qlo, self.alert_cov)
            for i, pid in enumerate(rows):
                r = rows[pid]
                r.hyb[h], r.qlo[h] = float(hyb[i]), float(qlo[i])
                r.lo90[h], r.hi90[h] = float(min(lo[i], hyb[i])), float(max(hi[i], hyb[i]))
                r.lo_alert[h] = float(min(la[i], hyb[i]))
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
        lows = np.flatnonzero(mid < config.LOW_THRESHOLD)
        if cg < config.LOW_THRESHOLD:
            out["low"] = "now"
        elif len(lows):
            out["low"] = "forecast"
            out["low_minute"] = (r.k + int(lows[0])) * STEP
            out["low_value"] = float(mid.min())
        return out

    # ward ----------------------------------------------------------------------------
    def ward(self, minute: float) -> list[dict]:
        step = int(minute // STEP)
        with self.lock:
            if self._ward_cache and self._ward_cache[0] == step:
                return self._ward_cache[1]
        pids = list(self.patients.index)
        rows = self.forecast_rows(pids, minute)
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
            pr = 0
            if st:
                pr += {"alert": 40, "watch": 10, "high": 6}.get(st["tier"], 0) + (25 if st["low"] else 0)
                pr += max(st["peak"] - 140, 0) / 10
            if cv["flag"]:
                pr += 30
            pr += cv["risk"] * 20 if cv["risk"] is not None else 0
            out.append(clean({
                "id": pid, "name": f"{p.given} {p.family}", "age": int(e.age), "sex": "M" if p.sex == "male" else "F",
                "problems": self.problems(pid), "hba1c": float(e.hba1c), "glucose": st and st["glucose"],
                "trend30": st and st["trend30"], "sparkline": [None if np.isnan(v) else float(v) for v in spark],
                "event_a": st, "event_b": cv, "last_sync": last_sync and iso(last_sync), "priority": pr,
                "hero": pid in config.HERO_IDS.values(), "split": self.split[pid],
            }))
        out.sort(key=lambda r: -r["priority"])
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
        last = sc.sort_values("day").iloc[-1]
        prev = sc[sc.flag].day
        first_flag = None
        if last.flag:
            run = sc.sort_values("day").set_index("day").flag
            d = int(last.day)
            while d - 1 in run.index and run.loc[d - 1]:
                d -= 1
            first_flag = d
        return {"risk": float(last.risk), "flag": bool(last.flag), "post_event": False, "day": int(last.day),
                "flag_since": first_flag, "flags_in_window": int(len(prev))}

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
    def detail(self, pid: str) -> dict:
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
        return {
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
        }

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
        rows = self.forecast_rows([pid], minute)
        if pid not in rows:
            return {"available": False, "reason": "No CGM reading in the last 30 minutes."}
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
            ex = explain_mod.explain(self.pp(pid), self.theta(pid), r.k, self.bundle, r.feats, feats, peak_h)
            out["explanation"] = ex
        out["alerts"] = self.alert_cards(pid, minute, st, out.get("explanation"))
        return clean(out)

    def alert_log(self, pid: str, minute: float, hours: int = 6, every: int = 15) -> list[dict]:
        """What the twin said at earlier times today, so a clinician can see an alert was raised in advance."""
        out = []
        start = minute - hours * 60
        for m in np.arange(start - start % every + every, minute + 1, every):
            rows = self.forecast_rows([pid], float(m))
            if pid not in rows:
                continue
            st = self.status(rows[pid])
            if st["tier"] in ("alert", "watch") or st["low"]:
                out.append({"t": iso(m), "glucose": st["glucose"], "tier": st["tier"], "low": st["low"],
                            "peak": st["peak"], "peak_time": hhmm(st["peak_minute"]),
                            "low_value": st.get("low_value"),
                            "cross_time": hhmm(st["cross_minute"]) if "cross_minute" in st else None})
        return clean(out)

    def alert_cards(self, pid: str, minute: float, st: dict, ex: dict | None) -> list[dict]:
        cards = []
        sent = ex["sentence"] if ex else ""
        if st["tier"] in ("alert", "watch"):
            cards.append({
                "kind": "spike", "tier": st["tier"],
                "title": ("Glucose above 180 likely within 2 h" if st["tier"] == "alert" else "Possible rise above 180 within 2 h"),
                "detail": f"Forecast peak {st['peak']:.0f} mg/dL around {hhmm(st['peak_minute'])}; "
                          f"crossing 180 near {hhmm(st['cross_minute'])}."
                          + (f" At least a {(1 + self.alert_cov) / 2:.0%} chance of exceeding 180." if st["tier"] == "alert" else ""),
                "reason": sent,
            })
        if st["low"]:
            cards.append({
                "kind": "low", "tier": "alert" if st["low"] == "now" else "watch",
                "title": "Glucose below 70 now" if st["low"] == "now" else "Glucose may fall below 70",
                "detail": (f"Current reading {st['glucose']:.0f} mg/dL." if st["low"] == "now" else
                           f"Forecast low {st.get('low_value', 0):.0f} mg/dL around {hhmm(st['low_minute'])}."),
                "reason": "",
            })
            if st["peak"] > config.SPIKE_THRESHOLD:
                cards[-1]["detail"] += f" Rebound to {st['peak']:.0f} mg/dL expected after the next meal."
        cv = self.cardio_now(pid, minute)
        if cv.get("flag"):
            sc = self.cardio_scores[(self.cardio_scores.pid == pid) & (self.cardio_scores.day == cv["day"])]
            f = json.loads(sc.factors.iloc[0]) if len(sc) else []
            since = cv.get("flag_since")
            cards.append({
                "kind": "cardio", "tier": "alert", "title": "Cardiovascular risk flag",
                "detail": f"Seven day wearable pattern; estimated risk {cv['risk'] * 100:.0f}% of an event in 3 days"
                          + (f", flagged since {(config.START.date() + timedelta(days=since)).strftime('%d %b')}." if since is not None else "."),
                "reason": "; ".join(x["text"] for x in f[:3]),
            })
        if cv.get("post_event"):
            cards.append({"kind": "event", "tier": "info", "title": "Cardiovascular event recorded",
                          "detail": f"{cv['event']}, {config.minute_to_datetime(cv['event_minute']).strftime('%d %b %H:%M')}.",
                          "reason": "Risk scoring paused after an event."})
        return cards

    # what if -------------------------------------------------------------------------
    def whatif(self, pid: str, minute: float, req: dict) -> dict:
        k = self.origin(pid, minute)
        if k is None:
            return {"available": False}
        pp, th = self.pp(pid), self.theta(pid)
        H = 72
        base, info0 = forecast.simulate_scenario(pp, th, k, H, forecast.Scenario())
        sc = forecast.Scenario(**req)
        alt, info = forecast.simulate_scenario(pp, th, k, H, sc)

        def summary(g):
            g = np.asarray(g)[1:]
            j = int(np.argmax(g))
            return {"peak": float(g[j]), "peak_time": hhmm((k + j + 1) * STEP),
                    "tar_min": int((g > 180).sum() * STEP), "tbr_min": int((g < 70).sum() * STEP),
                    "mean": float(g.mean()), "auc_above_180": float(np.maximum(g - 180, 0).sum() * STEP)}
        b, a = summary(base), summary(alt)
        target = None
        if info0.get("target_step") is not None:
            ts = info0["target_step"]
            target = {"time": hhmm((k + ts) * STEP), "carbs": info0["target_carbs"],
                      "new_time": hhmm((k + info.get("meal_step", ts)) * STEP)}
        return clean({
            "available": True, "origin": iso(k * STEP), "horizon_h": 6, "solver": "scipy.integrate.solve_ivp (RK45)",
            "times": [iso((k + j) * STEP) for j in range(H + 1)], "baseline": list(base), "scenario": list(alt),
            "baseline_summary": b, "scenario_summary": a,
            "delta": {"peak": a["peak"] - b["peak"], "tar_min": a["tar_min"] - b["tar_min"], "mean": a["mean"] - b["mean"]},
            "target_meal": target, "request": req,
            "note": "Mechanistic twin only. The learned correction is trained for 2 h forecasts and cancels in the difference.",
        })

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
        walk = self.whatif(pid, minute, {"walk_minutes": 15})
        millet = self.whatif(pid, minute, {"swap": "millet"})
        early = self.whatif(pid, minute, {"shift_hours": -1.0})
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
             ["No active glucose or cardiovascular alerts from the twin."]
        tw = det["twin"]
        A_.append(f"Twin calibration: insulin sensitivity about {tw['insulin_sensitivity_pct_typical']:.0f}% of a typical adult "
                  f"without diabetes; fit error {tw['calibration_rmse_fit']:.0f} mg/dL over the calibration week.")
        P_ = []
        if walk.get("available") and walk["delta"]["peak"] < -3:
            P_.append(f"Simulated: a 15 minute walk after the next main meal lowers the predicted peak by "
                      f"{-walk['delta']['peak']:.0f} mg/dL and time above 180 by {-walk['delta']['tar_min']:.0f} min.")
        if millet.get("available") and millet["delta"]["peak"] < -5:
            P_.append(f"Simulated: millets instead of white rice at that meal lowers the predicted peak by "
                      f"{-millet['delta']['peak']:.0f} mg/dL.")
        if early.get("available") and early.get("target_meal"):
            d = early["delta"]["peak"]
            if d < -5:
                P_.append(f"Simulated: eating that meal 1 h earlier lowers the peak by {-d:.0f} mg/dL.")
            elif d > 3:
                P_.append(f"Simulated: eating that meal earlier does not help tonight (peak {d:+.0f} mg/dL); "
                          "glucose from the previous meal has not settled.")
        if cv.get("flag"):
            P_.append("Consider clinical review of cardiovascular symptoms, blood pressure and ECG given the wearable risk flag.")
        P_.append("Review with the patient; the twin's simulations are hypotheses, not prescriptions.")
        return clean({
            "patient": det["patient"], "generated": iso(minute), "problems": self.problems(pid),
            "medications": [m["dosage"] for m in det["medications"]],
            "S": S_, "O": O_, "A": A_, "P": P_,
            "disclaimer": "Decision support only, not a diagnosis. Generated from synthetic data by Prativimb.",
        })
