"""The patient twin: an extended Bergman minimal model.

States (all arrays over a batch of simulations):
    G   plasma glucose, mg/dL
    X   remote insulin action, 1/min
    I   insulin, uU/mL (relative to a nominal basal of 10)
    Q1  carbohydrate in the stomach, g
    Q2  carbohydrate in the gut, g (Vg is an effective volume that includes the fast tissue pool)
    E   exercise state (filtered steps per minute / 100)
    M   metformin effect level, dose units

    dG/dt  = -(SG + X) G + SG Gb H(t) + cf Ra(t) - eE E G
    dX/dt  = -p2 X + p2 SI S(t) (I - Ib)
    dI/dt  = -n (I - Ib) + gamma max(G - Gb, 0)
    dQ1/dt = -ka a(t) Q1 + meals,   dQ2/dt = ka a(t) (Q1 - Q2),   Ra = f ka a(t) Q2 / (Vg BW)
    dE/dt  = (A(t) - E) / tauE,     dM/dt = -M / tauM + doses

H(t) is hepatic output (dawn effect, metformin level relative to regular dosing). S(t) is
insulin sensitivity modulation (circadian rhythm, three night sleep debt, night shift
misalignment). a(t) is the absorption speed of the most recent meal (millets slow, iftar
dates and sherbet fast).

Personal parameters: SI, SG, Gb, ka, gamma, dawn, eE, cf. Everything else is population
physiology. Two integrators share one right hand side: a vectorised fixed step RK4 for
batches of thousands of forecast origins, and scipy.integrate.solve_ivp for single patient
scenario simulation. tests/test_twin.py checks that they agree.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

POP = {"p2": 0.025, "n": 0.12, "Ib": 10.0, "f": 0.9, "Vg": 3.2, "tauE": 10.0, "tauM": 720.0,
       "met_k": 0.12, "met_typ": 0.6, "circ_amp": 0.12, "sleep_slope": 0.03}
PARAMS = ("SI", "SG", "Gb", "ka", "gamma", "dawn", "eE", "cf")
STATE = ("G", "X", "I", "Q1", "Q2", "E", "M")
DT = 5.0


@dataclass
class Inputs:
    """Inputs on the 5 minute grid, shape [B, S]. Impulses (carbs, dose) apply at the start of a step."""
    carbs: np.ndarray
    af: np.ndarray
    A: np.ndarray
    dose: np.ndarray
    smod: np.ndarray
    dawn: np.ndarray
    ins: np.ndarray | None = None  # injected insulin appearing in plasma, uU/mL per min (what if only)

    def column(self, s: int) -> dict:
        return {"af": self.af[:, s], "A": self.A[:, s], "smod": self.smod[:, s], "dawn": self.dawn[:, s],
                "ins": 0.0 if self.ins is None else self.ins[:, s]}

    def window(self, a: int, b: int | None = None) -> "Inputs":
        cut = lambda x: None if x is None else x[:, a:b]
        return Inputs(*(cut(getattr(self, f)) for f in ("carbs", "af", "A", "dose", "smod", "dawn", "ins")))


def steady_state(p: dict, G0: np.ndarray | float, on_met: np.ndarray | float) -> np.ndarray:
    G0 = np.atleast_1d(np.asarray(G0, float))
    B = len(G0)
    x = np.zeros((7, B))
    x[0] = G0
    x[2] = POP["Ib"]
    x[6] = np.where(np.broadcast_to(on_met, (B,)) > 0, 1.2, 0.0)
    return x


def deriv(x: np.ndarray, p: dict, u: dict) -> np.ndarray:
    G, X, I, Q1, Q2, E, M = x
    ka = p["ka"] * u["af"]
    Ra = POP["f"] * ka * Q2 * 1000.0 / (POP["Vg"] * p["BW"])
    level = M / (M + 0.6)
    hep = (1 + p["dawn"] * u["dawn"]) * (1 + POP["met_k"] * p["on_met"] * (POP["met_typ"] - level))
    return np.stack([
        -(p["SG"] + X) * G + p["SG"] * p["Gb"] * hep + p["cf"] * Ra - p["eE"] * E * G,
        -POP["p2"] * X + POP["p2"] * p["SI"] * u["smod"] * (I - POP["Ib"]),
        -POP["n"] * (I - POP["Ib"]) + p["gamma"] * np.maximum(G - p["Gb"], 0) + u.get("ins", 0.0),
        -ka * Q1,
        ka * (Q1 - Q2),
        (u["A"] - E) / POP["tauE"],
        -M / POP["tauM"],
    ])


def run_rk4(p: dict, x0: np.ndarray, u: Inputs, obs: np.ndarray | None = None, gain: float = 0.5,
            obs_until: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Integrate S steps. Returns glucose at the start of every step plus the end, [B, S+1], and the final state.

    obs: CGM readings [B, S] used as a Luenberger style correction of G at the start of
    each step up to and including obs_until (the forecast origin). NaN readings are skipped.
    """
    x = x0.copy()
    B, S = u.carbs.shape
    G = np.empty((B, S + 1))
    last = S if obs_until is None else obs_until
    for s in range(S):
        x[3] += u.carbs[:, s]
        x[6] += u.dose[:, s]
        if obs is not None and s <= last:
            y = obs[:, s]
            ok = ~np.isnan(y)
            x[0, ok] += gain * (y[ok] - x[0, ok])
        G[:, s] = x[0]
        c = u.column(s)
        k1 = deriv(x, p, c)
        k2 = deriv(x + 0.5 * DT * k1, p, c)
        k3 = deriv(x + 0.5 * DT * k2, p, c)
        k4 = deriv(x + DT * k3, p, c)
        x = x + DT / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        x[3:5] = np.maximum(x[3:5], 0)
        x[0] = np.maximum(x[0], 20.0)
    G[:, S] = x[0]
    return G, x


def run_ivp(p: dict, x0: np.ndarray, u: Inputs) -> np.ndarray:
    """Single trajectory (B = 1) with scipy's adaptive RK45, split at every impulse.

    Returns glucose at the start of each 5 minute step plus the end, [S+1].
    """
    S = u.carbs.shape[1]
    ps = {k: (float(np.asarray(v).ravel()[0]) if np.ndim(v) else float(v)) for k, v in p.items()}
    x = x0[:, 0].astype(float).copy()
    out = np.empty(S + 1)

    def rhs(t, y):
        s = min(int(t // DT), S - 1)
        c = {k: float(v[0, s]) for k, v in (("af", u.af), ("A", u.A), ("smod", u.smod), ("dawn", u.dawn))}
        c["ins"] = 0.0 if u.ins is None else float(u.ins[0, s])
        return deriv(y, ps, c)

    for s in range(S):
        x[3] += u.carbs[0, s]
        x[6] += u.dose[0, s]
        out[s] = x[0]
        sol = solve_ivp(rhs, (s * DT, (s + 1) * DT), x, method="RK45", rtol=1e-7, atol=1e-9)
        x = sol.y[:, -1]
        x[3:5] = np.maximum(x[3:5], 0)
    out[S] = x[0]
    return out


def params_dict(theta: np.ndarray, bw: np.ndarray | float, on_met: np.ndarray | float) -> dict:
    """theta [B, 8] in PARAMS order -> parameter dict with population extras."""
    theta = np.atleast_2d(theta)
    d = {k: theta[:, i] for i, k in enumerate(PARAMS)}
    B = theta.shape[0]
    d["BW"] = np.broadcast_to(np.asarray(bw, float), (B,)).copy()
    d["on_met"] = np.broadcast_to(np.asarray(on_met, float), (B,)).copy()
    return d
