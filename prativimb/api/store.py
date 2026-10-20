"""Clinician and patient input that the twin should know about, plus an audit trail.

* Meal entries: a meal someone tells the twin about. If its time is at or before the moment it
  was entered it counts as eaten (it joins the meal log); if later, it is a plan that replaces
  the routine slot nearby. Patients can log meals from their share page.
* Acknowledgements: "seen by Dr X, snooze for an hour". An acknowledged alert stays visible but
  drops in the ward order until the snooze ends. An acknowledgement can be undone.
* Actions: what someone did about an alert (called the patient, booked a review, checked the
  patient with a fingerstick), with an outcome note.
* Plans: a change a doctor agreed with the patient (for example a walk after every main meal),
  checked against what actually happened a week later.
* Activities: a walk the patient says they did or will do. A planned walk enters the forecast; in this
  demo a walk also changes the replayed readings, using the reference simulator (see services.sync).
* Messages: what the patient replied to a care team message on their phone.
* Refits: a twin refitted on a recent week after its fit drifted.
* Consent: per data source (CGM, wearable, ABDM health records), granted or withdrawn. While
  withdrawn, the service stops using that source.

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
KEYS = ("meals", "acks", "actions", "plans", "consents", "activities", "messages", "refits")
CONSENT_SOURCES = ("cgm", "wearable", "abdm")


class ClinicalStore:
    def __init__(self, path=None, audit_path=None) -> None:
        # Resolved at run time, so tests can point the module constants at a temporary folder.
        self.path, self.audit_path = path or STORE, audit_path or AUDIT
        self.lock = threading.Lock()
        self.version = 0
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        for k in KEYS:
            setattr(self, k, data.get(k, []))

    def _save(self, action: str, record: dict) -> None:
        self.version += 1
        self.path.write_text(json.dumps({k: getattr(self, k) for k in KEYS}, indent=1))
        with self.audit_path.open("a") as f:
            f.write(json.dumps({"action": action, "wall_time": datetime.now(timezone.utc).isoformat(), **record}) + "\n")

    @staticmethod
    def _id() -> str:
        return uuid.uuid4().hex[:10]

    def _remove(self, key: str, pid: str, rid: str, action: str, by: str, now: int) -> bool:
        with self.lock:
            rows = getattr(self, key)
            hit = [r for r in rows if r["id"] == rid and r["pid"] == pid]
            if not hit:
                return False
            setattr(self, key, [r for r in rows if r["id"] != rid])
            self._save(action, {**hit[0], "removed_by": by, "removed_minute": int(now)})
        return True

    # meals -------------------------------------------------------------------------------
    def add_meal(self, pid: str, minute: int, carbs: float, kind: str, label: str, by: str, entered: int,
                 source: str = "clinician") -> dict:
        rec = {"id": self._id(), "pid": pid, "minute": int(minute), "carbs": float(carbs), "kind": kind,
               "label": label, "by": by, "entered_minute": int(entered), "source": source,
               "type": "logged" if minute <= entered else "planned"}
        with self.lock:
            self.meals.append(rec)
            self._save("meal_added", rec)
        return rec

    def remove_meal(self, pid: str, meal_id: str, by: str, now: int) -> bool:
        return self._remove("meals", pid, meal_id, "meal_removed", by, now)

    def meals_for(self, pid: str, now: float) -> list[dict]:
        return sorted((m for m in self.meals if m["pid"] == pid and m["entered_minute"] <= now), key=lambda m: m["minute"])

    # acknowledgements --------------------------------------------------------------------
    def acknowledge(self, pid: str, kind: str, by: str, now: int, snooze_minutes: int, note: str, role: str = "") -> dict:
        rec = {"id": self._id(), "pid": pid, "kind": kind, "by": by, "role": role, "minute": int(now),
               "until": int(now + snooze_minutes), "note": note}
        with self.lock:
            self.acks.append(rec)
            self._save("alert_acknowledged", rec)
        return rec

    def remove_ack(self, pid: str, ack_id: str, by: str, now: int) -> bool:
        return self._remove("acks", pid, ack_id, "acknowledgement_undone", by, now)

    def active_ack(self, pid: str, kind: str, now: float) -> dict | None:
        live = [a for a in self.acks if a["pid"] == pid and a["kind"] == kind and a["minute"] <= now < a["until"]]
        return max(live, key=lambda a: a["minute"]) if live else None

    # actions -----------------------------------------------------------------------------
    def add_action(self, pid: str, kind: str, by: str, now: int, note: str, outcome: str = "", role: str = "",
                   alert: str = "") -> dict:
        rec = {"id": self._id(), "pid": pid, "kind": kind, "by": by, "role": role, "minute": int(now),
               "note": note, "outcome": outcome, "alert": alert}
        with self.lock:
            self.actions.append(rec)
            self._save(f"action_{kind}", rec)
        return rec

    def remove_action(self, pid: str, action_id: str, by: str, now: int) -> bool:
        return self._remove("actions", pid, action_id, "action_undone", by, now)

    # plans -------------------------------------------------------------------------------
    def add_plan(self, pid: str, label: str, request: dict, by: str, now: int, predicted: dict, seeded: bool = False) -> dict:
        rec = {"id": self._id(), "pid": pid, "label": label, "request": request, "by": by, "minute": int(now),
               "predicted": predicted, "seeded": seeded}
        with self.lock:
            self.plans.append(rec)
            self._save("plan_agreed", rec)
        return rec

    def remove_plan(self, pid: str, plan_id: str, by: str, now: int) -> bool:
        return self._remove("plans", pid, plan_id, "plan_removed", by, now)

    # consent -----------------------------------------------------------------------------
    def set_consent(self, pid: str, source: str, granted: bool, by: str, now: int, role: str = "") -> dict:
        rec = {"id": self._id(), "pid": pid, "source": source, "granted": bool(granted), "by": by, "role": role,
               "minute": int(now)}
        with self.lock:
            self.consents.append(rec)
            self._save("consent_granted" if granted else "consent_withdrawn", rec)
        return rec

    def consent(self, pid: str, source: str, now: float) -> dict | None:
        """Latest consent change for this source at or before now; None means the enrolment consent stands."""
        rows = [c for c in self.consents if c["pid"] == pid and c["source"] == source and c["minute"] <= now]
        # Latest by clock time; two changes in the same minute resolve to the one made last.
        return max(enumerate(rows), key=lambda x: (x[1]["minute"], x[0]))[1] if rows else None

    def withdrawn(self, pid: str, source: str, now: float) -> dict | None:
        c = self.consent(pid, source, now)
        return c if c and not c["granted"] else None

    # activities and messages ---------------------------------------------------------------
    def add_activity(self, pid: str, kind: str, start: int, minutes: int, by: str, now: int, source: str,
                     planned_start: int | None = None) -> dict:
        rec = {"id": self._id(), "pid": pid, "kind": kind, "start": int(start), "minutes": int(minutes), "by": by,
               "planned_start": int(start if planned_start is None else planned_start),
               "entered_minute": int(now), "minute": int(now), "source": source}
        with self.lock:
            self.activities.append(rec)
            self._save("activity_added", rec)
        return rec

    def remove_activity(self, pid: str, aid: str, by: str, now: int) -> bool:
        return self._remove("activities", pid, aid, "activity_removed", by, now)

    def activities_for(self, pid: str, now: float) -> list[dict]:
        return sorted((a for a in self.activities if a["pid"] == pid and a["entered_minute"] <= now), key=lambda a: a["start"])

    def add_message(self, pid: str, sender: str, key: str, text: str, now: int, by: str, params: dict | None = None) -> dict:
        rec = {"id": self._id(), "pid": pid, "from": sender, "key": key, "text": text, "minute": int(now), "by": by,
               "params": params or {}}
        with self.lock:
            self.messages.append(rec)
            self._save("message", rec)
        return rec

    def remove_message(self, pid: str, mid: str, by: str, now: int) -> bool:
        return self._remove("messages", pid, mid, "message_removed", by, now)

    def messages_for(self, pid: str, now: float) -> list[dict]:
        return [m for m in self.messages if m["pid"] == pid and m["minute"] <= now]

    # refits ------------------------------------------------------------------------------
    def add_refit(self, pid: str, theta: list[float], by: str, now: int, report: dict) -> dict:
        rec = {"id": self._id(), "pid": pid, "theta": [float(x) for x in theta], "by": by, "minute": int(now), **report}
        with self.lock:
            self.refits.append(rec)
            self._save("twin_refitted", rec)
        return rec

    def remove_refit(self, pid: str, rid: str, by: str, now: int) -> bool:
        return self._remove("refits", pid, rid, "twin_refit_undone", by, now)

    def refit(self, pid: str, now: float) -> dict | None:
        rows = [r for r in self.refits if r["pid"] == pid and r["minute"] <= now]
        return max(rows, key=lambda r: r["minute"]) if rows else None

    # reading back ------------------------------------------------------------------------
    def between(self, start: float, end: float, pid: str | None = None) -> dict[str, list[dict]]:
        """Everything entered in (start, end], by kind, for handover and follow up."""
        out = {}
        for k in KEYS:
            t = "entered_minute" if k in ("meals", "activities") else "minute"
            out[k] = sorted((r for r in getattr(self, k) if start < r[t] <= end and (pid is None or r["pid"] == pid)),
                            key=lambda r: r[t])
        return out

    def audit(self, pid: str | None = None, limit: int = 200) -> list[dict]:
        if not self.audit_path.exists():
            return []
        rows = [json.loads(line) for line in self.audit_path.read_text().splitlines() if line.strip()]
        if pid:
            rows = [r for r in rows if r.get("pid") == pid]
        return rows[::-1][:limit]
