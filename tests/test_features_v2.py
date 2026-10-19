"""Planned and logged meals, acknowledgements, lever ranking, 24 hour scenarios, hypoglycaemia."""
import os

import numpy as np
import pytest

from prativimb.ml import hypo
from tests.conftest import needs_data, needs_models

os.environ["PRATIVIMB_PAUSED"] = "1"
DEMO = "2026-03-15T19:45:00+05:30"


def test_compression_detector_finds_a_fast_symmetric_dip_but_not_a_slow_fall():
    c = np.full(60, 120.0)
    c[20:26] = [100, 85, 80, 84, 98, 118]            # compression: fast down, fast back
    slow = np.linspace(120, 72, 60)                    # a real overnight fall
    asleep = np.ones(60, bool)
    assert hypo.compression_artefacts(c, asleep)[22]
    assert not hypo.compression_artefacts(slow, asleep).any()
    assert not hypo.compression_artefacts(c, np.zeros(60, bool)).any()   # awake: never flagged


def test_low_labels_need_two_readings_below_70():
    c = np.full(40, 100.0)
    c[10] = 65                                         # single low reading: not an event
    c[25:27] = 65
    y = hypo.labels(c, np.zeros(40, bool), np.array([5, 15, 30]))  # look ahead 60 min (12 steps)
    assert list(y) == [0, 1, 0]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from prativimb import config
    from prativimb.api.main import app
    for f in ("clinical_store.json", "audit.jsonl"):
        (config.ARTIFACT_DIR / f).unlink(missing_ok=True)
    with TestClient(app) as c:
        c.post("/api/clock", json={"at": DEMO, "paused": True})
        yield c
    for f in ("clinical_store.json", "audit.jsonl"):
        (config.ARTIFACT_DIR / f).unlink(missing_ok=True)


@needs_data
@needs_models
def test_planned_meal_changes_forecast_and_can_be_removed(client):
    before = client.get("/api/patients/PTV-0001/forecast").json()["status"]["peak"]
    m = client.post("/api/patients/PTV-0001/meals", json={"minutes_from_now": 75, "carbs": 50, "kind": "millet_meal",
                                                          "label": "Ragi roti", "by": "Test"}).json()
    assert m["type"] == "planned"
    after = client.get("/api/patients/PTV-0001/forecast").json()["status"]["peak"]
    assert after < before - 20
    client.delete(f"/api/patients/PTV-0001/meals/{m['id']}")
    assert abs(client.get("/api/patients/PTV-0001/forecast").json()["status"]["peak"] - before) < 1


@needs_data
@needs_models
def test_acknowledged_alert_drops_in_ward_until_snooze_ends(client):
    ids = lambda: [p["id"] for p in client.get("/api/ward").json()["patients"]]
    assert ids()[0] == "PTV-0001"
    client.post("/api/patients/PTV-0001/ack", json={"kind": "spike", "by": "Dr Test", "snooze_minutes": 30})
    assert ids().index("PTV-0001") > 5
    client.post("/api/clock", json={"at": "2026-03-15T20:20:00+05:30", "paused": True})
    card = client.get("/api/patients/PTV-0001/forecast").json()["alerts"]
    assert all(c.get("ack") is None for c in card)
    client.post("/api/clock", json={"at": DEMO, "paused": True})
    assert any(a["action"] == "alert_acknowledged" for a in client.get("/api/audit?pid=PTV-0001").json())


@needs_data
@needs_models
def test_levers_are_ranked_and_24h_scope_changes_every_meal(client):
    r = client.get("/api/patients/PTV-0001/levers").json()
    peaks = [x["peak"] for x in r["levers"]]
    assert peaks == sorted(peaks) and peaks[0] < -20
    day = client.post("/api/patients/PTV-0001/whatif", json={"walk_minutes": 15, "scope": "all", "horizon_h": 24}).json()
    assert day["meals_changed"] >= 2 and len(day["times"]) == 24 * 12 + 1
    assert day["delta"]["auc_above_180"] < 0
