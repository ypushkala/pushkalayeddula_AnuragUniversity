"""Two questions the headline metrics do not answer.

1. Alert load. How often does each kind of alert fire per patient day, how many of the
   confident high glucose alerts came true, and how many patients would sit on a 200 bed
   ward list at a given hour? Computed with the deployed service code (two tiers, the low
   glucose model, the heart risk flag) on the 40 test patients, days 8 to 30, every 15 minutes.

2. How much does the heart risk result depend on our own simulator? The events and the
   warning signs before them come from the same generator the model was trained on, so the
   test score mostly shows the model learned that generator. As a stress test we weaken the
   simulated warning signs in the ten days before each test event (pull every window feature
   toward the patient's own baseline) and score again with the deployed model and threshold.
   Illness episodes, which look similar but are not followed by an event, keep full strength.

Run: python -m prativimb.eval.followup   (writes reports/followup.json and reports/followup.md)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from prativimb import config
from prativimb.api.services import AppState
from prativimb.api.store import ClinicalStore
from prativimb.ml import cardio

EVERY = 15
STEP_END = 5
FOLD_MIN = 180
SHRINK = (1.0, 0.75, 0.5, 0.25)


def _episodes(times: np.ndarray, gap: float = 30) -> list[float]:
    starts, last = [], -1e9
    for t in times:
        if t - last > gap:
            starts.append(float(t))
        last = t
    return starts


def _fold(starts: list[float], window: float = FOLD_MIN) -> list[float]:
    """Pushes left if a new alert within `window` minutes of the last push is folded into it."""
    out = []
    for t in starts:
        if not out or t - out[-1] > window:
            out.append(t)
    return out


def alert_load(S: AppState, pids: list[str]) -> dict:
    flags = S.cardio_scores[["pid", "day", "flag", "post_event"]]
    flag_day = {(r.pid, int(r.day) + 1): bool(r.flag) and not r.post_event for r in flags.itertuples()}
    rows = []
    end = config.N_DAYS * 1440 - STEP_END
    for pid in pids:
        for m, st in S.statuses(pid, end, config.CALIBRATION_DAYS * 1440, EVERY):
            rows.append({"pid": pid, "m": m, "high": st["tier"] == "alert", "watch": st["tier"] == "watch",
                         "low": st["low"] in ("now", "forecast"), "heart": flag_day.get((pid, int(m // 1440)), False)})
    df = pd.DataFrame(rows)
    patient_days = len(df) * EVERY / 1440
    out = {"patients": len(pids), "patient_days": patient_days}
    hits = total = 0
    pushes = {}
    for kind in ("high", "watch", "low"):
        n = n_fold = 0
        for pid, g in df[df[kind]].groupby("pid"):
            st = _episodes(g.m.to_numpy())
            n += len(st)
            n_fold += len(_fold(st))
            if kind == "high":
                c = S.S[pid].cgm
                for t in st:
                    k0 = int(t // 5)
                    total += 1
                    hits += S._onset(c, k0, k0 + 27, True, 3) is not None
        out[f"{kind}_per_patient_day"] = n / patient_days
        pushes[kind] = n_fold / patient_days
    heart_eps = sum(len(_episodes(g.m.to_numpy(), gap=1440)) for _, g in df[df.heart].groupby("pid"))
    out["heart_flags_per_patient_week"] = heart_eps / patient_days * 7
    out["high_came_true"] = hits / max(total, 1)
    out["high_episodes"] = total
    out["pushes_per_patient_day_folded"] = {"high": pushes["high"], "low": pushes["low"]}
    df["attention"] = df.high | df.low | df.heart
    df["hour"] = ((df.m % 1440) // 60).astype(int)
    share = df.groupby("m").attention.mean()
    by_hour = df.groupby("hour").attention.mean()
    out["ward_of_200"] = {"median": float(share.median() * 200), "p90": float(share.quantile(0.9) * 200),
                          "busiest_hour": int(by_hour.idxmax()), "busiest_hour_mean": float(by_hour.max() * 200),
                          "quietest_hour": int(by_hour.idxmin()), "quietest_hour_mean": float(by_hour.min() * 200)}
    out["by_hour_of_200"] = {int(h): float(v * 200) for h, v in by_hour.items()}
    return out



def cardio_stress() -> dict:
    model = joblib.load(config.ARTIFACT_DIR / "cardio_model.joblib")
    w = pd.read_parquet(config.ARTIFACT_DIR / "cardio_windows.parquet")
    daily = pd.read_parquet(config.ARTIFACT_DIR / "cardio_daily.parquet")
    test = w[(w.split == "test") & ~w.post_event].reset_index(drop=True)
    ramp = test.event_day.notna() & (test.day >= test.event_day - 10) & (test.day < test.event_day)
    base = {}
    for i in np.flatnonzero(ramp):
        pid, d = test.pid[i], int(test.day[i])
        g = daily[(daily.pid == pid) & (daily.day <= d - 7)]
        base[i] = {m: g[m].mean() for m in cardio.METRICS}
    out = []
    for s in SHRINK:
        t = test.copy()
        for i, mu in base.items():
            for m in cardio.METRICS:
                for col in (f"{m}_mean7", f"{m}_last3"):
                    t.loc[i, col] = mu[m] + s * (t.loc[i, col] - mu[m])
                t.loc[i, f"{m}_slope"] *= s
                t.loc[i, f"z_{m}"] *= s
            t.loc[i, "z_composite"] *= s
        sc = cardio.score(model, t)
        y = t.label.to_numpy()
        flagged = sc.flag.to_numpy()
        ev = t[y == 1].groupby("pid").apply(lambda g: bool(flagged[g.index].any()), include_groups=False)
        out.append({"strength": s, "auroc": float(roc_auc_score(y, sc.risk)), "events": int(len(ev)),
                    "events_flagged": int(ev.sum()), "specificity": float(1 - flagged[y == 0].mean())})
    return {"windows": int(len(test)), "positives": int(test.label.sum()), "results": out,
            "threshold": float(model["threshold"])}


def _meal(hour: int) -> str:
    for lo, hi, name in ((6, 11, "breakfast"), (12, 16, "lunch"), (19, 24, "dinner")):
        if lo <= hour < hi:
            return f", after {name}"
    return ""


def markdown(r: dict) -> str:
    a, c = r["alert_load"], r["cardio_stress"]
    w = a["ward_of_200"]
    half = next(x for x in c["results"] if x["strength"] == 0.5)
    quarter = next(x for x in c["results"] if x["strength"] == 0.25)
    lines = [
        "# Alert load and how far the heart risk result can be trusted",
        "",
        "Synthetic data only. Test patients (40), days 8 to 30, checked every 15 minutes with the deployed service code.",
        "",
        "## 1. Alert load",
        "",
        "| Alert | Per patient per day |",
        "|---|---:|",
        f"| High glucose likely (pushed to the ward) | {a['high_per_patient_day']:.2f} |",
        f"| Glucose may go high (shown on the patient page only) | {a['watch_per_patient_day']:.2f} |",
        f"| Low glucose now or likely within the hour | {a['low_per_patient_day']:.2f} |",
        f"| Raised heart risk (new flags per patient per week) | {a['heart_flags_per_patient_week']:.2f} |",
        "",
        f"Of {a['high_episodes']:,} confident high glucose alerts, **{a['high_came_true'] * 100:.0f}% came true** "
        "(glucose above 180 for 15 minutes within 2 h 15 min). This counts an alert as true even if glucose had "
        "already been above 180 shortly before; the stricter definition in metrics.md, which needs a fresh rise, gives 85%.",
        "",
        f"On a ward of 200 patients like these, the Needs attention list would hold a median of **{w['median']:.0f}** "
        f"patients (90th percentile {w['p90']:.0f}). It is busiest around {w['busiest_hour']:02d}:00 "
        f"({w['busiest_hour_mean']:.0f} on average{_meal(w['busiest_hour'])}) and quietest around {w['quietest_hour']:02d}:00 "
        f"({w['quietest_hour_mean']:.0f}).",
        "",
        "Lows are the noisiest alert: most are brief dips just under 70 in people without diabetes. Folding a repeat "
        f"alert into the previous one when it comes within {FOLD_MIN // 60} hours would leave "
        f"{a['pushes_per_patient_day_folded']['high']:.2f} high and {a['pushes_per_patient_day_folded']['low']:.2f} low "
        "glucose pushes per patient per day without hiding any patient from the list.",
        "",
        "## 2. Heart risk: stress test against our own simulator",
        "",
        "The heart events and the warning signs before them come from the same generator the model learned from, so the "
        "headline result (AUROC 0.95) mostly shows that the model learned that generator. Here the warning signs in "
        "the ten days before each test event are weakened, while illness episodes that look similar keep full strength. "
        "Same model, same threshold.",
        "",
        "| Strength of warning signs | AUROC | Events flagged in the 3 days before | Specificity |",
        "|---|---:|---:|---:|",
    ]
    for x in c["results"]:
        lines.append(f"| {x['strength'] * 100:.0f}% | {x['auroc']:.2f} | {x['events_flagged']} of {x['events']} | "
                     f"{x['specificity'] * 100:.1f}% |")
    lines += [
        "",
        f"{c['windows']} test windows, {c['positives']} positive. With 6 test events every row is uncertain.",
        "",
        f"What this means: at half the simulated strength the flag catches {half['events_flagged']} of {half['events']} "
        f"events, and at a quarter {quarter['events_flagged']} of {quarter['events']}, at the same false alarm rate. "
        "The model is only as good as the resemblance between our simulated warning signs and real ones. The heart risk flag is a demonstration of the pipeline (wearable "
        "baselines, stacking, explanation, ward workflow), not evidence that it predicts real events. That needs "
        "real outcomes; open datasets that pair continuous wearable data with adjudicated cardiac events are not "
        "available without a data use agreement, which this project does not use.",
        "",
    ]
    return "\n".join(lines)


def run(verbose: bool = True) -> dict:
    S = AppState()
    tmp = Path(tempfile.mkdtemp())
    S.store = ClinicalStore(tmp / "store.json", tmp / "audit.jsonl")  # nobody's clicks change the evaluation
    split = json.loads((config.DATA_DIR / "splits.json").read_text())
    pids = sorted(p for p, s in split.items() if s == "test")
    cached = config.REPORT_DIR / "followup.json"
    if cached.exists() and "--markdown" in __import__("sys").argv:
        r = json.loads(cached.read_text())
    else:
        r = {"alert_load": alert_load(S, pids), "cardio_stress": cardio_stress()}
    (config.REPORT_DIR / "followup.json").write_text(json.dumps(r, indent=1))
    (config.REPORT_DIR / "followup.md").write_text(markdown(r))
    if verbose:
        print(markdown(r))
    return r


if __name__ == "__main__":
    run()
