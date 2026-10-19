"""Calibrate every patient's twin and store the parameters."""
from __future__ import annotations

import time

import pandas as pd
from joblib import Parallel, delayed

from prativimb import config
from prativimb.twin import bergman, calibrate, series


def _one(s: series.Series) -> dict:
    prior = calibrate.ehr_prior(s.ehr)
    theta, info = calibrate.calibrate(s, prior)
    row = {"pid": s.pid, **{k: float(v) for k, v in zip(bergman.PARAMS, theta)},
           **{f"prior_{k}": float(v) for k, v in zip(bergman.PARAMS, prior.mean)}, **info}
    return row


def run(verbose: bool = True) -> pd.DataFrame:
    t0 = time.time()
    config.ensure_dirs()
    S = series.load_all()
    rows = Parallel(n_jobs=-1, prefer="processes")(delayed(_one)(s) for s in S.values())
    df = pd.DataFrame(rows).sort_values("pid")
    df.to_parquet(config.ARTIFACT_DIR / "twins.parquet", index=False)
    if verbose:
        print(f"calibrated {len(df)} twins in {time.time() - t0:.1f}s; "
              f"median fit RMSE {df.rmse_prior.median():.1f} -> {df.rmse_fit.median():.1f} mg/dL")
    return df


def load() -> pd.DataFrame:
    return pd.read_parquet(config.ARTIFACT_DIR / "twins.parquet").set_index("pid")


if __name__ == "__main__":
    run()
