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
    ("02_twin_ramesh", "/patient/PTV-0001", "2026-03-15T19:45:00+05:30", "light", ".factors", None),
    ("03_whatif_ramesh", "/patient/PTV-0001/whatif", "2026-03-15T19:45:00+05:30", "light", "table.compare", "Walk and millets"),
    ("04_twin_fatima_iftar", "/patient/PTV-0002", "2026-03-15T18:00:00+05:30", "light", ".card", None),
    ("05_cardio_suresh", "/patient/PTV-0003/cardio?end=26", "2026-03-15T19:45:00+05:30", "light", "table.heat", None),
    ("06_note_ramesh", "/patient/PTV-0001/note", "2026-03-15T19:45:00+05:30", "light", "article.note", None),
    ("07_model_card", "/model", "2026-03-15T19:45:00+05:30", "light", "table.data", None),
    ("08_ward_dark", "/", "2026-03-15T19:45:00+05:30", "dark", "table.ward tbody tr", None),
    ("09_twin_ramesh_dark", "/patient/PTV-0001", "2026-03-15T19:45:00+05:30", "dark", ".factors", None),
]


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
            ctx = browser.new_context(viewport={"width": 1500, "height": 960}, device_scale_factor=1.5,
                                      color_scheme=theme)
            page = ctx.new_page()
            page.add_init_script(f"localStorage.setItem('prativimb-theme', '{theme}')")
            page.goto(WEB + path, wait_until="load")
            page.wait_for_selector(sel, timeout=30000)
            page.wait_for_function("!document.body.innerText.includes('Replaying the last 6 hours')", timeout=60000)
            if click:
                page.get_by_text(click, exact=True).click()
                page.wait_for_timeout(1500)
            page.wait_for_timeout(1200)
            viewport_only = name.startswith(("01", "08"))
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=not viewport_only)
            print("saved", name)
            ctx.close()
        browser.close()
    set_clock("2026-03-15T19:45:00+05:30")


if __name__ == "__main__":
    main(sys.argv[2:] or None)
