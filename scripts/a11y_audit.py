"""Automated accessibility audit (axe-core, WCAG 2.1 A and AA rules) of every screen, light and dark.

Needs the API on :8000 serving the built dashboard (make serve). Exits non zero on any violation.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AXE = ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
WEB = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PAGES = [("/", "table.ward tbody tr.row"), ("/patient/PTV-0001", ".b-title"), ("/patient/PTV-0001/try", ".lever-card"),
         ("/patient/PTV-0001/record", "table.episodes"), ("/handover", ".handover h1"), ("/digest", ".digest-nums"),
         ("/patient/PTV-0003?heart=26", "table.heat"), ("/note/PTV-0001", "article.note"), ("/model", "table.data"),
         ("/share/PTV-0001", ".share h1")]


SESSION = "localStorage.setItem('prativimb-session', JSON.stringify({role: 'doctor', name: 'Dr Rao'}));" \
          "localStorage.setItem('prativimb-hints', JSON.stringify(['banner', 'ward', 'difference']));"


def main() -> int:
    req = urllib.request.Request(f"{WEB}/api/clock", data=json.dumps({"at": "2026-03-15T19:45:00+05:30", "paused": True}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req).read()
    total = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme=theme)
            page = ctx.new_page()
            page.add_init_script(f"localStorage.setItem('prativimb-theme', '{theme}');" + SESSION)
            for path, sel in PAGES + [("/signin", "fieldset.roles")]:
                page.goto(WEB + path, wait_until="load")
                page.wait_for_selector(sel, timeout=90000)
                page.wait_for_timeout(1200)
                page.add_script_tag(path=str(AXE))
                res = page.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag',
                    values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}})).violations.map(v => ({id: v.id,
                    impact: v.impact, help: v.help, n: v.nodes.length, target: v.nodes.slice(0, 3).map(x => x.target.join(' '))}))""")
                total += len(res)
                status = "clean" if not res else f"{len(res)} violation types"
                print(f"{theme:5s} {path:28s} {status}")
                for v in res:
                    print(f"      {v['impact']:8s} {v['id']}: {v['help']} ({v['n']} nodes) e.g. {v['target']}")
            ctx.close()
        browser.close()
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
