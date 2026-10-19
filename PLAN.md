# Prativimb build plan

Prativimb is a hybrid patient digital twin for Indian Type 2 diabetes and cardiovascular risk. This file lists the build stages, what each stage produces, and the check that decides whether the stage is done. Each stage ends with a commit.

## Fixed decisions

- Synthetic data only. Cohort of 200 fictional patients, 30 days of wearable data each, window 14 Feb 2026 to 15 Mar 2026 (IST). The window covers Maha Shivaratri (15 Feb), Ramadan (fasts from 19 Feb), Holi (4 Mar) and two Ekadashi days, so fasting and festival patterns are real calendar events.
- Demo clock: Sunday 15 Mar 2026, 19:45 IST. The replay service streams from there.
- Ground truth physiology is the UVA/Padova (Dalla Man) model using simglucose adult parameter sets, adapted for T2D by replacing the insulin pump with an impaired endogenous beta cell secretion model. The twin is a different, simpler model (extended Bergman minimal model). This mismatch is intentional: it is what the residual model has to learn, and it keeps the evaluation honest.
- Patient level split: 60% train, 20% conformal calibration, 20% test. The three hero patients are forced into the test split so every demo forecast is out of sample.
- Twin calibration uses days 1 to 7 of each patient. Forecasting models are trained and evaluated on days 8 to 30 only.
- Seed 20260315 for everything.

## Stages and acceptance criteria

### 1. Data generation
Produces `data/raw/` (FHIR style EHR bundles, device style exports for hero patients) and `data/processed/` (canonical parquet) plus `data/prativimb.duckdb`.
- [x] `make data` regenerates everything from the seed in under 3 minutes (about 20 s).
- [x] Two runs give identical file hashes.
- [x] Glucose summaries are plausible per phenotype (healthy fasting 80 to 100, T2D post meal peaks 200 to 300 mg/dL).
- [x] Hero stories visible in raw data: Ramesh post dinner spike, Fatima late fast low and post iftar rebound, Suresh HRV decline before the 13 Mar event.
- [x] Device adapters round trip Apple Health and Google Fit style records.

### 2. Twin model
`prativimb/twin/`: extended Bergman model, EHR priors, wearable calibration, observer, scenario simulation.
- [x] Steady state holds with no inputs; meal raises glucose and it returns to basal.
- [x] Batch RK4 integrator agrees with `scipy.integrate.solve_ivp` within 1 mg/dL.
- [x] Calibration recovers known parameters from twin generated data.
- [x] Calibrated twin beats the EHR only (cold start) twin on held out days.

### 3. Residual ML and conformal
`prativimb/ml/glucose.py`, `prativimb/ml/conformal.py`.
- [x] Physics only, ML only and hybrid models trained at 30, 60, 90, 120 min.
- [x] Hybrid RMSE below both ablations at every horizon.
- [x] Conformal intervals reach 90% (plus or minus 2 points) coverage on test patients. Implemented as conformalised quantile regression (88.7% to 89.8%).

### 4. Cardio model
`prativimb/ml/cardio.py`.
- [x] Isolation forest, per patient z score composite, LightGBM classifier and stacked ensemble.
- [x] Daily risk trajectory and top factors stored for every patient day.
- [x] Suresh is flagged at least 3 days before his event (flagged 9 Mar, event 13 Mar).

### 5. Evaluation report
`reports/metrics.md`, `reports/metrics.json`, `reports/figures/`.
- [x] RMSE and MARD at 30/60/120 min, Clarke zones, spike sensitivity, precision, median lead time, false alarms per patient day, ablation table.
- [x] Cardio AUROC, AUPRC, sensitivity at 90% specificity with bootstrap intervals, calibration plot.
- [x] Conformal coverage and width by horizon. Limitations written out.

### 6. API and streaming
`prativimb/api/`.
- [x] Endpoints for ward, patient, forecast, what-if, cardio, note (JSON and PDF), model card, FHIR bundle.
- [x] WebSocket replay pushes readings as the demo clock advances; the clock can be paused and set.
- [x] pytest API tests pass.

### 7. Dashboard
`frontend/` (React, TypeScript, Vite, Observable Plot).
- [x] Ward, patient twin, what-if, cardio week, clinical note, model card screens all render against the live API.
- [x] Light and dark mode. Serif headings, sans data, tabular numerals. Red only for alerts.
- [x] `npm run build` passes with no type errors.

### 8. Docs and slides
- [x] README with every mandatory section in the required order.
- [x] `docs/architecture.pdf` and `.png` generated from code.
- [x] `docs/presentation.pptx` and `.pdf` (13 to 15 slides) with charts from the actual run.
- [x] `docs/DATA.md`, `docs/MODEL_CARD.md`, `docs/VIDEO_SCRIPT.md` (20 minutes, timed).

### 9. Screenshots
- [x] Playwright captures every screen, light mode plus one dark mode, into `docs/screenshots/`.

### 10. Final polish
- [x] All tests pass, metrics regenerated, slides rebuilt with the final numbers.
- [x] `scripts/check_style.py` finds no em dashes, en dashes or emoji anywhere in the repo.
- [x] README section checklist confirmed.

## Outcome notes

* Every stage ran end to end; `make all` takes about 5 minutes, `make test` runs 28 tests.
* Alert design changed during evaluation: a 90% lower bound alone caught only 44% of spikes with 25 minutes' notice, so the deployed design has two tiers (watch on the point forecast, alert on the lower bound of the 50% interval chosen on calibration patients).
* Storyline deviation: for Ramesh at 19:45 the twin finds that an earlier dinner does not lower tonight's peak (lunch glucose has not settled; the ground truth agrees). The demo uses a post dinner walk and a millet swap instead, and shows the twin saying no to the earlier dinner.
* Synthea itself was not used: its modules are calibrated to the United States. A Synthea style Python generator emits FHIR R4 bundles with Indian diet, calendar and genetics instead (see docs/DATA.md).
