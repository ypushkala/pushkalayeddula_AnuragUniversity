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
- [x] `docs/DATA.md`, `docs/MODEL_CARD.md`.

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

## Version 1.1 improvements

- [x] Planned and eaten meals entered from the dashboard change the twin's prior and the features immediately.
- [x] Acknowledge and snooze alerts, with an append only audit log.
- [x] Real data validation on CGMacros (open access, PhysioNet): `make realdata`, `reports/real_data.md`.
- [x] Levers ranked per patient; what-if over 24 hours across every main meal.
- [x] Low glucose as its own event: compression artefact filter (validated against injected dips) and a classifier.
- [x] Ward: since you last looked, keyboard navigation, compact rows, sticky header.
- [x] Patient view in English, Hindi and Tamil with print and WhatsApp sharing (translations marked for review).
- [x] Phone and tablet layouts, skeletons, band explained in words, a table twin for every chart.
- [x] axe-core audit clean for WCAG 2.1 A and AA on every screen, light and dark.

## Version 1.2: easier to use

- [x] Larger type (16 px base), bigger charts and controls.
- [x] Ward opens on "Needs attention"; five columns; glucose trend in words; one line change summary.
- [x] Patient Overview leads with one sentence and the chart; reasons, meal entry, history and the two week pattern open on demand.
- [x] Health record, Heart health and Clinical note are separate tabs; breadcrumb back to the ward.
- [x] What if starts with the best changes as cards; custom controls and full tables are one click away.
- [x] Masthead reduced to the clock, Play, and Replay and Settings menus; plain language problem names and heart reasons.
- [x] Accessibility audit still clean in both themes.

## Version 1.3: easier to move around

- [x] Slim list of patients needing attention beside every patient page; Previous and Next (Alt and arrows); ward keeps its scroll position.
- [x] One alert banner under the name with Mark as seen, Try a change, Log a meal and Share with the patient.
- [x] Three task tabs: Today, Try a change, Record. Heart risk folded into Today as a one line summary that opens into the week. Clinical note is a printable sheet at /note/:id.
- [x] Fewer collapsed sections; collapsed ones carry a preview line; the reasons are open by default.
- [x] Demo controls moved to a separate Demo replay strip at the bottom.
- [x] Patient search in the top bar (/ or Ctrl K).
- [x] One vocabulary: glucose forecast, Try a change, heart risk, High glucose likely, Low glucose now, Mark as seen. Old addresses redirect.
- [x] Accessibility audit clean in both themes; 34 tests pass.

## Version 1.4: evidence, follow up, roles and consent

- [x] Alert load measured with the deployed code on test patients (`reports/followup.md`); ward compares today's count with a typical day at that hour.
- [x] Heart risk stress test against our own simulator; stated plainly on the model page, model card, README and video.
- [x] Earlier alerts and what happened, per patient: outcome, warning time, actions, highs with no alert; track record on Today.
- [x] First week mode: record based parameters before day 7, possible highs not pushed, explained on screen; demo jump to 17 Feb.
- [x] 24 hour and 7 day what ifs show the change against the usual plan; levels on request.
- [x] Banner actions by alert type (check now, call, book a review); Mark as seen per alert; Clinical note in the banner; tidier header.
- [x] Ward and patient list grouped by urgency with reasons; list count, fade and More below; deep links into the heart section.
- [x] n for the next unseen alert; shift handover page; daily digest; desktop notifications for confirmed alerts only.
- [x] Undo for 10 seconds on acknowledgements, actions, meals, plans and consent; first use tips; loading previews.
- [x] Patients log meals and manage consent from their page; units, time zone and larger text in Settings.
- [x] Insulin (population action), evening metformin timing, week plans with a one week adherence and outcome check.
- [x] Roles (doctor, nurse or health educator, patient) checked by the API; synthetic ABHA; simulated ABDM consent; Health Connect adapter.
- [x] 43 tests pass; accessibility audit clean on 11 screens in both themes; tests use a temporary store.

## Version 1.5: what makes it stand out

- [x] Reference simulator restartable from saved state; rebuilt patients match the generated data exactly; midnight checkpoints for all patients.
- [x] What ifs checked against the reference: per change on Try a change, and across 316 moments in 40 test patients (`reports/counterfactual.md`, model page, model card).
- [x] What would sharpen the forecast: the meal's usual spread re-run through the twin, plus fingerstick, watch and sensor gaps.
- [x] See inside the twin: animated stomach, gut, blood, insulin action and walking, usual against the change.
- [x] Ask in plain words: offline phrase matcher, optional language model behind an API key, settings shown for checking.
- [x] The loop with the patient: nudge from the banner, the patient's phone in Hindi, Tamil or English, replies, a planned walk entering the forecast, the replay following the reference, the result to both sides.
- [x] Festival planner (Ugadi and Gudi Padwa, Chaitra Navratri, Eid al-Fitr), ward level what if, twin health with refit, Listen buttons.
- [x] Fixed: glucose already above 180 now has its own card instead of No alerts.
- [x] 49 tests pass; accessibility audit clean on 13 screens and the interactive panels in both themes.

## Version 1.5.1: the smaller ideas, taken further

- [x] Festival planner: state specific festival and dish, each patient's best suggestion and minutes saved, messages to one patient or all in their language, call list, coming up line on Today.
- [x] Ward what if: every change at once against each patient's own best change, optionally with possible highs; message each patient their best change (skips anyone messaged in the last 6 hours).
- [x] Twin health: week by week error, an out of sample refit test before refitting, refit wording that follows the test, fit scan started with the service.
- [x] Listening: sentence by sentence with progress, slower option, voice picker, units in words, English fallback when no Hindi or Tamil voice, listen to all messages.

