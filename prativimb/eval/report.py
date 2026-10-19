"""Evaluation report: reports/metrics.json, reports/metrics.md and reports/figures/*.png.

All numbers are on test patients (never seen in training, early stopping or conformal
calibration) and on days 8 to 30 (after the twin calibration week).
"""
from __future__ import annotations

import json
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve, precision_recall_curve

from prativimb import config
from prativimb.eval import clarke, style
from prativimb.eval.alerts import LEVELS, alert_policy, evaluate_alerts, low_onsets, lower_hits
from prativimb.ml import conformal
from prativimb.twin.series import PER_DAY

MODELS = [("cold", "Twin, EHR prior only"), ("phys", "Twin, calibrated (physics only)"),
          ("ml", "LightGBM only"), ("hyb", "Hybrid (twin + residual LightGBM)")]


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def mard(pred, ref):
    return float(np.mean(np.abs(pred - ref) / ref) * 100)


# Glucose ---------------------------------------------------------------------------------

def glucose_accuracy(t: pd.DataFrame) -> dict:
    out = {}
    for h in config.HORIZONS:
        ok = t[f"y{h}"].notna()
        y = t.loc[ok, f"y{h}"].to_numpy()
        out[h] = {m: {"rmse": rmse(t.loc[ok, f"{m}{h}"].to_numpy(), y), "mard": mard(t.loc[ok, f"{m}{h}"].to_numpy(), y)}
                  for m, _ in MODELS}
        out[h]["n"] = int(ok.sum())
        out[h]["clarke"] = clarke.zone_table(y, t.loc[ok, f"hyb{h}"].to_numpy())
    return out


def conformal_summary(t: pd.DataFrame, bundle_q: dict) -> dict:
    out = {}
    for h in config.HORIZONS:
        ok = t[f"y{h}"].notna()
        y = t.loc[ok, f"y{h}"]
        lo, hi = t.loc[ok, f"lo{h}"], t.loc[ok, f"hi{h}"]
        hy = t.loc[ok, f"hyb{h}"]
        q_abs = bundle_q[h]
        by_range = {}
        for name, m in (("below 70", y < 70), ("70 to 180", (y >= 70) & (y <= 180)), ("above 180", y > 180)):
            by_range[name] = {"coverage": conformal.coverage(lo[m], hi[m], y[m]), "n": int(m.sum())}
        out[h] = {
            "cqr_coverage": conformal.coverage(lo, hi, y), "cqr_median_width": float(np.median(hi - lo)),
            "split_coverage": conformal.coverage(hy - q_abs, hy + q_abs, y), "split_width": float(2 * q_abs),
            "by_range": by_range,
        }
    return out


# Cardio ----------------------------------------------------------------------------------

def sens_at_spec(y, s, spec):
    fpr, tpr, _ = roc_curve(y, s)
    return float(np.max(tpr[fpr <= 1 - spec])) if (fpr <= 1 - spec).any() else 0.0


def bootstrap_ci(df: pd.DataFrame, col: str, fn, n: int = 1000, seed: int = config.SEED):
    rng = np.random.default_rng(seed)
    pids = df.pid.unique()
    groups = {p: g for p, g in df.groupby("pid")}
    vals = []
    for _ in range(n):
        b = pd.concat([groups[p] for p in rng.choice(pids, len(pids))])
        if b.label.nunique() == 2:
            vals.append(fn(b.label, b[col]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def cardio_metrics(scores: pd.DataFrame, threshold: float) -> dict:
    t = scores[(scores.split == "test") & ~scores.post_event]
    comps = [("iso_score", "Isolation forest (unsupervised)"), ("z_score", "Baseline z score composite"),
             ("lgbm_prob", "LightGBM (supervised)"), ("risk", "Stacked ensemble")]
    out = {"n_windows": len(t), "n_positive": int(t.label.sum()), "n_events": int(t[t.label == 1].pid.nunique()),
           "components": {}}
    for col, name in comps:
        out["components"][col] = {
            "name": name,
            "auroc": float(roc_auc_score(t.label, t[col])), "auroc_ci": bootstrap_ci(t, col, roc_auc_score),
            "auprc": float(average_precision_score(t.label, t[col])),
            "auprc_ci": bootstrap_ci(t, col, average_precision_score),
            "sens_at_90spec": sens_at_spec(t.label, t[col], 0.90),
            "sens_at_95spec": sens_at_spec(t.label, t[col], 0.95),
        }
    out["brier"] = float(brier_score_loss(t.label, t.risk))
    out["prevalence"] = float(t.label.mean())
    flagged = t.risk >= threshold
    ev = t[t.label == 1].groupby("pid")
    caught = ev.apply(lambda g: bool((g.risk >= threshold).any()))
    lead = ev.apply(lambda g: float((g.event_day - g.day[g.risk >= threshold]).max()) if (g.risk >= threshold).any() else np.nan)
    out["operating_point"] = {
        "threshold": threshold, "specificity": float((t.risk[t.label == 0] < threshold).mean()),
        "window_sensitivity": float(flagged[t.label == 1].mean()),
        "events_caught": int(caught.sum()), "events": int(len(caught)),
        "median_lead_days": float(np.nanmedian(lead)) if caught.any() else None,
        "flags_per_patient_day": float(flagged.mean()),
    }
    bins = pd.qcut(t.risk.rank(method="first"), 8, labels=False)
    cal = t.groupby(bins).agg(pred=("risk", "mean"), obs=("label", "mean"), n=("label", "size"))
    out["calibration_bins"] = cal.to_dict(orient="records")
    return out


# Figures ---------------------------------------------------------------------------------

def fig_rmse(acc: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    hs = list(config.HORIZONS)
    colors = {"cold": style.GREY, "phys": style.GREY_DARK, "ml": style.GREY, "hyb": style.ACCENT}
    styles = {"cold": (0, (1, 0)), "phys": (0, (1, 0)), "ml": (0, (1, 0)), "hyb": (0, (1, 0))}
    for m, name in MODELS:
        vals = [acc[h][m]["rmse"] for h in hs]
        ax.plot(hs, vals, color=colors[m], lw=2.4 if m == "hyb" else 1.6, linestyle=styles[m], zorder=3 if m == "hyb" else 2)
        ax.scatter(hs, vals, s=22, color=colors[m], edgecolor=style.PAPER, linewidth=1.5, zorder=4)
        ax.annotate(f"{name.split(' (')[0]}  {vals[-1]:.1f}", (hs[-1], vals[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=style.INK if m == "hyb" else style.INK_2,
                    bbox=dict(facecolor=style.PAPER, edgecolor="none", pad=1.5))
    ax.set_xticks(hs, [f"{h} min" for h in hs])
    ax.set_xlim(25, 160)
    ax.set_ylim(0, None)
    ax.set_ylabel("RMSE, mg/dL")
    ax.grid(axis="x", visible=False)
    style.title(ax, "Forecast error by horizon", "Test patients, days 8 to 30. Lower is better.")
    style.save(fig, "glucose_rmse_by_horizon")


def fig_clarke(t: pd.DataFrame, h: int = 60) -> None:
    ok = t[f"y{h}"].notna()
    d = t[ok].sample(n=min(15000, ok.sum()), random_state=config.SEED)
    y, p = d[f"y{h}"].to_numpy(), d[f"hyb{h}"].to_numpy()
    z = clarke.zones(y, p)
    fig, ax = plt.subplots(figsize=(5.2, 5.0))
    ax.scatter(y[z == "A"], p[z == "A"], s=2, color=style.ACCENT, alpha=0.25, linewidths=0)
    ax.scatter(y[z != "A"], p[z != "A"], s=3, color=style.GREY_DARK, alpha=0.5, linewidths=0)
    lc = dict(color=style.INK_3, lw=0.8)
    ax.plot([0, 400], [0, 400], color=style.RULE, lw=0.8)
    ax.plot([0, 175 / 3], [70, 70], **lc); ax.plot([175 / 3, 400 / 1.2], [70, 400], **lc)
    ax.plot([70, 70], [84, 400], **lc); ax.plot([0, 70], [180, 180], **lc); ax.plot([70, 290], [180, 400], **lc)
    ax.plot([70, 70], [0, 56], **lc); ax.plot([70, 400], [56, 320], **lc); ax.plot([180, 180], [0, 70], **lc)
    ax.plot([180, 400], [70, 70], **lc); ax.plot([240, 240], [70, 180], **lc); ax.plot([240, 400], [180, 180], **lc)
    ax.plot([130, 180], [0, 70], **lc)
    for lab, (x, yy) in {"A": (30, 15), "B": (370, 260), "B ": (280, 370), "C": (160, 370), "C ": (160, 15),
                         "D": (30, 140), "D ": (370, 120), "E": (30, 370), "E ": (370, 15)}.items():
        ax.text(x, yy, lab.strip(), fontsize=11, color=style.INK_3, fontfamily=style.SERIF)
    ax.set_xlim(0, 400); ax.set_ylim(0, 400)
    ax.set_xlabel("Reference CGM, mg/dL"); ax.set_ylabel(f"Hybrid forecast at {h} min, mg/dL")
    ax.grid(False)
    tab = clarke.zone_table(t.loc[ok, f"y{h}"], t.loc[ok, f"hyb{h}"])
    style.title(ax, f"Clarke error grid, {h} minute forecast",
                f"Zone A {tab['A']:.1f}%, B {tab['B']:.1f}%, C to E {tab['C'] + tab['D'] + tab['E']:.1f}%")
    style.save(fig, f"clarke_grid_{h}min")


def fig_coverage(conf: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    hs = list(config.HORIZONS)
    ax = axes[0]
    cov = [conf[h]["cqr_coverage"] * 100 for h in hs]
    ax.axhline(90, color=style.INK_3, lw=0.8)
    ax.text(hs[0] - 8, 90.4, "target 90%", fontsize=8, color=style.INK_3)
    ax.plot(hs, cov, color=style.ACCENT)
    ax.scatter(hs, cov, s=24, color=style.ACCENT, edgecolor=style.PAPER, linewidth=1.5, zorder=3)
    for h, c in zip(hs, cov):
        ax.annotate(f"{c:.1f}", (h, c), xytext=(0, -14), textcoords="offset points", ha="center", fontsize=8, color=style.INK_2)
    ax.set_ylim(84, 94); ax.set_xticks(hs, [f"{h}" for h in hs]); ax.set_xlabel("Horizon, min")
    ax.set_ylabel("Empirical coverage, %"); ax.grid(axis="x", visible=False)
    style.title(ax, "Interval coverage")
    ax = axes[1]
    w = [conf[h]["cqr_median_width"] for h in hs]
    ax.bar(hs, w, width=14, color=style.ACCENT, alpha=0.9)
    for h, v in zip(hs, w):
        ax.text(h, v + 2, f"{v:.0f}", ha="center", fontsize=8, color=style.INK_2)
    ax.set_xticks(hs, [f"{h}" for h in hs]); ax.set_xlabel("Horizon, min"); ax.set_ylabel("Median width, mg/dL")
    ax.grid(axis="x", visible=False)
    style.title(ax, "Interval width")
    fig.tight_layout(w_pad=3)
    style.save(fig, "conformal_coverage")


def fig_alert_tradeoff(policies: dict, curve: list[dict], level: float) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    xs = [r["false_alarms_per_patient_day"] for r in curve]
    ys = [r["sensitivity"] * 100 for r in curve]
    ax.plot(xs, ys, color=style.ACCENT, lw=1.6)
    ax.scatter(xs, ys, s=16, color=style.ACCENT, edgecolor=style.PAPER, linewidth=1.2, zorder=3)
    for r in curve:
        if r["coverage"] in (0.2, 0.9):
            ax.annotate(f"{r['coverage']:.0%} interval", (r["false_alarms_per_patient_day"], r["sensitivity"] * 100),
                        xytext=(6, -10 if r["coverage"] == 0.9 else 4), textcoords="offset points", fontsize=7.8, color=style.INK_3)
    a = policies["alert"]
    ax.scatter(a["false_alarms_per_patient_day"], a["sensitivity"] * 100, s=70, facecolor=style.PAPER,
               edgecolor=style.ACCENT, linewidth=2, zorder=4)
    ax.annotate(f"Alert tier: lower bound of {level:.0%} interval", (a["false_alarms_per_patient_day"], a["sensitivity"] * 100),
                xytext=(10, -14), textcoords="offset points", fontsize=8.4, color=style.INK)
    names = {"hyb": "Watch tier: hybrid point forecast", "ml": "LightGBM only, point", "phys": "Twin only, point"}
    for k, name in names.items():
        r = policies[k]
        ax.scatter(r["false_alarms_per_patient_day"], r["sensitivity"] * 100, s=34,
                   color=style.INK_2 if k == "hyb" else style.GREY, edgecolor=style.PAPER, linewidth=1.5, zorder=3)
        ax.annotate(name, (r["false_alarms_per_patient_day"], r["sensitivity"] * 100), xytext=(-6, 7 if k != "ml" else -12),
                    textcoords="offset points", ha="right", fontsize=8.2, color=style.INK_2)
    ax.set_xlabel("False alarms per patient day")
    ax.set_ylabel("Spikes flagged in advance, %")
    ax.set_xlim(0, max(r["false_alarms_per_patient_day"] for r in policies.values()) * 1.1)
    ax.set_ylim(30, 100)
    style.title(ax, "Spike alert policies on test patients", "Line: conformal lower bound at different interval levels. Up and to the left is better.")
    style.save(fig, "alert_tradeoff")


def fig_cardio(scores: pd.DataFrame, cm: dict) -> None:
    t = scores[(scores.split == "test") & ~scores.post_event]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.4))
    order = [("iso_score", style.GREY), ("z_score", style.GREY), ("lgbm_prob", style.GREY_DARK), ("risk", style.ACCENT)]
    for col, color in order:
        fpr, tpr, _ = roc_curve(t.label, t[col])
        axes[0].plot(fpr, tpr, color=color, lw=2.2 if col == "risk" else 1.3)
        pr, rc, _ = precision_recall_curve(t.label, t[col])
        axes[1].plot(rc, pr, color=color, lw=2.2 if col == "risk" else 1.3)
    labels = {"iso_score": "Isolation forest", "z_score": "z composite", "lgbm_prob": "LightGBM", "risk": "Ensemble"}
    for i, (col, color) in enumerate(order):
        c = cm["components"][col]
        axes[0].text(0.97, 0.05 + 0.08 * i, f"{labels[col]}  {c['auroc']:.2f}", transform=axes[0].transAxes, ha="right",
                     fontsize=8, color=style.INK if col == "risk" else style.INK_2)
        axes[1].text(0.97, 0.66 + 0.08 * i, f"{labels[col]}  {c['auprc']:.2f}", transform=axes[1].transAxes, ha="right",
                     fontsize=8, color=style.INK if col == "risk" else style.INK_2)
    axes[0].plot([0, 1], [0, 1], color=style.RULE, lw=0.8)
    axes[0].set_xlabel("False positive rate"); axes[0].set_ylabel("True positive rate")
    style.title(axes[0], "ROC, AUROC")
    axes[1].axhline(cm["prevalence"], color=style.RULE, lw=0.8)
    axes[1].set_xlabel("Recall"); axes[1].set_ylabel("Precision")
    style.title(axes[1], "Precision and recall, AUPRC")
    bins = pd.DataFrame(cm["calibration_bins"])
    ax = axes[2]
    ax.plot([0, bins.pred.max() * 1.1], [0, bins.pred.max() * 1.1], color=style.RULE, lw=0.8)
    ax.plot(bins.pred, bins.obs, color=style.ACCENT, lw=1.6)
    ax.scatter(bins.pred, bins.obs, s=26, color=style.ACCENT, edgecolor=style.PAPER, linewidth=1.5, zorder=3)
    ax.set_xlabel("Predicted risk"); ax.set_ylabel("Observed event rate")
    style.title(ax, "Calibration (octiles)")
    for a in axes:
        a.set_xlim(left=0); a.set_ylim(bottom=0)
    fig.tight_layout(w_pad=2.5)
    style.save(fig, "cardio_performance")


def fig_hero_cardio(scores: pd.DataFrame, daily: pd.DataFrame, threshold: float) -> None:
    pid = config.HERO_IDS["suresh"]
    s = scores[scores.pid == pid].set_index("day")
    d = daily[daily.pid == pid].set_index("day")
    days = np.arange(config.N_DAYS)
    dates = [config.START.date() + pd.Timedelta(days=int(i)) for i in days]
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.4), sharex=True, gridspec_kw={"height_ratios": [1, 1.1]})
    ax = axes[0]
    ax.plot(days, d.rmssd.reindex(days), color=style.GREY_DARK, lw=1.6)
    ax.set_ylabel("RMSSD, ms")
    style.title(ax, "Suresh Menon (synthetic): falling HRV before the event")
    ax = axes[1]
    ax.axhline(threshold, color=style.INK_3, lw=0.8)
    ax.text(12, threshold * 1.15 + 0.01, "flag threshold", fontsize=8, color=style.INK_3)
    r = s.risk.reindex(days)
    pre = r.where(~s.post_event.reindex(days).fillna(False).astype(bool))
    ax.plot(days, pre, color=style.ACCENT)
    flagged = pre >= threshold
    ax.scatter(days[flagged.to_numpy()], pre[flagged], s=30, color=style.ALERT, edgecolor=style.PAPER, linewidth=1.5, zorder=3)
    ev = int(s.event_day.dropna().iloc[0])
    for a in axes:
        a.axvline(ev, color=style.ALERT, lw=1.0)
    axes[1].text(ev + 0.2, 0.9 * np.nanmax(pre), "event", color=style.ALERT, fontsize=8.5)
    ax.set_ylabel("Risk of event in 3 days")
    ax.set_xticks(days[::3], [dates[i].strftime("%d %b") for i in days[::3]])
    ax.set_xlim(10, 29.5)
    fig.tight_layout()
    style.save(fig, "suresh_cardio_trajectory")


# Markdown --------------------------------------------------------------------------------

def write_markdown(m: dict) -> str:
    g, c, cf, al = m["glucose"], m["cardio"], m["conformal"], m["alerts"]
    L = []
    L.append("# Prativimb: evaluation report\n")
    L.append(f"Generated {m['generated']} from seed {config.SEED}. Synthetic data only. "
             f"All figures are on **{m['split']['test_patients']} test patients** who were not used for training, "
             "early stopping or conformal calibration, on days 8 to 30 (days 1 to 7 calibrate each twin).\n")
    L.append("## 1. Glucose forecasting (Event A)\n")
    L.append("### Accuracy and ablation\n")
    L.append("| Model | RMSE 30 min | RMSE 60 min | RMSE 120 min | MARD 30 min | MARD 60 min | MARD 120 min |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for k, name in MODELS:
        r = [g[h][k]["rmse"] for h in config.REPORT_HORIZONS] + [g[h][k]["mard"] for h in config.REPORT_HORIZONS]
        bold = "**" if k == "hyb" else ""
        L.append(f"| {bold}{name}{bold} | " + " | ".join(f"{bold}{v:.1f}{bold}" for v in r[:3]) + " | "
                 + " | ".join(f"{bold}{v:.1f}%{bold}" for v in r[3:]) + " |")
    L.append(f"\nRMSE in mg/dL against the CGM reading at the target time. n = {g[60]['n']:,} forecasts at 60 min.\n")
    L.append("![RMSE by horizon](figures/glucose_rmse_by_horizon.png)\n")
    L.append("### Clarke error grid (hybrid)\n")
    L.append("| Horizon | Zone A | Zone B | Zone C | Zone D | Zone E |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for h in config.REPORT_HORIZONS:
        z = g[h]["clarke"]
        L.append(f"| {h} min | " + " | ".join(f"{z[k]:.1f}%" for k in "ABCDE") + " |")
    L.append("\n![Clarke grid](figures/clarke_grid_60min.png)\n")
    L.append("### Spike alerts (glucose above 180 mg/dL)\n")
    lv = m["alert_level"]["alert_coverage"]
    L.append("A spike is three consecutive CGM readings above 180 mg/dL after at least 30 minutes not above. "
             "An alert counts as a detection if it fires up to 2 hours before onset. An alert episode is a false "
             "alarm if no spike starts within 2 h 15 min.\n")
    L.append(f"Two tiers are deployed. **Watch**: the hybrid point forecast crosses 180 within 2 h; shown on the "
             f"patient view as an early heads up. **Alert**: the conformal lower bound crosses 180 within 2 h; pushed "
             f"to the ward list. The alert uses the lower bound of the {lv:.0%} interval, which reads as at least a "
             f"{(1 + lv) / 2:.0%} chance of exceeding 180. That level was chosen on calibration patients as the most "
             f"sensitive one with at most {m['alert_level']['fa_budget']:.2f} false alarms per patient day there.\n")
    L.append("| Policy | Spikes | Sensitivity | Precision | Median lead time | False alarms per patient day |")
    L.append("|---|---:|---:|---:|---:|---:|")
    names = {"alert": f"**Alert tier: lower bound of {lv:.0%} interval (deployed)**",
             "hyb": "**Watch tier: hybrid point forecast (deployed)**",
             "lower90": "Lower bound of 90% interval", "ml": "LightGBM only, point forecast",
             "phys": "Twin only, point forecast"}
    for k, name in names.items():
        a = al[k]
        L.append(f"| {name} | {a['events']} | {a['sensitivity'] * 100:.1f}% | {a['precision'] * 100:.1f}% | "
                 f"{a['median_lead_min']:.0f} min | {a['false_alarms_per_patient_day']:.2f} |")
    L.append("\nThe lower bound tier trades lead time for precision: at 2 hours the interval is wide, so a confident "
             "call usually comes 25 to 35 minutes before onset. The watch tier gives the longer warning with more "
             "false alarms, which is why it is not pushed.\n")
    lw = m.get("hypo")
    if lw:
        c_, o_, ad = lw["test_classifier"], lw["test_point_forecast"], lw["artefact_detector"]
        L.append("### Low glucose (below 70 mg/dL)\n")
        L.append("Lows are a separate event with their own model: a LightGBM classifier for glucose below 70 mg/dL "
                 "within 60 minutes (two consecutive readings), trained on labels cleaned of sensor compression "
                 f"artefacts. Its threshold ({lw['threshold']}) is chosen on calibration patients as the most sensitive "
                 f"with at most {lw['fa_budget']:.2f} false alarms per patient day; lows are the costlier miss, so this budget "
                 "is looser than the spike alert's.\n")
        L.append("| Low policy, test patients | Lows | Flagged in advance | Precision | Median lead | False alarms per patient day |")
        L.append("|---|---:|---:|---:|---:|---:|")
        for name, r in (("**Low glucose classifier (deployed)**", c_), ("Hybrid point forecast below 70", o_)):
            L.append(f"| {name} | {r['events']} | {r['sensitivity'] * 100:.0f}% | {r['precision'] * 100:.0f}% | "
                     f"{r['median_lead_min'] or 0:.0f} min | {r['false_alarms_per_patient_day']:.2f} |")
        L.append(f"\nCompression artefact filter, checked against the dips the sensor simulator injected: it finds "
                 f"{ad['dips_found']} of {ad['dips']} dips that reach below 90 mg/dL, and {ad['reading_precision'] * 100:.0f}% "
                 "of the readings it flags are real artefacts. In the dashboard a fast fall during sleep is reported as "
                 "probable sensor compression rather than a low. Most remaining lows are brief level 1 dips in people "
                 "without diabetes, which a meal driven model cannot anticipate.\n")
    L.append("![Alert trade off](figures/alert_tradeoff.png)\n")
    L.append("### Conformal prediction intervals (90% target)\n")
    L.append("| Horizon | CQR coverage | CQR median width | Plain split coverage | Plain split width | Coverage below 70 | 70 to 180 | above 180 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for h in config.HORIZONS:
        x = cf[h]
        br = x["by_range"]
        L.append(f"| {h} min | {x['cqr_coverage'] * 100:.1f}% | {x['cqr_median_width']:.0f} mg/dL | "
                 f"{x['split_coverage'] * 100:.1f}% | {x['split_width']:.0f} mg/dL | "
                 f"{br['below 70']['coverage'] * 100:.0f}% (n={br['below 70']['n']}) | "
                 f"{br['70 to 180']['coverage'] * 100:.1f}% | {br['above 180']['coverage'] * 100:.1f}% |")
    L.append("\nConformalised quantile regression (Romano et al. 2019) gives intervals that widen when the "
             "situation is uncertain (for example around unlogged meals) and narrow overnight. At the same marginal "
             "coverage they are 8 to 16 percent narrower (median) than a fixed width split interval. Coverage falls "
             "in the hypoglycaemic range, where training data are sparse.\n")
    L.append("![Coverage](figures/conformal_coverage.png)\n")
    L.append("## 2. Cardiovascular risk flag (Event B)\n")
    L.append(f"Windows: {c['n_windows']} seven day windows from test patients, {c['n_positive']} labelled positive "
             f"(event in the next 3 days, {c['n_events']} distinct events). Prevalence {c['prevalence'] * 100:.1f}%. "
             "95% intervals are patient level bootstrap (1,000 resamples).\n")
    L.append("| Detector | AUROC | AUPRC | Sensitivity at 90% specificity | Sensitivity at 95% specificity |")
    L.append("|---|---:|---:|---:|---:|")
    for k, x in c["components"].items():
        bold = "**" if k == "risk" else ""
        L.append(f"| {bold}{x['name']}{bold} | {x['auroc']:.3f} ({x['auroc_ci'][0]:.2f} to {x['auroc_ci'][1]:.2f}) | "
                 f"{x['auprc']:.3f} ({x['auprc_ci'][0]:.2f} to {x['auprc_ci'][1]:.2f}) | "
                 f"{x['sens_at_90spec'] * 100:.0f}% | {x['sens_at_95spec'] * 100:.0f}% |")
    op = c["operating_point"]
    L.append(f"\nOperating point (threshold set at 95% specificity on calibration patients): test specificity "
             f"{op['specificity'] * 100:.1f}%, {op['events_caught']} of {op['events']} events flagged in the 3 days before, "
             f"median lead {op['median_lead_days']:.0f} days, {op['flags_per_patient_day'] * 100:.1f}% of patient days flagged. "
             f"Brier score {c['brier']:.3f}.\n")
    L.append("![Cardio performance](figures/cardio_performance.png)\n")
    L.append("![Suresh trajectory](figures/suresh_cardio_trajectory.png)\n")
    L.append("## 3. Twin calibration\n")
    tw = m["twin"]
    L.append(f"Median in sample error over the calibration week fell from {tw['rmse_prior_median']:.1f} mg/dL "
             f"(EHR prior only) to {tw['rmse_fit_median']:.1f} mg/dL after wearable calibration, across "
             f"{tw['n']} patients. Calibration takes about one second per patient.\n")
    L.append("## 4. Evaluation design\n")
    L.append(f"* Patient level split: {m['split']['train_patients']} train, {m['split']['calibration_patients']} "
             f"calibration, {m['split']['test_patients']} test. No patient contributes to more than one split. "
             "The three demo patients are in the test split.")
    L.append("* Twin parameters use only days 1 to 7 of each patient; every forecast is scored on days 8 to 30.")
    L.append("* Forecasts use only information available at the origin. Future meals come from the routine the "
             "patient declared at enrolment, not from the meal log.")
    L.append("* Early stopping uses a validation slice of training patients.\n")
    L.append("## 5. Limitations\n")
    for item in m["limitations"]:
        L.append(f"* {item}")
    L.append("")
    return "\n".join(L)


LIMITATIONS = [
    "All data are synthetic. The ground truth simulator (UVA/Padova based) is more complex than the twin, but it "
    "is still a model; real patients have behaviours and sensor artefacts we did not simulate. These numbers show "
    "the method works end to end; they are not evidence of clinical performance.",
    "Cardiovascular events are a synthetic composite driven by a latent strain process. With 6 events among test "
    "patients the confidence intervals are wide, and the supervised model has learned the shape of our simulated "
    "prodrome. Prospective validation on real outcomes would be required.",
    "Conformal coverage assumes exchangeability. Readings within a patient are serially correlated, so the "
    "guarantee is approximate; coverage is lower in the hypoglycaemic range, where data are scarce.",
    "Spike alerts depend on the declared routine. Unlogged or unplanned meals are the main source of missed "
    "spikes and wide intervals.",
    "The dawn phenomenon amplitude was not identifiable from seven days for most patients and usually fits to zero.",
    "Decision support only. Nothing here is a diagnosis or a treatment recommendation.",
]


def run(verbose: bool = True) -> dict:
    import joblib

    style.use()
    preds = pd.read_parquet(config.ARTIFACT_DIR / "glucose_predictions.parquet")
    bundle = joblib.load(config.ARTIFACT_DIR / "glucose_models.joblib")
    t = preds[preds.split == "test"].copy()
    from prativimb.twin import series
    S = series.load_all(pids=sorted(t.pid.unique()))
    cgm = {pid: s.cgm for pid, s in S.items()}

    acc = glucose_accuracy(t)
    alert_cfg = json.loads((config.ARTIFACT_DIR / "alert_config.json").read_text())
    level = alert_cfg["alert_coverage"]
    policies = {"alert": evaluate_alerts(t, cgm, lower_hits(t, bundle, level))}
    policies.update({k: evaluate_alerts(t, cgm, alert_policy(t, k)) for k in ("lower90", "hyb", "ml", "phys")})
    curve = [{"coverage": c, **evaluate_alerts(t, cgm, lower_hits(t, bundle, c))} for c in LEVELS]
    low_alert = (np.column_stack([t[f"hyb{h}"] < config.LOW_THRESHOLD for h in config.HORIZONS]).any(1)
                 & (t.cgm.to_numpy() >= config.LOW_THRESHOLD))
    lows = evaluate_alerts(t, cgm, low_alert, onset_fn=low_onsets)
    conf = conformal_summary(t, {h: bundle["models"][h]["abs_q"] for h in config.HORIZONS})

    hypo_path = config.ARTIFACT_DIR / "low_metrics.json"
    hypo_metrics = json.loads(hypo_path.read_text()) if hypo_path.exists() else None
    cardio_model = joblib.load(config.ARTIFACT_DIR / "cardio_model.joblib")
    scores = pd.read_parquet(config.ARTIFACT_DIR / "cardio_scores.parquet")
    daily = pd.read_parquet(config.ARTIFACT_DIR / "cardio_daily.parquet")
    cm = cardio_metrics(scores, cardio_model["threshold"])
    twins = pd.read_parquet(config.ARTIFACT_DIR / "twins.parquet")
    split = json.loads((config.DATA_DIR / "splits.json").read_text())

    metrics = {
        "generated": datetime.now().strftime("%d %b %Y"),
        "split": {f"{k}_patients": sum(v == k for v in split.values()) for k in ("train", "calibration", "test")},
        "glucose": acc, "alerts": policies, "alert_level": alert_cfg, "alert_curve": curve, "low_alerts": lows, "hypo": hypo_metrics, "conformal": conf, "cardio": cm,
        "twin": {"n": len(twins), "rmse_prior_median": float(twins.rmse_prior.median()),
                 "rmse_fit_median": float(twins.rmse_fit.median())},
        "limitations": LIMITATIONS,
    }
    fig_rmse(acc)
    for h in config.REPORT_HORIZONS:
        fig_clarke(t, h)
    fig_coverage(conf)
    fig_alert_tradeoff(policies, curve, level)
    fig_cardio(scores, cm)
    fig_hero_cardio(scores, daily, cardio_model["threshold"])
    (config.REPORT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=1, default=float))
    (config.REPORT_DIR / "metrics.md").write_text(write_markdown(metrics))
    if verbose:
        print(f"report written: {config.REPORT_DIR / 'metrics.md'}")
        for k, a in policies.items():
            print(f"  alerts {k:6s}: sens {a['sensitivity']:.2f} prec {a['precision']:.2f} "
                  f"lead {a['median_lead_min']} FA/pd {a['false_alarms_per_patient_day']:.2f} ({a['events']} spikes)")
        print(f"  cardio AUROC {cm['components']['risk']['auroc']:.3f} AUPRC {cm['components']['risk']['auprc']:.3f}")
    return metrics


if __name__ == "__main__":
    run()
