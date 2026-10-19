"""Synthetic cohort: demographics, EHR content, lifestyle routine and hidden physiology.

Everything here is fictional. Names are random combinations of common given and family
names; any resemblance to a real person is coincidental. Distributions are loosely
informed by Indian population studies (ICMR-INDIAB for diabetes prevalence, NFHS-5 for
religion and region mix, South Asian allele frequencies from gnomAD for the markers), but
the cohort is enriched for diabetes because it represents a diabetes clinic panel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from prativimb import config

REGIONS = {
    "north": ["Delhi", "Lucknow", "Jaipur", "Chandigarh", "Kanpur"],
    "west": ["Mumbai", "Pune", "Ahmedabad", "Nagpur", "Surat"],
    "south": ["Chennai", "Bengaluru", "Hyderabad", "Kochi", "Coimbatore", "Visakhapatnam"],
    "east": ["Kolkata", "Bhubaneswar", "Patna", "Guwahati"],
}
STATE_OF = {
    "Delhi": "Delhi", "Lucknow": "Uttar Pradesh", "Jaipur": "Rajasthan", "Chandigarh": "Chandigarh",
    "Kanpur": "Uttar Pradesh", "Mumbai": "Maharashtra", "Pune": "Maharashtra", "Ahmedabad": "Gujarat",
    "Nagpur": "Maharashtra", "Surat": "Gujarat", "Chennai": "Tamil Nadu", "Bengaluru": "Karnataka",
    "Hyderabad": "Telangana", "Kochi": "Kerala", "Coimbatore": "Tamil Nadu",
    "Visakhapatnam": "Andhra Pradesh", "Kolkata": "West Bengal", "Bhubaneswar": "Odisha",
    "Patna": "Bihar", "Guwahati": "Assam",
}

GIVEN = {
    ("hindu", "male"): ["Amit", "Rajesh", "Vijay", "Anil", "Sunil", "Prakash", "Manoj", "Sanjay", "Ravi",
                        "Arun", "Deepak", "Ashok", "Mahesh", "Ganesh", "Srinivas", "Venkatesh", "Karthik",
                        "Harish", "Naveen", "Prasad", "Dinesh", "Mukesh", "Rakesh", "Vinod", "Ajay", "Gopal",
                        "Kishore", "Mohan", "Subhash", "Narayan"],
    ("hindu", "female"): ["Sunita", "Anita", "Kavita", "Priya", "Lakshmi", "Meena", "Geeta", "Rekha", "Usha",
                          "Padma", "Shobha", "Asha", "Radha", "Savitri", "Vandana", "Deepa", "Jyoti", "Neha",
                          "Pooja", "Shanti", "Kamala", "Saroja", "Vijaya", "Lata", "Nirmala", "Bharati"],
    ("muslim", "male"): ["Imran", "Salim", "Javed", "Arif", "Faisal", "Rashid", "Anwar", "Irfan", "Nadeem",
                         "Shahid", "Aslam", "Zubair", "Iqbal", "Tariq"],
    ("muslim", "female"): ["Ayesha", "Nasreen", "Shabana", "Rukhsana", "Zainab", "Farzana", "Salma",
                           "Rehana", "Yasmin", "Sana", "Nazia", "Shazia"],
    ("christian", "male"): ["Joseph", "Thomas", "George", "Mathew", "Paul", "Francis", "Anthony"],
    ("christian", "female"): ["Mary", "Elizabeth", "Annie", "Grace", "Susan", "Lilly", "Teresa"],
    ("sikh", "male"): ["Gurpreet", "Harpreet", "Manjit", "Jaspreet", "Baljit", "Kulwant"],
    ("sikh", "female"): ["Simran", "Amrit", "Harleen", "Manpreet", "Navneet"],
}
FAMILY = {
    "north": ["Sharma", "Verma", "Gupta", "Yadav", "Mishra", "Pandey", "Chauhan", "Saxena", "Agarwal", "Tiwari"],
    "west": ["Patil", "Joshi", "Deshpande", "Kulkarni", "Shah", "Patel", "Desai", "Jadhav", "Pawar", "Mehta"],
    "south": ["Reddy", "Naidu", "Rao", "Iyer", "Nair", "Menon", "Pillai", "Krishnan", "Gowda", "Shetty"],
    "east": ["Banerjee", "Chatterjee", "Das", "Ghosh", "Mukherjee", "Bose", "Sen", "Mohanty", "Sahu", "Dutta"],
    "muslim": ["Shaikh", "Khan", "Ansari", "Qureshi", "Siddiqui", "Syed", "Pathan", "Mirza"],
    "christian": ["D'Souza", "Fernandes", "Varghese", "Pereira", "Rodrigues", "Kurian"],
    "sikh": ["Gill", "Sandhu", "Dhillon", "Grewal", "Bajwa"],
}
OCCUPATIONS_DAY = ["Teacher", "Shopkeeper", "Accountant", "Homemaker", "Software engineer", "Clerk",
                   "Driver", "Retired", "Bank officer", "Tailor", "Sales executive", "Electrician"]
OCCUPATIONS_NIGHT = ["Security supervisor", "Call centre agent", "Nurse", "Taxi driver", "Factory operator"]

# Meal absorption speed relative to a mixed meal (1.0). Faster foods peak earlier and higher.
MEAL_TYPES = {
    "idli_dosa": ("Idli, sambar, chutney", 1.10),
    "poha_upma": ("Poha or upma with tea", 1.05),
    "paratha": ("Paratha with curd", 0.85),
    "bread_tea": ("Bread, egg and sweet tea", 1.10),
    "rice_meal": ("Rice, dal, sabzi", 1.05),
    "roti_meal": ("Roti, dal, sabzi", 0.90),
    "biryani": ("Biryani with raita", 0.95),
    "tea_snack": ("Tea with biscuits", 1.20),
    "suhoor": ("Suhoor: roti, egg, milk", 0.85),
    "iftar": ("Iftar: dates, fruit, sherbet, pakora", 1.30),
    "sabudana": ("Sabudana khichdi (fasting meal)", 1.15),
    "fruit": ("Fruit and milk", 1.00),
    "sweets": ("Festival sweets (gujiya, thandai)", 1.20),
    "millet_meal": ("Millet (ragi or jowar) meal", 0.65),
}

ICD10 = {
    "t2d": ("E11.9", "Type 2 diabetes mellitus without complications"),
    "prediabetes": ("R73.03", "Prediabetes"),
    "hypertension": ("I10", "Essential (primary) hypertension"),
    "dyslipidemia": ("E78.5", "Hyperlipidaemia, unspecified"),
    "obesity": ("E66.9", "Obesity, unspecified"),
    "fh_cad": ("Z82.49", "Family history of ischaemic heart disease"),
    "shift_work": ("G47.26", "Circadian rhythm sleep disorder, shift work type"),
    "tobacco": ("F17.210", "Nicotine dependence, cigarettes"),
}

DRUGS = {
    "metformin": ("A10BA02", "Metformin"),
    "glimepiride": ("A10BB12", "Glimepiride"),
    "sitagliptin": ("A10BH01", "Sitagliptin"),
    "empagliflozin": ("A10BK03", "Empagliflozin"),
    "telmisartan": ("C09CA07", "Telmisartan"),
    "amlodipine": ("C08CA01", "Amlodipine"),
    "metoprolol": ("C07AB02", "Metoprolol"),
    "atorvastatin": ("C10AA05", "Atorvastatin"),
    "aspirin": ("B01AC06", "Acetylsalicylic acid"),
}

# rsid, gene, risk allele, other allele, approximate South Asian risk allele frequency
MARKERS = [
    ("rs7903146", "TCF7L2", "T", "C", 0.30),
    ("rs2237892", "KCNQ1", "C", "T", 0.75),
    ("rs13266634", "SLC30A8", "C", "T", 0.78),
    ("rs1333049", "CDKN2B-AS1 (9p21)", "C", "G", 0.50),
]


SENS_SLOPE, SECR_SLOPE = 0.9, 0.75


@dataclass
class MealSlot:
    name: str
    minute: int          # minute of day
    carbs: float         # grams
    kind: str            # key of MEAL_TYPES
    jitter: float = 30.0  # sd of timing in minutes
    skip_prob: float = 0.05


@dataclass
class Patient:
    id: str
    given: str
    family: str
    sex: str
    birth_date: date
    age: int
    city: str
    region: str
    religion: str
    occupation: str
    night_shift: bool
    device: str
    phenotype: str
    hypertension: bool
    dyslipidemia: bool
    fh_cad: bool
    smoker: str
    height_cm: float
    weight_kg: float
    bmi: float
    waist_cm: float
    labs: dict
    lab_date: date
    conditions: list
    meds: list
    genotypes: dict
    prs_t2d: float
    lifestyle: dict
    routine: dict
    physio: dict
    cardio: dict
    hero: str | None = None
    notes: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.given} {self.family}"

    def has_drug(self, key: str) -> bool:
        return any(m["key"] == key for m in self.meds)


def _pick(rng, seq):
    return seq[int(rng.integers(len(seq)))]


def _birth_date(rng, age: int) -> date:
    ref = config.START.date()
    return date(ref.year - age, 1, 1) + timedelta(days=int(rng.integers(0, 365)))


def _phenotype(rng, age: int) -> str:
    p_t2d = 0.20 + 0.006 * (age - 30)
    p_pre = 0.27
    u = rng.random()
    if u < p_t2d:
        return "t2d"
    if u < p_t2d + p_pre:
        return "prediabetes"
    return "healthy"


def _labs(rng, phenotype: str, bmi: float, sex: str, dyslip: bool, age: int) -> dict:
    if phenotype == "t2d":
        hba1c = float(np.clip(rng.normal(8.0, 1.1), 6.5, 11.5))
    elif phenotype == "prediabetes":
        hba1c = float(rng.uniform(5.7, 6.4))
    else:
        hba1c = float(np.clip(rng.normal(5.25, 0.2), 4.6, 5.6))
    # Fasting glucose tracks HbA1c with spread (ADAG regression, fasting runs below the mean).
    fpg = 28.7 * hba1c - 46.7 - rng.normal(18, 8) if phenotype == "t2d" else 18.0 * hba1c - 4 + rng.normal(0, 4)
    fpg = float(np.clip(fpg, 72, 260))
    hdl = rng.normal(40 if sex == "male" else 46, 7) - (4 if dyslip else 0)
    tg = rng.lognormal(np.log(150 if dyslip else 115), 0.3) + (20 if phenotype == "t2d" else 0)
    ldl = rng.normal(132 if dyslip else 105, 22)
    tc = ldl + hdl + tg / 5
    creat = rng.normal(1.0 if sex == "male" else 0.8, 0.15) + max(0, age - 60) * 0.005
    # CKD-EPI 2021, race free.
    k, a = (0.9, -0.302) if sex == "male" else (0.7, -0.241)
    egfr = 142 * min(creat / k, 1) ** a * max(creat / k, 1) ** -1.2 * 0.9938 ** age * (1 if sex == "male" else 1.012)
    return {
        "hba1c": round(hba1c, 1), "fpg": round(fpg), "tc": round(tc), "ldl": round(ldl), "hdl": round(hdl),
        "tg": round(tg), "creatinine": round(creat, 2), "egfr": round(egfr),
    }


def _routine(rng, region: str, religion: str, night_shift: bool, phenotype: str) -> dict:
    staple = "rice" if region in ("south", "east") else ("wheat" if region == "north" else _pick(rng, ["rice", "wheat"]))
    scale = rng.uniform(0.85, 1.2) * (0.9 if phenotype == "t2d" else 1.0)  # T2D patients have had diet advice
    bf_kind = {"south": "idli_dosa", "west": "poha_upma", "north": "paratha", "east": "bread_tea"}[region]
    main = "rice_meal" if staple == "rice" else "roti_meal"
    if night_shift:
        normal = [
            MealSlot("Breakfast (post shift)", 7 * 60 + 45, 40 * scale, "bread_tea", 20),
            MealSlot("Lunch", 14 * 60 + 15, 85 * scale, main, 30),
            MealSlot("Tea", 18 * 60, 25 * scale, "tea_snack", 25, 0.15),
            MealSlot("Dinner", 20 * 60 + 30, 108 * scale, "rice_meal", 15),
            MealSlot("Night snack", 2 * 60, 28 * scale, "tea_snack", 30, 0.2),
        ]
    else:
        normal = [
            MealSlot("Breakfast", int(rng.normal(8 * 60, 30)), 55 * scale, bf_kind, 25),
            MealSlot("Lunch", int(rng.normal(13 * 60 + 15, 25)), 90 * scale, main, 30),
            MealSlot("Tea", 17 * 60, 22 * scale, "tea_snack", 25, 0.25),
            MealSlot("Dinner", int(rng.normal(20 * 60 + 45, 30)), 85 * scale, main, 35),
        ]
    ramadan = [
        MealSlot("Suhoor", 4 * 60 + 40, 65 * scale, "suhoor", 10),
        MealSlot("Iftar", 18 * 60 + 30, 80 * scale, "iftar", 3, 0.0),
        MealSlot("Dinner", 21 * 60 + 15, 75 * scale, main, 30, 0.1),
    ]
    hindu_fast = [
        MealSlot("Fasting lunch", 13 * 60, 60 * scale, "sabudana", 40),
        MealSlot("Fruit", 17 * 60, 25 * scale, "fruit", 40),
        MealSlot("Fasting dinner", 20 * 60, 70 * scale, "sabudana", 40),
    ]
    return {"staple": staple, "normal": normal, "ramadan": ramadan, "hindu_fast": hindu_fast}


def _physio(rng, phenotype: str, labs: dict, bmi: float, age: int, genotypes: dict, meds: list) -> dict:
    """Hidden ground truth parameters for the UVA/Padova based simulator (never shown to the twin)."""
    tcf = genotypes["rs7903146"]["risk_alleles"]
    # Severity follows HbA1c so hidden physiology and the lab record agree.
    x = float(np.clip((labs["hba1c"] - 5.2) / 4.0, 0, 1.4))
    sens = 1.05 * np.exp(-SENS_SLOPE * x) * rng.lognormal(0, 0.12) * np.exp(-0.02 * (bmi - 24))
    secr = 1.05 * np.exp(-SECR_SLOPE * x) * rng.lognormal(0, 0.12) * (1 - 0.08 * tcf)
    return {
        "base_adult": int(rng.integers(1, 11)),
        "Gb": float(labs["fpg"] + rng.normal(0, 4)),
        "sens": float(sens),
        "secr": float(secr),
        "Ib": float(42 / sens ** 0.6),
        "kabs_scale": float(rng.uniform(0.75, 1.25) * (0.85 if phenotype == "t2d" else 1.0)),
        "dawn_amp": float(rng.uniform(0.08, 0.2) if phenotype == "t2d" else rng.uniform(0.0, 0.06)),
        "fast_k": float(rng.uniform(0.05, 0.15)),
        "met_eff": 0.20 if any(m["key"] == "metformin" for m in meds) else 0.0,
        "day_sd": float(rng.uniform(0.05, 0.12)),
    }


def _cardio(rng, p: dict) -> dict:
    """Synthetic composite cardiovascular risk (loosely Framingham shaped) and event schedule."""
    lp = (-4.1 + 0.055 * (p["age"] - 50) + 0.5 * (p["sex"] == "male") + 0.018 * (p["sbp"] - 125)
          + 0.6 * (p["smoker"] == "current") + 0.25 * (p["smoker"] == "former") + 0.55 * (p["phenotype"] == "t2d")
          + 0.012 * (p["tc"] / p["hdl"] - 4) * 10 + 0.7 * p["fh_cad"] + 0.25 * p["chd_alleles"])
    base_risk = float(1 / (1 + np.exp(-lp)))
    p_event = min(0.75, 1.6 * base_risk)
    event_day = int(rng.integers(13, config.N_DAYS - 1)) if rng.random() < p_event else None
    illness = []
    if rng.random() < 0.28:
        d0 = int(rng.integers(8, config.N_DAYS - 4))
        illness.append((d0, int(rng.integers(3, 6)), float(rng.uniform(0.9, 1.8))))
    return {
        "risk_score": round(base_risk, 3),
        "event_day": event_day,
        "event_severity": float(rng.uniform(1.4, 2.4)),
        "event_hour": float(rng.choice([5.5, 7.0, 9.5, 14.0, 22.0])),
        "illness": illness,
        "rmssd_base": None,
    }


def make_patient(idx: int, rng: np.random.Generator) -> Patient:
    region = _pick(rng, list(REGIONS))
    city = _pick(rng, REGIONS[region])
    u = rng.random()
    religion = "hindu" if u < 0.78 else "muslim" if u < 0.93 else "christian" if u < 0.97 else "sikh"
    if religion == "sikh":
        region, city = "north", _pick(rng, ["Chandigarh", "Delhi"])
    sex = "male" if rng.random() < 0.52 else "female"
    age = int(np.clip(rng.normal(52, 11), 28, 78))
    given = _pick(rng, GIVEN[(religion, sex)])
    family = (_pick(rng, FAMILY[religion]) if religion in ("muslim", "christian") else
              ("Kaur" if sex == "female" else "Singh") if religion == "sikh" and rng.random() < 0.6 else
              _pick(rng, FAMILY["sikh"]) if religion == "sikh" else _pick(rng, FAMILY[region]))
    night_shift = bool(rng.random() < 0.12 and age < 62)
    occupation = _pick(rng, OCCUPATIONS_NIGHT) if night_shift else _pick(rng, OCCUPATIONS_DAY if age < 62 else ["Retired", "Homemaker"])
    phenotype = _phenotype(rng, age)
    height = rng.normal(167 if sex == "male" else 154, 6)
    bmi_mu = {"t2d": 27.0, "prediabetes": 26.0, "healthy": 23.5}[phenotype]
    bmi = float(np.clip(rng.normal(bmi_mu, 3.2), 18.5, 40))
    weight = bmi * (height / 100) ** 2
    hypertension = bool(rng.random() < 0.15 + 0.008 * (age - 30) + (0.12 if phenotype == "t2d" else 0) + 0.02 * (bmi - 24))
    dyslip = bool(rng.random() < (0.55 if phenotype == "t2d" else 0.3))
    fh_cad = bool(rng.random() < 0.2)
    smoker = "current" if rng.random() < (0.18 if sex == "male" else 0.02) else ("former" if rng.random() < 0.15 else "never")
    labs = _labs(rng, phenotype, bmi, sex, dyslip, age)
    sbp = rng.normal(146, 10) if hypertension else rng.normal(122, 9)
    dbp = sbp * 0.62 + rng.normal(4, 4)
    labs.update({"sbp": round(sbp), "dbp": round(dbp)})
    genotypes = {}
    for rsid, gene, risk, other, freq in MARKERS:
        n_risk = int(rng.binomial(2, freq))
        genotypes[rsid] = {"gene": gene, "genotype": risk * n_risk + other * (2 - n_risk), "risk_alleles": n_risk,
                           "risk_allele": risk}
    prs = sum(genotypes[r]["risk_alleles"] for r in ("rs7903146", "rs2237892", "rs13266634")) + rng.normal(0, 0.8)
    device = "apple_health" if rng.random() < 0.3 else "google_fit"
    pid = f"PTV-{idx:04d}"
    lab_date = config.START.date() - timedelta(days=int(rng.integers(10, 120)))
    start = config.START.date()

    conditions, meds = [], []
    if phenotype == "t2d":
        dur = int(np.clip(rng.exponential(6), 0.5, 25))
        conditions.append(("t2d", start - timedelta(days=365 * dur)))
        meds.append({"key": "metformin", "dose": "1000 mg" if labs["hba1c"] > 7.5 else "500 mg", "freq": "BD",
                     "times": ["breakfast", "dinner"]})
        r = rng.random()
        if labs["hba1c"] > 8.0 and r < 0.45:
            meds.append({"key": "glimepiride", "dose": "1 mg", "freq": "OD", "times": ["breakfast"]})
        elif r < 0.7:
            meds.append({"key": "sitagliptin", "dose": "100 mg", "freq": "OD", "times": ["breakfast"]})
        elif r < 0.85:
            meds.append({"key": "empagliflozin", "dose": "10 mg", "freq": "OD", "times": ["breakfast"]})
    elif phenotype == "prediabetes":
        conditions.append(("prediabetes", start - timedelta(days=int(rng.integers(60, 1500)))))
        if rng.random() < 0.35:
            meds.append({"key": "metformin", "dose": "500 mg", "freq": "OD", "times": ["dinner"]})
    if hypertension:
        conditions.append(("hypertension", start - timedelta(days=int(rng.integers(200, 5000)))))
        meds.append({"key": "telmisartan", "dose": "40 mg", "freq": "OD", "times": ["breakfast"]})
        if sbp > 148:
            meds.append({"key": "amlodipine", "dose": "5 mg", "freq": "OD", "times": ["breakfast"]})
        if rng.random() < 0.15:
            meds.append({"key": "metoprolol", "dose": "25 mg", "freq": "OD", "times": ["breakfast"]})
    if dyslip:
        conditions.append(("dyslipidemia", start - timedelta(days=int(rng.integers(100, 3000)))))
        meds.append({"key": "atorvastatin", "dose": "20 mg", "freq": "OD", "times": ["dinner"]})
    if bmi >= 27.5:
        conditions.append(("obesity", start - timedelta(days=int(rng.integers(300, 3000)))))
    if fh_cad:
        conditions.append(("fh_cad", start - timedelta(days=int(rng.integers(300, 3000)))))
    if night_shift:
        conditions.append(("shift_work", start - timedelta(days=int(rng.integers(200, 2000)))))
    if smoker == "current":
        conditions.append(("tobacco", start - timedelta(days=int(rng.integers(2000, 9000)))))
    for m in meds:
        m["start"] = start - timedelta(days=int(rng.integers(60, 1500)))

    observes_ramadan = religion == "muslim" and rng.random() < (0.65 if phenotype == "t2d" else 0.85)
    lifestyle = {
        "observes_ramadan": bool(observes_ramadan),
        "observes_hindu_fasts": bool(religion == "hindu" and rng.random() < 0.3),
        "celebrates_holi": bool(religion in ("hindu", "sikh") and rng.random() < 0.8),
        "step_level": float(rng.lognormal(np.log(5500), 0.35) * (0.8 if phenotype == "t2d" else 1.0)),
        "morning_walk": bool(rng.random() < 0.3),
        "post_meal_walk_p": float(rng.uniform(0.0, 0.5) if rng.random() < 0.35 else 0.0),
        "sleep_hours": float(np.clip(rng.normal(5.2 if night_shift else 6.8, 0.5), 4.3, 8.2)),
        "sleep_sd": float(rng.uniform(0.35, 0.8)),
        "bedtime": float(rng.normal(23.0, 0.6)),
        "meal_log_p": float(rng.uniform(0.6, 0.95)),
        "carb_err_sd": float(rng.uniform(0.15, 0.35)),
        "adherence": float(rng.uniform(0.78, 0.98)),
        "fitness": float(np.clip(rng.normal(1.0, 0.18) - 0.012 * (bmi - 24), 0.5, 1.4)),
    }
    chd_alleles = genotypes["rs1333049"]["risk_alleles"]
    p = Patient(
        id=pid, given=given, family=family, sex=sex, birth_date=_birth_date(rng, age), age=age, city=city,
        region=region, religion=religion, occupation=occupation, night_shift=night_shift, device=device,
        phenotype=phenotype, hypertension=hypertension, dyslipidemia=dyslip, fh_cad=fh_cad, smoker=smoker,
        height_cm=round(height, 1), weight_kg=round(weight, 1), bmi=round(bmi, 1),
        waist_cm=round(bmi * 3.4 + rng.normal(0, 4) + (4 if sex == "male" else 0), 0),
        labs=labs, lab_date=lab_date, conditions=conditions, meds=meds, genotypes=genotypes,
        prs_t2d=round(float(prs), 2), lifestyle=lifestyle,
        routine=_routine(rng, region, religion, night_shift, phenotype),
        physio={}, cardio={},
    )
    p.physio = _physio(rng, phenotype, labs, bmi, age, genotypes, meds)
    p.cardio = _cardio(rng, {"age": age, "sex": sex, "sbp": sbp, "smoker": smoker, "phenotype": phenotype,
                             "tc": labs["tc"], "hdl": labs["hdl"], "fh_cad": fh_cad, "chd_alleles": chd_alleles})
    return p


def _apply_heroes(patients: list[Patient]) -> None:
    """The three demo patients. Fictional people built to illustrate the three use cases."""
    start = config.START.date()

    r = patients[0]
    r.given, r.family, r.sex, r.age, r.city, r.region, r.religion = "Ramesh", "Patil", "male", 52, "Mumbai", "west", "hindu"
    r.birth_date = date(1973, 8, 21)
    r.occupation, r.night_shift, r.device, r.phenotype = "Security supervisor (night shift)", True, "apple_health", "t2d"
    r.hypertension, r.dyslipidemia, r.fh_cad, r.smoker = False, True, False, "never"
    r.height_cm, r.weight_kg, r.bmi, r.waist_cm = 168.0, 76.5, 27.1, 98
    r.labs = {"hba1c": 8.4, "fpg": 134, "tc": 204, "ldl": 128, "hdl": 38, "tg": 192, "creatinine": 0.98,
              "egfr": 89, "sbp": 132, "dbp": 84}
    r.conditions = [("t2d", date(2019, 6, 10)), ("dyslipidemia", date(2021, 2, 3)), ("shift_work", date(2017, 1, 15))]
    r.meds = [
        {"key": "metformin", "dose": "1000 mg", "freq": "BD", "times": ["breakfast", "dinner"], "start": date(2019, 6, 10)},
        {"key": "sitagliptin", "dose": "100 mg", "freq": "OD", "times": ["breakfast"], "start": date(2023, 4, 2)},
        {"key": "atorvastatin", "dose": "10 mg", "freq": "OD", "times": ["dinner"], "start": date(2021, 2, 3)},
    ]
    r.genotypes["rs7903146"].update(genotype="CT", risk_alleles=1)
    r.lifestyle.update(observes_ramadan=False, observes_hindu_fasts=False, celebrates_holi=True, step_level=4800,
                       morning_walk=False, post_meal_walk_p=0.0, sleep_hours=4.9, sleep_sd=0.4, meal_log_p=0.92,
                       carb_err_sd=0.18, adherence=0.86, fitness=0.85)
    r.routine = _routine(np.random.default_rng(1), "west", "hindu", True, "t2d")
    for s in r.routine["normal"]:
        if s.name == "Dinner":
            s.carbs, s.kind, s.minute, s.jitter, s.skip_prob = 112.0, "rice_meal", 20 * 60 + 30, 12, 0.0
        if s.name == "Lunch":
            s.carbs, s.minute, s.jitter = 78.0, 13 * 60 + 45, 20
        if s.name == "Tea":
            s.carbs, s.minute, s.skip_prob = 12.0, 17 * 60 + 30, 0.0
    r.physio.update(Gb=128.0, sens=0.42, secr=0.38, Ib=70.0, kabs_scale=1.0, dawn_amp=0.14, fast_k=0.08,
                    met_eff=0.20, day_sd=0.06)
    r.cardio.update(event_day=None, illness=[], risk_score=0.11)

    f = patients[1]
    f.given, f.family, f.sex, f.age, f.city, f.region, f.religion = "Fatima", "Shaikh", "female", 46, "Hyderabad", "south", "muslim"
    f.birth_date = date(1979, 11, 4)
    f.occupation, f.night_shift, f.device, f.phenotype = "Homemaker", False, "google_fit", "prediabetes"
    f.hypertension, f.dyslipidemia, f.fh_cad, f.smoker = False, False, False, "never"
    f.height_cm, f.weight_kg, f.bmi, f.waist_cm = 155.0, 68.2, 28.4, 92
    f.labs = {"hba1c": 6.1, "fpg": 101, "tc": 186, "ldl": 112, "hdl": 44, "tg": 148, "creatinine": 0.74,
              "egfr": 99, "sbp": 124, "dbp": 80}
    f.conditions = [("prediabetes", date(2024, 9, 12)), ("obesity", date(2022, 3, 1))]
    f.meds = [{"key": "metformin", "dose": "500 mg", "freq": "OD", "times": ["dinner"], "start": date(2024, 9, 12)}]
    f.lifestyle.update(observes_ramadan=True, observes_hindu_fasts=False, celebrates_holi=False, step_level=5200,
                       morning_walk=False, post_meal_walk_p=0.0, sleep_hours=6.4, sleep_sd=0.5, meal_log_p=0.9,
                       carb_err_sd=0.2, adherence=0.92, fitness=0.9)
    f.routine = _routine(np.random.default_rng(2), "south", "muslim", False, "prediabetes")
    for s in f.routine["ramadan"]:
        if s.name == "Iftar":
            s.carbs, s.minute = 90.0, 18 * 60 + 19
        if s.name == "Suhoor":
            s.minute, s.carbs = 4 * 60 + 45, 55.0
    # Strong late phase secretion plus falling hepatic output in a long fast: the reactive pattern.
    f.physio.update(Gb=97.0, sens=0.62, secr=0.95, Ib=60.0, kabs_scale=1.15, dawn_amp=0.03, fast_k=0.80,
                    met_eff=0.20, day_sd=0.05)
    f.cardio.update(event_day=None, illness=[], risk_score=0.04)

    s = patients[2]
    s.given, s.family, s.sex, s.age, s.city, s.region, s.religion = "Suresh", "Menon", "male", 61, "Kochi", "south", "hindu"
    s.birth_date = date(1964, 5, 30)
    s.occupation, s.night_shift, s.device, s.phenotype = "Retired bank officer", False, "google_fit", "prediabetes"
    s.hypertension, s.dyslipidemia, s.fh_cad, s.smoker = True, True, True, "former"
    s.height_cm, s.weight_kg, s.bmi, s.waist_cm = 170.0, 74.0, 25.6, 96
    s.labs = {"hba1c": 5.9, "fpg": 106, "tc": 221, "ldl": 146, "hdl": 37, "tg": 178, "creatinine": 1.08,
              "egfr": 76, "sbp": 152, "dbp": 92}
    s.conditions = [("hypertension", date(2012, 7, 19)), ("dyslipidemia", date(2016, 1, 8)),
                    ("prediabetes", date(2022, 10, 1)), ("fh_cad", date(2010, 1, 1))]
    s.meds = [
        {"key": "telmisartan", "dose": "40 mg", "freq": "OD", "times": ["breakfast"], "start": date(2012, 7, 19)},
        {"key": "amlodipine", "dose": "5 mg", "freq": "OD", "times": ["breakfast"], "start": date(2018, 3, 2)},
        {"key": "atorvastatin", "dose": "20 mg", "freq": "OD", "times": ["dinner"], "start": date(2016, 1, 8)},
    ]
    s.genotypes["rs1333049"].update(genotype="CC", risk_alleles=2)
    s.lifestyle.update(observes_ramadan=False, observes_hindu_fasts=True, celebrates_holi=False, step_level=6500,
                       morning_walk=True, post_meal_walk_p=0.2, sleep_hours=6.9, sleep_sd=0.4, meal_log_p=0.85,
                       adherence=0.95, fitness=0.95)
    s.physio.update(Gb=103.0, sens=0.7, secr=0.75, Ib=55.0, met_eff=0.0)
    s.cardio.update(event_day=config.day_index(date(2026, 3, 13)), event_severity=2.3, event_hour=5.67,
                    illness=[], risk_score=0.31)
    s.notes.append("Father: myocardial infarction at 58.")

    for p in (r, f, s):
        p.bmi = round(p.weight_kg / (p.height_cm / 100) ** 2, 1)
        p.lab_date = start - timedelta(days=21)
        p.hero = {"Ramesh": "ramesh", "Fatima": "fatima", "Suresh": "suresh"}[p.given]


def make_cohort(n: int = config.N_PATIENTS, seed: int = config.SEED) -> list[Patient]:
    seeds = np.random.SeedSequence(seed).spawn(n)
    patients = [make_patient(i + 1, np.random.default_rng(s)) for i, s in enumerate(seeds)]
    _apply_heroes(patients)
    return patients


def split_of(patients: list[Patient], seed: int = config.SEED) -> dict[str, str]:
    """Patient level split. Heroes go to test so every demo forecast is out of sample."""
    rng = np.random.default_rng(seed + 7)
    ids = [p.id for p in patients if p.hero is None]
    rng.shuffle(ids)
    n = len(patients)
    n_test, n_cal = round(0.2 * n), round(0.2 * n)
    heroes = [p.id for p in patients if p.hero]
    test = heroes + ids[: n_test - len(heroes)]
    cal = ids[n_test - len(heroes): n_test - len(heroes) + n_cal]
    out = {pid: "train" for pid in ids}
    out.update({pid: "calibration" for pid in cal})
    out.update({pid: "test" for pid in test})
    return out
