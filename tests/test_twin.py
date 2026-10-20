import numpy as np
import pandas as pd
import pytest

from prativimb.twin import bergman, calibrate, forecast
from prativimb.twin.series import N, PER_DAY, Series
from tests.conftest import needs_data

THETA = np.array([3e-4, 0.01, 120.0, 0.03, 0.03, 0.0, 0.004, 0.55])


def _inputs(S, carbs_at=None, carbs=0.0, walk=None):
    z = lambda: np.zeros((1, S))
    u = bergman.Inputs(z(), np.ones((1, S)), z(), z(), np.ones((1, S)), z())
    if carbs_at is not None:
        u.carbs[0, carbs_at] = carbs
    if walk is not None:
        u.A[0, walk[0]: walk[1]] = 1.0
    return u


def _p(theta=THETA):
    return bergman.params_dict(theta, 70.0, 0.0)


def test_steady_state_holds_without_inputs():
    x0 = bergman.steady_state({}, 120.0, 0.0)
    G, _ = bergman.run_rk4(_p(), x0, _inputs(72))
    assert np.abs(G - 120.0).max() < 0.01
    assert np.abs(bergman.run_ivp(_p(), x0, _inputs(72)) - 120.0).max() < 0.01


def test_meal_raises_then_returns_toward_basal():
    G, _ = bergman.run_rk4(_p(), bergman.steady_state({}, 120.0, 0.0), _inputs(120, 2, 80.0))
    G = G[0]
    assert G.max() > 180
    assert 4 <= np.argmax(G) <= 36          # peak between 20 min and 3 h
    assert abs(G[-1] - 120) < 15             # back near basal after 10 h


def test_walk_after_meal_lowers_peak():
    x0 = bergman.steady_state({}, 120.0, 0.0)
    base = bergman.run_rk4(_p(), x0, _inputs(72, 2, 90.0))[0][0]
    walk = bergman.run_rk4(_p(), x0, _inputs(72, 2, 90.0, walk=(4, 7)))[0][0]
    assert walk.max() < base.max() - 3
    assert walk[:36].mean() < base[:36].mean() - 1


def test_rk4_matches_solve_ivp():
    u = _inputs(72, 3, 70.0, walk=(10, 14))
    u.carbs[0, 40] = 25.0
    u.smod[0] = np.linspace(0.9, 1.1, 72)
    x0 = bergman.steady_state({}, 140.0, 0.0)
    a = bergman.run_rk4(_p(), x0, u)[0][0]
    b = bergman.run_ivp(_p(), x0, u)
    assert np.abs(a - b).max() < 1.0


def _synthetic_series(theta, seed=0):
    """A patient whose CGM is produced by the twin itself, for a parameter recovery check."""
    rng = np.random.default_rng(seed)
    carbs, af = np.zeros(N), np.zeros(N)
    for d in range(30):
        for minute, g in ((8 * 60, 50), (13 * 60, 85), (20 * 60 + 30, 80)):
            k = (d * 1440 + minute + int(rng.integers(-30, 30))) // 5
            carbs[k], af[k] = g * rng.uniform(0.8, 1.2), 1.0
    steps = np.zeros(N)
    for d in range(30):
        k = (d * 1440 + 18 * 60) // 5
        steps[k: k + 4] = 100.0
    s = Series(pid="SYN", ehr={"hba1c": 7.0, "bmi": 26, "fpg": 125, "t2d": 1, "age": 50, "weight": 70.0,
                               "on_metformin": 0, "tcf7l2_risk": 0},
               cgm=np.full(N, 120.0), carbs=carbs, meal_af=af, steps=steps, hr=np.full(N, 70.0),
               met_dose=np.zeros(N), met_missed=np.zeros(N), sleep_hours=np.full(30, 7.0), nightly=None,
               routine={"normal": [(8 * 60, 50.0, "rice_meal", "Breakfast"), (13 * 60, 85.0, "rice_meal", "Lunch"),
                                   (20 * 60 + 30, 80.0, "rice_meal", "Dinner")]},
               declared={}, meal_log=pd.DataFrame({"minute": np.flatnonzero(carbs) * 5, "carbs": carbs[carbs > 0]}))
    pp = forecast.prepare(s)
    u, _ = forecast.build(pp, np.array([forecast.W]), N - forecast.W, future="actual")
    x0 = bergman.steady_state({}, theta[2], 0.0)
    G, _ = bergman.run_rk4(bergman.params_dict(theta, 70.0, 0.0), x0, u)
    s.cgm = G[0, :N] + rng.normal(0, 4, N)
    return s


def test_calibration_recovers_known_parameters():
    s = _synthetic_series(THETA)
    theta, info = calibrate.calibrate(s)
    assert abs(theta[2] - THETA[2]) / THETA[2] < 0.06          # Gb
    assert abs(np.log(theta[3] / THETA[3])) < 0.3               # ka
    assert info["rmse_fit"] < 8.0
    assert info["rmse_fit"] < info["rmse_prior"]


@needs_data
def test_calibrated_twin_beats_cold_start_on_held_out_days():
    from prativimb.twin import series
    S = series.load_all(pids=["PTV-0001", "PTV-0002", "PTV-0003"])
    for s in S.values():
        theta, _ = calibrate.calibrate(s)
        pp = forecast.prepare(s)
        ks = np.arange(8 * PER_DAY, 29 * PER_DAY, 6)
        ks = ks[~np.isnan(s.cgm[ks])]
        y = forecast._take(s.cgm, ks + 12, np.nan)
        m = ~np.isnan(y)
        err = lambda th: np.sqrt(np.mean((forecast.forecast(pp, th, ks, 13)[m, 12] - y[m]) ** 2))
        assert err(theta) < err(calibrate.ehr_prior(s.ehr).mean)


def test_insulin_appearance_delivers_the_whole_dose():
    from prativimb.twin import forecast
    H = 288 * 2
    bolus = forecast.insulin_appearance(H, 70.0, [0], 6.0, 0.0)
    total = bolus.sum() * 5 * forecast.INSULIN_VD_ML_PER_KG * 70.0 / 1e6
    assert abs(total - 6.0) < 0.05
    basal = forecast.insulin_appearance(288, 70.0, [], 0.0, 12.0)
    assert np.allclose(basal, basal[0]) and abs(basal.sum() * 5 * forecast.INSULIN_VD_ML_PER_KG * 70.0 / 1e6 - 12.0) < 0.05


@needs_data
def test_reference_simulator_restarts_exactly_and_answers_what_ifs():
    from prativimb import config
    from prativimb.data import reference
    truth = pd.read_parquet(config.PROCESSED_DIR / "truth_glucose.parquet", filters=[("pid", "==", "PTV-0001")]).set_index("minute")
    t = 29 * 1440 + 19 * 60 + 45
    base, _ = reference.changed_inputs("PTV-0001", t, 200, reference.Change())
    gs = reference.run_from("PTV-0001", t, base)[::5]
    assert np.abs(gs - truth.gs.loc[t: t + 199].to_numpy()[: len(gs)]).max() < 0.05
    walk = reference.what_if("PTV-0001", t, 240, reference.Change(walk_minutes=15))
    half = reference.what_if("PTV-0001", t, 240, reference.Change(swap="half_portion"))
    assert walk["delta"]["peak"] < -3 and half["delta"]["peak"] < walk["delta"]["peak"]
