"""Hypoglycaemia as an event in its own right.

Two parts:
1. Compression artefact filter. Lying on the sensor at night produces a sharp false dip that
   recovers within about 45 minutes; real overnight falls are slow. Offline we mark the whole
   dip (used to clean labels); online we can only flag a suspicious reading (fast fall while
   asleep), which the dashboard reports as "probable sensor compression" instead of a low.
2. A LightGBM classifier for "glucose below 70 mg/dL within 60 minutes", trained on the same
   features as the forecaster but on artefact cleaned labels, with its threshold chosen on
   calibration patients under a false alarm budget.
"""
from __future__ import annotations

import json
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from prativimb import config
from prativimb.eval.alerts import evaluate_alerts
from prativimb.ml.glucose import feature_columns
from prativimb.twin import series
from prativimb.twin.series import N, PER_DAY, STEP

LOOKAHEAD = 12          # 60 minutes
FA_BUDGET = 0.25        # false alarms per patient day, on calibration patients (lows are the costlier miss)


def asleep_mask(s: series.Series) -> np.ndarray:
    m = np.zeros(N, bool)
    if s.nightly is not None:
        for a, b in zip(s.nightly.bed_minute.to_numpy(), s.nightly.wake_minute.to_numpy()):
            m[int(a) // STEP: int(b) // STEP + 1] = True
    return m


def compression_artefacts(cgm: np.ndarray, asleep: np.ndarray, drop: float = 20, rate: float = 15,
                           match: float = 12) -> np.ndarray:
    """Offline: True for readings inside a compression dip.

    A compression dip happens during sleep, falls and recovers at least `rate` mg/dL within 15
    minutes on each side, is at least `drop` below the level before it, and returns to within
    `match` of that level. Real overnight falls are slower and do not bounce back. Validated
    against the dips the sensor simulator injects (see run()).
    """
    c = cgm
    out = np.zeros(len(c), bool)
    for i in range(7, len(c) - 9):
        if not asleep[i] or np.isnan(c[i]) or c[i] > 110:
            continue
        if np.nanmin(c[i - 3:i + 4]) < c[i]:
            continue
        b, a = c[i - 7:i - 2], c[i + 4:i + 9]
        b, a = b[~np.isnan(b)], a[~np.isnan(a)]
        if len(b) < 3 or len(a) < 3:
            continue
        before, after = float(np.median(b)), float(np.median(a))
        if before - c[i] < drop or abs(after - before) > match:
            continue
        if not (np.isfinite(c[i - 3]) and c[i - 3] - c[i] >= rate and np.isfinite(c[i + 3]) and c[i + 3] - c[i] >= rate):
            continue
        lo = min(before, after) - 8
        j, k = i, i
        while j > i - 6 and np.isfinite(c[j - 1]) and c[j - 1] < lo:
            j -= 1
        while k < i + 6 and np.isfinite(c[k + 1]) and c[k + 1] < lo:
            k += 1
        out[j:k + 1] = True
    return out


def suspect_now(cgm: np.ndarray, asleep: np.ndarray, k: int) -> bool:
    """Online: a low reading reached by a fall of at least 1 mg/dL per minute while asleep."""
    if k < 3 or np.isnan(cgm[k]) or not asleep[k]:
        return False
    prev = cgm[k - 3]
    return bool(np.isfinite(prev) and prev - cgm[k] >= 15 and cgm[k] < 90)


def labels(cgm: np.ndarray, artefact: np.ndarray, ks: np.ndarray) -> np.ndarray:
    clean = np.where(artefact, np.nan, cgm)
    low = np.nan_to_num(clean, nan=200) < config.LOW_THRESHOLD
    pair = low[:-1] & low[1:]                         # two consecutive readings below 70
    pair = np.concatenate([pair, [False]])
    cs = np.concatenate([[0], np.cumsum(pair)])
    n = len(cgm)
    k1 = np.minimum(ks + 1, n)
    k2 = np.minimum(ks + LOOKAHEAD + 1, n)
    return ((cs[k2] - cs[k1]) > 0).astype(int)


def low_onsets_clean(c: np.ndarray, start: int, artefact: np.ndarray) -> np.ndarray:
    clean = np.where(artefact, np.nan, c)
    below = np.nan_to_num(clean, nan=200) < config.LOW_THRESHOLD
    out = []
    for i in range(max(start, 6), len(c) - 2):
        if below[i] and below[i + 1] and below[i + 2] and not below[i - 6:i].any():
            out.append(i)
    return np.array(out, int)


def run(verbose: bool = True) -> dict:
    t0 = time.time()
    df = pd.read_parquet(config.ARTIFACT_DIR / "glucose_dataset.parquet")
    preds = pd.read_parquet(config.ARTIFACT_DIR / "glucose_predictions.parquet")
    cols = feature_columns(df)
    S = series.load_all()
    art, sleep = {}, {}
    y = np.zeros(len(df), int)
    for pid, idx in df.groupby("pid").indices.items():
        s = S[pid]
        sleep[pid] = asleep_mask(s)
        art[pid] = compression_artefacts(s.cgm, sleep[pid])
        y[idx] = labels(s.cgm, art[pid], df.k.to_numpy()[idx])
    df["low60"] = y
    eligible = df.cgm >= config.LOW_THRESHOLD
    tr = (df.split == "train") & eligible
    pos = df.loc[tr, "low60"].mean()
    clf = lgb.LGBMClassifier(n_estimators=600, learning_rate=0.03, num_leaves=31, min_child_samples=60, subsample=0.8,
                             subsample_freq=1, colsample_bytree=0.8, scale_pos_weight=min(20.0, (1 - pos) / pos),
                             random_state=config.SEED, verbose=-1, n_jobs=-1)
    clf.fit(df.loc[tr, cols], df.loc[tr, "low60"])

    # Choose the threshold on calibration patients: most sensitive within the false alarm budget.
    cgm = {pid: S[pid].cgm for pid in df.pid.unique()}
    def policy(part: pd.DataFrame, thr: float) -> np.ndarray:
        p = clf.predict_proba(part[cols])[:, 1]
        return (p >= thr) & (part.cgm.to_numpy() >= config.LOW_THRESHOLD)
    def onset_fn_for(pid_art):
        return lambda c, start: low_onsets_clean(c, start, pid_art)

    def evaluate(part: pd.DataFrame, hits: np.ndarray) -> dict:
        tot = {"events": 0, "detected": 0, "alert_episodes": 0, "false": 0, "days": 0.0, "leads": []}
        for pid, g in part.assign(hit=hits).groupby("pid"):
            r = evaluate_alerts(g, {pid: cgm[pid]}, g.hit.to_numpy(), onset_fn=onset_fn_for(art[pid]), window=LOOKAHEAD)
            tot["events"] += r["events"]; tot["detected"] += r["detected"]; tot["alert_episodes"] += r["alert_episodes"]
            tot["false"] += r["alert_episodes"] - round(r["precision"] * r["alert_episodes"])
            tot["days"] += r["patient_days"]
            if r["median_lead_min"] is not None:
                tot["leads"] += [r["median_lead_min"]] * max(r["detected"], 1)
        return {"events": tot["events"], "sensitivity": tot["detected"] / max(tot["events"], 1),
                "precision": (tot["alert_episodes"] - tot["false"]) / max(tot["alert_episodes"], 1),
                "median_lead_min": float(np.median(tot["leads"])) if tot["leads"] else None,
                "false_alarms_per_patient_day": tot["false"] / max(tot["days"], 1e-9)}

    cal = df[df.split == "calibration"]
    scan = []
    for thr in (0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99):
        scan.append({"threshold": thr, **evaluate(cal, policy(cal, thr))})
    ok = [r for r in scan if r["false_alarms_per_patient_day"] <= FA_BUDGET]
    best = max(ok, key=lambda r: r["sensitivity"]) if ok else scan[-1]
    thr = best["threshold"]

    test = df[df.split == "test"].reset_index(drop=True)
    tp = preds[preds.split == "test"].reset_index(drop=True)
    old = (np.column_stack([tp[f"hyb{h}"] < config.LOW_THRESHOLD for h in (30, 60)]).any(1)
           & (tp.cgm.to_numpy() >= config.LOW_THRESHOLD))
    result = {
        "threshold": thr, "fa_budget": FA_BUDGET, "calibration_scan": scan,
        "test_classifier": evaluate(test, policy(test, thr)),
        "test_point_forecast": evaluate(test, old),
    }
    # Artefact detector against the compression dips the sensor simulator injected. Only dips that
    # take the reading below 90 mg/dL matter for low glucose labels, so recall is measured on those.
    truth = pd.read_parquet(config.PROCESSED_DIR / "truth_glucose.parquet", columns=["pid", "minute", "compression"])
    tp_, fp_, fn_, ev_hit, ev_all = 0, 0, 0, 0, 0
    for pid, g in truth.groupby("pid"):
        c = S[pid].cgm
        a = art[pid] if pid in art else compression_artefacts(c, asleep_mask(S[pid]))
        true_art = np.zeros(N, bool)
        true_art[g.minute.to_numpy() // STEP] = g.compression.to_numpy()
        relevant = true_art & (np.nan_to_num(c, nan=999) < 90)
        tp_ += int((a & true_art).sum()); fp_ += int((a & ~true_art).sum()); fn_ += int((~a & relevant).sum())
        starts = np.flatnonzero(np.diff(np.concatenate([[0], relevant.astype(int)])) == 1)
        for st in starts:
            ev_all += 1
            ev_hit += int(a[st: st + 8].any())
    result["artefact_detector"] = {"reading_precision": tp_ / max(tp_ + fp_, 1), "reading_recall": tp_ / max(tp_ + fn_, 1),
                                   "dips_found": ev_hit, "dips": ev_all}
    joblib.dump({"model": clf, "threshold": thr, "features": cols}, config.ARTIFACT_DIR / "low_model.joblib")
    (config.ARTIFACT_DIR / "low_metrics.json").write_text(json.dumps(result, indent=1, default=float))
    if verbose:
        c_, o_ = result["test_classifier"], result["test_point_forecast"]
        print(f"low model: threshold {thr} (calibration); test sensitivity {c_['sensitivity']:.2f} vs point rule "
              f"{o_['sensitivity']:.2f}, precision {c_['precision']:.2f} vs {o_['precision']:.2f}, FA/pd "
              f"{c_['false_alarms_per_patient_day']:.2f} vs {o_['false_alarms_per_patient_day']:.2f}; "
              f"artefact detector precision {result['artefact_detector']['reading_precision']:.2f}, dips found "
              f"{result['artefact_detector']['dips_found']} of {result['artefact_detector']['dips']} ({time.time() - t0:.0f}s)")
    return result


if __name__ == "__main__":
    run()
