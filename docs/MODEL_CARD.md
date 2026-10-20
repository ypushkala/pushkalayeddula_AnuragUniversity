# Model card: Prativimb hybrid patient twin, version 1.1

> Decision support only, not a diagnosis. Every forecast, flag and simulation needs a clinician's judgement.

The same content, with live numbers, is on the dashboard at `/model`. Full metrics: `reports/metrics.md`.

## Model details

| | |
|---|---|
| Developers | `<TeamName>`, `<CollegeName>` |
| Version | 1.1, October 2026 |
| Type | Hybrid: mechanistic ODE twin per patient, gradient boosted residual model, conformal intervals; separate cardiovascular ensemble |
| Code | `prativimb/twin/` (twin), `prativimb/ml/` (residual, conformal, cardio, explanations) |
| Licence | MIT |
| Contact | `<team email>` |

### Components

1. **Twin.** Extended Bergman minimal model with seven states (glucose, remote insulin action, insulin, stomach and gut carbohydrate, exercise, metformin level). Known modifiers: circadian insulin sensitivity, three night sleep debt, night shift misalignment, dawn effect, metformin regularity, food specific absorption speed. Eight personal parameters (insulin sensitivity, glucose effectiveness, basal glucose, absorption rate, secretion gain, dawn amplitude, exercise uptake, carbohydrate effect).
2. **Personalisation.** An EHR prior (HbA1c, BMI, fasting glucose, TCF7L2 genotype, diagnosis, age) then maximum a posteriori least squares (scipy) on days 1 to 7 of CGM, logged meals, steps and doses. Forecasts start from a six hour observer warm up on CGM.
3. **Residual model.** LightGBM per horizon (30, 60, 90, 120 min) predicts the twin's error from CGM history and trend, logged and expected meals, steps and heart rate, completed sleep, medication adherence, EHR covariates and twin parameters.
4. **Uncertainty.** Conformalised quantile regression (Romano, Patterson and Candes 2019), written by hand in `prativimb/ml/conformal.py`, calibrated on 40 held out patients. The display band is 90%. The alert tier uses the lower bound of the 50% interval, a level chosen on calibration patients as the most sensitive one with at most 0.10 false alarms per patient day.
5. **Cardiovascular ensemble.** Seven day wearable windows (resting heart rate, nightly RMSSD, sleep architecture, awakenings, efficiency, steps) with per patient baseline z scores; isolation forest and a composite z score (unsupervised), LightGBM (supervised on synthetic episodes), stacked by logistic regression on calibration patients. Operating threshold at 95% specificity on calibration patients.
6. **Low glucose model.** LightGBM classifier for glucose below 70 mg/dL within 60 minutes (two consecutive readings), trained on labels cleaned by a compression artefact filter; threshold 0.95 chosen on calibration patients for at most 0.25 false alarms per patient day. A fast fall during sleep is shown as probable sensor compression, not as a low.
7. **Clinician input.** Planned meals replace the routine slot in the twin's prior and in the features; eaten meals join the log. Alert acknowledgements quieten an alert for a chosen period. Both are kept with an audit trail.
8. **Explanations.** Exact Shapley values over six twin inputs (upcoming meal, recent meals, activity, sleep and shift, medication, personal physiology) plus TreeSHAP of the residual model, both in mg/dL of predicted peak, worded as one clinical sentence. Cardiovascular factors are SHAP values grouped by measure and worded against the patient's own baseline.

## Intended use

* Remote monitoring of adults with prediabetes or Type 2 diabetes who wear a CGM and a wrist band, by a clinical team.
* Two hour glucose forecasts with calibrated uncertainty; early warning of rises above 180 mg/dL and of lows.
* Weekly review of cardiovascular drift from wearables.
* Shared decision making: exploring what if questions with the patient.

## Out of scope

* Insulin dosing, closed loop control, Type 1 diabetes, gestational diabetes, children.
* Diagnosis or triage of acute coronary syndrome.
* Any use on real patients before prospective validation, regulatory review (CDSCO Software as a Medical Device pathway) and local governance.

## Training and evaluation data

Synthetic only (see `docs/DATA.md`). 200 fictional patients, 30 days each. Split by patient: 120 train, 40 calibration, 40 test; the three demo patients are in test. Twins calibrate on days 1 to 7; every metric is computed on days 8 to 30 of test patients.

## Factors

Phenotype (healthy, prediabetes, T2D), diet region, fasting observance (Ramadan, Hindu fasts), night shift work, medication class, device platform. Performance by phenotype and by glucose range is in `reports/metrics.md`; interval coverage drops in the hypoglycaemic range.

## Metrics (test patients)

### Glucose forecasting (Event A)

| Model | RMSE 30 min | RMSE 60 min | RMSE 120 min | MARD 60 min |
|---|---:|---:|---:|---:|
| Twin, EHR prior only | 25.8 | 33.4 | 35.2 | 16.1% |
| Twin, calibrated (physics only) | 16.7 | 24.8 | 29.0 | 13.4% |
| LightGBM only | 13.7 | 21.6 | 27.6 | 11.5% |
| **Hybrid** | **12.9** | **20.2** | **25.2** | **11.1%** |

Clarke error grid, hybrid: zone A 94.2% (30 min), 85.4% (60 min), 79.3% (120 min); zones C to E 1.4%, 2.5%, 3.1%.

| Spike alert policy | Sensitivity | Precision | Median lead | False alarms per patient day |
|---|---:|---:|---:|---:|
| Alert tier (lower bound of 50% interval) | 67.1% | 85.2% | 30 min | 0.20 |
| Watch tier (hybrid point forecast) | 90.3% | 69.8% | 75 min | 0.65 |
| Lower bound of 90% interval | 43.7% | 88.8% | 25 min | 0.10 |

1,599 spike onsets over 920 patient days.

| Horizon | 90% interval coverage | Median width |
|---|---:|---:|
| 30 min | 89.8% | 36 mg/dL |
| 60 min | 89.2% | 50 mg/dL |
| 90 min | 88.7% | 57 mg/dL |
| 120 min | 88.7% | 64 mg/dL |

### Low glucose

| Policy | Lows | Flagged in advance | Precision | Median lead | False alarms per patient day |
|---|---:|---:|---:|---:|---:|
| Low glucose classifier | 720 | 37% | 61% | 10 min | 0.19 |
| Point forecast below 70 | 720 | 18% | 68% | 18 min | 0.07 |

Compression artefact filter against injected dips: 144 of 235 found, 63% of flagged readings are true artefacts.

### Real CGM traces (CGMacros, 45 participants)

| Model | RMSE 30 min | RMSE 60 min | RMSE 120 min |
|---|---:|---:|---:|
| Persistence | 19.7 | 28.6 | 38.3 |
| Twin, routine prior | 22.3 | 32.1 | 38.4 |
| Hybrid, synthetic trained | 19.3 | 29.5 | 36.7 |
| **Twin, meals announced** | **20.7** | **26.1** | **29.6** |

90% interval coverage on real data: 83% to 78% with synthetic calibration; 87% to 88% after refitting the conformal margin on half the participants. See `reports/real_data.md`.

### Cardiovascular risk flag (Event B)

675 windows, 17 positive (event in the next 3 days), 6 distinct events, prevalence 2.5%. Patient level bootstrap 95% intervals.

| Detector | AUROC | AUPRC | Sensitivity at 90% specificity |
|---|---|---|---:|
| Isolation forest | 0.77 (0.65 to 0.92) | 0.24 (0.02 to 0.58) | 41% |
| Baseline z score composite | 0.92 (0.87 to 0.98) | 0.32 (0.07 to 0.59) | 76% |
| LightGBM | 0.95 (0.90 to 0.99) | 0.36 (0.11 to 0.65) | 88% |
| **Stacked ensemble** | **0.95 (0.90 to 0.99)** | **0.36 (0.11 to 0.65)** | **88%** |

At the operating threshold (6.9% risk): specificity 94.4%, 5 of 6 events flagged in the 3 days before (median lead 3 days), 7.3% of patient days flagged. Brier score 0.020.

**How far to trust this.** The events and the warning signs before them come from the same simulator the model learned from, so these numbers mostly show that the model learned that simulator. Stress test (same model, same threshold), weakening the simulated warning signs in the ten days before each test event toward the patient's own baseline while illness episodes keep full strength:

| Strength of warning signs | AUROC | Events flagged in the 3 days before | Specificity |
|---|---:|---:|---:|
| 100% | 0.95 | 5 of 6 | 94.4% |
| 75% | 0.94 | 5 of 6 | 94.5% |
| 50% | 0.89 | 4 of 6 | 94.5% |
| 25% | 0.74 | 1 of 6 | 94.5% |

There is no validation on real cardiac outcomes; open datasets pairing continuous wearable data with adjudicated events need a data use agreement, which this project does not use.

### What if answers, checked against the reference simulator

The synthetic patients come from a richer, deterministic simulator (UVA/Padova based, `prativimb/data/physiology.py`) that the twin never sees. Any patient can be rebuilt exactly (largest difference 0.00003 mg/dL) and re-run from any minute with one change applied to what they actually ate. 316 moments, 40 minutes before a real main meal, in 40 test patients; 8 changes; 6 hour window; the twin sees only data up to that moment and the declared routine.

| Change | Twin, average change in peak | Reference | Direction agrees | Typical error |
|---|---:|---:|---:|---:|
| Walk 15 min after the meal | -6 | -9 | 71% | 6 |
| Walk 30 min after the meal | -13 | -17 | 83% | 11 |
| Millets instead of white rice | -20 | -22 | 83% | 11 |
| Roti instead of rice | -9 | -10 | 85% | 4 |
| Brown rice instead of white rice | -10 | -11 | 84% | 5 |
| Half the portion | -31 | -36 | 91% | 11 |
| Meal 1 h earlier | +0 | +10 | 31% | 13 |
| Walk 15 min and millets | -23 | -26 | 83% | 14 |

mg/dL. Overall direction agreement 76%, correlation 0.73; the reference's best change is the twin's first choice 69% of the time and in its top two 85%. Known weaknesses: walks slightly underestimated; an earlier meal on top of an unsettled previous meal is not penalised enough. Not checked: sleep, missed doses, night shifts and insulin, which act through day level factors in the reference. This tests structure against a second model of the same physiology; it is necessary, not sufficient.

### Alert load

Per patient per day on test patients: 1.33 confident high glucose alerts (94% came true within 2 h 15 min, counting rises that continue an earlier high), 1.89 possible highs (shown on the patient page only), 1.06 low glucose alerts; 0.15 new heart risk flags per patient per week. A 200 patient ward would hold a median of 25 patients on the Needs attention list (90th percentile 41). Details: `reports/followup.md`.

### First week of a new patient

Before day 7 the forecast uses parameters estimated from the health record (median error over that week 28.3 mg/dL, against 19.9 once fitted). The dashboard says so, keeps possible highs off the ward list, and still flags lows.

## Ethical considerations

* **Privacy.** No personal data was processed. The design assumes DPDP Act 2023 obligations for a real deployment: purpose limited, time bound, revocable consent (modelled as a FHIR `Consent` per patient), data minimisation (no identifiers in features), on premises inference, audit logging, ABDM consent manager integration.
* **Automation bias.** Alerts carry their reasons and their uncertainty; the alert tier is deliberately conservative; the what-if page says "a conversation aid, not a prescription".
* **Equity.** The synthetic cohort spans regions, religions and both sexes, but it encodes our assumptions. Real data may reveal subgroup gaps (for example in women, older adults or people with CKD) that synthetic data cannot.
* **Alarm fatigue.** Two tiers: only the confident tier is pushed to the ward list and to notifications. The ward groups alerts by urgency and shows why each fired; acknowledgements quiet an alert for a chosen time; alert load is measured and reported (above).
* **Accountability.** Roles (doctor, nurse or health educator, patient) are checked by the service; heart risk alerts and plans need a doctor; every action, undo and consent change is in the audit log.

## Caveats and limitations

* Synthetic ground truth is still a model; these numbers show the method works end to end, not clinical performance.
* Only 6 cardiovascular events among test patients; intervals are wide and the supervised model has learned our simulated prodrome (see the stress test).
* What if answers agree with the reference simulator in direction 76% of the time; an earlier meal is the weak spot (31%).
* The forecast sharpening estimate assumes the meal's spread and the rest of the uncertainty are independent; it is an estimate, labelled as one.
* Twin health uses a threshold set on this synthetic cohort (errors 30% worse than the first week of use, or a 10 mg/dL bias); real patients will drift more and the threshold needs local tuning.
* On real traces, models trained only on synthetic data perform at about persistence level; local retraining and per site conformal recalibration are prerequisites for deployment. Twin forecasts start from the observer estimate rather than the last reading, which costs accuracy at 30 minutes.
* Low glucose forecasting has a short median lead and modest sensitivity; most lows here are brief level 1 dips in people without diabetes.
* Conformal guarantees assume exchangeability; within patient correlation makes coverage approximate, and it is lower below 70 mg/dL.
* Forecasts rely on the declared routine; unlogged and unplanned meals are the main source of error.
* The dawn amplitude is usually not identifiable from one week and fits to zero.
* What-if results come from the mechanistic twin only (the learned correction is trained for 2 hour forecasts); effect sizes for walking and food swaps are only as good as the calibration week's excitation.
