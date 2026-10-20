"""Are the twin's what if answers right? Checked against the reference simulator.

In real life nobody sees what would have happened had the patient walked after dinner. Here we
can: the synthetic patients come from a richer, deterministic simulator (physiology.py), so for
any patient and moment we re-run it with the change applied to what the patient actually ate,
and compare the size of the effect with the twin's prediction.

Design: 40 test patients, days 8 to 29, origins 40 minutes before a real main meal (sampled, at
most 8 per patient), 8 lifestyle changes applied to that meal, 6 hour window. The twin sees only
what it would see in use: data up to the origin and the patient's declared routine (so its idea of
the meal's time and size can be off). Effects are compared as changes in the 6 hour peak and in
time above 180 against each model's own usual plan.

Run: python -m prativimb.eval.counterfactual   (writes reports/counterfactual.json, .md and a figure)
"""
from __future__ import annotations

import json
import time

import duckdb
import numpy as np
import pandas as pd

from prativimb import config
from prativimb.data import physiology, reference
from prativimb.twin import bergman, forecast, series

H_MIN = 360
H = H_MIN // 5
LEVERS = [
    ("Walk 15 min after the meal", {"walk_minutes": 15}),
    ("Walk 30 min after the meal", {"walk_minutes": 30}),
    ("Millets instead of white rice", {"swap": "millet"}),
    ("Roti instead of rice", {"swap": "roti"}),
    ("Brown rice instead of white rice", {"swap": "brown_rice"}),
    ("Half the portion", {"swap": "half_portion"}),
    ("Meal 1 h earlier", {"shift_hours": -1.0}),
    ("Walk 15 min and millets", {"walk_minutes": 15, "swap": "millet"}),
]
NOISE = 2.0  # mg/dL: a change smaller than this counts as no change


def direction(x: np.ndarray) -> np.ndarray:
    return np.where(x < -NOISE, -1, np.where(x > NOISE, 1, 0))


def twin_effects(S, twins, pid: str, t: int) -> list[dict] | None:
    pp = forecast.prepare(S[pid])
    th = twins.loc[pid, list(bergman.PARAMS)].to_numpy(float)
    k = t // 5
    base, info = forecast.simulate_scenario(pp, th, k, H, forecast.Scenario(), method="rk4")
    if info.get("target_step") is None:
        return None
    gb = np.asarray(base)[1:]
    out = []
    for _, req in LEVERS:
        g, _ = forecast.simulate_scenario(pp, th, k, H, forecast.Scenario(**req), method="rk4")
        g = np.asarray(g)[1:]
        out.append({"peak": float(g.max() - gb.max()), "tar_min": int(((g > 180).sum() - (gb > 180).sum()) * 5)})
    return out


def origins(rng: np.random.Generator, pids: list[str], per_patient: int = 8) -> list[tuple[str, int]]:
    out = []
    for pid in pids:
        _, s, _, _ = reference.patient_inputs(pid)
        cand = [int(m) - 40 for m, g, _k, _n in s.meals
                if g >= forecast.MAIN_MEAL_G and 8 * 1440 <= m - 40 and m - 40 + H_MIN < config.N_DAYS * 1440]
        cand = [c - c % 5 for c in cand]
        rng.shuffle(cand)
        out += [(pid, c) for c in sorted(cand[:per_patient])]
    return out


def reference_effects(cases: list[tuple[str, int]]) -> np.ndarray:
    """[cases, levers + 1] peak and time above 180 from batched reference runs."""
    pids = sorted({p for p, _ in cases})
    pidx = {p: i for i, p in enumerate(pids)}
    parts = [reference.patient_inputs(p) for p in pids]
    P_all = physiology.build_params([x[0] for x in parts])
    states = [reference.state_at(p, t) for p, t in cases]
    rows, inputs, t0 = [], [], []
    for (p, t), st in zip(cases, states):
        for j, req in enumerate([{}] + [r for _, r in LEVERS]):
            inp, _ = reference.changed_inputs(p, t, H_MIN, reference.Change(**req))
            inputs.append(inp)
            rows.append(pidx[p])
            t0.append(t)
    n = len(rows)
    batch = {k: np.concatenate([x[k] for x in inputs]) for k in reference.INPUTS}
    batch["sens_day"] = np.concatenate([parts[i][2]["sens_day"] for i in rows])
    batch["egp_day"] = np.concatenate([parts[i][2]["egp_day"] for i in rows])
    st = {k: np.concatenate([states[c][k] for c in range(len(cases)) for _ in range(len(LEVERS) + 1)])
          for k in physiology.STATE_KEYS}
    Gs = physiology.run(physiology.rows(P_all, rows), batch, st, np.array(t0))["Gs"]
    Gs = Gs.reshape(len(cases), len(LEVERS) + 1, -1)
    peak = Gs.max(axis=2)
    tar = (Gs > 180).sum(axis=2)
    assert n == Gs.shape[0] * Gs.shape[1]
    return np.stack([peak - peak[:, :1], tar - tar[:, :1]], axis=2)[:, 1:, :]


def run(verbose: bool = True, per_patient: int = 8) -> dict:
    t0 = time.time()
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    S = series.load_all(con)
    con.close()
    twins = pd.read_parquet(config.ARTIFACT_DIR / "twins.parquet").set_index("pid")
    split = json.loads((config.DATA_DIR / "splits.json").read_text())
    pids = sorted(p for p, s in split.items() if s == "test")
    rng = np.random.default_rng(config.SEED + 11)
    cases, tw = [], []
    for pid, t in origins(rng, pids, per_patient):
        e = twin_effects(S, twins, pid, t)
        if e is not None:
            cases.append((pid, t))
            tw.append(e)
    ref = reference_effects(cases)
    twin_peak = np.array([[x["peak"] for x in e] for e in tw])
    twin_tar = np.array([[x["tar_min"] for x in e] for e in tw])
    ref_peak, ref_tar = ref[:, :, 0], ref[:, :, 1]

    per_lever = []
    for j, (label, _) in enumerate(LEVERS):
        a, b = twin_peak[:, j], ref_peak[:, j]
        per_lever.append({
            "label": label, "n": int(len(a)), "twin_mean": float(a.mean()), "reference_mean": float(b.mean()),
            "direction_agree": float((direction(a) == direction(b)).mean()),
            "mae": float(np.abs(a - b).mean()), "corr": float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else None,
            "twin_tar_mean": float(twin_tar[:, j].mean()), "reference_tar_mean": float(ref_tar[:, j].mean()),
        })
    best_t, best_r = twin_peak.argmin(axis=1), ref_peak.argmin(axis=1)
    from scipy.stats import spearmanr
    rho = [spearmanr(twin_peak[i], ref_peak[i]).statistic for i in range(len(cases))]
    # Is the reference's best change in the twin's top two?
    top2 = np.mean([best_r[i] in np.argsort(twin_peak[i])[:2] for i in range(len(cases))])
    a, b = twin_peak.ravel(), ref_peak.ravel()
    res = {
        "cases": len(cases), "patients": len({p for p, _ in cases}), "levers": [l for l, _ in LEVERS], "window_h": H_MIN // 60,
        "overall": {"direction_agree": float((direction(a) == direction(b)).mean()), "mae": float(np.abs(a - b).mean()),
                    "corr": float(np.corrcoef(a, b)[0, 1]), "best_same": float((best_t == best_r).mean()),
                    "best_in_top2": float(top2), "rank_spearman_median": float(np.nanmedian(rho))},
        "per_lever": per_lever,
        "points": {"twin": twin_peak.round(1).tolist(), "reference": ref_peak.round(1).tolist()},
    }
    (config.REPORT_DIR / "counterfactual.json").write_text(json.dumps(res, indent=1))
    (config.REPORT_DIR / "counterfactual.md").write_text(markdown(res))
    figure(res)
    if verbose:
        print(markdown(res))
        print(f"({time.time() - t0:.0f}s)")
    return res


def figure(r: dict) -> None:
    from prativimb.eval import style
    import matplotlib.pyplot as plt
    style.use()
    tw, rf = np.array(r["points"]["twin"]), np.array(r["points"]["reference"])
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), gridspec_kw={"width_ratios": [1, 1.25]})
    ax = axes[0]
    lim = [min(tw.min(), rf.min()) - 5, max(tw.max(), rf.max()) + 5]
    ax.plot(lim, lim, color=style.RULE, lw=1)
    ax.scatter(rf.ravel(), tw.ravel(), s=7, color=style.ACCENT, alpha=0.35, linewidths=0)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Reference simulator: change in 6 h peak, mg/dL")
    ax.set_ylabel("Twin: change in 6 h peak, mg/dL")
    style.title(ax, "Each change, each moment", f"{r['cases']} moments x {len(r['levers'])} changes; on the line means the twin was exact")
    ax = axes[1]
    pl = r["per_lever"]
    y = np.arange(len(pl))[::-1]
    ax.barh(y + 0.18, [x["reference_mean"] for x in pl], height=0.34, color=style.GREY, label="Reference simulator")
    ax.barh(y - 0.18, [x["twin_mean"] for x in pl], height=0.34, color=style.ACCENT, label="Twin")
    ax.set_yticks(y, [x["label"] for x in pl])
    ax.axvline(0, color=style.INK_3, lw=0.8)
    ax.set_xlabel("Average change in 6 h peak, mg/dL")
    ax.legend(frameon=False, loc="lower left", fontsize=8.5)
    style.title(ax, "Average effect of each change", "twin against reference, test patients")
    fig.tight_layout()
    fig.savefig(config.FIGURE_DIR / "counterfactual_check.png", dpi=180)
    plt.close(fig)


def markdown(r: dict) -> str:
    o = r["overall"]
    lines = [
        "# Are the what if answers right? Checked against the reference simulator",
        "",
        "Synthetic data only. The synthetic patients come from a richer simulator than the twin (UVA/Padova based, see "
        "docs/DATA.md). It is deterministic, so for any patient and moment it can be re-run with one change applied to "
        "what the patient actually ate. Nobody can do this with real patients; it is the one thing synthetic data allows "
        "that real data does not.",
        "",
        f"{r['cases']} moments from {r['patients']} test patients, each 40 minutes before a real main meal on days 8 to 29, "
        f"{len(r['levers'])} changes each, {r['window_h']} hour window. The twin sees only data up to that moment and the "
        "patient's declared routine, so its idea of the meal can be off in time and size.",
        "",
        "## Overall",
        "",
        f"* The twin gets the direction right (helps, no change of more than {NOISE:.0f} mg/dL, or hurts) "
        f"**{o['direction_agree'] * 100:.0f}%** of the time.",
        f"* Typical size error: {o['mae']:.1f} mg/dL on the change in peak; correlation {o['corr']:.2f}.",
        f"* The change that helps most according to the reference is the twin's first choice {o['best_same'] * 100:.0f}% "
        f"of the time and in its top two {o['best_in_top2'] * 100:.0f}% of the time; median rank correlation "
        f"{o['rank_spearman_median']:.2f}.",
        "",
        "## By change",
        "",
        "| Change | Twin, average change in peak | Reference | Direction agrees | Typical error | Twin, time above 180 | Reference |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for x in r["per_lever"]:
        lines.append(f"| {x['label']} | {x['twin_mean']:+.0f} mg/dL | {x['reference_mean']:+.0f} mg/dL | "
                     f"{x['direction_agree'] * 100:.0f}% | {x['mae']:.0f} mg/dL | {x['twin_tar_mean']:+.0f} min | "
                     f"{x['reference_tar_mean']:+.0f} min |")
    lines += [
        "",
        "![Twin against reference](figures/counterfactual_check.png)",
        "",
        "## What this does and does not show",
        "",
        "* It tests the twin's structure (meal absorption, insulin action, exercise) against a different and richer model "
        "of the same physiology. Where both models share an assumption (for example how much a 15 minute walk raises "
        "glucose uptake) agreement is easier than it would be against real people.",
        "* Sleep, a missed dose and a night shift are not checked here: in the reference simulator they act through "
        "day level factors that cannot be changed for one evening without changing the whole day.",
        "* Real patients add behaviour the reference does not have (stress, illness, unlogged snacks). This is a "
        "necessary check, not a sufficient one.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    run()
