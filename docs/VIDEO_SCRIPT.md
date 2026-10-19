# Demo video script (about 20 minutes)

Unlisted YouTube upload. Screen at 1920 x 1080, browser zoom 100%, light theme unless noted. Speak slowly; the numbers below are from the committed run (seed 20260315).

## Before recording

1. `make all` (or use the committed artefacts), then in two terminals `make api` and `make web`. Open http://localhost:5173.
2. In the masthead set replay speed to **10x** and press **Pause**. Use **Jump to** for every time change below.
3. Have `docs/presentation.pdf`, `docs/architecture.png` and `reports/metrics.md` open in other tabs.
4. Close notifications. Record the terminal for the `make data` moment in section 5.

## Timeline

| Time | Section | Screen |
|---|---|---|
| 00:00 to 01:00 | Introduction | Slide 1 |
| 01:00 to 02:30 | The problem | Slide 2 |
| 02:30 to 04:00 | Why a twin, our four ideas | Slides 3 and 4 |
| 04:00 to 05:30 | Architecture | Slide 5 |
| 05:30 to 07:00 | Data | Slide 6, terminal, `data/raw` |
| 07:00 to 08:15 | Ward view | Dashboard `/` |
| 08:15 to 10:30 | Ramesh: patient twin, acknowledge, plan a meal | `/patient/PTV-0001` |
| 10:30 to 12:30 | What if case study, ranked levers, patient view | `/patient/PTV-0001/whatif`, `/share/PTV-0001` |
| 12:30 to 13:45 | Fatima: hypoglycaemia to rebound around iftar | `/patient/PTV-0002` at 18:00 |
| 13:45 to 14:45 | Suresh: cardio week | `/patient/PTV-0003/cardio` |
| 14:45 to 15:30 | Clinical note | `/patient/PTV-0001/note` |
| 15:30 to 17:00 | Metrics and model card | `/model`, slides 8 to 10 |
| 17:00 to 18:15 | Real CGM traces | Slide 11, `reports/real_data.md` |
| 18:15 to 19:15 | Privacy, safety, limitations | Slide 14 |
| 19:15 to 20:00 | Roadmap and close | Slide 15 |

## 00:00 Introduction

Slide 1.

"We are `<TeamName>` from `<CollegeName>`. This is Prativimb, Sanskrit for reflection: a digital twin of a patient that you can question. Most models tell you what is likely to happen next. A twin can also tell you what would happen if something changed: a walk after dinner, millets instead of rice, a missed dose. Everything you will see runs on synthetic, fictional patients."

## 01:00 The problem

Slide 2.

"India has about 101 million adults with diabetes and 136 million with prediabetes. Most are reviewed every three months, but glucose, sleep and heart rhythm change every five minutes. Wearables record that stream, yet they show the past. Risk scores say who is at risk; they do not say what to change today, or how confident they are. At the bedside a clinician wants four things: who will go out of range soon, why in plain words, what would help, and who is drifting towards a cardiac event."

## 02:30 Why a twin

Slides 3 and 4.

"A classifier learns from data only and answers one question. Our twin is a physiological model, the Bergman minimal model extended for meals, exercise, sleep debt, circadian rhythm, night shifts and metformin, fitted to each patient's first week. A gradient boosted model learns only what the physics misses. Physics gives plausibility and extrapolation; machine learning gives accuracy.

Four ideas: the hybrid twin; counterfactual simulation; honest uncertainty, where alerts fire only when a calibrated lower bound crosses the threshold; and an India first design, with rice, roti, idli and iftar meals, Ramadan, Shivaratri and Holi in the calendar, and night shift workers."

## 04:00 Architecture

Slide 5 (or `docs/architecture.png`).

Point left to right: "EHR arrives as FHIR bundles; wearables through Apple Health and Google Fit adapters; everything lands in DuckDB. EHR priors start the twin, a week of data calibrates it. The teal boxes are the hybrid core: physics model, residual LightGBM, and the conformal layer. On the right, the alert engine, explanations and the what-if simulator, served by FastAPI and a WebSocket replay to the dashboard. A separate ensemble watches seven day wearable windows for cardiovascular risk."

## 05:30 Data

Slide 6, then the terminal.

"Two hundred fictional patients, thirty days each, from 14 February to 15 March 2026, a window that contains Maha Shivaratri, most of Ramadan and Holi. Glucose comes from the UVA/Padova simulator with simglucose parameters and its Dexcom noise model, adapted for Type 2 diabetes with impaired insulin secretion. Heart rate every minute, sleep stages, nightly HRV and steps come from our generators."

Run `make data` on camera (about 20 seconds). Show `data/raw/ehr/PTV-0001.json` (a FHIR bundle with LOINC codes, the TCF7L2 genotype and a Consent resource) and `data/raw/devices/PTV-0001/apple_health_export.xml`.

"One command, one seed, identical files every time. The demo patients' streams go through the same Apple Health and Google Fit parsers a real integration would use."

## 07:00 Ward view

Jump to **15 Mar 19:45**. Ward page.

"This is the ward list at 19:45 on Sunday 15 March. Two hundred patients sorted by priority. Red means a confident alert: glucose above 180 likely within two hours, with the expected crossing time and peak. Grey outline is a watch, shown but not pushed. The next column is the cardiovascular risk of an event in three days. Sparklines are the last 24 hours, the shaded band is 70 to 180."

"The line above the table says what changed since I last looked: new alerts and resolved ones, by name. Clinicians scan for change, not state." Press `j` twice and `k` once to show keyboard navigation, then **Glucose alerts**, then **All patients**. Press Enter on Ramesh Patil.

## 08:15 Ramesh: the patient twin

"Ramesh, 52, a security supervisor on night shifts, HbA1c 8.4%. Left column is the record: problems with ICD-10 codes, medications, labs with dates and previous values, genetic markers, and the twin's own parameters: his insulin sensitivity is about 30% of a typical adult without diabetes.

In the centre, the black line is his CGM. Right now he is 158 and drifting down. The teal line is the hybrid forecast with its 90% interval; the dashed grey line is the twin alone. The twin expects his usual dinner at 20:15 and a peak around 278 at 21:45. Below, on the same time axis: meals, his missed morning metformin, his daytime sleep after the night shift, steps and heart rate.

On the right, the alert, with its reason in one sentence: expected dinner, reduced insulin sensitivity, and short sleep with the night shift. The bars show how many mg/dL each factor adds to the peak, combining exact Shapley values from the twin with SHAP from the learned correction. The alert log shows the twin has held this alert since 19:15, about two hours before the predicted crossing."

Scroll to the ambulatory glucose profile: "Two weeks at a glance: time in range, GMI and variability, in the international consensus format." Click **Show as table** under a chart: "every chart has a table twin, for screen readers and for anyone who wants the numbers."

Back on the alert, click **Acknowledge**, choose 1 h, note "Discussed walk after dinner", confirm. "The alert stays visible but drops down the ward list for an hour, and the activity log records who did what." Then under **Tell the twin about a meal**: In 1 h, Millet (ragi or jowar) meal, 60 g, **Tell the twin**. "Ramesh says he will have ragi rotis tonight. The forecast peak drops from about 278 to about 185 straight away, because the twin now knows the meal instead of assuming his usual rice." Remove the entry again.

## 10:30 What if: case study

Click **What if**.

"Now the question a doctor actually asks: what could help tonight? The twin re-simulates the next six hours from now."

1. Click **15 min walk after the meal**: "A 15 minute walk after dinner takes about 15 mg/dL off the peak."
2. Click **Millets instead of rice**: "Millets instead of white rice, slower and smaller in carbohydrate, take about 48."
3. Click **Walk and millets**: "Together the peak falls by 57 mg/dL and he spends 40 minutes less above 180."
4. Click **Meal 1 h earlier**: "And something the twin will not promise: dinner can only move to 19:50 now, and his lunch glucose has not settled, so an earlier dinner barely helps tonight. A twin that can say no is more trustworthy than one that always agrees."
5. Drag **Sleep, last 3 nights** to 7 h and tick **Missed metformin dose** briefly to show the controls, then **Reset**.

Scroll to **Levers for this patient, ranked**: "The twin tries every change on its own and ranks them for Ramesh tonight: half the portion, walk and millets, millets, a 30 minute walk. Click any row to show it." Switch to **Next 24 h, every meal**: "Over a whole day, a smaller portion and a 30 minute walk after every main meal matter most for him. Beyond six hours the absolute level drifts, so we read the difference between the curves."

"These curves come from the mechanistic twin, solved with scipy's adaptive solver. They are a conversation aid, not a prescription."

Click **Patient view** on the patient header, choose हिन्दी: "And this is what Ramesh takes home: large type, in Hindi or Tamil, the two or three changes that help him most, shareable on WhatsApp or printed. The translations are drafts for review by a native speaking clinician."

## 12:30 Fatima: hypoglycaemia to rebound

Go to the ward, open Fatima Shaikh. Jump to **15 Mar 18:00**.

"Fatima, 46, prediabetic, observing Ramadan. It is 18:00, half an hour before iftar. She is at 69 after a long fast and an afternoon walk to the market. A separate low glucose model flagged a likely low from 16:00 with 98% probability; the twin shows a low now, and a rebound to about 206 after iftar, with the reasons: a fast absorbing iftar of dates and sherbet. The alert log shows it was raised at 17:45, and that the low was forecast from 16:00. A clinician could suggest a smaller, slower iftar."

Scroll to the AGP: "Her two week profile shows the Ramadan pattern: a suhoor peak before dawn, the afternoon dip, the iftar rebound."

Jump back to **15 Mar 19:45**.

## 13:45 Suresh: cardio week

Open Suresh Menon, **Cardio week**. Click **Previous day** until the window ends 12 Mar (or use `/patient/PTV-0003/cardio?end=26`).

"Suresh, 61, hypertensive, father had a heart attack at 58. The heatmap compares each night with his own baseline; darker means a worse deviation. Over the week his resting heart rate climbs from 61 to 72 and his HRV falls from 38 to 23 milliseconds, with less deep and REM sleep. The risk trajectory crosses the flag threshold on 9 March, four days before the simulated event on 13 March, marked in red. The factors are worded against his own baseline."

## 14:45 Clinical note

Open Ramesh, **Clinical note**.

"One click turns the twin's findings into a SOAP note for the record: what the patient reported, CGM and wearable summaries, the alerts with their reasons, and the simulated options." Click **Download PDF** and show the one page PDF.

## 15:30 Metrics and model card

Open **Model card**, then slides 8 to 10.

"All metrics are on 40 test patients the models never saw, on days after the twin's calibration week. At 120 minutes the hybrid's error is 25.2 mg/dL, against 29.0 for physics alone and 27.6 for machine learning alone: the hybrid beats both parts at every horizon. Clarke zone A is 85% at one hour. The 90% intervals cover 88.7 to 89.8% of readings. The confident alert tier catches 67% of spikes at 85% precision with 0.2 false alarms per patient day; the watch tier catches 90% about 75 minutes ahead. For cardiovascular risk the ensemble reaches an AUROC of 0.95, but with only six test events the interval is wide, and we say so."

## 17:00 Real CGM traces

Slide 11, then `reports/real_data.md`.

"Synthetic data proves the pipeline, not the medicine, so we also ran Prativimb on CGMacros, an open access PhysioNet dataset: 45 people in the US, 14 with Type 2 diabetes, Dexcom sensors and meals with known carbohydrate. Models trained only on our synthetic Indian data land at about persistence level on these real traces. That is honest and expected. But the calibrated twin, told about each meal in advance, cuts two hour error from 38 to 30 mg/dL. That is why the planned meal box exists. And conformal intervals calibrated on synthetic data under cover on real data, 78% at two hours, and recover to 88% when the margin is refitted on local patients: exactly how a hospital would onboard this."

## 18:15 Privacy, safety, limitations

Slide 14.

"All data is synthetic, so no personal data under the DPDP Act or HIPAA was used. We still built for it: a consent artefact per record, no identifiers in features, on premises inference, ABDM consent flows in the roadmap. Limitations: synthetic ground truth is still a model; six cardiac events is few; conformal coverage is approximate with correlated readings and lower below 70; unlogged meals cause most misses. This is decision support only, not a diagnosis."

## 19:15 Roadmap and close

Slide 15, then back to slide 1 for the team.

"Next: validation on de-identified real data, federated learning of the residual model across hospitals so data never leaves them, ABDM and real device APIs, and a prospective clinic pilot. Prativimb: a reflection of the patient you can question. Thank you."
