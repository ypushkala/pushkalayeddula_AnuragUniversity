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
    abha: str = ""
    records_withheld: bool = False
    calibrating: int | None = None


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
    scope: Literal["next", "all"] = "next"
    horizon_h: Literal[6, 24, 168] = 6
    insulin_bolus_units: float = Field(0.0, ge=0, le=20, description="Rapid acting insulin with each targeted main meal")
    insulin_basal_units: float = Field(0.0, ge=0, le=40, description="Long acting insulin per day, at steady state")
    metformin_shift_hours: float = Field(0.0, ge=-3, le=3, description="Move the evening metformin dose")


class MealEntry(BaseModel):
    minutes_from_now: int = Field(..., ge=-360, le=1440, description="Negative for a meal already eaten")
    carbs: float = Field(..., gt=0, le=250)
    kind: str = "rice_meal"
    label: str = Field("Meal", max_length=80)
    by: str = Field("", max_length=60)


class Acknowledge(BaseModel):
    kind: Literal["spike", "low", "cardio"]
    by: str = Field("", max_length=60)
    snooze_minutes: int = Field(60, ge=0, le=720)
    note: str = Field("", max_length=280)


class Action(BaseModel):
    kind: Literal["call", "review", "check"]
    note: str = Field("", max_length=280)
    outcome: str = Field("", max_length=280)
    alert: Literal["spike", "low", "cardio", ""] = ""


class Plan(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    request: dict
    predicted: dict = {}


class Consent(BaseModel):
    source: Literal["cgm", "wearable", "abdm"]
    granted: bool


class Activity(BaseModel):
    kind: Literal["walk"] = "walk"
    minutes: int = Field(15, ge=5, le=90)
    when: Literal["after_next_meal", "now", "done"] = "after_next_meal"
    minutes_ago: int = Field(0, ge=0, le=240)


class Message(BaseModel):
    key: Literal["will_walk", "walked", "not_today", "nudge"]
    text: str = Field("", max_length=280)
    params: dict = {}


class Ask(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)
