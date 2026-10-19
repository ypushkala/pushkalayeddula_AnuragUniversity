import os

import pytest

from tests.conftest import needs_data, needs_models

os.environ["PRATIVIMB_PAUSED"] = "1"
pytestmark = [needs_data, needs_models]

DEMO = "2026-03-15T19:45:00+05:30"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from prativimb.api.main import app
    with TestClient(app) as c:
        c.post("/api/clock", json={"at": DEMO, "paused": True})
        yield c


def test_health_and_clock(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["patients"] == 200
    c = client.post("/api/clock", json={"at": "2026-03-15T18:00:00+05:30", "paused": True}).json()
    assert c["now"].startswith("2026-03-15T18:00") and c["paused"]
    client.post("/api/clock", json={"at": DEMO, "paused": True})


def test_ward_is_sorted_by_priority(client):
    w = client.get("/api/ward").json()["patients"]
    assert len(w) == 200
    pr = [p["priority"] for p in w]
    assert pr == sorted(pr, reverse=True)
    ramesh = next(p for p in w if p["id"] == "PTV-0001")
    assert ramesh["event_a"]["tier"] == "alert"


def test_patient_detail_is_fhir_shaped(client):
    d = client.get("/api/patients/PTV-0001").json()
    assert d["patient"]["name"] == "Ramesh Patil"
    assert any(c["code"]["code"] == "E11.9" for c in d["conditions"])
    assert any(l["code"]["system"] == "http://loinc.org" for l in d["labs"])
    assert {g["gene"] for g in d["genetics"]} >= {"TCF7L2"}
    assert client.get("/api/patients/NOPE").status_code == 404


def test_forecast_interval_ordering_and_explanation(client):
    f = client.get("/api/patients/PTV-0001/forecast").json()
    assert f["available"]
    for pt in f["points"]:
        assert pt["lo"] <= pt["mid"] + 1e-6 <= pt["hi"] + 2e-6
    assert f["explanation"]["sentence"].endswith("driving this forecast.")
    assert f["alerts"][0]["kind"] == "spike"


def test_whatif_walk_and_millet_lower_the_peak(client):
    walk = client.post("/api/patients/PTV-0001/whatif", json={"walk_minutes": 15}).json()
    millet = client.post("/api/patients/PTV-0001/whatif", json={"swap": "millet"}).json()
    assert walk["delta"]["peak"] < -5
    assert millet["delta"]["peak"] < walk["delta"]["peak"]
    assert client.post("/api/patients/PTV-0001/whatif", json={"walk_minutes": 500}).status_code == 422


def test_suresh_flagged_before_event(client):
    v = client.get("/api/patients/PTV-0003/cardio").json()
    assert v["event"] is not None
    flagged = [t["day"] for t in v["trajectory"] if t["flag"]]
    assert flagged and v["event"]["day"] - min(flagged) >= 3


def test_no_future_data_leaks(client):
    tl = client.get("/api/patients/PTV-0002/timeline?hours=6").json()
    assert max(r["t"] for r in tl["cgm"]) <= tl["now"]
    assert all(m["t"] <= tl["now"] for m in tl["meals"])


def test_note_and_pdf(client):
    n = client.get("/api/patients/PTV-0001/note").json()
    assert n["S"] and n["O"] and n["A"] and n["P"]
    pdf = client.get("/api/patients/PTV-0001/note.pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


def test_fhir_bundle(client):
    b = client.get("/api/fhir/Patient/PTV-0002/$everything").json()
    assert b["resourceType"] == "Bundle"
    assert any(e["resource"]["resourceType"] == "Consent" for e in b["entry"])
