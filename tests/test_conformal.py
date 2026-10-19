import numpy as np
import pytest

from prativimb.ml import conformal


def test_quantile_uses_finite_sample_correction():
    scores = np.arange(1, 10, dtype=float)       # n = 9
    # ceil((9 + 1) * 0.9) = 9, so the 9th smallest score
    assert conformal.conformal_quantile(scores, 0.1) == 9.0
    # too few points for the requested level gives an infinite interval
    assert conformal.conformal_quantile(scores[:5], 0.1) == float("inf")


@pytest.mark.parametrize("alpha", [0.05, 0.1, 0.2])
def test_split_conformal_covers_exchangeable_data(alpha):
    rng = np.random.default_rng(0)
    covs = []
    for _ in range(200):
        y_cal, y_test = rng.standard_t(3, 500), rng.standard_t(3, 500)
        lo, hi, _ = conformal.split_interval(np.zeros(500), np.zeros(500), y_cal, alpha)
        covs.append(conformal.coverage(lo, hi, y_test))
    assert abs(np.mean(covs) - (1 - alpha)) < 0.01
    assert np.mean(covs) >= 1 - alpha - 0.005


def test_cqr_is_adaptive_and_valid():
    rng = np.random.default_rng(1)
    n = 4000
    x = rng.uniform(0, 1, 2 * n)
    y = rng.normal(0, 0.1 + 2 * x)              # noise grows with x
    # Deliberately miscalibrated quantile model: right shape, half the width.
    lo, hi = -0.5 * 1.645 * (0.1 + 2 * x), 0.5 * 1.645 * (0.1 + 2 * x)
    q = conformal.conformal_quantile(conformal.cqr_scores(lo[:n], hi[:n], y[:n]), 0.1)
    L, U = conformal.cqr_interval(lo[n:], hi[n:], q)
    assert abs(conformal.coverage(L, U, y[n:]) - 0.9) < 0.02
    width = U - L
    assert width[x[n:] > 0.8].mean() > 2 * width[x[n:] < 0.2].mean()
