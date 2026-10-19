# Data

Everything in this repository is synthetic. No real patient, no dataset under a data use agreement, and no personal data of any kind was used. Every patient name is a random pairing of common given and family names; any resemblance to a real person is coincidental.

Regenerate all data with one command (about 20 seconds on a laptop):

```
make data          # or: python -m prativimb.pipeline data
```

Seed `20260315` drives everything. Two runs produce byte identical wearable files (checked with `shasum` during development; `tests/test_data.py` checks determinism of the cohort and schedules).

## Sources and licences

| Source | What we use it for | Licence | Agreement needed |
|---|---|---|---|
| Own Synthea style generator (`prativimb/data/cohort.py`, `fhir.py`) | Demographics, diagnoses, labs, medications, genetic markers, consent, as FHIR R4 bundles | MIT (this repository) | No |
| simglucose 0.2.11 (Jinyu Xie), `vpatient_params.csv` and `sensor_params.csv` | Between patient variability of UVA/Padova kinetic parameters; Dexcom CGM noise model (Johnson SU transformed AR process) | MIT | No |
| Dalla Man, Rizza, Cobelli. Meal simulation model of the glucose insulin system. IEEE TBME 2007 | Model structure and normal subject parameter means; endogenous secretion model | Published equations | No |
| Breton and Kovatchev, J Diabetes Sci Technol 2008 | CGM error model parameters (via simglucose) | Published | No |
| ICD-10 (WHO), LOINC (Regenstrief), WHO ATC, dbSNP and HGNC identifiers | Codes inside the FHIR bundles | Free to use codes (LOINC licence permits use of codes) | No |
| IBM Plex Sans and Serif | Typefaces for the dashboard, charts, slides and PDF note | SIL Open Font License 1.1 (`assets/fonts/OFL.txt`) | No |
| Noto Sans Devanagari and Tamil (via Fontsource) | Hindi and Tamil text in the patient view | SIL Open Font License 1.1 | No |
| CGMacros v1.0.0 (Gutierrez-Osuna, Kerr, Mortazavi, Das; PhysioNet 2025) | Validation of forecasts on real CGM traces only; never used for training | CC BY-NC-SA 4.0, open access | No (anyone can download under the licence terms) |

### Why not Synthea itself

Synthea (Apache 2.0) needs Java, which is available, but its disease modules and demographics are calibrated to the United States (Massachusetts by default). We needed Indian diet, fasting calendars, night shift work, Indian names and cities, South Asian allele frequencies and a diabetes clinic case mix. We therefore wrote a Synthea style generator in Python that emits the same kind of output (one FHIR R4 `Bundle` per patient with `Patient`, `Condition`, `Observation`, `MedicationStatement`, `FamilyMemberHistory` and `Consent` resources). The ingest path (`prativimb/data/ingest.py`) reads only these bundles, so a real Synthea or hospital FHIR export can be fed through the same parser.

## Cohort

* 200 patients, 30 days each, 14 Feb 2026 00:00 to 15 Mar 2026 23:59 IST.
* Phenotype mix is enriched for a diabetes clinic panel: about 40% healthy, 28% prediabetes, 32% Type 2 diabetes (prevalence of each rises with age). Hypertension, dyslipidaemia, obesity (Asian BMI cut offs), smoking and family history of ischaemic heart disease are layered on.
* Religion and region follow the broad national mix (NFHS-5 shaped): North, West, South and East cities; about 78% Hindu, 15% Muslim, 4% Christian, 3% Sikh.
* Labs: HbA1c, fasting glucose (consistent with HbA1c through the ADAG relation), lipid panel with the typical Indian pattern of low HDL and high triglycerides, creatinine and eGFR (CKD-EPI 2021, race free), blood pressure, BMI and waist.
* Medications: metformin (BD or OD), sulfonylurea, DPP-4 inhibitor, SGLT2 inhibitor, telmisartan, amlodipine, metoprolol, atorvastatin.
* Genetic markers: TCF7L2 rs7903146, KCNQ1 rs2237892, SLC30A8 rs13266634 (Type 2 diabetes) and CDKN2B-AS1 9p21 rs1333049 (coronary disease), drawn with approximate South Asian allele frequencies. TCF7L2 risk alleles lower simulated insulin secretion.

## India first behaviour

* Meals by region and occupation: idli and dosa, poha and upma, paratha, rice or roti thalis, biryani, tea with biscuits. Each food has an absorption speed (rice and idli fast, millets slow, iftar dates and sherbet fastest).
* Calendar inside the window: Maha Shivaratri (15 Feb), Ramadan from 19 Feb (suhoor about 04:45, iftar drifting from about 18:20 to 18:30 in Hyderabad), Amalaki and Papmochani Ekadashi (27 Feb and 15 Mar, approximate), Holi (4 Mar, festival sweets and a late night).
* Observant patients follow fasting plans on those days. Ramadan shortens and splits sleep around suhoor.
* About 12% of working age patients work night shifts (Thursday off), with daytime sleep and a night snack.

## Ground truth physiology (used only to make data)

The UVA/Padova meal model (Dalla Man 2007): gastric emptying, gut absorption, glucose in plasma and tissue, hepatic production, insulin kinetics. simglucose provides between patient variability (each patient inherits one simglucose adult's deviation from the cohort mean, square root damped). Adaptations for Type 2 diabetes and India:

* the insulin pump is replaced by endogenous beta cell secretion (Dalla Man 2007), scaled by a secretion factor tied to HbA1c and TCF7L2;
* insulin dependent uptake and hepatic insulin action scale with an insulin sensitivity factor tied to HbA1c and BMI;
* counter regulation below 70 mg/dL and glomerular renal glucose excretion (lower threshold on SGLT2 inhibitors);
* circadian insulin sensitivity, dawn phenomenon, metformin suppression of hepatic output with dose by dose kinetics, exercise uptake sized to published post meal walking effects, three night sleep debt, night shift misalignment, falling hepatic output late in a long fast, and day to day noise.

Calibration checks: a 75 g load reproduces the ADA two hour thresholds by phenotype; mean simulated glucose tracks HbA1c derived average glucose (correlation 0.98).

The twin never sees these equations or parameters. It is a simpler model (extended Bergman minimal model) that must be fitted from what is observable.

## Wearables and device formats

| Signal | Rate | Notes |
|---|---|---|
| CGM | 5 min | Interstitial glucose plus simglucose Dexcom noise (MARD about 7.6% against plasma), 14 day sensor sessions with calibration gain and warm up gaps, random signal loss, overnight compression lows, 40 to 400 mg/dL reporting range |
| Heart rate | 1 min | Resting level from age, fitness, diagnosis and beta blockers; sleep stage offsets; lagged response to steps; circadian swing; daily charging gap |
| Steps | 1 min | Walking bouts (morning walks, commutes, post meal walks, night patrols for security staff) plus background activity |
| Sleep | per night | Hypnogram of core, deep, REM and awake segments in 90 minute cycles; deep sleep falls with age and strain |
| HRV | per night | Nightly RMSSD from age, fitness, diabetes, hypertension, sleep length and strain |

Hero patients are also exported in device formats and read back through the adapters during ingest (`prativimb/data/devices.py`):

* Ramesh: Apple Health `export.xml` (`HKQuantityTypeIdentifierHeartRate`, `StepCount`, `BloodGlucose`, `HKCategoryTypeIdentifierSleepAnalysis`).
* Fatima and Suresh: Google Fit REST style datasets (`com.google.heart_rate.bpm`, `com.google.step_count.delta`, `com.google.blood_glucose` in mmol/L, `com.google.sleep.segment`).
* Neither platform has a native nightly RMSSD type (Apple exports SDNN). Nightly RMSSD, as rings and bands such as Oura or Fitbit report it, is written under our own namespaced type (`org.prativimb.NightlyRMSSD`, `com.prativimb.hrv.rmssd.nightly`).

## Cardiovascular events

A latent daily strain process (AR(1) noise) drives resting heart rate up and HRV, deep sleep, REM and steps down. Each patient's chance of an event in the window comes from a Framingham shaped synthetic risk (age, sex, systolic pressure, smoking, diabetes, TC/HDL, family history, 9p21 genotype). Before an event, strain ramps up over seven days; after it there is a hospital gap of about a day and a recovery tail. About 28% of patients have an illness episode (fever) that looks similar but is not followed by an event, so the classifier has confounders to learn around. 25 patients have an event.

## The three demo patients (fictional)

| Patient | Story | How it is built |
|---|---|---|
| Ramesh Patil, 52, Mumbai | T2D, HbA1c 8.4%, security supervisor on night shifts, about 4.9 h sleep | Post meal dominant T2D, night shift routine, short sleep on the last three nights, a missed morning metformin dose, dinner at 20:30 on 15 Mar |
| Fatima Shaikh, 46, Hyderabad | Prediabetes on metformin, observing Ramadan | Strong late phase secretion, falling hepatic output late in the fast, a walk to the market before iftar, fast absorbing iftar |
| Suresh Menon, 61, Kochi | Hypertension, dyslipidaemia, father had an MI at 58 | Strain ramp from about 6 Mar, simulated acute coronary event on 13 Mar 05:40 |

The demo day meals for Ramesh and Fatima are fixed so the story does not depend on random draws. All three are forced into the test split, so every forecast shown in the demo is out of sample.

## Tables

| File | Contents |
|---|---|
| `data/raw/ehr/<id>.json` | FHIR R4 bundle per patient |
| `data/raw/routines/<id>.json` | Routine declared at enrolment (rounded meal times and carbohydrate, fasting observance, shift pattern) |
| `data/raw/devices/<id>/` | Apple Health or Google Fit exports for the demo patients |
| `data/processed/cgm.parquet` | pid, minute, glucose |
| `data/processed/hr.parquet` | pid, minute, hr, steps |
| `data/processed/sleep_segments.parquet`, `sleep_nightly.parquet` | Sleep stages, nightly summaries with RMSSD |
| `data/processed/meals_log.parquet`, `doses.parquet` | Logged meals (with estimation error and missing logs), dose confirmations |
| `data/processed/events.parquet` | Cardiovascular events (ground truth) |
| `data/processed/truth_*.parquet` | Simulator ground truth for audit only; never used by any model |
| `data/prativimb.duckdb` | Everything above, loaded for the API |
| `data/splits.json` | Patient level split |

Time is stored as minutes since 14 Feb 2026 00:00 IST.

## Privacy

There is no personal data in this project, so the Digital Personal Data Protection Act 2023 and HIPAA do not apply to it. We still built the record as a real deployment would need: a FHIR `Consent` resource per patient modelled on a DPDP consent artefact (purpose: treatment; time bound; revocable), no identifiers in any model feature, and an architecture that keeps inference inside the hospital network. See `docs/MODEL_CARD.md`.

## Real data used for validation: CGMacros

CGMacros is an open access PhysioNet dataset of 45 adults in the United States (15 normoglycaemic, 16 with prediabetes, 14 with Type 2 diabetes by HbA1c) who wore a Dexcom G6 and a FreeStyle Libre Pro, plus a Fitbit, for about ten days while logging meals with known macronutrients. It is released under CC BY-NC-SA 4.0 with no credentialing or data use agreement.

* `scripts/fetch_cgmacros.sh` downloads the archive from PhysioNet's open data mirror, checks it against the published SHA-256, and extracts only the CSV files (no meal photos) into `data/external/` (gitignored).
* The data are used only for non commercial evaluation in `prativimb/eval/real_data.py`. They are not redistributed and no model is trained on them; only aggregate metrics (`reports/real_data.md`, `reports/real_data.json`) are committed.
* Mapping: Dexcom readings sampled every 5 minutes; Fitbit METs, intensity levels or steps mapped to steps per minute; meal carbohydrate scaled by the share eaten; weight converted from pounds. No sleep or medication data exist, so those features are missing and the twin uses defaults.

Citation: Gutierrez-Osuna R, Kerr D, Mortazavi B, Das A. CGMacros: a scientific dataset for personalized nutrition and diet monitoring (version 1.0.0). PhysioNet, 2025. https://doi.org/10.13026/3z8q-x658. Please also cite the original publication by Das, Kerr, Glanz, Bevier, Santiago, Gutierrez-Osuna and Mortazavi, and the PhysioNet platform (Pollard et al., Nature Health 2026).
