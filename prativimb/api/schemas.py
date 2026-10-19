"""Response and request models. EHR shapes loosely mirror FHIR R4 resources."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Coding(BaseModel):
    system: str
    code: str
    display: str


class PatientResource(BaseModel):
    resourceType: Literal["Patient"] = "Patient"
    id: str
    name: str
    gender: str
    birthDate: str
    age: int
    city: str
    occupation: str
    nightShift: bool
    synthetic: bool = True


class ConditionResource(BaseModel):
    resourceType: Literal["Condition"] = "Condition"
    code: Coding
    onsetDateTime: str | None
    clinicalStatus: str = "active"


class MedicationStatementResource(BaseModel):
    resourceType: Literal["MedicationStatement"] = "MedicationStatement"
    medication: Coding
    dosage: str
    effectiveStart: str
    drugClass: str


class ObservationResource(BaseModel):
    resourceType: Literal["Observation"] = "Observation"
    code: Coding
    value: float | None
    unit: str | None
    text: str | None = None
    effectiveDateTime: str
    previous: float | None = None
    previousDate: str | None = None


class GeneticVariant(BaseModel):
    gene: str
    rsid: str
    genotype: str
    riskAlleles: int


class TwinParameters(BaseModel):
    insulin_sensitivity_pct_typical: float
    glucose_effectiveness: float
    basal_glucose: float
    absorption_half_time_min: float
    secretion_pct_typical: float
    calibration_rmse_prior: float
    calibration_rmse_fit: float


class PatientDetail(BaseModel):
    patient: PatientResource
    conditions: list[ConditionResource]
    medications: list[MedicationStatementResource]
    labs: list[ObservationResource]
    vitals: list[ObservationResource]
    genetics: list[GeneticVariant]
    familyHistory: list[str]
    socialHistory: list[str]
    consent: str
    twin: TwinParameters
    device: str
    context: list[str]
    split: str


class ClockUpdate(BaseModel):
    minute: float | None = None
    at: str | None = Field(None, description="ISO time inside the replay window")
    speed: float | None = Field(None, ge=0, le=3600)
    paused: bool | None = None


class WhatIfRequest(BaseModel):
    walk_minutes: int = Field(0, ge=0, le=60)
    swap: Literal["none", "millet", "brown_rice", "roti", "half_portion"] = "none"
    shift_hours: float = Field(0.0, ge=-3, le=3)
    missed_dose: bool = False
    sleep_hours: float | None = Field(None, ge=3, le=10)
    night_shift: bool = False
