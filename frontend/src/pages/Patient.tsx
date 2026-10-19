import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, dayMonth, fmt, hhmm, minuteToDate, signed, type Obs, type PatientDetail } from "../api";
import { FactorBars } from "../components/FactorBars";
import { Activity } from "../components/Activity";
import { AgpChart } from "../components/AgpChart";
import { AlertCards } from "../components/AlertCards";
import { MealEntry } from "../components/MealEntry";
import { SkeletonBlock } from "../components/Skeleton";
import { TableView } from "../components/TableView";
import { ForecastChart } from "../components/ForecastChart";
import { useLiveData } from "../live";

const LAB_NAMES: Record<string, string> = {
  hba1c: "HbA1c", fpg: "Fasting glucose", ldl: "LDL cholesterol", hdl: "HDL cholesterol", tg: "Triglycerides",
  tc: "Total cholesterol", creatinine: "Creatinine", egfr: "eGFR", sbp: "Systolic BP", dbp: "Diastolic BP",
  bmi: "BMI", weight: "Weight", waist: "Waist",
};

export function usePatient() {
  return useOutletContext<{ detail: PatientDetail }>();
}

export function Patient() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setDetail(null); api.patient(id).then(setDetail).catch(e => setErr(String(e))); }, [id]);
  if (err) return <p className="empty">Patient not found ({err}).</p>;
  if (!detail) return <p className="empty">Loading record.</p>;
  const p = detail.patient;
  return (
    <>
      <div className="patient-head">
        <div>
          <div className="label">Patient twin</div>
          <h1>{p.name}</h1>
          <div className="facts">
            {p.age} {p.gender === "male" ? "M" : "F"} <span className="muted">&middot;</span> <span className="mono">{p.id}</span>{" "}
            <span className="muted">&middot;</span> {p.city} <span className="muted">&middot;</span> {p.occupation}{" "}
            <span className="muted">&middot;</span> {detail.device}
          </div>
          {detail.context.length > 0 && <div className="facts" style={{ marginTop: 2 }}>{detail.context.join(". ")}.</div>}
        </div>
        <div className="small muted" style={{ textAlign: "right" }}>
          <Link className="btn" to={`/share/${p.id}`} style={{ marginBottom: 8, display: "inline-block" }}>Patient view</Link><br />
          Synthetic record. Held out from training ({detail.split} split).<br />
          Twin calibrated on days 1 to 7, fit error {fmt(detail.twin.calibration_rmse_fit)} mg/dL.
        </div>
      </div>
      <nav className="tabs">
        <NavLink end to={`/patient/${id}`}>Twin</NavLink>
        <NavLink to={`/patient/${id}/whatif`}>What if</NavLink>
        <NavLink to={`/patient/${id}/cardio`}>Cardio week</NavLink>
        <NavLink to={`/patient/${id}/note`}>Clinical note</NavLink>
      </nav>
      <Outlet context={{ detail }} />
    </>
  );
}

function ObsRows({ rows }: { rows: Obs[] }) {
  return (
    <table className="kv num">
      <tbody>
        {rows.map(o => (
          <tr key={o.code.code}>
            <td>{LAB_NAMES[o.text ?? ""] ?? o.code.display}<div className="prev">{dayMonth(o.effectiveDateTime)}{o.previous !== null ? `, prev ${fmt(o.previous, o.text === "hba1c" ? 1 : 0)}` : ""}</div></td>
            <td>{fmt(o.value ?? null, ["hba1c", "creatinine", "bmi"].includes(o.text ?? "") ? 1 : 0)} <span className="muted small">{o.unit === "mm[Hg]" ? "mmHg" : o.unit}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EhrColumn({ d }: { d: PatientDetail }) {
  const year = (s: string | null) => (s ? new Date(s).getFullYear() : "");
  return (
    <>
      <div className="block">
        <span className="label">Problems</span>
        <ul className="plain">
          {d.conditions.map(c => <li key={c.code.code}><span>{c.code.display}</span><span>{c.code.code}, {year(c.onsetDateTime)}</span></li>)}
        </ul>
      </div>
      <div className="block">
        <span className="label">Medications</span>
        <ul className="plain">
          {d.medications.map(m => <li key={m.medication.code}><span>{m.dosage}</span><span>since {year(m.effectiveStart)}</span></li>)}
          {!d.medications.length && <li><span className="muted">None</span></li>}
        </ul>
      </div>
      <div className="block"><span className="label">Laboratory</span><ObsRows rows={d.labs} /></div>
      <div className="block"><span className="label">Vitals</span><ObsRows rows={d.vitals} /></div>
      <div className="block">
        <span className="label">Genetic markers</span>
        <table className="kv">
          <tbody>
            {d.genetics.map(g => (
              <tr key={g.rsid}><td>{g.gene}<div className="prev mono">{g.rsid}</div></td>
                <td><span className="mono">{g.genotype}</span> <span className="muted small">{g.riskAlleles} risk</span></td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="block">
        <span className="label">History</span>
        <ul className="plain">
          {[...d.familyHistory, ...d.socialHistory].map(x => <li key={x}><span>{x}</span></li>)}
        </ul>
      </div>
      <div className="block">
        <span className="label">Twin parameters</span>
        <table className="kv num">
          <tbody>
            <tr><td>Insulin sensitivity</td><td>{fmt(d.twin.insulin_sensitivity_pct_typical)}% of typical</td></tr>
            <tr><td>Insulin response</td><td>{fmt(d.twin.secretion_pct_typical)}% of typical</td></tr>
            <tr><td>Basal glucose</td><td>{fmt(d.twin.basal_glucose)} mg/dL</td></tr>
            <tr><td>Carb absorption half time</td><td>{fmt(d.twin.absorption_half_time_min)} min</td></tr>
            <tr><td>Fit error, EHR prior to fitted</td><td>{fmt(d.twin.calibration_rmse_prior)} to {fmt(d.twin.calibration_rmse_fit)}</td></tr>
          </tbody>
        </table>
      </div>
      <p className="small muted">{d.consent}</p>
    </>
  );
}

export function TwinTab() {
  const { id = "" } = useParams();
  const { detail } = usePatient();
  const tl = useLiveData(() => api.timeline(id, 12), [id]).data;
  const fc = useLiveData(() => api.forecast(id), [id]).data;
  const log = useLiveData(() => api.alertLog(id), [id]).data;
  const agp = useLiveData(() => api.agp(id), [id]).data;
  const st = fc?.available ? fc.status : null;
  const h120 = fc?.available ? fc.horizons.find(h => h.h === 120) : undefined;
  const cgmVals = tl?.cgm.filter(r => r.v !== null).map(r => r.v as number) ?? [];
  const tir = cgmVals.length ? (cgmVals.filter(v => v >= 70 && v <= 180).length / cgmVals.length) * 100 : null;

  return (
    <div className="three twin-layout">
      <section className="col-ehr" aria-label="Health record"><EhrColumn d={detail} /></section>
      <section className="col-main" aria-label="Glucose and forecast">
        <div className="stats num">
          <div className="stat"><div className="label">Now</div><div className="v">{fmt(st?.glucose)}<small>mg/dL</small></div>
            <div className="d">{st?.trend30 !== null && st?.trend30 !== undefined ? `${signed(st.trend30)} in 30 min` : ""}</div></div>
          <div className="stat"><div className="label">Forecast peak, 2 h</div><div className="v">{fmt(st?.peak)}<small>mg/dL</small></div>
            <div className="d">{st ? `at ${hhmm(minuteToDate(st.peak_minute))}` : ""}</div></div>
          <div className="stat"><div className="label">Likely range at 2 h</div><div className="v">{fmt(h120?.lo)} to {fmt(h120?.hi)}</div>
            <div className="d">9 in 10 readings fall inside</div></div>
          <div className="stat"><div className="label">Time in range, 12 h</div><div className="v">{fmt(tir)}<small>%</small></div>
            <div className="d">70 to 180 mg/dL</div></div>
        </div>
        {tl ? (
          <TableView title="Glucose, last 12 hours and forecast"
            columns={["Time", "CGM, mg/dL", "Forecast, mg/dL", "Likely range"]}
            rows={[...tl.cgm.filter((_, i) => i % 3 === 0).map(r => [hhmm(r.t), fmt(r.v), "", ""]),
                   ...(fc?.available ? fc.points.filter((_, i) => i % 3 === 0).map(p => [hhmm(p.t), "", fmt(p.mid), `${fmt(p.lo)} to ${fmt(p.hi)}`]) : [])]}>
            <ForecastChart tl={tl} fc={fc} />
          </TableView>
        ) : <SkeletonBlock height={560} label="Loading glucose timeline" />}
        {agp ? <AgpChart agp={agp} /> : <SkeletonBlock height={320} label="Loading glucose profile" />}
      </section>
      <section className="col-side" aria-label="Alerts and actions">
        <div className="block">
          <span className="label">Active alerts</span>
          <AlertCards pid={id} cards={fc?.alerts} />
        </div>
        {fc?.explanation && (
          <div className="block">
            <span className="label">What moves the forecast peak</span>
            <FactorBars drivers={fc.explanation.drivers} />
            <p className="small muted" style={{ marginTop: 6 }}>
              mg/dL added to or taken off the predicted 2 hour peak. Twin inputs by exact Shapley values; learned
              correction by TreeSHAP. Hover a row for the split.
            </p>
          </div>
        )}
        <div className="block">
          <span className="label">Tell the twin about a meal</span>
          <MealEntry pid={id} entries={fc?.entries} />
        </div>
        <div className="block">
          <span className="label">Alert log, last 6 hours</span>
          {log && log.length ? (
            <table className="log num">
              <tbody>
                {log.slice().reverse().map(e => (
                  <tr key={e.t}>
                    <td>{hhmm(e.t)}</td>
                    <td>
                      {e.low === "now" && <span className="alert-text">Low {fmt(e.glucose)} now. </span>}
                      {e.low === "forecast" && <span>Low likely within 60 min. </span>}
                      {e.tier === "alert" && <span className="alert-text">Alert: above 180 by {e.cross_time}, peak {fmt(e.peak)}.</span>}
                      {e.tier === "watch" && <span className="ink2">Watch: peak {fmt(e.peak)} at {e.peak_time}.</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="empty">{log ? "No alerts in the last 6 hours." : "Replaying the last 6 hours."}</div>}
        </div>
        <div className="block">
          <span className="label">Activity</span>
          <Activity pid={id} />
        </div>
      </section>
    </div>
  );
}
