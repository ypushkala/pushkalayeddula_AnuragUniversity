"""FHIR R4 shaped bundles for the synthetic EHR (Synthea style output, one bundle per patient).

Codes: ICD-10 for conditions, LOINC for observations, WHO ATC for medications, dbSNP and
HGNC for genetic markers. The Consent resource records the DPDP Act style consent artefact
(purpose limited, time bound, revocable) that a real deployment would need.
"""
from __future__ import annotations

from datetime import date, timedelta

from prativimb import config
from prativimb.data.cohort import DRUGS, ICD10, Patient

LOINC = {
    "hba1c": ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%"),
    "fpg": ("1558-6", "Fasting glucose [Mass/volume] in Serum or Plasma", "mg/dL"),
    "tc": ("2093-3", "Cholesterol [Mass/volume] in Serum or Plasma", "mg/dL"),
    "ldl": ("13457-7", "Cholesterol in LDL [Mass/volume] in Serum or Plasma by calculation", "mg/dL"),
    "hdl": ("2085-9", "Cholesterol in HDL [Mass/volume] in Serum or Plasma", "mg/dL"),
    "tg": ("2571-8", "Triglyceride [Mass/volume] in Serum or Plasma", "mg/dL"),
    "creatinine": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "mg/dL"),
    "egfr": ("98979-8", "Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] (CKD-EPI 2021)", "mL/min/1.73m2"),
    "sbp": ("8480-6", "Systolic blood pressure", "mm[Hg]"),
    "dbp": ("8462-4", "Diastolic blood pressure", "mm[Hg]"),
    "bmi": ("39156-5", "Body mass index (BMI) [Ratio]", "kg/m2"),
    "weight": ("29463-7", "Body weight", "kg"),
    "height": ("8302-2", "Body height", "cm"),
    "waist": ("8280-0", "Waist Circumference at umbilicus by Tape measure", "cm"),
}
VITALS = {"sbp", "dbp", "bmi", "weight", "height", "waist"}
SMOKING = {"never": ("266919005", "Never smoked tobacco"), "former": ("8517006", "Ex-smoker"),
           "current": ("77176002", "Smoker")}


def _ref(kind: str, pid: str, suffix: str) -> str:
    return f"{kind}/{pid}-{suffix}"


def _obs(p: Patient, key: str, value: float, when: date) -> dict:
    code, display, unit = LOINC[key]
    cat = "vital-signs" if key in VITALS else "laboratory"
    return {
        "resourceType": "Observation", "id": f"{p.id}-{key}", "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": cat}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}], "text": display},
        "subject": {"reference": f"Patient/{p.id}"},
        "effectiveDateTime": when.isoformat(),
        "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
    }


def bundle(p: Patient) -> dict:
    start = config.START.date()
    entries = [{
        "resourceType": "Patient", "id": p.id,
        "identifier": [{"system": "urn:prativimb:mrn", "value": p.id}],
        "name": [{"use": "official", "family": p.family, "given": [p.given]}],
        "gender": p.sex, "birthDate": p.birth_date.isoformat(),
        "address": [{"city": p.city, "country": "IN"}],
        "communication": [{"language": {"text": "en-IN"}}],
        "extension": [
            {"url": "urn:prativimb:occupation", "valueString": p.occupation},
            {"url": "urn:prativimb:night-shift", "valueBoolean": p.night_shift},
            {"url": "urn:prativimb:wearable-platform", "valueString": p.device},
            {"url": "urn:prativimb:synthetic", "valueBoolean": True},
        ],
    }]
    for key, onset in p.conditions:
        code, display = ICD10[key]
        entries.append({
            "resourceType": "Condition", "id": f"{p.id}-{key}",
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code, "display": display}], "text": display},
            "subject": {"reference": f"Patient/{p.id}"},
            "onsetDateTime": onset.isoformat(),
        })
    for key in ("hba1c", "fpg", "tc", "ldl", "hdl", "tg", "creatinine", "egfr", "sbp", "dbp"):
        entries.append(_obs(p, key, p.labs[key], p.lab_date))
    # An older HbA1c gives the clinician a trend.
    prior = round(p.labs["hba1c"] + (0.3 if p.phenotype == "t2d" else 0.1) * (1 if p.id[-1] in "02468" else -1), 1)
    older = _obs(p, "hba1c", prior, p.lab_date - timedelta(days=182))
    older["id"] = f"{p.id}-hba1c-prior"
    entries.append(older)
    for key, val in (("bmi", p.bmi), ("weight", p.weight_kg), ("height", p.height_cm), ("waist", p.waist_cm)):
        entries.append(_obs(p, key, val, p.lab_date))
    for m in p.meds:
        atc, name = DRUGS[m["key"]]
        entries.append({
            "resourceType": "MedicationStatement", "id": f"{p.id}-{m['key']}", "status": "active",
            "medicationCodeableConcept": {"coding": [{"system": "http://www.whocc.no/atc", "code": atc, "display": name}],
                                          "text": name},
            "subject": {"reference": f"Patient/{p.id}"},
            "effectivePeriod": {"start": m["start"].isoformat()},
            "dosage": [{"text": f"{name} {m['dose']} {m['freq']}", "timing": {"code": {"text": m["freq"]}}}],
        })
    for rsid, g in p.genotypes.items():
        entries.append({
            "resourceType": "Observation", "id": f"{p.id}-{rsid}", "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": "69548-6", "display": "Genetic variant assessment"}]},
            "subject": {"reference": f"Patient/{p.id}"},
            "effectiveDateTime": (start - timedelta(days=400)).isoformat(),
            "valueCodeableConcept": {"text": "Present" if g["risk_alleles"] else "Absent"},
            "component": [
                {"code": {"coding": [{"system": "http://loinc.org", "code": "48018-6", "display": "Gene studied"}]},
                 "valueCodeableConcept": {"text": g["gene"]}},
                {"code": {"coding": [{"system": "http://loinc.org", "code": "81255-2", "display": "dbSNP [ID]"}]},
                 "valueCodeableConcept": {"coding": [{"system": "http://www.ncbi.nlm.nih.gov/projects/SNP", "code": rsid}]}},
                {"code": {"coding": [{"system": "http://loinc.org", "code": "84414-2", "display": "Haplotype name"}]},
                 "valueString": g["genotype"]},
                {"code": {"text": "Risk allele count"}, "valueInteger": g["risk_alleles"]},
            ],
        })
    entries.append({
        "resourceType": "Observation", "id": f"{p.id}-smoking", "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "social-history"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2", "display": "Tobacco smoking status"}]},
        "subject": {"reference": f"Patient/{p.id}"}, "effectiveDateTime": p.lab_date.isoformat(),
        "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": SMOKING[p.smoker][0],
                                             "display": SMOKING[p.smoker][1]}]},
    })
    if p.fh_cad:
        entries.append({
            "resourceType": "FamilyMemberHistory", "id": f"{p.id}-fh", "status": "completed",
            "patient": {"reference": f"Patient/{p.id}"},
            "relationship": {"text": "Father"},
            "condition": [{"code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "I21.9",
                                                "display": "Acute myocardial infarction"}]},
                           "onsetAge": {"value": 58 if p.hero == "suresh" else 55 + (int(p.id[-2:]) % 15), "unit": "a"}}],
        })
    entries.append({
        "resourceType": "Consent", "id": f"{p.id}-consent", "status": "active",
        "scope": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/consentscope", "code": "patient-privacy"}]},
        "category": [{"text": "DPDP Act 2023 consent artefact (synthetic)"}],
        "patient": {"reference": f"Patient/{p.id}"},
        "dateTime": (start - timedelta(days=30)).isoformat(),
        "provision": {
            "type": "permit",
            "period": {"start": (start - timedelta(days=30)).isoformat(), "end": (start + timedelta(days=365)).isoformat()},
            "purpose": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActReason", "code": "TREAT",
                         "display": "treatment"}],
            "data": [{"meaning": "related", "reference": {"reference": "urn:prativimb:wearables"}}],
        },
    })
    return {"resourceType": "Bundle", "id": f"{p.id}-ehr", "type": "collection",
            "meta": {"tag": [{"code": "synthetic", "display": "Synthetic record, not a real person"}]},
            "entry": [{"fullUrl": f"urn:uuid:{r['resourceType']}-{r['id']}", "resource": r} for r in entries]}
