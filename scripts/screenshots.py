"""Capture every dashboard screen with Playwright into docs/screenshots/.

Needs the API on :8000 and the dashboard on :5173 (make api, make web). The replay clock is
set through the API for each shot so the images are reproducible.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
API = "http://127.0.0.1:8000"
WEB = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"

SHOTS = [
    # name, path, clock, theme, wait selector, optional click text
    ("01_ward", "/", "2026-03-15T19:45:00+05:30", "light", "table.ward tbody tr", None),
    ("02_twin_ramesh", "/patient/PTV-0001", "2026-03-15T19:45:00+05:30", "light", ".b-title", None),
    ("03_whatif_ramesh", "/patient/PTV-0001/try", "2026-03-15T19:45:00+05:30", "light", ".lever-card", None),
    ("04_twin_fatima_iftar", "/patient/PTV-0002", "2026-03-15T18:00:00+05:30", "light", ".b-title", None),
    ("05_cardio_suresh", "/patient/PTV-0003?heart=26", "2026-03-15T19:45:00+05:30", "light", "table.heat", None),
    ("06_note_ramesh", "/note/PTV-0001", "2026-03-15T19:45:00+05:30", "light", "article.note", None),
    ("07_model_card", "/model", "2026-03-15T19:45:00+05:30", "light", "table.data", None),
    ("08_ward_dark", "/", "2026-03-15T19:45:00+05:30", "dark", "table.ward tbody tr", None),
    ("09_twin_ramesh_dark", "/patient/PTV-0001", "2026-03-15T19:45:00+05:30", "dark", ".b-title", None),
    ("10_whatif_24h_levers", "/patient/PTV-0001/try", "2026-03-15T19:45:00+05:30", "light", ".lever-card", "Next 24 hours"),
    ("14_health_record", "/patient/PTV-0001/record", "2026-03-15T19:45:00+05:30", "light", ".record", None),
    ("11_patient_view_hindi", "/share/PTV-0001", "2026-03-15T19:45:00+05:30", "light", ".share h1", "lang:hi"),
    ("12_phone_ward", "/", "2026-03-15T19:45:00+05:30", "light", "table.ward tbody tr", "phone"),
    ("13_phone_twin", "/patient/PTV-0001", "2026-03-15T19:45:00+05:30", "light", ".b-title", "phone"),
    ("15_earlier_alerts", "/patient/PTV-0001/record", "2026-03-15T19:45:00+05:30", "light", "table.episodes", None),
    ("16_week_plan", "/patient/PTV-0001/try", "2026-03-15T19:45:00+05:30", "light", ".plans", "Next 7 days"),
    ("17_handover", "/handover", "2026-03-15T19:45:00+05:30", "light", ".handover h1", "seed"),
    ("18_digest", "/digest", "2026-03-15T19:45:00+05:30", "light", ".digest-nums", None),
    ("19_first_week", "/patient/PTV-0001", "2026-02-17T19:45:00+05:30", "light", ".b-title", None),
    ("20_heart_banner", "/patient/PTV-0151?heart=", "2026-03-15T19:45:00+05:30", "light", "table.heat", None),
    ("21_signin", "/signin", "2026-03-15T19:45:00+05:30", "light", "fieldset.roles", "signedout"),
]


SESSION = "localStorage.setItem('prativimb-session', JSON.stringify({role: 'doctor', name: 'Dr Rao'}));" \
          "localStorage.setItem('prativimb-hints', JSON.stringify(['banner', 'ward', 'difference']));"


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", "X-Prativimb-Role": "doctor", "X-Prativimb-User": "Dr%20Rao"})
    return json.loads(urllib.request.urlopen(req).read())


def set_clock(at: str) -> None:
    req = urllib.request.Request(f"{API}/api/clock", data=json.dumps({"at": at, "paused": True}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req).read()


def main(only: list[str] | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, path, at, theme, sel, click in SHOTS:
            if only and name not in only:
                continue
            set_clock(at)
            phone = click == "phone"
            ctx = browser.new_context(viewport={"width": 390, "height": 844} if phone else {"width": 1500, "height": 960},
                                      device_scale_factor=2 if phone else 1.5, is_mobile=phone, color_scheme=theme)
            page = ctx.new_page()
            page.add_init_script(f"localStorage.setItem('prativimb-theme', '{theme}');" + ("" if click == "signedout" else SESSION))
            undo = []
            if click == "seed":
                # A short shift's worth of actions so the handover has something to show; removed again after the shot.
                a = call("POST", "/api/patients/PTV-0001/ack", {"kind": "spike", "snooze_minutes": 60, "note": "Discussed a walk after dinner"})
                b = call("POST", "/api/patients/PTV-0159/actions", {"kind": "check", "outcome": "Fingerstick normal, probably the sensor", "alert": "low"})
                c = call("POST", "/api/patients/PTV-0151/actions", {"kind": "call", "outcome": "Spoke to the patient, no symptoms", "alert": "cardio"})
                undo = [f"/api/patients/PTV-0001/ack/{a['id']}", f"/api/patients/PTV-0159/actions/{b['id']}", f"/api/patients/PTV-0151/actions/{c['id']}"]
            page.goto(WEB + path, wait_until="load")
            page.wait_for_selector(sel, timeout=90000)
            page.wait_for_function("!document.body.innerText.includes('Replaying the last 6 hours')", timeout=60000)
            page.wait_for_function("!document.querySelector('[aria-busy=true]')", timeout=60000)
            page.wait_for_load_state("networkidle")
            if click and click.startswith("lang:"):
                page.select_option(".share-tools select", click[5:])
                page.wait_for_timeout(800)
            elif click and click not in ("phone", "seed", "signedout"):
                page.get_by_text(click, exact=True).click()
                page.wait_for_timeout(4000)
                page.wait_for_load_state("networkidle")
                page.wait_for_function("!document.querySelector('[aria-busy=true]')", timeout=60000)
            page.wait_for_timeout(1200)
            viewport_only = name.startswith(("01", "03", "08", "12", "13", "15"))
            if not viewport_only:
                page.add_style_tag(content=".demobar { position: static; } body { padding-bottom: 0; }")
                page.add_style_tag(content=".masthead { position: static; }")
                page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=not viewport_only)
            for u in undo:
                call("DELETE", u)
            print("saved", name)
            ctx.close()
        browser.close()
    set_clock("2026-03-15T19:45:00+05:30")


if __name__ == "__main__":
    main(sys.argv[2:] or None)
