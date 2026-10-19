"""Ground truth glucose physiology used only to generate synthetic data.

The glucose and insulin kinetics are the UVA/Padova meal simulation model
(Dalla Man, Rizza and Cobelli, IEEE TBME 2007) with parameter sets taken from the
simglucose adult virtual patients (MIT licence). simglucose models Type 1 diabetes
with an insulin pump; for Type 2 diabetes we remove the pump and add the endogenous
beta cell secretion model from the same paper, then impair it:

* insulin dependent utilisation (Vmx) and hepatic insulin action (kp3) are scaled by a
  per patient sensitivity factor,
* beta cell responsivity (beta, K) is scaled by a secretion factor (lower with TCF7L2 risk
  alleles),
* basal state is solved so that fasting glucose equals the patient's EHR value.

Extra modifiers, each with a literature anchor, make the behaviour Indian T2D like:
circadian insulin sensitivity, dawn phenomenon, metformin suppression of hepatic output,
exercise uptake, sleep debt, long fasts and night shift misalignment.

The digital twin never sees these equations or parameters. It is a different and much
simpler model (see prativimb/twin/bergman.py), so the twin has real structural error.
"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources

import numpy as np
import pandas as pd

from prativimb import config

MET_TYPICAL = 0.6  # typical metformin effect level M/(M+0.6) under regular dosing

DALLA_MAN_NORMAL = {
    "Vg": 1.88, "k1": 0.065, "k2": 0.079, "kp2": 0.0021, "Km0": 225.59, "p2u": 0.0331, "Fsnc": 1.0,
    "EGPb": 1.92, "m1": 0.190, "m2": 0.484, "m4": 0.194, "m30": 0.285, "Vi": 0.05, "ki": 0.0079,
    "kmax": 0.0558, "kmin": 0.0080, "b": 0.82, "d": 0.010, "f": 0.90,
}


@lru_cache(maxsize=1)
def simglucose_adults() -> pd.DataFrame:
    path = resources.files("simglucose") / "params" / "vpatient_params.csv"
    df = pd.read_csv(path)
    return df[df.Name.str.startswith("adult")].reset_index(drop=True)


def build_params(patients) -> dict[str, np.ndarray]:
    adults = simglucose_adults()
    rows = adults.iloc[[p.physio["base_adult"] - 1 for p in patients]]
    # Dalla Man 2007 normal subject means. Each patient inherits the relative deviation of one
    # simglucose adult from the simglucose cohort mean (square root damped), so the spread
    # between patients comes from the UVA/Padova virtual cohort while the centre stays
    # physiological for people who still secrete their own insulin.
    P = {}
    for k, v in DALLA_MAN_NORMAL.items():
        if k in adults:
            P[k] = v * np.sqrt(rows[k].to_numpy(float) / adults[k].mean())
        else:
            P[k] = np.full(len(patients), v)
    P["ksc"] = rows["ksc"].to_numpy(float)
    ph = {k: np.array([p.physio[k] for p in patients], float) for k in patients[0].physio}
    P["BW"] = np.array([p.weight_kg for p in patients], float)
    P["Gb"] = ph["Gb"]
    P["Ib"] = ph["Ib"]
    sens, secr = ph["sens"], ph["secr"]
    P["sens"], P["secr"] = sens, secr
    # Insulin action, hepatic insulin sensitivity and absorption are set by phenotype.
    # Vmx and beta are 1.5 times the paper values: with that a 75 g load reproduces the ADA
    # two hour thresholds across phenotypes (normal under 140, IGT 140 to 199, T2D 200 plus).
    P["Vmx"] = 0.0705 * sens
    P["kp3"] = 0.009 * np.sqrt(sens)
    P["kabs"] = 0.057 * ph["kabs_scale"]
    P["dawn"] = ph["dawn_amp"]
    P["fast_k"] = ph["fast_k"]
    P["met_eff"] = ph["met_eff"]
    # Endogenous secretion (Dalla Man 2007, normal subject values scaled by secretion capacity).
    P["beta"] = 0.165 * secr
    P["K"] = 3.45 * secr
    P["alpha"] = np.array([0.035 if p.hero == "fatima" else 0.05 for p in patients])
    P["gamma"] = np.full(len(patients), 0.5)
    # T2D livers produce more glucose at basal.
    P["EGPb"] = P["EGPb"] * (1 + 0.25 * (1 - np.clip(sens, 0, 1)))

    # Renal excretion from GFR: about 0.017 dL/kg/min filtered at eGFR 100 above the renal
    # threshold (190 mg/dL, about 120 on an SGLT2 inhibitor). Dalla Man's ke1 is far smaller.
    P["renal_k"] = np.array([0.017 * p.labs["egfr"] / 100 for p in patients])
    P["renal_thr"] = np.array([120.0 if p.has_drug("empagliflozin") else 190.0 for p in patients])

    # Basal steady state.
    Gpb = P["Gb"] * P["Vg"]
    Gtb = (P["Fsnc"] - P["EGPb"] + P["k1"] * Gpb) / P["k2"]
    P["Vm0"] = (P["EGPb"] - P["Fsnc"]) * (P["Km0"] + Gtb) / Gtb
    Ipb = P["Ib"] * P["Vi"]
    Ilb = (P["m2"] + P["m4"]) * Ipb / P["m1"]
    P["Sb"] = (P["m1"] + P["m30"]) * Ilb - P["m2"] * Ipb
    met_basal = 1 - P["met_eff"] * MET_TYPICAL
    P["kp1"] = (P["EGPb"] + P["kp2"] * Gpb + P["kp3"] * P["Ib"]) / met_basal
    P["Gpb"], P["Gtb"], P["Ipb"], P["Ilb"] = Gpb, Gtb, Ipb, Ilb
    # Basal renal loss must be covered by basal output, otherwise high Gb patients drift down.
    P["kp1"] += P["renal_k"] * np.maximum(P["Gb"] - P["renal_thr"], 0) / met_basal
    return P


def simulate(patients, inputs: dict, P: dict | None = None) -> dict[str, np.ndarray]:
    """Forward Euler at 1 minute, vectorised over patients.

    inputs: carbs [P,T] grams, absf [P,T] absorption factor at meal minutes, steps [P,T],
    metformin [P,T] dose units, night_work [P,T] bool, sens_day [P,D], egp_day [P,D].
    Returns plasma glucose G and subcutaneous glucose Gs [P,T] in mg/dL.
    """
    P = P or build_params(patients)
    n, T = inputs["carbs"].shape
    Vg, BW = P["Vg"], P["BW"]

    qsto1 = np.zeros(n); qsto2 = np.zeros(n); qgut = np.zeros(n)
    Gp = P["Gpb"].copy(); Gt = P["Gtb"].copy()
    Ip = P["Ipb"].copy(); Il = P["Ilb"].copy()
    X = np.zeros(n); I1 = P["Ib"].copy(); Id = P["Ib"].copy()
    Y = np.zeros(n); Ipo = P["Sb"] / P["gamma"]
    Gs = P["Gb"].copy()
    E = np.zeros(n); Z = np.zeros(n)
    M = np.full(n, 1.2) * (P["met_eff"] > 0)
    Dbar = np.zeros(n)
    absf = np.ones(n)
    since_meal = np.full(n, 300.0)
    G_prev = P["Gb"].copy()
    fast = np.ones(n)

    out_G = np.empty((n, T), np.float32)
    out_I = np.empty((n, T), np.float32)
    out_Gs = np.empty((n, T), np.float32)
    hours = (np.arange(T) % 1440) / 60.0
    circ = 1 + 0.15 * np.cos(2 * np.pi * (hours - 9.0) / 24)   # best sensitivity mid morning
    dawn_shape = np.exp(-0.5 * ((hours - 5.5) / 1.4) ** 2)

    carbs_all = inputs["carbs"]; absf_all = inputs["absf"]; steps_all = inputs["steps"]
    met_all = inputs["metformin"]; nw_all = inputs["night_work"]
    sens_day, egp_day = inputs["sens_day"], inputs["egp_day"]

    for t in range(T):
        d = t // 1440
        cho = carbs_all[:, t] * 1000.0  # mg
        meal = cho > 0
        if meal.any():
            Dbar = np.where(meal, qsto1 + qsto2 + cho, Dbar)
            absf = np.where(meal, absf_all[:, t], absf)
            since_meal = np.where(cho > 5000, 0.0, since_meal)
        qsto = qsto1 + qsto2
        safe = np.maximum(Dbar, 1.0)
        aa = 5 / (2 * safe * (1 - P["b"]))
        cc = 5 / (2 * safe * P["d"])
        kmax, kmin = P["kmax"] * absf, P["kmin"] * absf
        kgut = np.where(Dbar > 0, kmin + (kmax - kmin) / 2 *
                        (np.tanh(aa * (qsto - P["b"] * Dbar)) - np.tanh(cc * (qsto - P["d"] * Dbar)) + 2), P["kmax"])
        kabs = P["kabs"] * absf
        Ra = P["f"] * kabs * qgut / BW

        A = np.minimum(steps_all[:, t] / 100.0, 1.5)
        E += (A - E) / 8.0
        Z += (A - Z) / 120.0
        M += -M / 720.0 + met_all[:, t]
        met_level = M / (M + 0.6)

        # Hepatic output falls late in a long fast and recovers over about three hours after eating.
        target = 1 - P["fast_k"] * np.clip((since_meal - 480) / 600, 0, 1)
        fast += (target - fast) / np.where(target < fast, 60.0, 180.0)
        EGP = (P["kp1"] * (1 - P["met_eff"] * met_level) * (1 + P["dawn"] * dawn_shape[t]) * fast * egp_day[:, d]
               - P["kp2"] * Gp - P["kp3"] * Id)
        # Counter regulation (glucagon, adrenaline) below 70 mg/dL. The UVA/Padova T1D model omits it.
        EGP = np.maximum(EGP, 0) + 0.2 * np.maximum(70 - Gp / Vg, 0)
        smod = circ[t] * sens_day[:, d] * np.where(nw_all[:, t], 0.9, 1.0)
        # Working muscle takes up glucose independently of insulin: about 6 mg/kg/min at a brisk
        # walk, then insulin action stays raised for a couple of hours (Z).
        Uid = ((P["Vm0"] + P["Vmx"] * smod * X * (1 + 0.8 * Z)) * Gt / (P["Km0"] + Gt)
               + 10.0 * E * Gt / (Gt + 120.0))
        Et = P["renal_k"] * np.maximum(Gp / Vg - P["renal_thr"], 0)

        G = Gp / Vg
        dG = G - G_prev
        G_prev = G
        I = Ip / P["Vi"]

        # Endogenous secretion (portal), Dalla Man 2007.
        drive = P["beta"] * (G - P["Gb"])
        Y += np.where(drive >= -P["Sb"], -P["alpha"] * (Y - drive), -P["alpha"] * Y - P["alpha"] * P["Sb"])
        Spo = np.maximum(Y + P["K"] * np.maximum(dG, 0) + P["Sb"], 0)
        S = P["gamma"] * Ipo

        dqsto1 = -kmax * qsto1 + cho
        dqsto2 = kmax * qsto1 - kgut * qsto2
        dqgut = kgut * qsto2 - kabs * qgut
        dGp = EGP + Ra - P["Fsnc"] - Et - P["k1"] * Gp + P["k2"] * Gt
        dGt = -Uid + P["k1"] * Gp - P["k2"] * Gt
        dIp = -(P["m2"] + P["m4"]) * Ip + P["m1"] * Il
        dIl = -(P["m1"] + P["m30"]) * Il + P["m2"] * Ip + S
        dIpo = -P["gamma"] * Ipo + Spo
        dX = -P["p2u"] * X + P["p2u"] * (I - P["Ib"])
        dI1 = -P["ki"] * (I1 - I)
        dId = -P["ki"] * (Id - I1)

        qsto1 = np.maximum(qsto1 + dqsto1, 0)
        qsto2 = np.maximum(qsto2 + dqsto2, 0)
        qgut = np.maximum(qgut + dqgut, 0)
        Gp = np.maximum(Gp + dGp, 1.0)
        Gt = np.maximum(Gt + dGt, 1.0)
        Ip = np.maximum(Ip + dIp, 0)
        Il = np.maximum(Il + dIl, 0)
        Ipo = np.maximum(Ipo + dIpo, 0)
        X += dX
        I1 += dI1
        Id += dId
        Gs += P["ksc"] * (Gp / Vg - Gs)
        since_meal += 1

        out_G[:, t] = Gp / Vg
        out_Gs[:, t] = Gs
        out_I[:, t] = Ip / P["Vi"]
    return {"G": out_G, "Gs": out_Gs, "I": out_I}
