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
- [ ] `make data` regenerates everything from the seed in under 3 minutes.
- [ ] Two runs give identical file hashes.
- [ ] Glucose summaries are plausible per phenotype (healthy fasting 80 to 100, T2D post meal peaks 200 to 300 mg/dL).
- [ ] Hero stories visible in raw data: Ramesh post dinner spike, Fatima late fast low and post iftar rebound, Suresh HRV decline before the 13 Mar event.
- [ ] Device adapters round trip Apple Health and Google Fit style records.

### 2. Twin model
`prativimb/twin/`: extended Bergman model, EHR priors, wearable calibration, observer, scenario simulation.
- [ ] Steady state holds with no inputs; meal raises glucose and it returns to basal.
- [ ] Batch RK4 integrator agrees with `scipy.integrate.solve_ivp` within 1 mg/dL.
- [ ] Calibration recovers known parameters from twin generated data.
- [ ] Calibrated twin beats the EHR only (cold start) twin on held out days.

### 3. Residual ML and conformal
`prativimb/ml/glucose.py`, `prativimb/ml/conformal.py`.
- [ ] Physics only, ML only and hybrid models trained at 30, 60, 90, 120 min.
- [ ] Hybrid RMSE below both ablations at every horizon.
- [ ] Normalised split conformal intervals reach 90% (plus or minus 2 points) coverage on test patients.

### 4. Cardio model
`prativimb/ml/cardio.py`.
- [ ] Isolation forest, per patient z score composite, LightGBM classifier and stacked ensemble.
- [ ] Daily risk trajectory and top factors stored for every patient day.
- [ ] Suresh is flagged at least 3 days before his event.

### 5. Evaluation report
`reports/metrics.md`, `reports/metrics.json`, `reports/figures/`.
- [ ] RMSE and MARD at 30/60/120 min, Clarke zones, spike sensitivity, precision, median lead time, false alarms per patient day, ablation table.
- [ ] Cardio AUROC, AUPRC, sensitivity at 90% specificity with bootstrap intervals, calibration plot.
- [ ] Conformal coverage and width by horizon. Limitations written out.

### 6. API and streaming
`prativimb/api/`.
- [ ] Endpoints for ward, patient, forecast, what-if, cardio, note (JSON and PDF), model card, FHIR bundle.
- [ ] WebSocket replay pushes readings as the demo clock advances; the clock can be paused and set.
- [ ] pytest API tests pass.

### 7. Dashboard
`frontend/` (React, TypeScript, Vite, Observable Plot).
- [ ] Ward, patient twin, what-if, cardio week, clinical note, model card screens all render against the live API.
- [ ] Light and dark mode. Serif headings, sans data, tabular numerals. Red only for alerts.
- [ ] `npm run build` passes with no type errors.

### 8. Docs and slides
- [ ] README with every mandatory section in the required order.
- [ ] `docs/architecture.pdf` and `.png` generated from code.
- [ ] `docs/presentation.pptx` and `.pdf` (13 to 15 slides) with charts from the actual run.
- [ ] `docs/DATA.md`, `docs/MODEL_CARD.md`, `docs/VIDEO_SCRIPT.md` (20 minutes, timed).

### 9. Screenshots
- [ ] Playwright captures every screen, light mode plus one dark mode, into `docs/screenshots/`.

### 10. Final polish
- [ ] All tests pass, metrics regenerated, slides rebuilt with the final numbers.
- [ ] `scripts/check_style.py` finds no em dashes, en dashes or emoji anywhere in the repo.
- [ ] README section checklist confirmed.
