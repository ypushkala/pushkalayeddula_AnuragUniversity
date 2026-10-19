"""Load raw sources into DuckDB.

EHR comes only from the FHIR bundles, so every model feature derived from the record has
passed through the same parser a real integration would use. For the hero patients the
wearable streams are read from their Apple Health or Google Fit exports, checked against
the canonical tables, and used in their place.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from prativimb import config
from prativimb.data import devices

ATC_CLASS = {"A10BA02": "metformin", "A10BB12": "sulfonylurea", "A10BH01": "dpp4", "A10BK03": "sglt2",
             "C09CA07": "arb", "C08CA01": "ccb", "C07AB02": "beta_blocker", "C10AA05": "statin", "B01AC06": "aspirin"}
ICD_FLAG = {"E11.9": "t2d", "R73.03": "prediabetes", "I10": "hypertension", "E78.5": "dyslipidemia",
            "E66.9": "obesity", "Z82.49": "fh_cad", "G47.26": "shift_work", "F17.210": "tobacco"}
LOINC_KEY = {"4548-4": "hba1c", "1558-6": "fpg", "2093-3": "tc", "13457-7": "ldl", "2085-9": "hdl",
             "2571-8": "tg", "2160-0": "creatinine", "98979-8": "egfr", "8480-6": "sbp", "8462-4": "dbp",
             "39156-5": "bmi", "29463-7": "weight", "8302-2": "height", "8280-0": "waist"}


def parse_bundle(bundle: dict) -> dict[str, list[dict]]:
    out = {"patients": [], "conditions": [], "medications": [], "observations": [], "genetics": []}
    for e in bundle["entry"]:
        r = e["resource"]
        kind = r["resourceType"]
        if kind == "Patient":
            ext = {x["url"].split(":")[-1]: next(v for k, v in x.items() if k.startswith("value")) for x in r["extension"]}
            out["patients"].append({
                "pid": r["id"], "given": r["name"][0]["given"][0], "family": r["name"][0]["family"],
                "sex": r["gender"], "birth_date": r["birthDate"], "city": r["address"][0]["city"],
                "occupation": ext["occupation"], "night_shift": ext["night-shift"],
                "device": ext.get("wearable-platform", "unknown"),
            })
        elif kind == "Condition":
            c = r["code"]["coding"][0]
            out["conditions"].append({"pid": r["subject"]["reference"].split("/")[1], "code": c["code"],
                                      "display": c["display"], "onset": r["onsetDateTime"],
                                      "flag": ICD_FLAG.get(c["code"], c["code"])})
        elif kind == "MedicationStatement":
            c = r["medicationCodeableConcept"]["coding"][0]
            out["medications"].append({"pid": r["subject"]["reference"].split("/")[1], "atc": c["code"],
                                       "name": c["display"], "dosage": r["dosage"][0]["text"],
                                       "start": r["effectivePeriod"]["start"], "drug_class": ATC_CLASS.get(c["code"], "other")})
        elif kind == "Observation":
            code = r["code"]["coding"][0]["code"]
            pid = r["subject"]["reference"].split("/")[1]
            if code == "69548-6":
                comp = {c["code"]["coding"][0]["code"] if "coding" in c["code"] else c["code"]["text"]: c for c in r["component"]}
                out["genetics"].append({
                    "pid": pid, "gene": comp["48018-6"]["valueCodeableConcept"]["text"],
                    "rsid": comp["81255-2"]["valueCodeableConcept"]["coding"][0]["code"],
                    "genotype": comp["84414-2"]["valueString"], "risk_alleles": comp["Risk allele count"]["valueInteger"],
                })
            elif code == "72166-2":
                out["observations"].append({"pid": pid, "key": "smoking", "loinc": code, "value": None,
                                            "text": r["valueCodeableConcept"]["coding"][0]["display"],
                                            "unit": None, "date": r["effectiveDateTime"]})
            elif code in LOINC_KEY:
                q = r["valueQuantity"]
                out["observations"].append({"pid": pid, "key": LOINC_KEY[code], "loinc": code, "value": q["value"],
                                            "text": None, "unit": q["unit"], "date": r["effectiveDateTime"]})
        elif kind == "FamilyMemberHistory":
            out["conditions"].append({"pid": r["patient"]["reference"].split("/")[1], "code": "FH:I21.9",
                                      "display": f"{r['relationship']['text']}: myocardial infarction at "
                                                 f"{r['condition'][0]['onsetAge']['value']}",
                                      "onset": None, "flag": "fh_mi"})
    return out


def ehr_features(patients: pd.DataFrame, conditions: pd.DataFrame, meds: pd.DataFrame,
                 obs: pd.DataFrame, genetics: pd.DataFrame) -> pd.DataFrame:
    """One row per patient with the EHR covariates used by the twin priors and the models."""
    latest = (obs.dropna(subset=["value"]).sort_values("date").groupby(["pid", "key"]).value.last().unstack())
    df = patients.set_index("pid").join(latest)
    df["age"] = ((pd.Timestamp(config.START.date()) - pd.to_datetime(df.birth_date)).dt.days // 365).astype(int)
    df["male"] = (df.sex == "male").astype(int)
    for flag in ("t2d", "prediabetes", "hypertension", "dyslipidemia", "obesity", "fh_cad", "fh_mi", "tobacco"):
        has = set(conditions.loc[conditions.flag == flag, "pid"])
        df[flag] = df.index.isin(has).astype(int)
    for cls in ("metformin", "sulfonylurea", "dpp4", "sglt2", "beta_blocker", "statin", "arb", "ccb"):
        has = set(meds.loc[meds.drug_class == cls, "pid"])
        df[f"on_{cls}"] = df.index.isin(has).astype(int)
    smoke = obs[obs.key == "smoking"].set_index("pid").text
    df["smoker_current"] = (smoke.reindex(df.index) == "Smoker").astype(int)
    df["smoker_former"] = (smoke.reindex(df.index) == "Ex-smoker").astype(int)
    g = genetics.pivot_table(index="pid", columns="rsid", values="risk_alleles")
    df["tcf7l2_risk"] = g["rs7903146"].reindex(df.index)
    df["t2d_grs"] = g[["rs7903146", "rs2237892", "rs13266634"]].sum(axis=1).reindex(df.index)
    df["chd_9p21_risk"] = g["rs1333049"].reindex(df.index)
    df["night_shift"] = df.night_shift.astype(int)
    df["tc_hdl"] = df.tc / df.hdl
    return df.reset_index()


def load_ehr() -> dict[str, pd.DataFrame]:
    parts = {k: [] for k in ("patients", "conditions", "medications", "observations", "genetics")}
    for path in sorted((config.RAW_DIR / "ehr").glob("*.json")):
        for k, rows in parse_bundle(json.loads(path.read_text())).items():
            parts[k] += rows
    return {k: pd.DataFrame(v) for k, v in parts.items()}


def hero_device_streams(patients: pd.DataFrame) -> dict[str, dict[str, pd.DataFrame]]:
    out = {}
    for pid in sorted(p.name for p in (config.RAW_DIR / "devices").glob("PTV-*")):
        folder: Path = config.RAW_DIR / "devices" / pid
        if (folder / "apple_health_export.xml").exists():
            out[pid] = devices.read_apple(folder / "apple_health_export.xml")
        elif (folder / "google_fit").exists():
            out[pid] = devices.read_google(folder / "google_fit")
        elif (folder / "health_connect.json").exists():
            out[pid] = devices.read_health_connect(folder / "health_connect.json")
    return out


def run(verbose: bool = True) -> None:
    ehr = load_ehr()
    feats = ehr_features(ehr["patients"], ehr["conditions"], ehr["medications"], ehr["observations"], ehr["genetics"])
    proc = config.PROCESSED_DIR
    cgm = pd.read_parquet(proc / "cgm.parquet")
    hr = pd.read_parquet(proc / "hr.parquet")

    # Hero streams go through the device adapters. They must match the canonical tables exactly.
    for pid, streams in hero_device_streams(ehr["patients"]).items():
        c0 = cgm[cgm.pid == pid].reset_index(drop=True)
        c1 = streams["cgm"]
        assert np.allclose(c0.glucose.to_numpy(), c1.glucose.to_numpy(), equal_nan=True), f"CGM mismatch for {pid}"
        h0 = hr[hr.pid == pid].reset_index(drop=True)
        h1 = streams["hr"]
        assert np.allclose(h0.hr.to_numpy(), h1.hr.to_numpy(), equal_nan=True), f"HR mismatch for {pid}"
        assert (h0.steps.to_numpy() == h1.steps.to_numpy()).all(), f"steps mismatch for {pid}"
        cgm.loc[cgm.pid == pid, "glucose"] = c1.glucose.to_numpy(np.float32)
        hr.loc[hr.pid == pid, "hr"] = h1.hr.to_numpy(np.float32)
        if verbose:
            print(f"  {pid}: device export parsed and verified ({len(c1.dropna())} CGM, {int(h1.hr.notna().sum())} HR records)")

    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    con = duckdb.connect(str(config.DB_PATH))
    for name, df in {**ehr, "ehr_features": feats, "cgm": cgm, "hr": hr}.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    for name in ("sleep_segments", "sleep_nightly", "meals_log", "doses", "routine", "events"):
        path = proc / f"{name}.parquet"
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{path.as_posix()}')")
    split = json.loads((config.DATA_DIR / "splits.json").read_text())
    con.register("tmp_df", pd.DataFrame({"pid": list(split), "split": list(split.values())}))
    con.execute("CREATE TABLE splits AS SELECT * FROM tmp_df")
    con.execute("CREATE INDEX cgm_idx ON cgm(pid, minute)")
    con.execute("CREATE INDEX hr_idx ON hr(pid, minute)")
    con.close()
    if verbose:
        print(f"  DuckDB written to {config.DB_PATH}")


if __name__ == "__main__":
    run()
