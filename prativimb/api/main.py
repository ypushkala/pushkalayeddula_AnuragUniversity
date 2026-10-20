"""Prativimb API. Run: uvicorn prativimb.api.main:app --port 8000"""
from __future__ import annotations

import asyncio
import json
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import unquote

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from prativimb import config
from prativimb.api import note_pdf
from prativimb.api.clock import DemoClock
from prativimb.api import ask as ask_mod
from prativimb.api.schemas import (Acknowledge, Action, Activity, Ask, ClockUpdate, Consent, MealEntry, Message,
                                   PatientDetail, Plan, WhatIfRequest)
from prativimb.data.cohort import MEAL_TYPES
from prativimb.api.services import AppState, clean, iso

warnings.filterwarnings("ignore")
STATE: AppState | None = None
CLOCK = DemoClock.from_env()
SOCKETS: set[WebSocket] = set()


async def replay_loop() -> None:
    """Push every new CGM reading (and the 5 minute heart rate and steps) as the clock passes it."""
    last = int(CLOCK.minute() // config.CGM_STEP)
    while True:
        await asyncio.sleep(1.0)
        now = CLOCK.minute()
        k = int(now // config.CGM_STEP)
        if k == last or not SOCKETS or STATE is None:
            last = k if not SOCKETS else last
            if SOCKETS:
                await broadcast({"type": "clock", **CLOCK.state()})
            continue
        lo = last + 1 if k > last else k
        readings = []
        for pid, s in STATE.S.items():
            platform = STATE.patients.loc[pid].device
            for j in range(max(lo, k - 12), k + 1):
                g = s.cgm[j]
                readings.append({"pid": pid, "t": iso(j * config.CGM_STEP), "glucose": None if np.isnan(g) else float(g),
                                 "hr": None if np.isnan(s.hr[j]) else round(float(s.hr[j]), 1),
                                 "steps": int(s.steps[j] * config.CGM_STEP), "source": platform})
        last = k
        await broadcast({"type": "readings", **CLOCK.state(), "readings": readings})


async def broadcast(msg: dict) -> None:
    dead = []
    text = json.dumps(msg)
    for ws in list(SOCKETS):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        SOCKETS.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global STATE
    STATE = AppState()
    task = asyncio.create_task(replay_loop())
    yield
    task.cancel()


app = FastAPI(title="Prativimb API", version="1.4.0", lifespan=lifespan,
              description="Hybrid patient digital twin (synthetic data). Decision support only, not a diagnosis.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def state() -> AppState:
    if STATE is None:
        raise HTTPException(503, "Loading")
    STATE.sync(CLOCK.minute())
    return STATE


def check(pid: str) -> str:
    if pid not in state().patients.index:
        raise HTTPException(404, f"Unknown patient {pid}")
    return pid


# Roles. The demo has no passwords: the dashboard sends the role and name chosen on its sign in
# page in two headers. A deployment would take both from the clinic's single sign on instead.
ROLE_NAMES = {"doctor": "doctor", "nurse": "nurse or health educator", "patient": "patient"}


def actor(request: Request) -> tuple[str, str]:
    role = request.headers.get("x-prativimb-role", "")
    if role not in ROLE_NAMES:
        raise HTTPException(401, "Sign in first and choose a role.")
    return role, unquote(request.headers.get("x-prativimb-user", "")).strip()[:60] or ROLE_NAMES[role].capitalize()


def need(who: tuple[str, str], allowed: tuple[str, ...], what: str) -> None:
    if who[0] not in allowed:
        raise HTTPException(403, f"Signed in as a {ROLE_NAMES[who[0]]}, you cannot {what}.")


@app.get("/api/health")
def health():
    return {"status": "ok", "patients": len(state().patients), "clock": CLOCK.state()}


@app.get("/api/clock")
def get_clock():
    return CLOCK.state()


@app.post("/api/clock")
def set_clock(u: ClockUpdate):
    minute = u.minute
    if u.at:
        dt = datetime.fromisoformat(u.at)
        minute = config.datetime_to_minute(dt)
    CLOCK.set(minute=minute, speed=u.speed, paused=u.paused)
    return CLOCK.state()


@app.get("/api/ward")
def ward():
    m = CLOCK.minute()
    return {"clock": CLOCK.state(), "patients": state().ward(m),
            "alert_level": state().alert_cov, "cardio_threshold": state().cardio_threshold}


@app.get("/api/patients/{pid}", response_model=PatientDetail)
def patient(pid: str):
    return state().detail(check(pid), CLOCK.minute())


@app.get("/api/patients/{pid}/timeline")
def timeline(pid: str, hours: int = Query(12, ge=1, le=72)):
    return state().timeline(check(pid), CLOCK.minute(), hours)


@app.get("/api/patients/{pid}/forecast")
def patient_forecast(pid: str, explain: bool = True):
    return state().patient_forecast(check(pid), CLOCK.minute(), explain)


@app.get("/api/patients/{pid}/agp")
def agp(pid: str, days: int = Query(14, ge=3, le=28)):
    return state().agp(check(pid), CLOCK.minute(), days)


@app.get("/api/patients/{pid}/alert-log")
def alert_log(pid: str, hours: int = Query(6, ge=1, le=24)):
    return state().alert_log(check(pid), CLOCK.minute(), hours)


@app.post("/api/patients/{pid}/whatif")
def whatif(pid: str, req: WhatIfRequest):
    return state().whatif(check(pid), CLOCK.minute(), req.model_dump())


@app.get("/api/patients/{pid}/levers")
def levers(pid: str, horizon_h: int = Query(6, ge=6, le=168), scope: str = Query("next", pattern="^(next|all)$")):
    return state().rank_levers(check(pid), CLOCK.minute(), horizon_h, scope)


@app.get("/api/meal-types")
def meal_types():
    return [{"kind": k, "label": v[0], "speed": v[1]} for k, v in MEAL_TYPES.items()]


@app.post("/api/patients/{pid}/meals")
def add_meal(pid: str, e: MealEntry, who=Depends(actor)):
    if e.kind not in MEAL_TYPES:
        raise HTTPException(422, f"Unknown meal kind {e.kind}")
    now = int(CLOCK.minute())
    minute = (now + e.minutes_from_now) // 5 * 5
    return state().store.add_meal(check(pid), minute, e.carbs, e.kind, e.label, who[1], now,
                                  source="patient" if who[0] == "patient" else "clinician")


@app.delete("/api/patients/{pid}/meals/{meal_id}")
def remove_meal(pid: str, meal_id: str, who=Depends(actor)):
    if not state().store.remove_meal(check(pid), meal_id, who[1], int(CLOCK.minute())):
        raise HTTPException(404, "No such meal entry")
    return {"removed": meal_id}


@app.post("/api/patients/{pid}/ack")
def acknowledge(pid: str, a: Acknowledge, who=Depends(actor)):
    need(who, ("doctor", "nurse"), "mark alerts as seen")
    if a.kind == "cardio":
        need(who, ("doctor",), "mark a heart risk alert as seen; a doctor reviews those")
    return state().store.acknowledge(check(pid), a.kind, who[1], int(CLOCK.minute()), a.snooze_minutes, a.note, who[0])


@app.delete("/api/patients/{pid}/ack/{ack_id}")
def undo_acknowledge(pid: str, ack_id: str, who=Depends(actor)):
    need(who, ("doctor", "nurse"), "undo an acknowledgement")
    if not state().store.remove_ack(check(pid), ack_id, who[1], int(CLOCK.minute())):
        raise HTTPException(404, "No such acknowledgement")
    return {"removed": ack_id}


@app.post("/api/patients/{pid}/actions")
def add_action(pid: str, a: Action, who=Depends(actor)):
    need(who, ("doctor", "nurse"), "record clinical actions")
    return state().store.add_action(check(pid), a.kind, who[1], int(CLOCK.minute()), a.note, a.outcome, who[0], a.alert)


@app.delete("/api/patients/{pid}/actions/{action_id}")
def undo_action(pid: str, action_id: str, who=Depends(actor)):
    need(who, ("doctor", "nurse"), "undo clinical actions")
    if not state().store.remove_action(check(pid), action_id, who[1], int(CLOCK.minute())):
        raise HTTPException(404, "No such action")
    return {"removed": action_id}


@app.get("/api/patients/{pid}/history")
def history(pid: str, days: int = Query(7, ge=1, le=21)):
    return state().history(check(pid), CLOCK.minute(), days)


@app.get("/api/patients/{pid}/plans")
def plans(pid: str):
    return state().plans(check(pid), CLOCK.minute())


@app.post("/api/patients/{pid}/plans")
def add_plan(pid: str, p: Plan, who=Depends(actor)):
    need(who, ("doctor",), "agree a plan; a doctor does that with the patient")
    return state().store.add_plan(check(pid), p.label, p.request, who[1], int(CLOCK.minute()), p.predicted)


@app.delete("/api/patients/{pid}/plans/{plan_id}")
def remove_plan(pid: str, plan_id: str, who=Depends(actor)):
    need(who, ("doctor",), "remove a plan")
    if not state().store.remove_plan(check(pid), plan_id, who[1], int(CLOCK.minute())):
        raise HTTPException(404, "No such plan")
    return {"removed": plan_id}


@app.get("/api/patients/{pid}/consent")
def consent(pid: str):
    return state().consent_view(check(pid), CLOCK.minute())


@app.post("/api/patients/{pid}/consent")
def set_consent(pid: str, c: Consent, who=Depends(actor)):
    need(who, ("patient", "doctor"), "change the patient's consent")
    return state().store.set_consent(check(pid), c.source, c.granted, who[1], int(CLOCK.minute()), who[0])


@app.post("/api/patients/{pid}/reference")
def reference_check(pid: str, req: WhatIfRequest):
    return state().reference_check(check(pid), CLOCK.minute(), req.model_dump())


@app.get("/api/patients/{pid}/sharpen")
def sharpen(pid: str):
    return state().sharpen(check(pid), CLOCK.minute())


@app.post("/api/patients/{pid}/inside")
def inside(pid: str, req: WhatIfRequest):
    return state().inside(check(pid), CLOCK.minute(), req.model_dump())


@app.get("/api/patients/{pid}/twin-health")
def twin_health(pid: str):
    return state().twin_health(check(pid), CLOCK.minute())


@app.post("/api/patients/{pid}/refit")
def refit(pid: str, who=Depends(actor)):
    need(who, ("doctor",), "refit a patient's twin")
    return state().refit_twin(check(pid), CLOCK.minute(), who[1])


@app.delete("/api/patients/{pid}/refit/{rid}")
def undo_refit(pid: str, rid: str, who=Depends(actor)):
    need(who, ("doctor",), "undo a refit")
    if not state().store.remove_refit(check(pid), rid, who[1], int(CLOCK.minute())):
        raise HTTPException(404, "No such refit")
    return {"removed": rid}


@app.post("/api/ask")
def ask(q: Ask):
    return ask_mod.parse(q.text)


@app.get("/api/ward/whatif")
def ward_whatif(lever: str = Query("Walk 15 min after the meal", max_length=80)):
    st = state()
    if lever not in dict(st.LEVERS):
        raise HTTPException(422, "Unknown change")
    return st.ward_whatif(CLOCK.minute(), lever)


@app.get("/api/festivals")
def festivals():
    return state().festivals(CLOCK.minute())


@app.post("/api/patients/{pid}/activities")
def add_activity(pid: str, a: Activity, who=Depends(actor)):
    from prativimb.data import reference
    from prativimb.twin import forecast as fc
    st, pid = state(), check(pid)
    now = int(CLOCK.minute())
    planned = start = now
    if a.when == "done":
        planned = start = now - a.minutes_ago
    elif a.when == "after_next_meal":
        _, sched, _, _ = reference.patient_inputs(pid)
        meal = reference.target_meal(sched, now - 30, 6 * 60)
        if meal is None:
            raise HTTPException(409, "No main meal in the next few hours to walk after.")
        start = meal[0] + reference.WALK_DELAY
        k = st.origin(pid, now)
        exp = [m for m in fc.expected_meals(st.pp(pid, now), k, 72) if m[1] >= fc.MAIN_MEAL_G] if k is not None else []
        planned = (k + exp[0][0]) * 5 + reference.WALK_DELAY if exp else start
    rec = st.store.add_activity(pid, a.kind, start, a.minutes, who[1], now, "patient" if who[0] == "patient" else "clinician",
                                planned_start=planned)
    st.sync(CLOCK.minute())
    return rec


@app.delete("/api/patients/{pid}/activities/{aid}")
def remove_activity(pid: str, aid: str, who=Depends(actor)):
    if not state().store.remove_activity(check(pid), aid, who[1], int(CLOCK.minute())):
        raise HTTPException(404, "No such activity")
    return {"removed": aid}


@app.get("/api/patients/{pid}/activities")
def activities(pid: str):
    st = state()
    now = CLOCK.minute()
    out = []
    for a in st.store.activities_for(check(pid), now):
        out.append({**a, "start_t": iso(a["start"]), "done": a["start"] + a["minutes"] <= now})
    return clean(out)


@app.get("/api/patients/{pid}/messages")
def messages(pid: str):
    return clean([{**m, "t": iso(m["minute"])} for m in state().store.messages_for(check(pid), CLOCK.minute())])


@app.post("/api/patients/{pid}/messages")
def add_message(pid: str, m: Message, who=Depends(actor)):
    """A nudge from the care team (stored with the numbers it was sent with), or a patient's reply, which gets an
    automatic acknowledgement carrying the forecast as it stands once the reply is taken into account."""
    st, pid, now = state(), check(pid), int(CLOCK.minute())
    if m.key == "nudge":
        need(who, ("doctor", "nurse"), "send messages to patients")
        return st.store.add_message(pid, "care team", "nudge", m.text, now, who[1], {k: v for k, v in m.params.items() if k in ("peak", "after", "lever")})
    if who[0] != "patient":
        raise HTTPException(403, "Only the patient replies from their phone.")
    rec = st.store.add_message(pid, "patient", m.key, m.text, now, who[1])
    if m.key == "not_today":
        st.store.add_message(pid, "care team", "thanks_not", "", now, "Prativimb")
    else:
        fc = st.patient_forecast(pid, now, explain=False)
        peak = fc["status"]["peak"] if fc.get("available") else None
        st.store.add_message(pid, "care team", "thanks_plan", "", now, "Prativimb", {"peak": round(peak) if peak else None})
    return rec


@app.delete("/api/patients/{pid}/messages/{mid}")
def remove_message(pid: str, mid: str, who=Depends(actor)):
    """Removes a message; removing a patient's reply also removes the automatic acknowledgement made with it."""
    st, pid, now = state(), check(pid), int(CLOCK.minute())
    msg = next((x for x in st.store.messages if x["id"] == mid and x["pid"] == pid), None)
    if msg is None or not st.store.remove_message(pid, mid, who[1], now):
        raise HTTPException(404, "No such message")
    if msg["from"] == "patient":
        for x in [x for x in st.store.messages if x["pid"] == pid and x["key"].startswith("thanks") and x["minute"] == msg["minute"]]:
            st.store.remove_message(pid, x["id"], who[1], now)
    return {"removed": mid}


@app.get("/api/patients/{pid}/walk-result")
def walk_result(pid: str):
    """After a logged walk: the evening as it went, against the same evening without the walk (the original replay)."""
    st = state()
    pid = check(pid)
    now = CLOCK.minute()
    walks = [a for a in st.store.activities_for(pid, now) if a["kind"] == "walk"]
    orig = st.__dict__.get("_S_orig", {}).get(pid)
    if not walks or orig is None:
        return {"available": False}
    a = walks[-1]
    k0, k1 = a["start"] // 5, int(now // 5) + 1
    if k1 <= k0 + 6:
        return {"available": False, "pending": True, "start": iso(a["start"])}
    import numpy as np
    with_walk, without = st.S[pid].cgm[k0:k1], orig.cgm[k0:k1]
    ok = ~np.isnan(with_walk) & ~np.isnan(without)
    if not ok.any():
        return {"available": False}
    return clean({"available": True, "start": iso(a["start"]), "minutes": a["minutes"],
                  "peak_with": float(np.nanmax(with_walk)), "peak_without": float(np.nanmax(without)),
                  "minutes_above_with": int((with_walk[ok] > 180).sum() * 5), "minutes_above_without": int((without[ok] > 180).sum() * 5)})


@app.get("/api/handover")
def handover(hours: int = Query(12, ge=1, le=24)):
    return state().handover(CLOCK.minute(), hours)


@app.get("/api/digest")
def digest():
    return state().digest(CLOCK.minute())


@app.get("/api/audit")
def audit(pid: str | None = None, limit: int = Query(200, ge=1, le=2000)):
    return state().store.audit(pid, limit)


@app.get("/api/patients/{pid}/cardio")
def cardio(pid: str, end_day: int | None = Query(None, ge=6, lt=config.N_DAYS)):
    return state().cardio_view(check(pid), CLOCK.minute(), end_day)


@app.get("/api/patients/{pid}/note")
def note(pid: str):
    return state().note(check(pid), CLOCK.minute())


@app.get("/api/patients/{pid}/note.pdf")
def note_pdf_route(pid: str):
    n = state().note(check(pid), CLOCK.minute())
    return Response(note_pdf.render(n), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="prativimb-note-{pid}.pdf"'})


@app.get("/api/fhir/Patient/{pid}/$everything")
def fhir_bundle(pid: str):
    path = config.RAW_DIR / "ehr" / f"{check(pid)}.json"
    return JSONResponse(json.loads(path.read_text()), media_type="application/fhir+json")


@app.get("/api/model-card")
def model_card():
    m = state().metrics
    fu = config.REPORT_DIR / "followup.json"
    cf = config.REPORT_DIR / "counterfactual.json"
    return {"metrics": m, "alert_level": state().alert_cov, "cardio_threshold": state().cardio_threshold,
            "followup": json.loads(fu.read_text()) if fu.exists() else None,
            "counterfactual": {k: v for k, v in json.loads(cf.read_text()).items() if k != "points"} if cf.exists() else None,
            "figures": sorted(p.name for p in config.FIGURE_DIR.glob("*.png"))}


@app.websocket("/ws/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    SOCKETS.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", **CLOCK.state()}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        SOCKETS.discard(ws)


if config.FIGURE_DIR.exists():
    app.mount("/figures", StaticFiles(directory=config.FIGURE_DIR), name="figures")

DIST = config.ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
