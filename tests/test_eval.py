import numpy as np

from prativimb.eval import clarke
from prativimb.eval.alerts import spike_onsets


def test_clarke_zones_reference_points():
    ref = np.array([100, 50, 250, 60, 300, 150])
    pred = np.array([110, 60, 100, 250, 50, 300])
    assert list(clarke.zones(ref, pred)) == ["A", "A", "D", "E", "E", "C"]


def test_clarke_table_sums_to_100():
    rng = np.random.default_rng(0)
    ref = rng.uniform(40, 400, 1000)
    tab = clarke.zone_table(ref, ref * rng.normal(1, 0.2, 1000))
    assert abs(sum(tab.values()) - 100) < 1e-9


def test_spike_onset_needs_sustained_crossing():
    c = np.full(60, 150.0)
    c[20:25] = 200       # sustained: counts
    c[40] = 200          # single reading: ignored
    assert list(spike_onsets(c, 0)) == [20]
