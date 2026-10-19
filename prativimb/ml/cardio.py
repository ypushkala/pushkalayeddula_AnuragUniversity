"""Event B: cardiovascular risk flag from a rolling seven day wearable window.

Daily metrics: resting heart rate (mean while asleep), nightly RMSSD, sleep architecture,
awakenings, efficiency and steps. For the window ending on day d we compute window means,
last three day means, slopes and z scores against the patient's own earlier baseline.

Three detectors are stacked:
  1. isolation forest on the baseline z scores (unsupervised, no labels needed),
  2. a per patient composite z score in the adverse direction (transparent rule),
  3. LightGBM on window features plus EHR risk factors (supervised on synthetic episodes).
A logistic regression fitted on calibration patients combines them into a probability.
Label: a cardiovascular event in the next three days.
"""
from __future__ import annotations

import json
import time

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression

from prativimb import config

METRICS = {  # name: adverse direction (+1 means higher is worse)
    "rhr": +1, "rmssd": -1, "deep_min": -1, "rem_min": -1, "awakenings": +1, "efficiency": -1,
    "sleep_h": -1, "steps": -1,
}
EHR_COLS = ["age", "male", "sbp", "hypertension", "dyslipidemia", "fh_cad", "fh_mi", "smoker_current", "t2d",
            "tc_hdl", "ldl", "chd_9p21_risk", "on_beta_blocker", "on_statin", "hba1c", "bmi"]
FIRST_DAY = 12
HORIZON_DAYS = 3
Z_FLOOR = {"rhr": 1.5, "rmssd": 3.0, "deep_min": 6.0, "rem_min": 8.0, "awakenings": 0.8, "efficiency": 0.015,
           "sleep_h": 0.4, "steps": 800.0}


def daily_metrics(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    nightly = con.execute("SELECT * FROM sleep_nightly").df()
    segs = con.execute("SELECT * FROM sleep_segments WHERE stage IN ('core', 'deep', 'rem')").df()
    steps = con.execute("SELECT pid, minute // 1440 AS day, sum(steps) AS steps, count(hr) AS hr_minutes "
                        "FROM hr GROUP BY 1, 2").df()
    T = config.N_DAYS * 1440
    rows = []
    hr_all = con.execute("SELECT pid, minute, hr FROM hr ORDER BY pid, minute").df()
    for pid, h in hr_all.groupby("pid"):
        hr = h.hr.to_numpy(float)
        asleep = np.zeros(T, bool)
        for a, b in segs.loc[segs.pid == pid, ["start", "end"]].to_numpy():
            asleep[max(a, 0):min(b, T)] = True
        val = np.where(asleep & ~np.isnan(hr), hr, 0.0)
        cnt = (asleep & ~np.isnan(hr)).astype(float)
        cs, cc = np.concatenate([[0], np.cumsum(val)]), np.concatenate([[0], np.cumsum(cnt)])
        for n in nightly[nightly.pid == pid].itertuples():
            a, b = int(n.bed_minute), min(int(n.wake_minute), T)
            m = cc[b] - cc[a]
            rows.append({"pid": pid, "day": int(n.night), "rhr": (cs[b] - cs[a]) / m if m > 60 else np.nan,
                         "rmssd": n.rmssd, "deep_min": n.deep_min, "rem_min": n.rem_min, "core_min": n.core_min,
                         "awake_min": n.awake_min, "awakenings": n.awakenings, "efficiency": n.efficiency,
                         "sleep_h": n.total_sleep_min / 60})
    d = pd.DataFrame(rows)
    full = pd.MultiIndex.from_product([sorted(steps.pid.unique()), range(config.N_DAYS)], names=["pid", "day"])
    d = d.set_index(["pid", "day"]).reindex(full)
    st = steps.set_index(["pid", "day"])
    d["steps"] = st.steps.where(st.hr_minutes > 600)  # a day mostly off wrist is missing, not inactive
    return d.reset_index()


def _slope(y: np.ndarray) -> float:
    ok = ~np.isnan(y)
    if ok.sum() < 4:
        return np.nan
    x = np.arange(len(y))[ok]
    return float(np.polyfit(x, y[ok], 1)[0])


def window_features(daily: pd.DataFrame, ehr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, g in daily.groupby("pid"):
        g = g.set_index("day").sort_index()
        for d in range(FIRST_DAY, config.N_DAYS):
            win = g.loc[d - 6:d]
            last3 = g.loc[d - 2:d]
            base = g.loc[:d - 7]
            r = {"pid": pid, "day": d}
            zs = []
            for m, sign in METRICS.items():
                r[f"{m}_mean7"] = win[m].mean()
                r[f"{m}_last3"] = last3[m].mean()
                r[f"{m}_slope"] = _slope(win[m].to_numpy(float))
                mu, sd = base[m].mean(), base[m].std()
                sd = max(sd if np.isfinite(sd) else 0, Z_FLOOR[m])
                z = (r[f"{m}_last3"] - mu) / sd
                r[f"z_{m}"] = z
                zs.append(sign * z)
            r["z_composite"] = float(np.nanmean(zs))
            r["n_days"] = int(win.rhr.notna().sum())
            rows.append(r)
    w = pd.DataFrame(rows)
    return w.merge(ehr[["pid"] + EHR_COLS], on="pid", how="left")


def labels(w: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    ev = events.set_index("pid").day
    E = w.pid.map(ev)
    w = w.copy()
    w["event_day"] = E
    w["label"] = ((E > w.day) & (E <= w.day + HORIZON_DAYS)).astype(int)
    w["post_event"] = (E <= w.day).fillna(False)
    return w


Z_COLS = [f"z_{m}" for m in METRICS]


def feature_cols(w: pd.DataFrame) -> list[str]:
    return [c for c in w.columns if c not in ("pid", "day", "event_day", "label", "post_event", "split", "n_days")]


def fit(w: pd.DataFrame) -> dict:
    train = w[(w.split == "train") & ~w.post_event]
    cal = w[(w.split == "calibration") & ~w.post_event]
    cols = feature_cols(w)
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=config.SEED)
    iso.fit(train[Z_COLS].fillna(0))
    pos = train.label.mean()
    clf = lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=15, min_child_samples=15,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=2.0,
                             scale_pos_weight=(1 - pos) / pos, random_state=config.SEED, verbose=-1)
    clf.fit(train[cols], train.label)
    model = {"iso": iso, "clf": clf, "cols": cols}
    S = _component_scores(model, cal)
    stack = LogisticRegression(C=1.0).fit(S, cal.label)
    model["stack"] = stack
    p_cal = stack.predict_proba(S)[:, 1]
    neg = np.sort(p_cal[cal.label.to_numpy() == 0])
    # Operating point: 95% specificity on calibration patients, to keep the ward flag burden low.
    model["threshold"] = float(neg[int(np.ceil(0.95 * len(neg))) - 1])
    model["explainer"] = shap.TreeExplainer(clf)
    return model


def _component_scores(model: dict, w: pd.DataFrame) -> np.ndarray:
    iso = -model["iso"].score_samples(w[Z_COLS].fillna(0))
    z = w.z_composite.fillna(0).to_numpy()
    p = model["clf"].predict_proba(w[model["cols"]])[:, 1]
    logit = np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
    return np.column_stack([iso, z, logit])


def score(model: dict, w: pd.DataFrame) -> pd.DataFrame:
    S = _component_scores(model, w)
    out = w[["pid", "day"]].copy()
    out["iso_score"], out["z_score"], out["lgbm_logit"] = S[:, 0], S[:, 1], S[:, 2]
    out["lgbm_prob"] = 1 / (1 + np.exp(-S[:, 2]))
    out["risk"] = model["stack"].predict_proba(S)[:, 1]
    out["flag"] = out.risk >= model["threshold"]
    return out


PHRASES = {
    "rmssd": ("HRV (RMSSD) down", "ms"), "rhr": ("resting heart rate up", "bpm"),
    "deep_min": ("less deep sleep", "min"), "rem_min": ("less REM sleep", "min"),
    "awakenings": ("more night awakenings", ""), "efficiency": ("lower sleep efficiency", ""),
    "sleep_h": ("shorter sleep", "h"), "steps": ("fewer steps", ""),
}


def factors(model: dict, w: pd.DataFrame, top: int = 4) -> list[list[dict]]:
    """Top contributing factors per window: SHAP of the supervised model grouped by metric,
    with the patient's own baseline deviation used for the wording."""
    sv = model["explainer"].shap_values(w[model["cols"]])
    sv = sv[1] if isinstance(sv, list) else sv
    cols = model["cols"]
    out = []
    for i in range(len(w)):
        row = w.iloc[i]
        groups: dict[str, float] = {}
        for j, c in enumerate(cols):
            key = next((m for m in METRICS if c == f"z_{m}" or c.startswith(m + "_")), None) or c
            groups[key] = groups.get(key, 0.0) + float(sv[i, j])
        items = sorted(groups.items(), key=lambda kv: -kv[1])
        res = []
        for key, val in items[:top]:
            if val <= 0:
                continue
            res.append({"factor": key, "shap": round(val, 3), "text": factor_text(key, row)})
        out.append(res)
    return out


def _vs_usual(z: float, higher: bool) -> str:
    """Plain words for a deviation from the patient's own usual level."""
    if not np.isfinite(z) or abs(z) < 0.5:
        return "about usual"
    size = "slightly" if abs(z) < 1 else "clearly" if abs(z) < 2 else "well"
    return f"{size} {'above' if (z > 0) == higher else 'below'} usual"


def factor_text(key: str, row: pd.Series) -> str:
    if key in PHRASES:
        last3 = row.get(f"{key}_last3")
        z = float(row.get(f"z_{key}", np.nan))
        usual = _vs_usual(z, True)
        if key == "efficiency":
            return f"Sleep efficiency {last3 * 100:.0f}% over the last 3 nights, {usual}"
        if key == "sleep_h":
            return f"Sleep {last3:.1f} h a night over the last 3 nights, {usual}"
        if key == "steps":
            return f"{last3:,.0f} steps a day over the last 3 days, {usual}"
        if key == "awakenings":
            return f"{last3:.1f} awakenings a night over the last 3 nights, {usual}"
        labels = {"rhr": "Resting heart rate", "rmssd": "Heart rate variability", "deep_min": "Deep sleep", "rem_min": "REM sleep"}
        unit = PHRASES[key][1]
        return f"{labels.get(key, key)} {last3:.0f} {unit} over the last 3 nights, {usual}"
    ehr = {"age": f"Age {row.get('age', 0):.0f}", "sbp": f"Systolic BP {row.get('sbp', 0):.0f} mmHg",
           "fh_cad": "Family history of ischaemic heart disease", "fh_mi": "Family history of myocardial infarction",
           "chd_9p21_risk": f"9p21 risk alleles: {row.get('chd_9p21_risk', 0):.0f}", "tc_hdl": f"TC/HDL ratio {row.get('tc_hdl', 0):.1f}",
           "ldl": f"LDL {row.get('ldl', 0):.0f} mg/dL", "hypertension": "Hypertension", "dyslipidemia": "Dyslipidaemia",
           "smoker_current": "Current smoker", "t2d": "Type 2 diabetes", "hba1c": f"HbA1c {row.get('hba1c', 0):.1f}%",
           "male": "Male sex", "bmi": f"BMI {row.get('bmi', 0):.1f}", "z_composite": "Overall deviation from own baseline"}
    return ehr.get(key, key)


def run(verbose: bool = True) -> None:
    t0 = time.time()
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    daily = daily_metrics(con)
    ehr = con.execute("SELECT * FROM ehr_features").df()
    events = con.execute("SELECT * FROM events").df()
    con.close()
    split = json.loads((config.DATA_DIR / "splits.json").read_text())
    w = labels(window_features(daily, ehr), events)
    w["split"] = w.pid.map(split)
    model = fit(w)
    scored = score(model, w)
    scored = scored.merge(w[["pid", "day", "label", "post_event", "event_day", "split"]], on=["pid", "day"])
    f = factors(model, w)
    scored["factors"] = [json.dumps(x) for x in f]
    daily.to_parquet(config.ARTIFACT_DIR / "cardio_daily.parquet", index=False)
    w.to_parquet(config.ARTIFACT_DIR / "cardio_windows.parquet", index=False)
    scored.to_parquet(config.ARTIFACT_DIR / "cardio_scores.parquet", index=False)
    joblib.dump({k: v for k, v in model.items() if k != "explainer"}, config.ARTIFACT_DIR / "cardio_model.joblib")
    if verbose:
        from sklearn.metrics import average_precision_score, roc_auc_score
        t = scored[(scored.split == "test") & ~scored.post_event]
        print(f"cardio windows: {len(w)}, positives train/cal/test "
              f"{[int(scored[(scored.split == s) & ~scored.post_event].label.sum()) for s in ('train', 'calibration', 'test')]}")
        for col in ("iso_score", "z_score", "lgbm_prob", "risk"):
            print(f"  test {col:10s} AUROC {roc_auc_score(t.label, t[col]):.3f}  AUPRC {average_precision_score(t.label, t[col]):.3f}")
        su = scored[scored.pid == config.HERO_IDS["suresh"]].set_index("day")
        print("  Suresh risk by day:", {int(d): round(r, 2) for d, r in su.risk.items() if d >= 20},
              "threshold", round(model["threshold"], 3))
        print(f"  ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    run()
