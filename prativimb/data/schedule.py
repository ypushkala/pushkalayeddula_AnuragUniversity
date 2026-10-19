"""Turns a patient's routine into 30 days of minute level behaviour.

Outputs minute arrays (steps, sleep stage, carbohydrate, metformin) used by the
physiology simulator, plus the event tables that end up in the device exports and
the EHR timeline (meals, logged meals, medication doses, sleep segments, nightly
summaries) and a per day table with the latent strain that drives cardiovascular
deterioration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from prativimb import config
from prativimb.data.cohort import MEAL_TYPES, Patient

T = config.N_DAYS * 1440
WAKE, IN_BED_AWAKE, LIGHT, DEEP, REM = -1, 0, 1, 2, 3
STAGE_NAMES = {IN_BED_AWAKE: "awake", LIGHT: "core", DEEP: "deep", REM: "rem"}


# The demo day (15 Mar) is pinned for two heroes so the story does not depend on random draws.
DEMO_DAY_MEALS = {
    "ramesh": [(1 * 60 + 55, 30.0, "tea_snack", "Night snack"), (7 * 60 + 50, 40.0, "bread_tea", "Breakfast (post shift)"),
               (13 * 60 + 20, 55.0, "rice_meal", "Lunch"), (17 * 60 + 15, 12.0, "tea_snack", "Tea"),
               (20 * 60 + 30, 108.0, "rice_meal", "Dinner")],
    "fatima": [(4 * 60 + 45, 55.0, "suhoor", "Suhoor"), (18 * 60 + 29, 90.0, "iftar", "Iftar"),
               (21 * 60 + 30, 65.0, "rice_meal", "Dinner")],
}


@dataclass
class Schedule:
    steps: np.ndarray
    stage: np.ndarray
    carbs: np.ndarray
    absf: np.ndarray
    metformin: np.ndarray
    night_work: np.ndarray
    meals: list
    meal_log: list
    doses: list
    sleep_segments: list
    nights: list
    days: list
    gap: tuple[int, int] | None = None


def day_type(p: Patient, d: int) -> str:
    dt = config.START.date() + timedelta(days=d)
    lf = p.lifestyle
    if lf["observes_ramadan"] and dt >= config.RAMADAN_FIRST_FAST:
        return "ramadan"
    if lf["observes_hindu_fasts"] and (dt == config.MAHA_SHIVARATRI or dt in config.EKADASHI):
        return "hindu_fast"
    if lf["celebrates_holi"] and dt == config.HOLI:
        return "holi"
    return "normal"


def works_night(p: Patient, d: int) -> bool:
    # Night shift workers have Thursday night off.
    return p.night_shift and (config.START.date() + timedelta(days=d)).weekday() != 3


def strain_series(p: Patient, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Latent autonomic strain per day and a fever indicator.

    Strain is an AR(1) process plus a ramp in the week before a cardiovascular event,
    illness episodes (confounders that look similar but are not followed by an event)
    and a recovery tail after an event.
    """
    D = config.N_DAYS
    a = np.zeros(D)
    fever = np.zeros(D)
    prev = 0.0
    for d in range(D):
        prev = 0.55 * prev + rng.normal(0, 0.22)
        a[d] = prev
    E = p.cardio.get("event_day")
    if E is not None:
        sev = p.cardio["event_severity"]
        for d in range(max(0, E - 7), E + 1):
            a[d] += sev * ((d - (E - 7)) / 7) ** 1.4
        for d in range(E + 1, D):
            a[d] += 0.6 * sev * np.exp(-(d - E) / 3)
    if p.hero == "ramesh":
        a[20:] = np.minimum(a[20:], 0.0) - 0.1  # story patient: no cardiac prodrome
    for d0, length, amp in p.cardio.get("illness", []):
        for d in range(d0, min(D, d0 + length)):
            bump = amp * np.sin(np.pi * (d - d0 + 0.5) / length)
            a[d] += bump
            fever[d] = bump
    return a, fever


def hypnogram(rng, start: int, dur: int, deep_frac: float, rem_frac: float, n_wake: int) -> list[tuple[int, int, int]]:
    cycles = max(2, int(round(dur / 92)))
    L = dur / cycles
    w_deep = np.exp(-0.7 * np.arange(cycles))
    w_rem = 0.4 + 0.6 * np.arange(cycles) / max(cycles - 1, 1)
    deep = deep_frac * dur * w_deep / w_deep.sum()
    rem = rem_frac * dur * w_rem / w_rem.sum()
    segs = []
    t = float(start)
    for i in range(cycles):
        light = max(L - deep[i] - rem[i], 8)
        for stage, length in ((LIGHT, light * 0.55), (DEEP, deep[i]), (LIGHT, light * 0.45), (REM, rem[i])):
            if length >= 1:
                segs.append([int(round(t)), int(round(t + length)), stage])
                t += length
    # Awakenings overwrite short stretches of sleep.
    end = segs[-1][1]
    for _ in range(n_wake):
        w0 = int(rng.integers(start + 20, max(start + 21, end - 10)))
        segs.append([w0, w0 + int(rng.integers(2, 11)), IN_BED_AWAKE])
    return segs


def _paint(arr: np.ndarray, segs: list) -> None:
    # Later segments win, so awakenings appended last overwrite sleep stages.
    for s, e, v in segs:
        s, e = max(0, s), min(T, e)
        if e > s:
            arr[s:e] = v


def _segments_from_array(stage: np.ndarray, lo: int, hi: int) -> list[tuple[int, int, int]]:
    out = []
    seg = stage[lo:hi]
    if len(seg) == 0:
        return out
    change = np.flatnonzero(np.diff(seg)) + 1
    bounds = np.concatenate([[0], change, [len(seg)]])
    for a, b in zip(bounds[:-1], bounds[1:]):
        if seg[a] >= 0:
            out.append((lo + int(a), lo + int(b), int(seg[a])))
    return out


def build(p: Patient, rng: np.random.Generator) -> Schedule:
    D = config.N_DAYS
    lf = p.lifestyle
    steps = np.zeros(T, np.float32)
    stage = np.full(T, WAKE, np.int8)
    carbs = np.zeros(T, np.float32)
    absf = np.zeros(T, np.float32)
    metformin = np.zeros(T, np.float32)
    night_work = np.zeros(T, bool)
    meals, meal_log, doses, sleep_episodes, days = [], [], [], [], []
    strain, fever = strain_series(p, rng)

    hero_sleep = {}
    if p.hero == "ramesh":
        hero_sleep = {27: 4.6, 28: 4.8, 29: 4.7}
    if p.hero == "fatima":
        hero_sleep = {29: 6.1}

    # Sleep first: everything else depends on when the person is awake.
    for d in range(D):
        day0 = d * 1440
        dtype = day_type(p, d)
        weekday = (config.START.date() + timedelta(days=d)).weekday()
        a = strain[d]
        if works_night(p, d):
            night_work[day0 + 22 * 60: min(T, day0 + 31 * 60)] = True
            onset = day0 + 24 * 60 + 8 * 60 + 30 + int(rng.normal(0, 20))  # next morning after the shift
            hours = rng.normal(lf["sleep_hours"], lf["sleep_sd"])
        else:
            bed = lf["bedtime"] + rng.normal(0, 0.45) + (0.8 if weekday in (4, 5) else 0)
            if dtype == "ramadan":
                bed += 0.4
            if config.START.date() + timedelta(days=d) == config.HOLI - timedelta(days=1):
                bed += 1.0
            onset = day0 + int(bed * 60)
            hours = rng.normal(lf["sleep_hours"] if not p.night_shift else 7.0, lf["sleep_sd"])
        hours -= 0.35 * max(a, 0)
        wake_day = (onset + int(hours * 60) + 30) // 1440
        if wake_day in hero_sleep:
            hours = hero_sleep[wake_day]
        hours = float(np.clip(hours, 3.2, 9.5))
        age_deep = np.clip(0.21 - 0.0022 * (p.age - 30), 0.07, 0.22)
        deep_frac = float(age_deep * np.exp(-0.28 * max(a, 0)) * rng.lognormal(0, 0.12))
        rem_frac = float(np.clip(rng.normal(0.21, 0.025) - 0.02 * max(a, 0), 0.1, 0.28))
        n_wake = int(rng.poisson(2.2 + 1.6 * max(a, 0) + (1.0 if p.night_shift and works_night(p, d) else 0)))
        dur = int(hours * 60 + 6 * n_wake + 8)  # time in bed, so the asleep total lands near `hours`
        segs = hypnogram(rng, onset, dur, deep_frac, rem_frac, n_wake)
        if dtype == "ramadan" and not p.night_shift:
            # Suhoor break: awake 04:15 to 05:10 on the following morning.
            nxt = (d + 1) * 1440
            segs.append([nxt + 4 * 60 + 15, nxt + 5 * 60 + 10, WAKE])
        sleep_episodes.append((onset, onset + dur, wake_day))
        _paint(stage, segs)

    # Cardiovascular event: hospital attendance, device removed.
    E = p.cardio.get("event_day")
    event_minute = None
    gap = (0, 0)
    if E is not None:
        event_minute = E * 1440 + int(p.cardio["event_hour"] * 60)
        gap = (event_minute + 20, event_minute + int(rng.integers(20, 30)) * 60)

    for d in range(D):
        day0 = d * 1440
        dtype = day_type(p, d)
        weekday = (config.START.date() + timedelta(days=d)).weekday()
        if dtype == "ramadan":
            slots = p.routine["ramadan"]
        elif dtype == "hindu_fast":
            slots = p.routine["hindu_fast"]
        else:
            slots = p.routine["normal"]
        todays = []
        for s in slots:
            if s.name == "Night snack" and not works_night(p, (d - 1) % D):
                continue
            if rng.random() < s.skip_prob:
                continue
            t = s.minute + rng.normal(0, s.jitter)
            if weekday in (5, 6) and s.name == "Breakfast":
                t += 40
            if s.name == "Iftar":
                t = s.minute + 0.45 * (d - config.day_index(config.RAMADAN_FIRST_FAST))  # sunset drifts later
            g = s.carbs * rng.lognormal(0, 0.16)
            if weekday == 6 and s.name.startswith("Lunch"):
                g *= 1.15
            todays.append((day0 + int(round(t)), g, s.kind, s.name))
        if d == config.N_DAYS - 1 and p.hero in DEMO_DAY_MEALS:
            todays = [(day0 + m, g, kind, name) for m, g, kind, name in DEMO_DAY_MEALS[p.hero]]
        if dtype == "holi":
            todays += [(day0 + 11 * 60 + 30, 45.0, "sweets", "Holi sweets"), (day0 + 16 * 60 + 30, 40.0, "sweets", "Holi sweets")]
        if dtype == "normal" and rng.random() < 0.2:
            todays.append((day0 + int(rng.choice([11 * 60, 16 * 60 + 15])), float(rng.uniform(18, 35)), "tea_snack", "Snack"))
        for m, g, kind, name in todays:
            if not (0 <= m < T) or gap[0] <= m < gap[1]:
                continue
            g = round(float(min(g, 140.0)), 1)
            carbs[m] += g
            absf[m] = MEAL_TYPES[kind][1]
            meals.append((m, g, kind, name))
            if rng.random() < lf["meal_log_p"]:
                est = 5 * round(g * rng.lognormal(0, lf["carb_err_sd"]) / 5)
                meal_log.append((5 * round((m + rng.normal(0, 4)) / 5), float(max(est, 5)), kind, MEAL_TYPES[kind][0]))

        # Medications: scheduled doses anchored to the meal they are taken with.
        anchor = {}
        for m, g, kind, name in todays:
            n = name.lower()
            if "breakfast" in n or "suhoor" in n:
                anchor.setdefault("breakfast", m)
            if n.startswith("dinner") or "iftar" in n or "fasting dinner" in n:
                anchor["dinner"] = m if "iftar" not in n else anchor.get("dinner", m)
        if "breakfast" not in anchor:
            anchor["breakfast"] = day0 + 8 * 60 + 30
        if "dinner" not in anchor:
            anchor["dinner"] = day0 + 21 * 60
        for med in p.meds:
            for slot in med["times"]:
                m = anchor[slot] + 5
                if not (0 <= m < T) or gap[0] <= m < gap[1]:
                    continue
                adherence = lf["adherence"]
                if p.hero == "ramesh" and d == 29 and med["key"] == "metformin" and slot == "breakfast":
                    taken = False  # missed his post shift dose on the demo day
                else:
                    taken = bool(rng.random() < adherence)
                doses.append((m, med["key"], med["dose"], taken))
                if taken and med["key"] == "metformin":
                    metformin[m] += 1.0 if med["dose"].startswith("1000") else 0.7

        # Steps. Asleep minutes stay at zero.
        awake = stage[day0: day0 + 1440] == WAKE
        target = lf["step_level"] * rng.lognormal(0, 0.22) * np.exp(-0.25 * max(strain[d], 0))
        if dtype in ("ramadan", "hindu_fast"):
            target *= 0.8
        day_steps = np.zeros(1440, np.float32)

        def bout(start_min: int, length: int, cadence: float) -> None:
            s0, e0 = max(0, start_min), min(1440, start_min + length)
            if e0 > s0:
                day_steps[s0:e0] = np.maximum(day_steps[s0:e0], rng.normal(cadence, 6, e0 - s0).clip(40, 135))

        if lf["morning_walk"] and rng.random() < 0.75 and dtype != "ramadan":
            bout(int(rng.normal(6.5 * 60, 20)), int(rng.integers(20, 40)), 108)
        for m, g, kind, name in todays:
            if m // 1440 == d and rng.random() < lf["post_meal_walk_p"]:
                bout(m - day0 + int(rng.integers(10, 25)), int(rng.integers(10, 20)), 100)
        if works_night(p, d):
            for h in range(23, 30):
                bout((h * 60 + int(rng.integers(0, 40))) - (1440 if h >= 24 else 0), int(rng.integers(5, 12)), 92)
        if p.hero == "fatima" and dtype == "ramadan":
            bout(15 * 60 + 20, 40, 72)
            bout(16 * 60 + 40, 45, 104)  # walk to the market before iftar
        if p.occupation not in ("Retired", "Homemaker", "Retired bank officer"):
            bout(int(rng.normal(9 * 60, 20)), 12, 98)
            bout(int(rng.normal(18 * 60 + 15, 20)), 12, 98)
        tries = 0
        while day_steps.sum() < target and tries < 400:
            tries += 1
            mm = int(rng.integers(0, 1440))
            if awake[mm]:
                bout(mm, int(rng.integers(1, 7)), float(rng.uniform(55, 100)))
        day_steps[~awake] = 0
        steps[day0: day0 + 1440] = day_steps

        days.append({"day": d, "day_type": dtype, "strain": float(strain[d]), "fever": float(fever[d]),
                     "works_night": works_night(p, d), "step_target": float(target)})

    if gap[1] > gap[0]:
        steps[gap[0]:gap[1]] = 0
        stage[gap[0]:gap[1]] = WAKE

    # Nightly summaries from the painted stage array, dated by the day the person woke.
    # A shift worker can have two episodes ending on the same day; they are combined.
    by_night: dict[int, dict] = {}
    sleep_segments = []
    for onset, end, _ in sleep_episodes:
        lo, hi = max(0, onset - 5), min(T, end + 70)
        segs = _segments_from_array(stage, lo, hi)
        if not segs or (gap[0] < hi and gap[1] > lo):
            continue
        wake_day = segs[-1][1] // 1440
        if wake_day >= config.N_DAYS:
            continue
        sleep_segments += segs
        n = by_night.setdefault(wake_day, {"night": int(wake_day), "bed_minute": segs[0][0], "wake_minute": segs[-1][1],
                                           LIGHT: 0, DEEP: 0, REM: 0, IN_BED_AWAKE: 0, "awakenings": 0, "in_bed": 0})
        for a, b, v in segs:
            n[v] += b - a
        n["awakenings"] += sum(1 for a, b, v in segs if v == IN_BED_AWAKE)
        n["in_bed"] += segs[-1][1] - segs[0][0]
        n["bed_minute"] = min(n["bed_minute"], segs[0][0])
        n["wake_minute"] = max(n["wake_minute"], segs[-1][1])
    nights = []
    for d in sorted(by_night):
        n = by_night[d]
        asleep = n[LIGHT] + n[DEEP] + n[REM]
        nights.append({
            "night": n["night"], "bed_minute": n["bed_minute"], "wake_minute": n["wake_minute"],
            "total_sleep_min": asleep, "deep_min": n[DEEP], "rem_min": n[REM], "core_min": n[LIGHT],
            "awake_min": n[IN_BED_AWAKE], "awakenings": n["awakenings"],
            "efficiency": round(asleep / max(n["in_bed"], 1), 3),
        })

    return Schedule(steps, stage, carbs, absf, metformin, night_work, meals, meal_log, doses,
                    sleep_segments, nights, days, gap if gap[1] > gap[0] else None)


def sensitivity_multiplier(p: Patient, sched: Schedule, rng: np.random.Generator) -> np.ndarray:
    """Per day insulin sensitivity multiplier: sleep debt over three nights, strain, and day to day noise."""
    D = config.N_DAYS
    hours = np.full(D, p.lifestyle["sleep_hours"], float)
    for n in sched.nights:
        hours[n["night"]] = n["total_sleep_min"] / 60
    mult = np.ones(D)
    for d in range(D):
        debt3 = sum(max(0.0, 7.0 - hours[k]) for k in range(max(0, d - 2), d + 1))
        strain = sched.days[d]["strain"]
        mult[d] = np.clip(1 - 0.035 * debt3, 0.72, 1.05) * np.exp(-0.08 * max(strain, 0)) * rng.lognormal(0, p.physio["day_sd"])
    return mult
