"""Personalising the twin.

1. EHR prior (cold start). Literature shaped mappings from HbA1c, BMI, fasting glucose,
   TCF7L2 genotype, diagnosis and age to each parameter, with a prior spread.
2. Wearable refinement. Maximum a posteriori fit on the first seven days: from origins every
   two hours, warm up with the observer, run four hours open loop with the logged inputs,
   and compare to CGM. scipy.optimize.least_squares with the prior as extra residuals.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from prativimb import config
from prativimb.twin import bergman, forecast
from prativimb.twin.series import PER_DAY, Series

LOG = np.array([True, True, True, True, True, False, True, True])  # dawn is fitted on a linear scale
LOWER = np.array([2e-5, 0.002, 60.0, 0.008, 1e-4, 0.0, 5e-4, 0.15])
UPPER = np.array([4e-3, 0.08, 300.0, 0.12, 0.5, 0.4, 0.05, 2.5])
H_CAL = 48
SIGMA_Y = 18.0


@dataclass
class Prior:
    mean: np.ndarray
    sd: np.ndarray  # log scale sd for LOG params, absolute sd otherwise


def ehr_prior(ehr: dict) -> Prior:
    a1c = float(ehr.get("hba1c", 5.5))
    x = float(np.clip((a1c - 5.2) / 4.0, 0, 1.4))
    bmi = float(ehr.get("bmi", 24))
    t2d = bool(ehr.get("t2d", 0))
    tcf = float(ehr.get("tcf7l2_risk", 0) or 0)
    age = float(ehr.get("age", 50))
    mean = np.array([
        6e-4 * np.exp(-1.4 * x - 0.03 * (bmi - 24)),          # SI
        0.018 * np.exp(-0.5 * x),                              # SG
        float(ehr.get("fpg", 95)),                             # Gb
        0.03 * (0.85 if t2d else 1.0) * (1 - 0.003 * (age - 50)),  # ka
        0.05 * np.exp(-1.0 * x) * (1 - 0.08 * tcf),            # gamma
        0.12 if t2d else 0.03,                                 # dawn
        0.008,                                                 # eE
        0.5,                                                   # cf: share of logged carbohydrate seen in plasma
    ])
    sd = np.array([0.6, 0.4, 0.12, 0.35, 0.6, 0.08, 0.5, 0.25])
    return Prior(np.clip(mean, LOWER, UPPER), sd)


def to_z(theta: np.ndarray) -> np.ndarray:
    return np.where(LOG, np.log(np.where(LOG, theta, 1.0)), theta)


def from_z(z: np.ndarray) -> np.ndarray:
    return np.where(LOG, np.exp(np.where(LOG, z, 0.0)), z)


def _origins(s: Series) -> np.ndarray:
    ks = np.arange(PER_DAY // 4, config.CALIBRATION_DAYS * PER_DAY - H_CAL, 24)
    return ks[~np.isnan(s.cgm[ks])]


def calibrate(s: Series, prior: Prior | None = None, max_nfev: int = 40) -> tuple[np.ndarray, dict]:
    prior = prior or ehr_prior(s.ehr)
    pp = forecast.prepare(s)
    ks = _origins(s)
    u, obs = forecast.build(pp, ks, H_CAL, future="actual")
    y = forecast._take(s.cgm, ks[:, None] + np.arange(1, H_CAL + 1)[None, :], np.nan)
    mask = ~np.isnan(y)
    x0 = forecast.initial_state(obs, float(s.on_metformin))
    nb = len(ks)
    z_prior = to_z(prior.mean)

    def simulate(Z: np.ndarray) -> np.ndarray:
        K = Z.shape[0]
        theta = from_z(Z)
        p = bergman.params_dict(np.repeat(theta, nb, axis=0), s.bw, float(s.on_metformin))
        tile = lambda a: np.tile(a, (K, 1))
        uu = bergman.Inputs(*(tile(a) for a in (u.carbs, u.af, u.A, u.dose, u.smod, u.dawn)))
        G, _ = bergman.run_rk4(p, np.tile(x0, (1, K)), uu, obs=tile(obs), obs_until=forecast.W)
        pred = G[:, forecast.W + 1: forecast.W + 1 + H_CAL].reshape(K, nb, H_CAL)
        r = np.where(mask[None], (pred - np.nan_to_num(y)[None]) / SIGMA_Y, 0.0)
        return r.reshape(K, -1)

    def residuals_of(R: np.ndarray, Z: np.ndarray) -> np.ndarray:
        rp = (Z - z_prior[None]) / prior.sd[None]
        return np.concatenate([R, rp], axis=1)

    def fun(z):
        return residuals_of(simulate(z[None]), z[None])[0]

    def jac(z):
        h = 1e-4 * np.maximum(np.abs(z), 1.0)
        Z = np.vstack([z, z[None] + np.diag(h)])
        R = residuals_of(simulate(Z), Z)
        return ((R[1:] - R[0]) / h[:, None]).T

    lo, hi = to_z(LOWER), to_z(UPPER)
    z0 = np.clip(z_prior, lo + 1e-6, hi - 1e-6)
    res = least_squares(fun, z0, jac=jac, bounds=(lo, hi), method="trf", max_nfev=max_nfev, x_scale="jac")
    theta = from_z(res.x)
    rmse_prior = float(np.sqrt(np.mean((fun(z0)[: mask.size][mask.ravel()] * SIGMA_Y) ** 2)))
    rmse_fit = float(np.sqrt(np.mean((res.fun[: mask.size][mask.ravel()] * SIGMA_Y) ** 2)))
    return theta, {"origins": nb, "rmse_prior": rmse_prior, "rmse_fit": rmse_fit, "nfev": res.nfev,
                   "status": int(res.status)}
