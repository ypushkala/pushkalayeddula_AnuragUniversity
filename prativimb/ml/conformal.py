"""Split conformal prediction, written out so the guarantee is easy to audit.

Given n calibration scores, the interval built from the ceil((n+1)(1-alpha))/n empirical
quantile covers a new exchangeable point with probability at least 1 - alpha
(Vovk et al. 2005; Lei et al. 2018). We use the conformalised quantile regression score of
Romano, Patterson and Candes (2019) so interval width adapts to the situation (wide after
an unlogged meal, narrow overnight).

Caveat stated in the model card: readings from one patient are serially correlated, so
exchangeability holds only approximately. We split by patient to keep calibration and
test patients disjoint and report the empirical coverage on test patients.
"""
from __future__ import annotations

import numpy as np


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    scores = np.sort(np.asarray(scores, float))
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    if k < 1:
        return float("-inf")
    if k > n:
        return float("inf")
    return float(scores[k - 1])


def split_interval(pred: np.ndarray, cal_pred: np.ndarray, cal_y: np.ndarray, alpha: float):
    """Absolute residual split conformal: pred +/- q."""
    q = conformal_quantile(np.abs(cal_y - cal_pred), alpha)
    return pred - q, pred + q, q


def cqr_scores(lo: np.ndarray, hi: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.maximum(lo - y, y - hi)


def cqr_interval(lo: np.ndarray, hi: np.ndarray, q: float):
    return lo - q, hi + q


def coverage(lo: np.ndarray, hi: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))
