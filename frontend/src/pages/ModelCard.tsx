import { useEffect, useState } from "react";
import { api, fmt } from "../api";

type MC = Awaited<ReturnType<typeof api.modelCard>>;
const pct = (v: number, d = 1) => `${fmt(v * 100, d)}%`;

export function ModelCard() {
  const [mc, setMc] = useState<MC | null>(null);
  useEffect(() => { api.modelCard().then(setMc); }, []);
  if (!mc) return <p className="empty">Loading model card.</p>;
  const m = mc.metrics;
  const g = m.glucose, cf = m.conformal, al = m.alerts, c = m.cardio;
  const models: [string, string][] = [["cold", "Twin, EHR prior only"], ["phys", "Twin, calibrated (physics only)"], ["ml", "LightGBM only"], ["hyb", "Hybrid"]];
  const lv = m.alert_level.alert_coverage;
  const fu = mc.followup;
  const load = fu?.alert_load, stress = fu?.cardio_stress;
  return (
    <article className="doc">
      <div className="label">Model card</div>
      <h1>Prativimb hybrid patient twin, version 1.5</h1>
      <p className="statement">Decision support only, not a diagnosis. Every forecast and flag needs a clinician's judgement.</p>

      <h2>Intended use</h2>
      <ul>
        <li>Remote monitoring of adults with prediabetes or Type 2 diabetes who wear a CGM and a wrist band, by a clinical team.</li>
        <li>Forecast glucose for the next 2 hours with calibrated uncertainty, and flag likely rises above 180 mg/dL (Event A).</li>
        <li>Flag a raised short term cardiovascular risk from a seven day wearable pattern (Event B).</li>
        <li>Let clinicians and patients explore what if questions (a walk, a food swap, meal timing, a missed dose, sleep, a night shift).</li>
      </ul>
      <h2>Not intended for</h2>
      <ul>
        <li>Insulin dosing, Type 1 diabetes, pregnancy, children, or any automated treatment decision.</li>
        <li>Diagnosis of acute coronary syndrome. The cardiovascular flag is a prompt to review, not a triage tool.</li>
        <li>Use on real patients before prospective validation, regulatory review and local governance approval.</li>
      </ul>

      <h2>Data provenance</h2>
      <p>
        All data are synthetic: {m.split.train_patients + m.split.calibration_patients + m.split.test_patients} fictional
        patients, 30 days each (14 Feb to 15 Mar 2026, IST). EHR records are FHIR R4 shaped bundles from our own
        Synthea style generator, calibrated to Indian prevalence and diet. Glucose comes from the UVA/Padova meal model
        with simglucose parameter sets and its CGM noise model, adapted for Type 2 diabetes. Heart rate, HRV, sleep stages
        and steps come from our generators with circadian rhythm, sensor gaps and Apple Health and Google Fit export
        formats. No real person's data was used, so no consent or data use agreement was needed. See docs/DATA.md.
      </p>
      <p>
        Split by patient: {m.split.train_patients} train, {m.split.calibration_patients} calibration (conformal and
        stacking only), {m.split.test_patients} test. Twins calibrate on days 1 to 7; all metrics are on days 8 to 30 of
        test patients.
      </p>

      <h2>Models</h2>
      <ul>
        <li><b>Twin:</b> extended Bergman minimal model (glucose, insulin action, insulin, two gut compartments, exercise, metformin), personalised from the EHR and then fitted to the first week of CGM, meals and steps by maximum a posteriori least squares.</li>
        <li><b>Residual model:</b> LightGBM predicts the twin's error at 30, 60, 90 and 120 minutes from CGM history, meals, activity, sleep, medication adherence and EHR.</li>
        <li><b>Uncertainty:</b> conformalised quantile regression, 90% intervals. Alerts use the lower bound of the {pct(lv, 0)} interval, chosen on calibration patients.</li>
        <li><b>Cardiovascular:</b> isolation forest and personal baseline z scores (unsupervised) plus a LightGBM classifier, stacked by logistic regression.</li>
        <li><b>Explanations:</b> exact Shapley values over twin inputs and TreeSHAP over the residual model, in mg/dL, worded as clinical sentences.</li>
      </ul>

      <h2>Glucose forecasting, test patients</h2>
      <table className="data num">
        <thead><tr><th>Model</th><th>RMSE 30 min</th><th>RMSE 60 min</th><th>RMSE 120 min</th><th>MARD 60 min</th></tr></thead>
        <tbody>
          {models.map(([k, name]) => (
            <tr key={k} style={k === "hyb" ? { fontWeight: 500 } : undefined}>
              <td>{name}</td><td>{fmt(g["30"][k].rmse, 1)}</td><td>{fmt(g["60"][k].rmse, 1)}</td><td>{fmt(g["120"][k].rmse, 1)}</td><td>{fmt(g["60"][k].mard, 1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">RMSE in mg/dL. Clarke zone A at 60 min: {fmt(g["60"].clarke.A, 1)}%; zones C to E: {fmt(g["60"].clarke.C + g["60"].clarke.D + g["60"].clarke.E, 1)}%.</p>
      <table className="data num">
        <thead><tr><th>Spike policy</th><th>Sensitivity</th><th>Precision</th><th>Median lead</th><th>False alarms per patient day</th></tr></thead>
        <tbody>
          <tr><td>Alert tier (lower bound, {pct(lv, 0)} interval)</td><td>{pct(al.alert.sensitivity)}</td><td>{pct(al.alert.precision)}</td><td>{fmt(al.alert.median_lead_min)} min</td><td>{fmt(al.alert.false_alarms_per_patient_day, 2)}</td></tr>
          <tr><td>Watch tier (point forecast)</td><td>{pct(al.hyb.sensitivity)}</td><td>{pct(al.hyb.precision)}</td><td>{fmt(al.hyb.median_lead_min)} min</td><td>{fmt(al.hyb.false_alarms_per_patient_day, 2)}</td></tr>
        </tbody>
      </table>
      <table className="data num">
        <thead><tr><th>Horizon</th><th>Coverage (target 90%)</th><th>Median width</th></tr></thead>
        <tbody>
          {["30", "60", "90", "120"].map(h => <tr key={h}><td>{h} min</td><td>{pct(cf[h].cqr_coverage)}</td><td>{fmt(cf[h].cqr_median_width)} mg/dL</td></tr>)}
        </tbody>
      </table>
      {m.hypo && (
        <>
          <h3 style={{ marginTop: 18 }}>Low glucose (below 70 mg/dL), test patients</h3>
          <table className="data num">
            <thead><tr><th>Policy</th><th>Flagged in advance</th><th>Precision</th><th>False alarms per patient day</th></tr></thead>
            <tbody>
              <tr style={{ fontWeight: 500 }}><td>Low glucose classifier (deployed)</td><td>{pct(m.hypo.test_classifier.sensitivity, 0)}</td>
                <td>{pct(m.hypo.test_classifier.precision, 0)}</td><td>{fmt(m.hypo.test_classifier.false_alarms_per_patient_day, 2)}</td></tr>
              <tr><td>Point forecast below 70</td><td>{pct(m.hypo.test_point_forecast.sensitivity, 0)}</td>
                <td>{pct(m.hypo.test_point_forecast.precision, 0)}</td><td>{fmt(m.hypo.test_point_forecast.false_alarms_per_patient_day, 2)}</td></tr>
            </tbody>
          </table>
          <p className="small muted">Labels cleaned of sensor compression artefacts. The artefact filter finds {m.hypo.artefact_detector.dips_found} of
            {" "}{m.hypo.artefact_detector.dips} injected dips that reach below 90 mg/dL, and {pct(m.hypo.artefact_detector.reading_precision, 0)} of
            the readings it flags are true artefacts.</p>
        </>
      )}
      <figure><img src="/figures/glucose_rmse_by_horizon.png" alt="Forecast error by horizon" /><figcaption>Forecast error by horizon. The hybrid beats both of its parts at every horizon.</figcaption></figure>
      <figure><img src="/figures/alert_tradeoff.png" alt="Spike alert policies" /><figcaption>Alert policies on test patients.</figcaption></figure>
      <figure><img src="/figures/clarke_grid_60min.png" alt="Clarke error grid" style={{ maxWidth: 480 }} /><figcaption>Clarke error grid, 60 minute hybrid forecast.</figcaption></figure>

      {load && (
        <>
          <h2>Alert load</h2>
          <p>How often each alert fires matters as much as how accurate it is: an alert nobody reads helps nobody. Measured with the deployed
            service code on the 40 test patients, days 8 to 30, every 15 minutes.</p>
          <table className="data num">
            <thead><tr><th>Alert</th><th>Per patient per day</th></tr></thead>
            <tbody>
              <tr><td>High glucose likely (pushed to the ward)</td><td>{fmt(load.high_per_patient_day, 2)}</td></tr>
              <tr><td>Glucose may go high (patient page only)</td><td>{fmt(load.watch_per_patient_day, 2)}</td></tr>
              <tr><td>Low glucose now or likely within the hour</td><td>{fmt(load.low_per_patient_day, 2)}</td></tr>
              <tr><td>Raised heart risk (new flags per patient per week)</td><td>{fmt(load.heart_flags_per_patient_week, 2)}</td></tr>
            </tbody>
          </table>
          <p>{pct(load.high_came_true, 0)} of {load.high_episodes.toLocaleString("en-IN")} confident high glucose alerts came true (above 180 for
            15 minutes within 2 h 15 min, counting rises that continue an earlier high; the stricter fresh rise definition above gives {pct(al.alert?.precision ?? 0.852, 0)}).
            On a ward of 200 such patients the Needs attention list holds a median of {fmt(load.ward_of_200.median)} (90th percentile {fmt(load.ward_of_200.p90)}),
            most around {String(load.ward_of_200.busiest_hour).padStart(2, "0")}:00 ({fmt(load.ward_of_200.busiest_hour_mean)}) and fewest around
            {" "}{String(load.ward_of_200.quietest_hour).padStart(2, "0")}:00 ({fmt(load.ward_of_200.quietest_hour_mean)}). Lows are the noisiest alert: most are brief dips just
            under 70 in people without diabetes.</p>
          <p className="small muted">What the dashboard does about it: the ward groups patients by urgency, shows why each alert fired, lets a nurse or doctor mark an
            alert as seen for a set time, keeps possible highs off the ward list and out of notifications, and the digest counts them instead.</p>
        </>
      )}

      {mc.counterfactual && (() => {
        const cf = mc.counterfactual, o = cf.overall;
        return (
          <>
            <h2>Are the what if answers right?</h2>
            <p>In real life nobody sees what would have happened had the patient walked after dinner. Here we can: the synthetic patients come
              from a richer, deterministic simulator (UVA/Padova based) that the twin never sees. For {cf.cases} moments in {cf.patients} test patients,
              40 minutes before a real main meal, we re-ran that simulator with each change applied to what the patient actually ate and compared
              the effect with the twin's prediction. The twin saw only data up to that moment and the declared routine.</p>
            <table className="data num">
              <thead><tr><th>Change</th><th>Twin, change in peak</th><th>Reference</th><th>Direction agrees</th><th>Typical error</th></tr></thead>
              <tbody>
                {cf.per_lever.map((x: any) => (
                  <tr key={x.label}><td>{x.label}</td><td>{x.twin_mean > 0 ? "+" : ""}{fmt(x.twin_mean)} mg/dL</td>
                    <td>{x.reference_mean > 0 ? "+" : ""}{fmt(x.reference_mean)} mg/dL</td><td>{pct(x.direction_agree, 0)}</td><td>{fmt(x.mae)} mg/dL</td></tr>
                ))}
              </tbody>
            </table>
            <p>Overall the twin gets the direction right {pct(o.direction_agree, 0)} of the time (typical error {fmt(o.mae, 1)} mg/dL, correlation {fmt(o.corr, 2)}),
              and the change that helps most according to the reference is in the twin's top two {pct(o.best_in_top2, 0)} of the time. Two weaknesses:
              it slightly underestimates walks, and it misses that eating an hour earlier usually makes the peak worse when the previous meal has not settled.</p>
            <figure><img src="/figures/counterfactual_check.png" alt="Twin against reference simulator" /><figcaption>Each point is one change at one moment. On the diagonal the twin was exact.</figcaption></figure>
            <p className="small muted">This tests the twin's structure against a different model of the same physiology; it is necessary, not sufficient.
              Sleep, missed doses, night shifts and insulin act through whole day factors in the reference and are not checked here.</p>
          </>
        );
      })()}

      <h2>A new patient's first week</h2>
      <p>A new patient's forecast starts from the health record alone (HbA1c, BMI, fasting glucose, age, TCF7L2 genotype, medicines). Across
        200 patients its typical error over that week is {fmt(m.twin?.rmse_prior_median ?? 28.3, 1)} mg/dL; fitting to the first week of sensor and
        wearable data brings it to {fmt(m.twin?.rmse_fit_median ?? 19.9, 1)}. Until day 7 the dashboard says the forecast is still learning, possible
        highs are shown on the patient's page but not pushed to the ward, and lows are flagged as usual. Use the demo strip's "17 Feb, new patients" to see it.</p>

      <h2>Cardiovascular risk flag, test patients</h2>
      <table className="data num">
        <thead><tr><th>Detector</th><th>AUROC (95% CI)</th><th>AUPRC (95% CI)</th><th>Sensitivity at 90% specificity</th></tr></thead>
        <tbody>
          {Object.entries(c.components).map(([k, x]: [string, any]) => (
            <tr key={k} style={k === "risk" ? { fontWeight: 500 } : undefined}>
              <td>{x.name}</td><td>{fmt(x.auroc, 2)} ({fmt(x.auroc_ci[0], 2)} to {fmt(x.auroc_ci[1], 2)})</td>
              <td>{fmt(x.auprc, 2)} ({fmt(x.auprc_ci[0], 2)} to {fmt(x.auprc_ci[1], 2)})</td><td>{pct(x.sens_at_90spec, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">
        {c.n_windows} windows, {c.n_positive} positive, {c.n_events} events. At the operating threshold
        ({pct(c.operating_point.threshold, 1)}, set at 95% specificity on calibration patients) {c.operating_point.events_caught} of {c.operating_point.events} events
        were flagged in the 3 days before, with {pct(c.operating_point.flags_per_patient_day)} of patient days flagged.
      </p>
      <figure><img src="/figures/cardio_performance.png" alt="Cardiovascular model performance" /><figcaption>ROC, precision and recall, and calibration.</figcaption></figure>

      {stress && (
        <>
          <h2>How far to trust the heart risk flag</h2>
          <p className="statement">The heart events and the warning signs before them come from our own simulator, the same one the model learned from.
            The result above mostly shows that the model learned that simulator. It is not evidence that it predicts real cardiac events.</p>
          <p>Stress test: the simulated warning signs in the ten days before each test event are weakened toward the patient's own baseline, while
            illness episodes that look similar keep full strength. Same model, same threshold.</p>
          <table className="data num">
            <thead><tr><th>Strength of warning signs</th><th>AUROC</th><th>Events flagged in the 3 days before</th><th>Specificity</th></tr></thead>
            <tbody>
              {stress.results.map((x: any) => (
                <tr key={x.strength}><td>{fmt(x.strength * 100)}%</td><td>{fmt(x.auroc, 2)}</td><td>{x.events_flagged} of {x.events}</td><td>{pct(x.specificity, 1)}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="small muted">{stress.windows} test windows, {stress.positives} positive, 6 events: every row is uncertain. Real validation needs real outcomes;
            open datasets that pair continuous wearable data with adjudicated cardiac events are not available without a data use agreement, which this
            project does not use. Until then the heart flag demonstrates the pipeline (personal baselines, stacking, explanation, the ward workflow), not a clinical claim.</p>
        </>
      )}

      {m.real_data && (
        <>
          <h2>Validation on real CGM traces</h2>
          <p>
            CGMacros (PhysioNet, open access, CC BY-NC-SA 4.0): {m.real_data.participants} adults with normoglycaemia,
            prediabetes or Type 2 diabetes, Dexcom G6 and Fitbit for about ten days, meals with known carbohydrate. Twins
            calibrate on days 1 to 5; days 6 onward are scored. Models trained only on synthetic data are applied unchanged.
          </p>
          <table className="data num">
            <thead><tr><th>RMSE, all participants</th><th>30 min</th><th>60 min</th><th>120 min</th></tr></thead>
            <tbody>
              {([["persist", "Persistence"], ["phys", "Twin, routine prior"], ["hyb", "Hybrid, synthetic trained"],
                 ["known", "Twin, meals announced"]] as [string, string][]).map(([k, name]) => (
                <tr key={k} style={k === "known" ? { fontWeight: 500 } : undefined}><td>{name}</td>
                  {["30", "60", "120"].map(h => <td key={h}>{fmt(m.real_data.by_group.all[h][k], 1)}</td>)}</tr>
              ))}
            </tbody>
          </table>
          <p className="small muted">90% interval coverage on real data: {pct(m.real_data.conformal["120"].synthetic_calibration, 0)} at 2 h
            with synthetic calibration, {pct(m.real_data.conformal["120"].site_recalibrated, 0)} after refitting the conformal margin on local participants.</p>
          <figure><img src="/figures/real_data_cgmacros.png" alt="Real data validation" /><figcaption>Forecast error and interval coverage on CGMacros.</figcaption></figure>
        </>
      )}

      <h2>Limitations</h2>
      <ul>{m.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>

      <h2>Privacy and governance</h2>
      <ul>
        <li>Synthetic only; no personal data under the Digital Personal Data Protection Act 2023 or HIPAA was processed.</li>
        <li>Each synthetic record carries a FHIR Consent resource modelled on a DPDP consent artefact: purpose limited (treatment), time bound and revocable.</li>
        <li>Consent is on screen: the patient (from their own page) or a doctor can withdraw or grant sharing of glucose, wearable data and ABDM health records, and the service stops using a source while it is withdrawn. Every change is in the audit log.</li>
        <li>Roles: doctors, nurses or health educators, and patients can each do different things, and the service checks the role on every change. The demo signs in without a password; a deployment would use the clinic's single sign on.</li>
        <li>Device data arrives through Apple Health, Google Fit or Health Connect (Android) adapters, and records through FHIR, the format ABDM health information exchange uses.</li>
        <li>A real deployment would run inside the hospital network, keep identifiers out of model features and log every access.</li>
      </ul>
    </article>
  );
}
