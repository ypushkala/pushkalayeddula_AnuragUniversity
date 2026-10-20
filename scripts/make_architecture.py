"""Architecture diagram as code: docs/architecture.png and docs/architecture.pdf."""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

from prativimb import config
from prativimb.eval import style

style.use()
W, H = 16.0, 9.0


def box(ax, x, y, w, h, title, lines, accent=False):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=style.PAPER if not accent else "#E9EFEC",
                           edgecolor=style.ACCENT if accent else style.RULE, linewidth=1.2 if accent else 0.9))
    if accent:
        ax.add_patch(Rectangle((x, y), 0.06, h, facecolor=style.ACCENT, edgecolor="none"))
    ax.text(x + 0.16, y + h - 0.18, title, fontsize=10.2, fontweight="medium", color=style.INK, va="top")
    for i, line in enumerate(lines):
        ax.text(x + 0.16, y + h - 0.48 - i * 0.24, line, fontsize=8.2, color=style.INK_2, va="top")
    return (x, y, w, h)


def arrow(ax, a, b, side_a="r", side_b="l", color=None, label=None, rad=0.0):
    def pt(bx, side):
        x, y, w, h = bx
        return {"r": (x + w, y + h / 2), "l": (x, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]
    p, q = pt(a, side_a), pt(b, side_b)
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, linewidth=0.9,
                                 color=color or style.INK_3, connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))
    if label:
        ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 0.08, label, fontsize=7.4, color=style.INK_3, ha="center")


def main() -> None:
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    ax.text(0.4, 8.62, "Prativimb architecture", fontfamily=style.SERIF, fontsize=19, color=style.INK)
    ax.text(0.4, 8.3, "Hybrid patient twin: mechanistic physiology, learned residual, calibrated uncertainty, plain language reasons.",
            fontsize=9.5, color=style.INK_3)
    cols = [(0.4, "Sources"), (3.05, "Ingest and storage"), (5.75, "Twin"), (8.5, "Learning and uncertainty"),
            (11.2, "Decision support"), (13.75, "Delivery")]
    for x, name in cols:
        ax.text(x, 7.85, name.upper(), fontsize=8.2, color=style.INK_3, fontweight="medium")
        ax.plot([x, x + 2.25], [7.75, 7.75], color=style.RULE, lw=0.8)

    T, M, L, B = 5.95, 4.05, 2.15, 0.62   # row baselines
    h = 1.55
    X = [c[0] for c in cols]
    ehr = box(ax, X[0], T, 2.25, h, "EHR (FHIR R4 bundles)", ["Problems, ICD-10", "Labs and vitals, LOINC", "Medications, ATC", "Genetic markers, consent"])
    wear = box(ax, X[0], M, 2.25, h, "Wearable stream", ["CGM every 5 min", "Heart rate and steps, 1 min", "Sleep stages, nightly RMSSD", "Apple Health, Google Fit, Health Connect"])
    logs = box(ax, X[0], L, 2.25, h, "Patient reported", ["Meal log with carbohydrate", "Dose confirmations", "Declared routine and fasts", "Replies from the patient's phone"])
    gen = box(ax, X[0], B, 2.25, 1.38, "Synthetic generator", ["UVA/Padova physiology", "Indian diet, Ramadan, shifts", "Restartable: the reference", "for checking what ifs"])

    parse = box(ax, X[1], T, 2.3, h, "Parsers and adapters", ["FHIR bundle parser", "Apple Health, Google Fit,", "Health Connect adapters", "Unit checks (mmol/L)"])
    db = box(ax, X[1], M, 2.3, h, "DuckDB", ["EHR tables and features", "5 minute wearable grid", "Logs, sleep summaries", "Seven day windows"])
    replay = box(ax, X[1], L, 2.3, h, "Replay service", ["Demo clock, pause, speed", "WebSocket stream", "Withdrawn consent stops a source", "Logged walks via the reference"])
    store = box(ax, X[1], B, 2.3, 1.38, "Clinical store", ["Seen, calls, checks, meals, plans,", "consent, messages, via FastAPI", "Append only audit log", "Undo for every change"])

    prior = box(ax, X[2], T, 2.35, h, "EHR priors", ["HbA1c, BMI, fasting glucose", "TCF7L2, diagnosis, age", "give a cold start twin"])
    cal = box(ax, X[2], M, 2.35, h, "Twin calibration", ["Days 1 to 7 of each patient", "MAP least squares (scipy)", "8 personal parameters", "about 1 s per patient"], accent=True)
    phys = box(ax, X[2], L, 2.35, h, "Physics model", ["Extended Bergman ODE", "Meals, exercise, sleep debt,", "circadian, shift, metformin", "RK4 batch, solve_ivp"], accent=True)

    cardio = box(ax, X[3], T, 2.35, h, "Cardio ensemble", ["Windows from DuckDB", "Isolation forest, baseline z", "LightGBM, stacked by", "logistic regression"])
    conf = box(ax, X[3], M, 2.35, h, "Conformal layer", ["Conformalised quantile", "regression, 90% band", "Alert level chosen on", "calibration patients"], accent=True)
    resid = box(ax, X[3], L, 2.35, h, "Residual LightGBM", ["Learns the twin's error", "at 30, 60, 90, 120 min", "Features from DuckDB"], accent=True)

    alerts = box(ax, X[4], T, 2.3, h, "Alert engine", ["Watch: point above 180", "Alert: lower bound above 180", "Low glucose", "Cardiovascular flag"])
    expl = box(ax, X[4], M, 2.3, h, "Explainability", ["Exact Shapley, twin inputs", "TreeSHAP, residual model", "mg/dL, then one plain", "clinical sentence"])
    whatif = box(ax, X[4], B, 2.3, 1.38, "What-if simulator", ["Walk, food, timing, insulin", "Tonight, 24 hours, 7 days", "Checked against the generator", "Plans checked a week later"])

    apib = box(ax, X[5], T, 2.0, h, "FastAPI", ["REST and WebSocket", "Role checks: doctor,", "nurse, patient", "SOAP note PDF"])
    dash = box(ax, X[5], B, 2.0, M + h - B, "Dashboard and phone", ["Ward by urgency, reasons", "Today, Try a change, Record", "Earlier alerts, outcomes", "Handover, daily digest", "Festival planner", "Patient phone, Hindi,", "Tamil, English, Listen", "Consent on screen", "React, Observable Plot"])

    ac = style.ACCENT
    arrow(ax, gen, logs, "t", "b")
    arrow(ax, ehr, parse); arrow(ax, wear, db); arrow(ax, logs, replay)
    arrow(ax, parse, db, "b", "t"); arrow(ax, db, replay, "b", "t")
    arrow(ax, parse, prior); arrow(ax, db, cal, color=ac)
    arrow(ax, prior, cal, "b", "t", color=ac); arrow(ax, cal, phys, "b", "t", color=ac)
    arrow(ax, phys, resid, color=ac)
    arrow(ax, resid, conf, "t", "b", color=ac)
    arrow(ax, conf, alerts, "r", "l", color=ac); arrow(ax, cardio, alerts)
    arrow(ax, resid, expl, "r", "l")
    arrow(ax, phys, whatif, "b", "l", rad=0.25)
    arrow(ax, alerts, apib); arrow(ax, apib, dash, "b", "t")
    arrow(ax, expl, dash, "r", "l"); arrow(ax, whatif, dash, "r", "l")
    arrow(ax, store, replay, "t", "b")

    ax.add_patch(Rectangle((0.42, 0.28), 0.18, 0.12, facecolor="#E9EFEC", edgecolor=style.ACCENT, lw=1.0))
    ax.text(0.7, 0.34, "Hybrid core: physics gives plausibility and extrapolation, the residual model gives accuracy, "
            "conformal gives honest uncertainty.", fontsize=8.5, color=style.INK_2, va="center")
    ax.text(W - 0.25, 0.34, "Synthetic data only. Decision support, not a diagnosis.", fontsize=8.5, color=style.INK_3,
            va="center", ha="right")
    out = config.DOCS_DIR
    fig.savefig(out / "architecture.png", dpi=170)
    fig.savefig(out / "architecture.pdf")
    plt.close(fig)
    print("wrote docs/architecture.png and docs/architecture.pdf")


if __name__ == "__main__":
    main()
