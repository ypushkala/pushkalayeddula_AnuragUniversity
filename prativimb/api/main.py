"""Prativimb API. Run: uvicorn prativimb.api.main:app --port 8000"""
from __future__ import annotations

import asyncio
import json
import warnings
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from prativimb import config
from prativimb.api import note_pdf
from prativimb.api.clock import DemoClock
from prativimb.api.schemas import Acknowledge, ClockUpdate, MealEntry, PatientDetail, WhatIfRequest
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


app = FastAPI(title="Prativimb API", version="1.2.0", lifespan=lifespan,
              description="Hybrid patient digital twin (synthetic data). Decision support only, not a diagnosis.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def state() -> AppState:
    if STATE is None:
        raise HTTPException(503, "Loading")
    return STATE


def check(pid: str) -> str:
    if pid not in state().patients.index:
        raise HTTPException(404, f"Unknown patient {pid}")
    return pid


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
    return state().detail(check(pid))


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
def levers(pid: str, horizon_h: int = Query(6, ge=6, le=24), scope: str = Query("next", pattern="^(next|all)$")):
    return state().rank_levers(check(pid), CLOCK.minute(), horizon_h, scope)


@app.get("/api/meal-types")
def meal_types():
    return [{"kind": k, "label": v[0], "speed": v[1]} for k, v in MEAL_TYPES.items()]


@app.post("/api/patients/{pid}/meals")
def add_meal(pid: str, e: MealEntry):
    if e.kind not in MEAL_TYPES:
        raise HTTPException(422, f"Unknown meal kind {e.kind}")
    now = int(CLOCK.minute())
    minute = (now + e.minutes_from_now) // 5 * 5
    return state().store.add_meal(check(pid), minute, e.carbs, e.kind, e.label, e.by, now)


@app.delete("/api/patients/{pid}/meals/{meal_id}")
def remove_meal(pid: str, meal_id: str, by: str = Query("Clinician", max_length=60)):
    if not state().store.remove_meal(check(pid), meal_id, by, int(CLOCK.minute())):
        raise HTTPException(404, "No such meal entry")
    return {"removed": meal_id}


@app.post("/api/patients/{pid}/ack")
def acknowledge(pid: str, a: Acknowledge):
    return state().store.acknowledge(check(pid), a.kind, a.by, int(CLOCK.minute()), a.snooze_minutes, a.note)


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
    return {"metrics": m, "alert_level": state().alert_cov, "cardio_threshold": state().cardio_threshold,
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
