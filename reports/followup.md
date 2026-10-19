# Alert load and how far the heart risk result can be trusted

Synthetic data only. Test patients (40), days 8 to 30, checked every 15 minutes with the deployed service code.

## 1. Alert load

| Alert | Per patient per day |
|---|---:|
| High glucose likely (pushed to the ward) | 1.33 |
| Glucose may go high (shown on the patient page only) | 1.89 |
| Low glucose now or likely within the hour | 1.06 |
| Raised heart risk (new flags per patient per week) | 0.15 |

Of 1,204 confident high glucose alerts, **94% came true** (glucose above 180 for 15 minutes within 2 h 15 min). This counts an alert as true even if glucose had already been above 180 shortly before; the stricter definition in metrics.md, which needs a fresh rise, gives 85%.

On a ward of 200 patients like these, the Needs attention list would hold a median of **25** patients (90th percentile 41). It is busiest around 13:00 (45 on average, after lunch) and quietest around 15:00 (14).

Lows are the noisiest alert: most are brief dips just under 70 in people without diabetes. Folding a repeat alert into the previous one when it comes within 3 hours would leave 1.26 high and 0.82 low glucose pushes per patient per day without hiding any patient from the list.

## 2. Heart risk: stress test against our own simulator

The heart events and the warning signs before them come from the same generator the model learned from, so the headline result (AUROC 0.95) mostly shows that the model learned that generator. Here the warning signs in the ten days before each test event are weakened, while illness episodes that look similar keep full strength. Same model, same threshold.

| Strength of warning signs | AUROC | Events flagged in the 3 days before | Specificity |
|---|---:|---:|---:|
| 100% | 0.95 | 5 of 6 | 94.4% |
| 75% | 0.94 | 5 of 6 | 94.5% |
| 50% | 0.89 | 4 of 6 | 94.5% |
| 25% | 0.74 | 1 of 6 | 94.5% |

675 test windows, 17 positive. With 6 test events every row is uncertain.

What this means: at half the simulated strength the flag catches 4 of 6 events, and at a quarter 1 of 6, at the same false alarm rate. The model is only as good as the resemblance between our simulated warning signs and real ones. The heart risk flag is a demonstration of the pipeline (wearable baselines, stacking, explanation, ward workflow), not evidence that it predicts real events. That needs real outcomes; open datasets that pair continuous wearable data with adjudicated cardiac events are not available without a data use agreement, which this project does not use.
