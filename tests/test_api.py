import os

import pytest

from tests.conftest import needs_data, needs_models

os.environ["PRATIVIMB_PAUSED"] = "1"
pytestmark = [needs_data, needs_models]

DEMO = "2026-03-15T19:45:00+05:30"


DOCTOR = {"X-Prativimb-Role": "doctor", "X-Prativimb-User": "Dr%20Test"}
NURSE = {"X-Prativimb-Role": "nurse", "X-Prativimb-User": "Nurse%20Test"}
PATIENT = {"X-Prativimb-Role": "patient", "X-Prativimb-User": "Ramesh"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from prativimb.api import store
    tmp = tmp_path_factory.mktemp("store")
    store.STORE, store.AUDIT = tmp / "clinical_store.json", tmp / "audit.jsonl"  # tests never touch the demo's store
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


def test_ward_is_grouped_by_urgency(client):
    w = client.get("/api/ward").json()["patients"]
    assert len(w) == 200
    rank = {"low": 0, "high": 1, "heart": 2, "watch": 3, None: 4}
    key = [(rank[p["group"]], p["seen"], -p["priority"]) for p in w]
    assert key == sorted(key)
    ramesh = next(p for p in w if p["id"] == "PTV-0001")
    assert ramesh["event_a"]["tier"] == "alert" and ramesh["group"] == "high"
    assert ramesh["event_a"]["reason"].startswith("dinner")
    assert "low insulin sensitivity" not in ramesh["event_a"]["reason"]


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


def test_roles_are_checked_and_acks_can_be_undone(client):
    pid = "PTV-0001"
    assert client.post(f"/api/patients/{pid}/ack", json={"kind": "spike"}).status_code == 401
    assert client.post(f"/api/patients/PTV-0151/ack", json={"kind": "cardio"}, headers=NURSE).status_code == 403
    assert client.post(f"/api/patients/{pid}/plans", json={"label": "x", "request": {}}, headers=NURSE).status_code == 403
    assert client.post(f"/api/patients/{pid}/ack", json={"kind": "spike"}, headers=PATIENT).status_code == 403
    a = client.post(f"/api/patients/{pid}/ack", json={"kind": "spike", "snooze_minutes": 60, "note": "walk"}, headers=NURSE).json()
    assert a["by"] == "Nurse Test" and a["role"] == "nurse"
    ward = {p["id"]: p for p in client.get("/api/ward").json()["patients"]}
    assert ward[pid]["seen"]
    h = client.get("/api/handover?hours=12").json()
    assert any(d["pid"] == pid and "seen" in d["what"] for d in h["done"])
    assert client.delete(f"/api/patients/{pid}/ack/{a['id']}", headers=NURSE).status_code == 200
    assert not {p["id"]: p for p in client.get("/api/ward").json()["patients"]}[pid]["seen"]


def test_actions_and_patient_meals(client):
    r = client.post("/api/patients/PTV-0151/actions", json={"kind": "call", "outcome": "No symptoms", "alert": "cardio"}, headers=NURSE)
    assert r.status_code == 200
    assert client.delete(f"/api/patients/PTV-0151/actions/{r.json()['id']}", headers=NURSE).status_code == 200
    m = client.post("/api/patients/PTV-0001/meals", json={"minutes_from_now": 0, "carbs": 60, "kind": "millet_meal", "label": "Ragi"},
                    headers=PATIENT).json()
    assert m["source"] == "patient" and m["by"] == "Ramesh"
    assert client.delete(f"/api/patients/PTV-0001/meals/{m['id']}", headers=PATIENT).status_code == 200


def test_earlier_alerts_have_outcomes(client):
    h = client.get("/api/patients/PTV-0001/history").json()
    s = h["summary"]
    assert s["alerts"] > 5 and 0 <= s["rate"] <= 1 and s["happened"] <= s["decided"] <= s["alerts"]
    assert {e["result"] for e in h["episodes"]} <= {"happened", "did not happen", "pending"}
    # The alert raised at 19:15 before the 21:00 crossing is there, with its warning time.
    assert any(e["start"].startswith("2026-03-15T19:15") and e["result"] == "happened" for e in h["episodes"])


def test_seeded_plan_is_checked_against_what_happened(client):
    plans = client.get("/api/patients/PTV-0001/plans").json()
    p = next(x for x in plans if x["seeded"])
    assert p["check"]["complete"] and p["check"]["adherence"].endswith("main meals")
    assert "not followed" in p["check"]["verdict"]


def test_withdrawn_consent_stops_the_forecast(client):
    pid = "PTV-0002"
    assert client.post(f"/api/patients/{pid}/consent", json={"source": "cgm", "granted": False}, headers=NURSE).status_code == 403
    assert client.post(f"/api/patients/{pid}/consent", json={"source": "cgm", "granted": False}, headers=PATIENT).status_code == 200
    f = client.get(f"/api/patients/{pid}/forecast").json()
    assert not f["available"] and f["paused"]
    row = next(p for p in client.get("/api/ward").json()["patients"] if p["id"] == pid)
    assert row["sharing_paused"] == ["cgm"] and row["glucose"] is None
    client.post(f"/api/patients/{pid}/consent", json={"source": "cgm", "granted": True}, headers=PATIENT)
    assert client.get(f"/api/patients/{pid}/forecast").json()["available"]


def test_insulin_and_week_long_what_if(client):
    base = client.post("/api/patients/PTV-0001/whatif", json={}).json()
    ins = client.post("/api/patients/PTV-0001/whatif", json={"insulin_bolus_units": 6}).json()
    assert ins["delta"]["peak"] < -10 and "population insulin action" in ins["note"]
    assert base["delta"]["peak"] == 0
    week = client.post("/api/patients/PTV-0001/whatif", json={"walk_minutes": 30, "scope": "all", "horizon_h": 168}).json()
    assert len(week["days"]) == 7 and week["delta"]["tir_pct"] > 0
    lev = client.get("/api/patients/PTV-0001/levers?horizon_h=168&scope=all").json()
    assert lev["available"] and lev["levers"][0]["tir_pct"] >= lev["levers"][-1]["tir_pct"]


def test_first_week_downgrades_alerts(client):
    client.post("/api/clock", json={"at": "2026-02-17T19:45:00+05:30", "paused": True})
    try:
        f = client.get("/api/patients/PTV-0001/forecast").json()
        assert f["status"]["calibrating"] == 4 and f["status"]["tier"] != "alert"
        assert f["alerts"][0]["kind"] == "calibrating"
    finally:
        client.post("/api/clock", json={"at": DEMO, "paused": True})


def test_digest(client):
    d = client.get("/api/digest").json()
    assert d["patients"] == 200 and d["alerts_happened"] <= d["alerts_total"] and 0 <= d["tir"] <= 100
