# Demo video script (about 20 minutes)

Unlisted YouTube upload. Screen at 1920 x 1080, browser zoom 100%, light theme unless noted. Speak slowly; the numbers below are from the committed run (seed 20260315).

## Before recording

1. `make all` (or use the committed artefacts), then in two terminals `make api` and `make web`. Open http://localhost:5173 and sign in as **Doctor**, name "Dr Rao". Keep a second private window ready to sign in as **Nurse or health educator** for the roles moment.
2. In the **Demo replay** strip at the bottom of the screen, set speed to **10x** and press **Pause**. Every time change below uses a jump button in that strip.
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
| 08:15 to 10:30 | Ramesh: patient twin, track record, acknowledge with undo, plan a meal | `/patient/PTV-0001`, Record tab |
| 10:30 to 12:30 | Try a change, a week plan and its one week check, patient view | `/patient/PTV-0001/try`, `/share/PTV-0001` |
| 12:30 to 13:45 | Fatima: hypoglycaemia to rebound around iftar | `/patient/PTV-0002` at 18:00 |
| 13:45 to 14:45 | Suresh: heart risk week | `/patient/PTV-0003?heart=26` |
| 14:45 to 15:30 | Clinical note and shift handover | `/note/PTV-0001`, `/handover` |
| 15:30 to 17:00 | Metrics and model card | `/model`, slides 8 to 10 |
| 17:00 to 18:15 | Real CGM traces | Slide 11, `reports/real_data.md` |
| 18:15 to 19:15 | Privacy, safety, limitations | Slide 14 |
| 19:15 to 20:00 | Roadmap and close | Slide 15 |

## 00:00 Introduction

Slide 1.

"I am Pushkala Yeddula from Anurag University, and I built this project on my own. This is Prativimb, Sanskrit for reflection: a digital twin of a patient that you can question. Most models tell you what is likely to happen next. A twin can also tell you what would happen if something changed: a walk after dinner, millets instead of rice, a missed dose. Everything you will see runs on synthetic, fictional patients."

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

Demo replay strip, **19:45**. Ward page.

"This is the ward at 19:45 on Sunday 15 March. It opens on the patients who need attention, not all two hundred, grouped by urgency: lows first, then likely highs, then raised heart risk. Under each alert, in grey, a few words on why: dinner, short sleep, night shift. Twenty three need attention now; the line at the top says a ward like this typically has about thirty at this hour, so tonight is ordinary. That number matters: we measured alert load, and we will come back to it."

"The line above the table says what changed since I last looked: new alerts and resolved ones, by name. Clinicians scan for change, not state." Press `j` twice and `k` once to show keyboard navigation, then open Ramesh Patil from the High glucose likely group. Point out the search box in the top bar (`/` finds any patient) and say: "`n` anywhere jumps to the next alert nobody has seen."

## 08:15 Ramesh: Today

"Ramesh, 52, a security supervisor on night shifts. Under his name, one banner: high glucose likely within two hours, peak 278 near 21:45, with everything I can do about it in one row. On the left, everyone else who needs attention; Next takes me to Savitri without going back to the ward. Today leads with 158 and steady now and the glucose forecast for 21:45.

The black line is his CGM; the teal line is the forecast with its likely range. The twin expects his usual dinner at 20:15 and a peak around 278 at 21:45. Below, on the same time axis: meals, his missed morning metformin, his daytime sleep after the night shift, steps and heart rate.

Scroll to **Why the glucose forecast says this**, open by default: the reason in one sentence, expected dinner, reduced insulin sensitivity, short sleep with the night shift, and bars showing how many mg/dL each factor adds to the peak, from exact Shapley values on the twin and SHAP on the learned correction. Under it, its track record for Ramesh: 21 alerts in the last week, 19 came true, median warning 45 minutes. Below that, one line: heart risk normal this week, which opens into the seven day view."

Click the **Record** tab. "Problems with ICD-10 codes, medicines, labs with dates, genetic markers, and what the glucose forecast has learned, for example his insulin sensitivity is about 30% of a typical adult without diabetes." **Earlier alerts and what happened** is open at the top: "Every alert this week, what the forecast said, whether it came true, how much warning it gave, and what the team did. Four highs came with no alert, and we show that too." The **Two week glucose pattern** is open at the top: "Two weeks at a glance: time in range, GMI and variability, in the international consensus format." Click **Show as table** under a chart: "every chart has a table twin, for screen readers and for anyone who wants the numbers."

In the banner, click **Mark as seen**, choose 1 hour, note "Discussed walk after dinner", confirm. "The alert stays visible but moves below the unseen ones for an hour, and the audit log records who did what. Every change offers Undo for ten seconds." Point at the Undo message, do not click it. Then click **Log a meal** in the banner: In 1 h, Millet (ragi or jowar) meal, 60 g, **Add meal**. "Ramesh says he will have ragi rotis tonight. The forecast peak drops from about 278 to about 185 straight away, because the twin now knows the meal instead of assuming his usual rice." Remove the entry again.

## 10:30 Try a change: case study

Click **Try a change** in the banner.

"Now the question a doctor actually asks: what could help tonight? The twin re-simulates the next six hours from now."

1. Click **15 min walk after the meal**: "A 15 minute walk after dinner takes about 15 mg/dL off the peak."
2. Click **Millets instead of rice**: "Millets instead of white rice, slower and smaller in carbohydrate, take about 48."
3. Click **Walk and millets**: "Together the peak falls by 57 mg/dL and he spends 40 minutes less above 180."
4. Click **Meal 1 h earlier**: "And something the twin will not promise: dinner can only move to 19:50 now, and his lunch glucose has not settled, so an earlier dinner barely helps tonight. A twin that can say no is more trustworthy than one that always agrees."
5. Drag **Sleep, last 3 nights** to 7 h and tick **Missed metformin dose** briefly to show the controls, then **Reset**.

"The page opens on the changes that would help Ramesh most tonight, as cards: half the portion, walk and millets, millets, a 30 minute walk. The top one is already showing: his peak falls from 318 to 243." Click the other cards in turn. Switch to **Next 24 hours, every meal**: "Over a whole day, a smaller portion and a 30 minute walk after every main meal matter most for him. Beyond six hours the absolute level drifts, so we read the difference between the curves."

"These curves come from the mechanistic twin, solved with scipy's adaptive solver. They are a conversation aid, not a prescription. But are they right?" Click **Walk 15 min and millets**, then **Check against the reference simulator**: "Our synthetic patients come from a richer simulator the twin never sees, and it is deterministic, so we can re-run Ramesh's evening with the change. The twin said 57 lower; the reference says 61. Across 316 moments in 40 test patients the twin gets the direction right three times in four. And it shows us its weak spot: it misses that an earlier dinner usually makes things worse. No real clinic can check a what if like this; synthetic data can."

Open **See inside the twin** and press **Play**: "This is the twin's own insides: dinner in the stomach, then the gut, glucose entering the blood, insulin action and the walk pulling glucose into muscle. On the right, millets empty more slowly and the walk lights up." Type into the box above the cards: "what if he skips rice and walks after dinner for the next week?" and press **Ask**: "The question becomes the simulator's settings, shown so I can check them. The numbers still come from the twin."

Click **Next 7 days** (a few seconds). "Over a week, a 30 minute walk after every main meal adds about 21 points of time in range. A week ahead the level drifts, so the chart shows only the change against his usual plan." Scroll up to **Plans agreed with Ramesh**: "On 6 March his doctor agreed a 15 minute walk after every main meal. The one week check compares before and after with what the forecast expected, and it checks from his steps whether he actually walked: after 3 of 20 meals. So the plan was not tested, and the dashboard says ask what got in the way, instead of claiming it failed or worked."

Back on **Today**, point to **What would sharpen this forecast**: "When the range is wide, it says what would narrow it: logging tonight's dinner would bring the 21:45 range from 204 to 334 down to about 231 to 324."

Click **Message Ramesh a walk suggestion** in the banner, then **Ramesh's phone (demo)**: the message arrives in Hindi; press **सुनें** to hear it. Press **हाँ, खाने के बाद टहलेंगे**. "The care team sees the reply at once, and the forecast now expects about 256." Demo replay strip, **22:30**: "Because the walk happened, the replay now follows the reference simulator: tonight he reached 283; the same evening without the walk would have reached about 297. Ramesh gets that message too." Return with the strip to **19:45** and remove the reply with Undo, or leave it for the handover.

Click **Share with Ramesh** in the banner, choose हिन्दी: "And this is what Ramesh takes home: large type, in Hindi or Tamil, the changes that help him most, shareable on WhatsApp or printed. From the same page he can log a meal himself, and choose what he shares: glucose, wearable data and health records through ABDM, each with a button to stop sharing. The translations are drafts for review by a native speaking clinician."

## 12:30 Fatima: hypoglycaemia to rebound

Type `/`, then "Fatima", Enter. Demo replay strip, **18:00** (iftar approaching).

"Fatima, 46, prediabetic, observing Ramadan. It is 18:00, half an hour before iftar. She is at 69 after a long fast and an afternoon walk to the market. A separate low glucose model flagged a likely low from 16:00 with 98% probability; the twin shows a low now, and a rebound to about 206 after iftar, with the reasons: a fast absorbing iftar of dates and sherbet. The alert log shows it was raised at 17:45, and that the low was forecast from 16:00. A clinician could suggest a smaller, slower iftar."

Scroll to the AGP: "Her two week profile shows the Ramadan pattern: a suhoor peak before dawn, the afternoon dip, the iftar rebound."

Demo replay strip, **19:45**.

## 13:45 Suresh: heart risk week

Find Suresh Menon from the top bar. On **Today**, open the heart risk line near the bottom and click **Earlier** until the week ends 12 Mar (or use `/patient/PTV-0003?heart=26`).

"Suresh, 61, hypertensive, father had a heart attack at 58. The heatmap compares each night with his own baseline; darker means a worse deviation. Over the week his resting heart rate climbs from 61 to 72 and his HRV falls from 38 to 23 milliseconds, with less deep and REM sleep. The risk trajectory crosses the flag threshold on 9 March, four days before the simulated event on 13 March, marked in red. For a heart alert the banner leads with Call the patient and Book a review, not a glucose change."

Optional, in the nurse window: open Manoj Naidu, click **Mark as seen**. "A nurse can mark glucose alerts as seen but not heart risk; that goes to a doctor, and the service enforces it."

## 14:45 Clinical note

Open Ramesh, click **Clinical note** next to his name; it opens as a printable sheet.

"One click turns the twin's findings into a SOAP note for the record: what the patient reported, CGM and wearable summaries, the alerts with their reasons, and the simulated options." Click **Download PDF** and show the one page PDF. Click **Festivals** in the top bar: "Each patient's twin replays Ugadi, the first Navratri fast and Eid against a usual day. Gopal Mehta would spend almost two more hours above 180 on Gudi Padwa; half the usual puran poli takes most of that off, so that is what we message him." Click **Message** on his row. On the ward, open **If tonight's 6 likely high patients made one change** : "Added up from each patient's own twin: 4 fewer hours above 180 tonight if each does what helps them most, against 2.9 if everyone took the same walk." Then click **Handover** in the top bar: "At the end of a shift: what is still open, what was seen, and what was done and by whom, ready to print or paste."

## 15:30 Metrics and model card

Open **About the model**, then slides 8 to 10.

"All metrics are on 40 test patients the models never saw, on days after the twin's calibration week. At 120 minutes the hybrid's error is 25.2 mg/dL, against 29.0 for physics alone and 27.6 for machine learning alone: the hybrid beats both parts at every horizon. Clarke zone A is 85% at one hour. The 90% intervals cover 88.7 to 89.8% of readings. The confident alert tier catches 67% of spikes at 85% precision with 0.2 false alarms per patient day; the watch tier catches 90% about 75 minutes ahead. Alert load: about 1.3 confident high alerts per patient per day, 94% of which came true, and lows are the noisiest alert. For cardiovascular risk the ensemble reaches an AUROC of 0.95, and here we have to be straight: the events and their warning signs come from our own simulator, so that number mostly shows the model learned our simulator. When we weaken the simulated warning signs to half strength it still flags 4 of 6 events; at a quarter, 1 of 6. It is a demonstration of the pipeline, not evidence about real hearts."

## 17:00 Real CGM traces

Slide 11, then `reports/real_data.md`.

"Synthetic data proves the pipeline, not the medicine, so we also ran Prativimb on CGMacros, an open access PhysioNet dataset: 45 people in the US, 14 with Type 2 diabetes, Dexcom sensors and meals with known carbohydrate. Models trained only on our synthetic Indian data land at about persistence level on these real traces. That is honest and expected. But the calibrated twin, told about each meal in advance, cuts two hour error from 38 to 30 mg/dL. That is why the planned meal box exists. And conformal intervals calibrated on synthetic data under cover on real data, 78% at two hours, and recover to 88% when the margin is refitted on local patients: exactly how a hospital would onboard this."

## 18:15 Privacy, safety, limitations

Slide 14.

"All data is synthetic, so no personal data under the DPDP Act or HIPAA was used. We still built for it: consent the patient can withdraw on screen, which stops the service using that source; roles the service checks; an audit log of every action and undo; no identifiers in features; on premises inference; and device adapters for Apple Health, Google Fit and Health Connect. Limitations: synthetic ground truth is still a model; six cardiac events is few; conformal coverage is approximate with correlated readings and lower below 70; unlogged meals cause most misses. This is decision support only, not a diagnosis."

## 19:15 Roadmap and close

Slide 15, then back to slide 1 for the team.

"Next: validation on de-identified real data, including real cardiac outcomes, federated learning of the residual model across hospitals so data never leaves them, a real ABDM consent manager behind the screens we built, refitting each twin as weeks of data arrive, and a prospective clinic pilot with alert burden and time in range as outcomes. Prativimb: a reflection of the patient you can question. Thank you."
