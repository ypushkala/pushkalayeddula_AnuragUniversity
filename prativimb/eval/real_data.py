"""Validation on real CGM traces: CGMacros (PhysioNet, open access, CC BY-NC-SA 4.0).

45 adults (normoglycaemia, prediabetes, Type 2 diabetes) wore a Dexcom G6 and a Fitbit for about
ten days and logged meals with known carbohydrate. There is no sleep or medication data. We do
not redistribute the data; run scripts/fetch_cgmacros.sh first.

Protocol, per participant:
  * days 1 to 5 calibrate the twin; the "declared routine" is the participant's median meal time
    and carbohydrate per meal type over those days;
  * days 6 onward are scored at 30, 60 and 120 minutes, origins every 10 minutes;
  * models: persistence, the calibrated twin with its routine prior, the hybrid and ML only
    models trained on synthetic data only (zero shot transfer), and the twin told about each
    real meal in advance (what the planned meal feature gives when patients use it);
  * conformal: coverage of the synthetic calibrated intervals on real data, then intervals
    recalibrated on half the participants and tested on the other half (site onboarding).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from prativimb import config
from prativimb.eval import style
from prativimb.ml import conformal
from prativimb.ml.features import glucose_features
from prativimb.twin import calibrate, forecast
from prativimb.twin.series import N, PER_DAY, STEP, Series

ROOT = config.DATA_DIR / "external" / "cgmacros" / "CGMacros"
CAL_DAYS = 5
HS = (30, 60, 120)
SLOT = {"Breakfast": "Breakfast", "Lunch": "Lunch", "Dinner": "Dinner", "Snacks": "Snack", "Snack": "Snack"}


def group(a1c: float) -> str:
    return "T2D" if a1c >= 6.5 else "prediabetes" if a1c >= 5.7 else "normoglycaemia"


def load_participant(sid: int, bio: pd.Series) -> Series | None:
    path = ROOT / f"CGMacros-{sid:03d}" / f"CGMacros-{sid:03d}.csv"
    if not path.exists():
        return None
    d = pd.read_csv(path)
    d.columns = [c.strip() for c in d.columns]
    d["Timestamp"] = pd.to_datetime(d["Timestamp"])
    t0 = d["Timestamp"].min().normalize()
    minute = ((d["Timestamp"] - t0).dt.total_seconds() // 60).astype(int).to_numpy()
    keep = minute < N * STEP
    d, minute = d[keep], minute[keep]
    k = minute // STEP
    cgm = np.full(N, np.nan)
    g = d["Dexcom GL"].to_numpy(float)
    ok = np.isfinite(g)
    if ok.sum() < 500:
        return None
    cgm[k[ok]] = g[ok]
    hr = np.full(N, np.nan)
    hr_df = pd.DataFrame({"k": k, "hr": d["HR"].to_numpy(float)}).groupby("k").hr.mean()
    hr[hr_df.index.to_numpy()] = hr_df.to_numpy()
    # Activity comes as Fitbit METs (stored times ten), intensity levels 0 to 3, or steps, depending on
    # the participant. Each is mapped to steps per minute; walking at about 3 METs counts as 100.
    if "METs" in d:
        act = np.clip((d["METs"].to_numpy(float) / 10 - 1.5) / 1.5, 0, 1.5) * 100
    elif "Intensity" in d:
        act = d["Intensity"].map({0: 0.0, 1: 30.0, 2: 100.0, 3: 140.0}).to_numpy(float)
    elif "Steps" in d:
        act = d["Steps"].to_numpy(float)
    else:
        act = np.zeros(len(d))
    a = pd.DataFrame({"k": k, "a": act}).groupby("k").a.mean().fillna(0)
    steps = np.zeros(N)
    steps[a.index.to_numpy()] = a.to_numpy()
    meals = d[d["Carbs"].notna() & (d["Carbs"] > 0)].copy()
    amount = meals["Amount Consumed"].fillna(100).clip(0, 100) / 100 if "Amount Consumed" in meals else 1.0
    meals["carbs"] = meals["Carbs"] * amount
    meals["minute"] = ((meals["Timestamp"] - t0).dt.total_seconds() // 60).astype(int)
    meals = meals[meals.carbs >= 3]
    carbs, af = np.zeros(N), np.zeros(N)
    for m, c in zip(meals.minute, meals.carbs):
        if m // STEP < N:
            carbs[m // STEP] += c
            af[m // STEP] = 1.0
    log = pd.DataFrame({"minute": meals.minute.to_numpy(), "carbs": meals.carbs.to_numpy(),
                        "kind": "rice_meal", "description": meals["Meal Type"].fillna("Meal").to_numpy()})
    # Declared routine: median time and carbohydrate per meal type over the calibration days.
    cal = meals[meals.minute < CAL_DAYS * 1440].copy()
    cal["slot"] = cal["Meal Type"].map(SLOT).fillna("Snack")
    cal["tod"] = cal.minute % 1440
    routine = []
    for slot, gq in cal.groupby("slot"):
        per_day = gq.groupby(gq.minute // 1440).carbs.sum()
        if slot == "Snack" and len(per_day) < 3:
            continue
        routine.append((int(gq.tod.median()), float(per_day.median()), "rice_meal", slot))
    a1c = float(bio["A1c PDL (Lab)"])
    ehr = {"hba1c": a1c, "bmi": float(bio["BMI"]), "age": float(bio["Age"]), "fpg": float(bio["Fasting GLU - PDL (Lab)"]),
           "t2d": int(a1c >= 6.5), "prediabetes": int(5.7 <= a1c < 6.5), "male": int(str(bio["Gender"]).strip() == "M"),
           "weight": float(bio["Body weight "]) * 0.4536, "on_metformin": 0, "tcf7l2_risk": np.nan, "night_shift": 0}
    return Series(pid=f"CGM-{sid:03d}", ehr=ehr, cgm=cgm, carbs=carbs, meal_af=af, steps=steps, hr=hr,
                  met_dose=np.zeros(N), met_missed=np.zeros(N), sleep_hours=np.full(config.N_DAYS, np.nan),
                  nightly=None, routine={"normal": routine}, declared={}, meal_log=log)


def evaluate_participant(s: Series, bundle: dict) -> pd.DataFrame | None:
    theta, info = calibrate.calibrate(s, days=CAL_DAYS)
    pp = forecast.prepare(s)
    last = int(np.flatnonzero(np.isfinite(s.cgm)).max())
    ks = np.arange(CAL_DAYS * PER_DAY, last - 24, 2)
    ks = ks[np.isfinite(s.cgm[ks]) & (ks >= forecast.W)]
    if len(ks) < 50:
        return None
    G = forecast.forecast(pp, theta, ks, 24)
    G_known = forecast.forecast(pp, theta, ks, 24, future="actual")  # meals announced in advance
    X = glucose_features(pp, ks, G, theta)
    out = pd.DataFrame({"pid": s.pid, "k": ks, "group": group(s.ehr["hba1c"]), "cgm": s.cgm[ks]})
    for h in HS:
        j = h // STEP
        m = bundle["models"][h]
        tw = X[f"tw{h}"].to_numpy()
        out[f"y{h}"] = forecast._take(s.cgm, ks + j, np.nan)
        out[f"persist{h}"] = s.cgm[ks]
        out[f"phys{h}"] = tw
        out[f"known{h}"] = G_known[:, j]
        out[f"ml{h}"] = m["ml"].predict(X[bundle["ml_features"]])
        out[f"hyb{h}"] = tw + m["hybrid"].predict(X[bundle["features"]])
        out[f"qlo{h}"] = tw + m["q_lo"].predict(X[bundle["features"]])
        out[f"qhi{h}"] = tw + m["q_hi"].predict(X[bundle["features"]])
    out.attrs["fit_rmse"] = info["rmse_fit"]
    return out


MODELS = [("persist", "Persistence (no change)"), ("phys", "Twin, calibrated, routine prior"),
          ("ml", "LightGBM only (synthetic trained)"), ("hyb", "Hybrid (synthetic trained)"),
          ("known", "Twin, meals announced in advance")]


def summarise(df: pd.DataFrame, bundle: dict) -> dict:
    res = {"participants": int(df.pid.nunique()), "by_group": {}}
    for gname, g in [("all", df)] + list(df.groupby("group")):
        r = {"participants": int(g.pid.nunique()), "origins": int(len(g))}
        for h in HS:
            ok = g[f"y{h}"].notna()
            y = g.loc[ok, f"y{h}"].to_numpy()
            r[h] = {k: float(np.sqrt(np.mean((g.loc[ok, f"{k}{h}"].to_numpy() - y) ** 2))) for k, _ in MODELS}
        res["by_group"][gname] = r
    # Conformal: synthetic calibration as is, then recalibrated on half the real participants.
    rng = np.random.default_rng(config.SEED)
    pids = np.array(sorted(df.pid.unique()))
    rng.shuffle(pids)
    cal_p, test_p = set(pids[: len(pids) // 2]), set(pids[len(pids) // 2:])
    cov = {}
    for h in HS:
        ok = df[f"y{h}"].notna()
        d = df[ok]
        y = d[f"y{h}"].to_numpy()
        q = bundle["models"][h]["cqr_q"]
        lo, hi = d[f"qlo{h}"] - q, d[f"qhi{h}"] + q
        t = d.pid.isin(test_p).to_numpy()
        c = d.pid.isin(cal_p).to_numpy()
        scores = conformal.cqr_scores(d[f"qlo{h}"].to_numpy()[c], d[f"qhi{h}"].to_numpy()[c], y[c])
        q2 = conformal.conformal_quantile(scores, config.CONFORMAL_ALPHA)
        lo2, hi2 = d[f"qlo{h}"].to_numpy()[t] - q2, d[f"qhi{h}"].to_numpy()[t] + q2
        cov[h] = {"synthetic_calibration": conformal.coverage(lo.to_numpy()[t], hi.to_numpy()[t], y[t]),
                  "synthetic_width": float(np.median((hi - lo).to_numpy()[t])),
                  "site_recalibrated": conformal.coverage(lo2, hi2, y[t]), "site_width": float(np.median(hi2 - lo2))}
    res["conformal"] = cov
    res["calibration_split"] = {"calibration_participants": len(cal_p), "test_participants": len(test_p)}
    return res


def figure(res: dict) -> None:
    style.use()
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6), gridspec_kw={"width_ratios": [1.4, 1]})
    ax = axes[0]
    names = {"persist": "Persistence", "phys": "Twin, routine", "ml": "LightGBM (synthetic)", "hyb": "Hybrid (synthetic)",
             "known": "Twin, meals announced"}
    colors = {"persist": style.GREY, "phys": style.GREY_DARK, "ml": style.GREY, "hyb": style.GREY_DARK, "known": style.ACCENT}
    r = res["by_group"]["all"]
    ends = []
    for k, _ in MODELS:
        v = [r[h][k] for h in HS]
        ax.plot(HS, v, color=colors[k], lw=2.3 if k == "known" else 1.4,
                linestyle=(0, (3, 2)) if k in ("ml", "persist") else "-")
        ends.append([v[-1], k])
    # Spread end labels so close lines stay legible; leader lines tie each label to its line.
    ends.sort()
    pos = [e[0] for e in ends]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + 2.9)
    for (val, k), y in zip(ends, pos):
        ax.plot([HS[-1], HS[-1] + 9], [val, y], color=style.RULE, lw=0.7)
        ax.text(HS[-1] + 11, y, f"{names[k]}  {val:.1f}", va="center", fontsize=8,
                color=style.INK if k == "known" else style.INK_2)
    ax.set_xticks(HS, [f"{h} min" for h in HS]); ax.set_xlim(25, 200); ax.set_ylim(0, max(pos) + 3)
    ax.set_ylabel("RMSE, mg/dL"); ax.grid(axis="x", visible=False)
    style.title(ax, "Real CGM traces (CGMacros)", f"{res['participants']} participants, days 6 onward")
    ax = axes[1]
    c = res["conformal"]
    xs = np.arange(len(HS))
    ax.bar(xs - 0.18, [c[h]["synthetic_calibration"] * 100 for h in HS], width=0.34, color=style.GREY, label="Synthetic calibration")
    ax.bar(xs + 0.18, [c[h]["site_recalibrated"] * 100 for h in HS], width=0.34, color=style.ACCENT, label="Recalibrated on site")
    ax.axhline(90, color=style.INK_3, lw=0.8)
    ax.text(-0.45, 91.5, "target 90%", fontsize=7.8, color=style.INK_3)
    ax.set_xticks(xs, [f"{h} min" for h in HS]); ax.set_ylim(0, 100); ax.set_ylabel("90% interval coverage, %")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=7.8); ax.grid(axis="x", visible=False)
    style.title(ax, "Interval coverage on real data")
    fig.tight_layout(w_pad=2.5)
    style.save(fig, "real_data_cgmacros")


def markdown(res: dict) -> str:
    L = ["# Validation on real CGM traces (CGMacros)\n",
         "Data: CGMacros v1.0.0 (Gutierrez-Osuna, Kerr, Mortazavi and Das; PhysioNet 2025; doi:10.13026/3z8q-x658), open access under CC BY-NC-SA 4.0. Dexcom G6 every 5 minutes, "
         "Fitbit heart rate and activity, meals with known carbohydrate. No sleep or medication data. The data are not "
         "redistributed here; `scripts/fetch_cgmacros.sh` downloads and checks them, `make realdata` reruns this report.\n",
         "Protocol: each twin is calibrated on the participant's first 5 days, with a routine prior built from the median "
         "meal times and carbohydrate of those days. Forecasts are scored from day 6 onward every 10 minutes. The residual "
         "and ML only models were trained on synthetic Indian data only and are applied without retraining (zero shot).\n",
         "| Group | Participants | Horizon | Persistence | Twin, routine | LightGBM (synthetic) | Hybrid (synthetic) | Twin, meals announced |",
         "|---|---:|---|---:|---:|---:|---:|---:|"]
    for gname in ("all", "T2D", "prediabetes", "normoglycaemia"):
        r = res["by_group"].get(gname)
        if not r:
            continue
        for h in HS:
            L.append(f"| {gname if h == HS[0] else ''} | {r['participants'] if h == HS[0] else ''} | {h} min | "
                     + " | ".join(f"{r[str(h)][k]:.1f}" for k, _ in MODELS) + " |")
    L.append("\nRMSE in mg/dL against the Dexcom reading at the target time.\n")
    c = {int(k): v for k, v in res["conformal"].items()}
    cs = res["calibration_split"]
    L.append("| Horizon | Coverage, synthetic calibration | Median width | Coverage, recalibrated on site | Median width |")
    L.append("|---|---:|---:|---:|---:|")
    for h in HS:
        x = c[h]
        L.append(f"| {h} min | {x['synthetic_calibration'] * 100:.1f}% | {x['synthetic_width']:.0f} mg/dL | "
                 f"{x['site_recalibrated'] * 100:.1f}% | {x['site_width']:.0f} mg/dL |")
    L.append(f"\nSite recalibration uses {cs['calibration_participants']} participants and is tested on the other "
             f"{cs['test_participants']}. The quantile models stay as trained; only the conformal margin is refitted.\n")
    a = res["by_group"]["all"]
    L.append("## What this shows\n")
    L.append(f"* **Known meals are where the twin earns its place.** Told about each meal in advance, the calibrated twin "
             f"cuts 2 hour error from {a['120']['persist']:.1f} (persistence) to {a['120']['known']:.1f} mg/dL. That is the "
             "case the planned meal input in the dashboard is built for.")
    L.append(f"* **Synthetic training transfers, but only just.** Models trained only on synthetic Indian data land close "
             f"to persistence on American real world traces ({a['120']['hyb']:.1f} against {a['120']['persist']:.1f} at "
             "2 hours). Retraining the residual model on local data is the obvious next step.")
    L.append("* **The routine prior is weak here.** CGMacros participants ate on a varied study schedule, so median meal "
             "times from five days predict the next meal poorly, and the twin trails persistence at 30 minutes because a "
             "forecast starts from the observer estimate rather than the last reading.")
    L.append("* **Conformal intervals must be recalibrated per site.** Synthetic calibration under covers on real data; "
             "refitting only the conformal margin on half the participants brings coverage to within about 2 to 3 points "
             "of 90%, with wider intervals.\n")
    L.append("![Real data](figures/real_data_cgmacros.png)\n")
    return "\n".join(L)


def run(verbose: bool = True) -> dict | None:
    t0 = time.time()
    if not (ROOT / "bio.csv").exists():
        print("CGMacros not found. Run scripts/fetch_cgmacros.sh first.")
        return None
    bio = pd.read_csv(ROOT / "bio.csv").set_index("subject")
    bundle = joblib.load(config.ARTIFACT_DIR / "glucose_models.joblib")
    S = [s for s in (load_participant(int(sid), row) for sid, row in bio.iterrows()) if s is not None]
    parts = Parallel(n_jobs=-1)(delayed(evaluate_participant)(s, bundle) for s in S)
    df = pd.concat([p for p in parts if p is not None], ignore_index=True)
    res = summarise(df, bundle)
    figure(res)
    (config.REPORT_DIR / "real_data.json").write_text(json.dumps(res, indent=1, default=float))
    (config.REPORT_DIR / "real_data.md").write_text(markdown(json.loads(json.dumps(res, default=float))))
    if verbose:
        r = res["by_group"]["all"]
        for h in HS:
            print(f"  {h:>3} min RMSE: " + ", ".join(f"{k} {r[h][k]:.1f}" for k, _ in MODELS))
        for h in HS:
            x = res["conformal"][h]
            print(f"  {h:>3} min coverage: synthetic {x['synthetic_calibration']:.3f}, recalibrated {x['site_recalibrated']:.3f}")
        print(f"real data: {res['participants']} participants, {len(df):,} origins ({time.time() - t0:.0f}s)")
    return res


if __name__ == "__main__":
    run()
