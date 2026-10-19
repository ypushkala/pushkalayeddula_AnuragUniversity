# Validation on real CGM traces (CGMacros)

Data: CGMacros v1.0.0 (Gutierrez-Osuna, Kerr, Mortazavi and Das; PhysioNet 2025; doi:10.13026/3z8q-x658), open access under CC BY-NC-SA 4.0. Dexcom G6 every 5 minutes, Fitbit heart rate and activity, meals with known carbohydrate. No sleep or medication data. The data are not redistributed here; `scripts/fetch_cgmacros.sh` downloads and checks them, `make realdata` reruns this report.

Protocol: each twin is calibrated on the participant's first 5 days, with a routine prior built from the median meal times and carbohydrate of those days. Forecasts are scored from day 6 onward every 10 minutes. The residual and ML only models were trained on synthetic Indian data only and are applied without retraining (zero shot).

| Group | Participants | Horizon | Persistence | Twin, routine | LightGBM (synthetic) | Hybrid (synthetic) | Twin, meals announced |
|---|---:|---|---:|---:|---:|---:|---:|
| all | 45 | 30 min | 19.7 | 22.3 | 19.9 | 19.3 | 20.7 |
|  |  | 60 min | 28.6 | 32.1 | 29.0 | 29.5 | 26.1 |
|  |  | 120 min | 38.3 | 38.4 | 38.6 | 36.7 | 29.6 |
| T2D | 14 | 30 min | 22.2 | 24.1 | 21.2 | 21.1 | 22.2 |
|  |  | 60 min | 34.7 | 37.8 | 32.6 | 34.5 | 30.6 |
|  |  | 120 min | 48.6 | 48.8 | 48.4 | 46.3 | 37.1 |
| prediabetes | 16 | 30 min | 19.6 | 20.6 | 19.4 | 18.1 | 18.2 |
|  |  | 60 min | 28.0 | 31.2 | 26.9 | 28.4 | 23.0 |
|  |  | 120 min | 36.4 | 35.9 | 33.1 | 33.9 | 25.7 |
| normoglycaemia | 15 | 30 min | 17.3 | 22.1 | 19.1 | 18.8 | 21.6 |
|  |  | 60 min | 22.5 | 27.0 | 27.3 | 25.3 | 24.5 |
|  |  | 120 min | 28.3 | 29.2 | 33.2 | 28.9 | 25.2 |

RMSE in mg/dL against the Dexcom reading at the target time.

| Horizon | Coverage, synthetic calibration | Median width | Coverage, recalibrated on site | Median width |
|---|---:|---:|---:|---:|
| 30 min | 82.5% | 41 mg/dL | 88.0% | 51 mg/dL |
| 60 min | 81.8% | 60 mg/dL | 86.7% | 73 mg/dL |
| 120 min | 78.2% | 68 mg/dL | 88.3% | 98 mg/dL |

Site recalibration uses 22 participants and is tested on the other 23. The quantile models stay as trained; only the conformal margin is refitted.

## What this shows

* **Known meals are where the twin earns its place.** Told about each meal in advance, the calibrated twin cuts 2 hour error from 38.3 (persistence) to 29.6 mg/dL. That is the case the planned meal input in the dashboard is built for.
* **Synthetic training transfers, but only just.** Models trained only on synthetic Indian data land close to persistence on American real world traces (36.7 against 38.3 at 2 hours). Retraining the residual model on local data is the obvious next step.
* **The routine prior is weak here.** CGMacros participants ate on a varied study schedule, so median meal times from five days predict the next meal poorly, and the twin trails persistence at 30 minutes because a forecast starts from the observer estimate rather than the last reading.
* **Conformal intervals must be recalibrated per site.** Synthetic calibration under covers on real data; refitting only the conformal margin on half the participants brings coverage to within about 2 to 3 points of 90%, with wider intervals.

![Real data](figures/real_data_cgmacros.png)
