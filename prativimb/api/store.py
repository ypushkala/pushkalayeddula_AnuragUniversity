"""Clinician and patient input that the twin should know about, plus an audit trail.

* Meal entries: a meal someone tells the twin about. If its time is at or before the moment it
  was entered it counts as eaten (it joins the meal log); if later, it is a plan that replaces
  the routine slot nearby.
* Acknowledgements: "seen by Dr X, snooze for an hour". An acknowledged alert stays visible but
  drops in the ward order until the snooze ends.

Everything is keyed to the replay clock (so jumping back in time hides later entries) and is
appended to an audit log with wall clock time as well.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

from prativimb import config

STORE = config.ARTIFACT_DIR / "clinical_store.json"
AUDIT = config.ARTIFACT_DIR / "audit.jsonl"


class ClinicalStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.meals: list[dict] = []
        self.acks: list[dict] = []
        self.version = 0
        if STORE.exists():
            data = json.loads(STORE.read_text())
            self.meals, self.acks = data.get("meals", []), data.get("acks", [])

    def _save(self, action: str, record: dict) -> None:
        self.version += 1
        STORE.write_text(json.dumps({"meals": self.meals, "acks": self.acks}, indent=1))
        with AUDIT.open("a") as f:
            f.write(json.dumps({"action": action, "wall_time": datetime.now(timezone.utc).isoformat(), **record}) + "\n")

    # meals -------------------------------------------------------------------------------
    def add_meal(self, pid: str, minute: int, carbs: float, kind: str, label: str, by: str, entered: int) -> dict:
        rec = {"id": uuid.uuid4().hex[:10], "pid": pid, "minute": int(minute), "carbs": float(carbs), "kind": kind,
               "label": label, "by": by, "entered_minute": int(entered),
               "type": "logged" if minute <= entered else "planned"}
        with self.lock:
            self.meals.append(rec)
            self._save("meal_added", rec)
        return rec

    def remove_meal(self, pid: str, meal_id: str, by: str, now: int) -> bool:
        with self.lock:
            hit = [m for m in self.meals if m["id"] == meal_id and m["pid"] == pid]
            if not hit:
                return False
            self.meals = [m for m in self.meals if m["id"] != meal_id]
            self._save("meal_removed", {**hit[0], "removed_by": by, "removed_minute": int(now)})
        return True

    def meals_for(self, pid: str, now: float) -> list[dict]:
        return sorted((m for m in self.meals if m["pid"] == pid and m["entered_minute"] <= now), key=lambda m: m["minute"])

    # acknowledgements --------------------------------------------------------------------
    def acknowledge(self, pid: str, kind: str, by: str, now: int, snooze_minutes: int, note: str) -> dict:
        rec = {"id": uuid.uuid4().hex[:10], "pid": pid, "kind": kind, "by": by, "minute": int(now),
               "until": int(now + snooze_minutes), "note": note}
        with self.lock:
            self.acks.append(rec)
            self._save("alert_acknowledged", rec)
        return rec

    def active_ack(self, pid: str, kind: str, now: float) -> dict | None:
        live = [a for a in self.acks if a["pid"] == pid and a["kind"] == kind and a["minute"] <= now < a["until"]]
        return max(live, key=lambda a: a["minute"]) if live else None

    def audit(self, pid: str | None = None, limit: int = 200) -> list[dict]:
        if not AUDIT.exists():
            return []
        rows = [json.loads(line) for line in AUDIT.read_text().splitlines() if line.strip()]
        if pid:
            rows = [r for r in rows if r.get("pid") == pid]
        return rows[::-1][:limit]
