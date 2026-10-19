"""Glucose forecaster: physics only, ML only, and hybrid (twin plus residual LightGBM), each
at 30, 60, 90 and 120 minutes, with conformalised quantile intervals for the hybrid.

Split by patient: train (120), calibration (40, conformal only), test (40, metrics only).
Early stopping uses a validation slice of the training patients, never calibration or test.
"""
from __future__ import annotations

import json
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from prativimb import config
from prativimb.ml import conformal
from prativimb.ml.features import glucose_features, ml_only_columns
from prativimb.twin import calibrate, fit_all, forecast, series
from prativimb.twin.series import PER_DAY

H_STEPS = {h: h // config.CGM_STEP for h in config.HORIZONS}
ORIGIN_STRIDE = 2  # every 10 minutes
LGB_PARAMS = dict(n_estimators=1200, learning_rate=0.04, num_leaves=63, min_child_samples=80, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, n_jobs=-1, verbose=-1)


def _patient_rows(s: series.Series, theta: np.ndarray, split: str) -> pd.DataFrame:
    pp = forecast.prepare(s)
    ks = np.arange(config.CALIBRATION_DAYS * PER_DAY, config.N_DAYS * PER_DAY - 1, ORIGIN_STRIDE)
    ks = ks[~np.isnan(s.cgm[ks])]
    G = forecast.forecast(pp, theta, ks, 24)
    G_prior = forecast.forecast(pp, calibrate.ehr_prior(s.ehr).mean, ks, 24)
    df = glucose_features(pp, ks, G, theta)
    df.insert(0, "pid", s.pid)
    df.insert(1, "k", ks)
    df.insert(2, "split", split)
    for h, j in H_STEPS.items():
        df[f"y{h}"] = forecast._take(s.cgm, ks + j, np.nan)
        df[f"cold{h}"] = G_prior[:, j]
    return df


def build_dataset(verbose: bool = True) -> pd.DataFrame:
    t0 = time.time()
    S = series.load_all()
    twins = fit_all.load()
    split = json.loads((config.DATA_DIR / "splits.json").read_text())
    params = ["SI", "SG", "Gb", "ka", "gamma", "dawn", "eE", "cf"]
    parts = Parallel(n_jobs=-1)(delayed(_patient_rows)(s, twins.loc[pid, params].to_numpy(float), split[pid])
                                for pid, s in S.items())
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(config.ARTIFACT_DIR / "glucose_dataset.parquet", index=False)
    if verbose:
        print(f"glucose dataset: {len(df):,} origins from {df.pid.nunique()} patients ({time.time() - t0:.1f}s)")
    return df


def feature_columns(df: pd.DataFrame) -> list[str]:
    skip = {"pid", "k", "split"} | {c for c in df.columns if c.startswith(("y", "cold", "pred", "lo", "hi"))}
    return [c for c in df.columns if c not in skip]


def _fit(X, y, Xv, yv, **extra):
    m = lgb.LGBMRegressor(**{**LGB_PARAMS, **extra})
    m.fit(X, y, eval_set=[(Xv, yv)], callbacks=[lgb.early_stopping(60, verbose=False)])
    return m


def train(df: pd.DataFrame | None = None, verbose: bool = True) -> dict:
    t0 = time.time()
    df = df if df is not None else pd.read_parquet(config.ARTIFACT_DIR / "glucose_dataset.parquet")
    cols = feature_columns(df)
    ml_cols = ml_only_columns(cols)
    tr_p = sorted(df.loc[df.split == "train", "pid"].unique())
    rng = np.random.default_rng(config.SEED)
    val_p = set(rng.choice(tr_p, size=len(tr_p) // 6, replace=False))
    fit_mask = (df.split == "train") & ~df.pid.isin(val_p)
    val_mask = (df.split == "train") & df.pid.isin(val_p)
    cal_mask = df.split == "calibration"

    bundle = {"features": cols, "ml_features": ml_cols, "horizons": list(config.HORIZONS), "models": {},
              "alpha": config.CONFORMAL_ALPHA}
    for h in config.HORIZONS:
        y = f"y{h}"
        tw = f"tw{h}"
        ok = df[y].notna()
        a, v, c = fit_mask & ok, val_mask & ok, cal_mask & ok
        resid = df[y] - df[tw]
        ml = _fit(df.loc[a, ml_cols], df.loc[a, y], df.loc[v, ml_cols], df.loc[v, y])
        hyb = _fit(df.loc[a, cols], resid[a], df.loc[v, cols], resid[v])
        qlo = _fit(df.loc[a, cols], resid[a], df.loc[v, cols], resid[v], objective="quantile", alpha=0.05)
        qhi = _fit(df.loc[a, cols], resid[a], df.loc[v, cols], resid[v], objective="quantile", alpha=0.95)
        Xc = df.loc[c, cols]
        lo_c, hi_c = qlo.predict(Xc), qhi.predict(Xc)
        q = conformal.conformal_quantile(conformal.cqr_scores(lo_c, hi_c, resid[c].to_numpy()), config.CONFORMAL_ALPHA)
        # Plain split conformal on the hybrid point forecast, kept for comparison in the report.
        q_abs = conformal.conformal_quantile(np.abs(resid[c].to_numpy() - hyb.predict(Xc)), config.CONFORMAL_ALPHA)
        bundle["models"][h] = {"ml": ml, "hybrid": hyb, "q_lo": qlo, "q_hi": qhi, "cqr_q": q, "abs_q": q_abs}
        if verbose:
            print(f"  h={h:>3} min: trees ml {ml.best_iteration_}, hybrid {hyb.best_iteration_}; "
                  f"CQR margin {q:.1f} mg/dL ({time.time() - t0:.0f}s)")
    joblib.dump(bundle, config.ARTIFACT_DIR / "glucose_models.joblib", compress=3)
    return bundle


def predict(bundle: dict, df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    X = df[bundle["features"]]
    Xm = df[bundle["ml_features"]]
    for h in bundle["horizons"]:
        m = bundle["models"][h]
        tw = df[f"tw{h}"].to_numpy()
        out[f"phys{h}"] = tw
        out[f"ml{h}"] = m["ml"].predict(Xm)
        out[f"hyb{h}"] = tw + m["hybrid"].predict(X)
        lo, hi = conformal.cqr_interval(tw + m["q_lo"].predict(X), tw + m["q_hi"].predict(X), m["cqr_q"])
        out[f"lo{h}"] = np.minimum(lo, out[f"hyb{h}"])
        out[f"hi{h}"] = np.maximum(hi, out[f"hyb{h}"])
    return out


def run(verbose: bool = True) -> None:
    df = build_dataset(verbose)
    bundle = train(df, verbose)
    test = df[df.split.isin(["test", "calibration"])].copy()
    preds = predict(bundle, test)
    out = pd.concat([test[["pid", "k", "split", "cgm"] + [f"y{h}" for h in config.HORIZONS]
                          + [f"cold{h}" for h in config.HORIZONS]], preds], axis=1)
    out.to_parquet(config.ARTIFACT_DIR / "glucose_predictions.parquet", index=False)
    if verbose:
        t = out[out.split == "test"]
        for h in config.REPORT_HORIZONS:
            ok = t[f"y{h}"].notna()
            r = lambda col: np.sqrt(np.mean((t.loc[ok, col] - t.loc[ok, f"y{h}"]) ** 2))
            cov = conformal.coverage(t.loc[ok, f"lo{h}"], t.loc[ok, f"hi{h}"], t.loc[ok, f"y{h}"])
            print(f"  test h={h}: RMSE cold {r(f'cold{h}'):.1f} | physics {r(f'phys{h}'):.1f} | ML {r(f'ml{h}'):.1f} | "
                  f"hybrid {r(f'hyb{h}'):.1f} | 90% coverage {cov:.3f}")


if __name__ == "__main__":
    run()
