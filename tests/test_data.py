import hashlib

import numpy as np
import pandas as pd

from prativimb import config
from prativimb.data import cohort, devices, schedule
from tests.conftest import needs_data


def test_cohort_is_deterministic():
    a = cohort.make_cohort(12)
    b = cohort.make_cohort(12)
    assert [p.name for p in a] == [p.name for p in b]
    assert [p.labs for p in a] == [p.labs for p in b]


def test_schedule_is_deterministic():
    p = cohort.make_cohort(5)[3]
    s1 = schedule.build(p, np.random.default_rng(7))
    s2 = schedule.build(p, np.random.default_rng(7))
    h = lambda s: hashlib.sha1(s.steps.tobytes() + s.carbs.tobytes() + s.stage.tobytes()).hexdigest()
    assert h(s1) == h(s2)


def test_split_keeps_heroes_in_test_and_is_disjoint():
    pts = cohort.make_cohort(200)
    sp = cohort.split_of(pts)
    assert all(sp[pid] == "test" for pid in config.HERO_IDS.values())
    assert pd.Series(sp).value_counts().to_dict() == {"train": 120, "calibration": 40, "test": 40}


def test_device_adapters_round_trip(tmp_path):
    minutes = np.arange(0, 3 * 1440)
    hr = pd.DataFrame({"minute": minutes, "hr": np.where(minutes % 97 == 0, np.nan, 60 + minutes % 30).astype(float),
                       "steps": (minutes % 13 == 0) * 40})
    cgm = pd.DataFrame({"minute": minutes[::5], "glucose": (100 + (minutes[::5] % 120)).astype(float)})
    sleep = pd.DataFrame({"start": [60, 120], "end": [120, 200], "stage": ["core", "deep"]})
    hrv = pd.DataFrame({"minute": [480], "rmssd": [33.5]})
    devices.write_apple(tmp_path / "export.xml", "Test", cgm, hr, sleep, hrv)
    devices.write_google(tmp_path / "gfit", cgm, hr, sleep, hrv)
    devices.write_health_connect(tmp_path / "hc.json", cgm, hr, sleep, hrv)
    for parsed in (devices.read_apple(tmp_path / "export.xml"), devices.read_google(tmp_path / "gfit"),
                   devices.read_health_connect(tmp_path / "hc.json")):
        got = parsed["cgm"].set_index("minute").glucose.dropna()
        assert np.allclose(got.loc[cgm.minute].to_numpy(), cgm.glucose.to_numpy())
        h = parsed["hr"].set_index("minute")
        assert np.allclose(h.hr.loc[minutes].to_numpy(), hr.hr.to_numpy(), equal_nan=True)
        assert (h.steps.loc[minutes].to_numpy() == hr.steps.to_numpy()).all()
        assert parsed["sleep"].stage.tolist() == ["core", "deep"]


@needs_data
def test_fhir_bundles_parse_into_features():
    from prativimb.data import ingest
    ehr = ingest.load_ehr()
    f = ingest.ehr_features(ehr["patients"], ehr["conditions"], ehr["medications"], ehr["observations"], ehr["genetics"])
    assert len(f) == 200 and f.hba1c.between(4, 13).all()
    r = f.set_index("pid").loc["PTV-0001"]
    assert r.t2d == 1 and r.on_metformin == 1 and r.night_shift == 1
