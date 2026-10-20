"""Turn a plain words question into the twin's what if settings.

"What if he skips rice and walks after dinner for the next week?" becomes
{"swap": "roti", "walk_minutes": 15, "scope": "all", "horizon_h": 168}.

A built in phrase matcher does this offline and always runs. If ANTHROPIC_API_KEY is set, a
language model may be asked instead, only to fill the same settings (never to produce numbers or
advice); only the question text is sent, no patient data, and any failure falls back to the matcher.
The numbers always come from the twin.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

MODEL = os.environ.get("PRATIVIMB_ASK_MODEL", "claude-haiku-5-5")
FIELDS = {"walk_minutes": (0, 60), "shift_hours": (-3, 3), "sleep_hours": (3, 10), "insulin_bolus_units": (0, 20),
          "insulin_basal_units": (0, 40), "metformin_shift_hours": (-3, 3)}
SWAPS = ("none", "millet", "brown_rice", "roti", "half_portion")

_NUM = r"(\d+(?:\.\d+)?|an?|one|two|three|half an?)"
WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "half a": 0.5, "half an": 0.5}


def _n(x: str) -> float:
    x = x.strip().lower()
    return float(WORDS.get(x, x))


def match(text: str) -> dict:
    t = " " + text.lower().replace("-", " ") + " "
    req: dict = {}
    said: list[str] = []
    if re.search(r"\b(walk|walks|walking|stroll|टहल)", t):
        m = re.search(r"(\d+)\s*(?:min|minute)", t)
        req["walk_minutes"] = int(m.group(1)) if m else 15
        if re.search(r"half an hour|half hour", t):
            req["walk_minutes"] = 30
        said.append(f"walk {req['walk_minutes']} min after the meal")
    if re.search(r"\b(millet|ragi|jowar|bajra|nachni)", t):
        req["swap"] = "millet"; said.append("millets instead of white rice")
    elif re.search(r"brown rice", t):
        req["swap"] = "brown_rice"; said.append("brown rice instead of white rice")
    elif re.search(r"\b(roti|chapati|chapathi|phulka)", t) or re.search(r"\b(skip|skips|skipping|no|without|avoid)s?\s+(the\s+)?rice", t):
        req["swap"] = "roti"
        said.append("roti instead of rice" + (" (skipping rice taken as roti instead)" if "rice" in t and "roti" not in t else ""))
    elif re.search(r"\b(half|smaller|less|small)\s+(the\s+)?(portion|plate|serving|amount|meal)|eat less|half portion", t):
        req["swap"] = "half_portion"; said.append("half the portion")
    m = re.search(_NUM + r"\s*(?:hour|hr|h)s?\s+(earlier|later|sooner)", t) or re.search(r"(earlier|later|sooner)\s+by\s+" + _NUM + r"\s*(?:hour|hr|h)", t)
    if m:
        g = m.groups()
        amount, way = (g[0], g[1]) if g[0] not in ("earlier", "later", "sooner") else (g[1], g[0])
        req["shift_hours"] = _n(amount) * (1 if way == "later" else -1)
        said.append(f"meal {abs(req['shift_hours']):g} h {'later' if req['shift_hours'] > 0 else 'earlier'}")
    elif re.search(r"\b(eat|eats|dinner|lunch|meal)\b[^.]*\bearlier\b", t):
        req["shift_hours"] = -1.0; said.append("meal 1 h earlier")
    m = re.search(r"sleep[s]?\s+(?:for\s+)?" + _NUM + r"\s*(?:hour|hr|h)", t) or re.search(_NUM + r"\s*(?:hour|hr|h)s?\s+(?:of\s+)?sleep", t)
    if m:
        req["sleep_hours"] = max(3.0, min(10.0, _n(m.group(1)))); said.append(f"sleep {req['sleep_hours']:g} h")
    if re.search(r"(miss|misses|missed|skip|skips|forget|forgets|forgot)\w*\s+(his |her |the |a )?(metformin|dose|tablet|medicine)", t):
        req["missed_dose"] = True; said.append("a missed metformin dose")
    if re.search(r"night shift", t):
        req["night_shift"] = True; said.append("working a night shift")
    m = re.search(r"(\d+)\s*units?\s+(?:of\s+)?(basal|long acting|glargine|degludec|lantus)", t) or \
        re.search(r"(basal|long acting|glargine|degludec|lantus)[^\d]*(\d+)\s*units?", t)
    if m:
        units = float(m.group(1) if m.group(1).isdigit() else m.group(2))
        req["insulin_basal_units"] = min(units, 40); said.append(f"{units:g} units of long acting insulin a day")
    m = re.search(r"(\d+)\s*units?\s+(?:of\s+)?(?:rapid|mealtime|meal time|bolus|aspart|lispro|insulin)", t)
    if m and "insulin_basal_units" not in req:
        req["insulin_bolus_units"] = min(float(m.group(1)), 20); said.append(f"{m.group(1)} units of mealtime insulin")
    m = re.search(r"metformin\s+(?:at\s+)?" + _NUM + r"\s*(?:hour|hr|h)s?\s+(earlier|later)", t)
    if m:
        req["metformin_shift_hours"] = _n(m.group(1)) * (1 if m.group(2) == "later" else -1)
        said.append(f"evening metformin {abs(req['metformin_shift_hours']):g} h {m.group(2)}")
    horizon = 6
    if re.search(r"week|7 days|seven days|every day|daily", t):
        horizon = 168
    elif re.search(r"tomorrow|24 hours|whole day|all day|today", t):
        horizon = 24
    if horizon > 6 or re.search(r"every (meal|main meal)|each meal|all meals", t):
        req["scope"] = "all"
    req["horizon_h"] = horizon
    return {"request": req, "understood": said, "parser": "built in phrase matcher"}


def _clean(req: dict) -> dict:
    out = {}
    for k, (lo, hi) in FIELDS.items():
        if k in req and req[k] is not None:
            out[k] = max(lo, min(hi, float(req[k])))
            if k == "walk_minutes":
                out[k] = int(round(out[k] / 5) * 5)
    if req.get("swap") in SWAPS:
        out["swap"] = req["swap"]
    for k in ("missed_dose", "night_shift"):
        if req.get(k):
            out[k] = True
    out["horizon_h"] = req.get("horizon_h") if req.get("horizon_h") in (6, 24, 168) else 6
    out["scope"] = "all" if out["horizon_h"] > 6 or req.get("scope") == "all" else "next"
    return out


def model(text: str) -> dict | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = (
        "Convert a clinician's what if question about one patient into JSON settings for a glucose simulator. "
        "Reply with JSON only, keys optional: walk_minutes (0 to 60), swap (one of none, millet, brown_rice, roti, "
        "half_portion), shift_hours (meal time change, -3 to 3), sleep_hours (3 to 10), missed_dose (bool), "
        "night_shift (bool), insulin_bolus_units (0 to 20), insulin_basal_units (0 to 40), metformin_shift_hours "
        "(-3 to 3), horizon_h (6, 24 or 168), understood (list of short plain phrases saying what you took from the "
        "question). Leave out anything the question does not say.\n\nQuestion: " + text)
    body = json.dumps({"model": MODEL, "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            msg = json.loads(r.read())
        raw = "".join(b.get("text", "") for b in msg.get("content", []))
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        return {"request": _clean(data), "understood": [str(x) for x in data.get("understood", [])][:8], "parser": MODEL}
    except Exception:
        return None


def parse(text: str, use_model: bool = True) -> dict:
    text = text.strip()[:400]
    out = (model(text) if use_model else None) or match(text)
    out["request"] = _clean(out["request"])
    if not out["understood"]:
        out["understood"] = []
        out["unclear"] = ("No change recognised. Try for example: walk 15 minutes after dinner, millets instead of rice, "
                          "dinner an hour earlier, half the portion, sleep 7 hours, for the next week.")
    return out
