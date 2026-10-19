import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { api, dayMonth, fmt, hhmm, minuteToDate, type Forecast, type Obs, type PatientDetail } from "../api";
import { Activity } from "../components/Activity";
import { AgpChart } from "../components/AgpChart";
import { AlertCards } from "../components/AlertCards";
import { Disclosure } from "../components/Disclosure";
import { ForecastChart } from "../components/ForecastChart";
import { MealEntry } from "../components/MealEntry";
import { SkeletonBlock } from "../components/Skeleton";
import { TableView } from "../components/TableView";
import { useLiveData } from "../live";
import { trendWord } from "./Ward";

const LAB_NAMES: Record<string, string> = {
  hba1c: "HbA1c", fpg: "Fasting glucose", ldl: "LDL cholesterol", hdl: "HDL cholesterol", tg: "Triglycerides",
  tc: "Total cholesterol", creatinine: "Creatinine", egfr: "eGFR", sbp: "Systolic BP", dbp: "Diastolic BP",
  bmi: "BMI", weight: "Weight", waist: "Waist",
};

// Plain words for the header; the full coded list is on the Health record tab.
const PLAIN: Record<string, string> = {
  "E11.9": "Type 2 diabetes", "R73.03": "Prediabetes", "I10": "High blood pressure", "E78.5": "High cholesterol",
  "E66.9": "Obesity", "Z82.49": "Family history of heart disease", "G47.26": "Night shift work", "F17.210": "Smoker",
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
  if (!detail) return <SkeletonBlock height={120} label="Loading patient" />;
  const p = detail.patient;
  const problems = detail.conditions.map(c => PLAIN[c.code.code] ?? c.code.display);
  return (
    <>
      <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Ward</Link><span aria-hidden="true"> / </span><span>{p.name}</span></nav>
      <div className="patient-head">
        <div>
          <h1>{p.name}</h1>
          <div className="facts">{p.age} {p.gender === "male" ? "M" : "F"}, {p.city}. {problems.slice(0, 4).join(", ")}.</div>
          {detail.context.length > 0 && <div className="facts muted">{detail.context.join(". ")}.</div>}
        </div>
        <Link className="btn" to={`/share/${p.id}`}>Patient view</Link>
      </div>
      <nav className="tabs" aria-label="Patient sections">
        <NavLink end to={`/patient/${id}`}>Overview</NavLink>
        <NavLink to={`/patient/${id}/whatif`}>What if</NavLink>
        <NavLink to={`/patient/${id}/cardio`}>Heart health</NavLink>
        <NavLink to={`/patient/${id}/record`}>Health record</NavLink>
        <NavLink to={`/patient/${id}/note`}>Clinical note</NavLink>
      </nav>
      <Outlet context={{ detail }} />
    </>
  );
}

function Headline({ fc }: { fc: Forecast | null }) {
  if (!fc) return <SkeletonBlock height={92} label="Loading forecast" />;
  if (!fc.available) return <div className="headline"><p className="lead">No CGM reading in the last 30 minutes.</p></div>;
  const st = fc.status;
  const h120 = fc.horizons.find(h => h.h === 120);
  let sentence = "Expected to stay between 70 and 180 for the next 2 hours.";
  if (st.low === "now") sentence = "Glucose is low now.";
  else if (st.low === "forecast") sentence = "Glucose is likely to fall below 70 within the hour.";
  else if (st.tier === "alert" || st.tier === "watch")
    sentence = `${st.tier === "alert" ? "Likely" : "May"} to go above 180 around ${hhmm(minuteToDate(st.cross_minute!))}, peaking near ${fmt(st.peak)} at ${hhmm(minuteToDate(st.peak_minute))}.`;
  else if (st.tier === "high") sentence = `Above 180 now; peak near ${fmt(st.peak)} expected at ${hhmm(minuteToDate(st.peak_minute))}.`;
  return (
    <div className="headline">
      <div className="now num"><span className="big">{fmt(st.glucose)}</span> mg/dL <span className="trend">{trendWord(st.trend30)}</span></div>
      <p className={`lead ${st.tier === "alert" || st.low ? "alert-text" : ""}`}>{sentence}</p>
      {h120 && <p className="muted">In 2 hours: most likely {fmt(h120.mid)}, very probably between {fmt(h120.lo)} and {fmt(h120.hi)}.</p>}
    </div>
  );
}

export function Overview() {
  const { id = "" } = useParams();
  const tl = useLiveData(() => api.timeline(id, 12), [id]).data;
  const fc = useLiveData(() => api.forecast(id), [id]).data;
  const log = useLiveData(() => api.alertLog(id), [id]).data;
  const agp = useLiveData(() => api.agp(id), [id]).data;

  return (
    <div className="overview">
      <section className="ov-main" aria-label="Glucose">
        <Headline fc={fc} />
        {tl ? (
          <TableView title="Glucose, last 12 hours and forecast"
            columns={["Time", "Measured, mg/dL", "Forecast, mg/dL", "Likely range"]}
            rows={[...tl.cgm.filter((_, i) => i % 3 === 0).map(r => [hhmm(r.t), fmt(r.v), "", ""]),
                   ...(fc?.available ? fc.points.filter((_, i) => i % 3 === 0).map(p => [hhmm(p.t), "", fmt(p.mid), `${fmt(p.lo)} to ${fmt(p.hi)}`]) : [])]}>
            <ForecastChart tl={tl} fc={fc} />
          </TableView>
        ) : <SkeletonBlock height={420} label="Loading glucose" />}
        <Disclosure title="Two week pattern" hint="time in range, average and variability">
          {agp ? <AgpChart agp={agp} /> : <SkeletonBlock height={300} label="Loading pattern" />}
        </Disclosure>
      </section>
      <aside className="ov-side" aria-label="Alerts and actions">
        <h2>Alerts</h2>
        <AlertCards pid={id} cards={fc?.alerts} drivers={fc?.explanation?.drivers} />
        <Disclosure title="Tell the twin about a meal" hint="a planned or eaten meal updates the forecast">
          <MealEntry pid={id} entries={fc?.entries} />
        </Disclosure>
        <Disclosure title="History" hint="earlier alerts and actions today">
          <h3 className="mini">Alerts in the last 6 hours</h3>
          {log && log.length ? (
            <table className="log num">
              <tbody>
                {log.slice().reverse().map(e => (
                  <tr key={e.t}>
                    <td>{hhmm(e.t)}</td>
                    <td>
                      {e.low === "now" && <span className="alert-text">Low, {fmt(e.glucose)}. </span>}
                      {e.low === "forecast" && <span>Low likely within the hour. </span>}
                      {e.tier === "alert" && <span className="alert-text">High by {e.cross_time}, peak {fmt(e.peak)}.</span>}
                      {e.tier === "watch" && <span className="ink2">May go high, peak {fmt(e.peak)}.</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="empty">{log ? "None." : "Loading."}</p>}
          <h3 className="mini">Actions</h3>
          <Activity pid={id} />
        </Disclosure>
      </aside>
    </div>
  );
}

function ObsTable({ rows }: { rows: Obs[] }) {
  return (
    <table className="kv num">
      <tbody>
        {rows.map(o => (
          <tr key={o.code.code}>
            <td>{LAB_NAMES[o.text ?? ""] ?? o.code.display}<div className="prev">{dayMonth(o.effectiveDateTime)}{o.previous !== null ? `, before: ${fmt(o.previous, o.text === "hba1c" ? 1 : 0)}` : ""}</div></td>
            <td>{fmt(o.value ?? null, ["hba1c", "creatinine", "bmi"].includes(o.text ?? "") ? 1 : 0)} <span className="muted">{o.unit === "mm[Hg]" ? "mmHg" : o.unit}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Record() {
  const { detail: d } = usePatient();
  const year = (s: string | null) => (s ? new Date(s).getFullYear() : "");
  return (
    <div className="record">
      <section className="block">
        <h2>Problems</h2>
        <ul className="plain">{d.conditions.map(c => <li key={c.code.code}><span>{c.code.display}</span><span>since {year(c.onsetDateTime)}</span></li>)}</ul>
      </section>
      <section className="block">
        <h2>Medicines</h2>
        <ul className="plain">
          {d.medications.map(m => <li key={m.medication.code}><span>{m.dosage}</span><span>since {year(m.effectiveStart)}</span></li>)}
          {!d.medications.length && <li><span className="muted">None</span></li>}
        </ul>
      </section>
      <section className="block"><h2>Blood tests</h2><ObsTable rows={d.labs} /></section>
      <section className="block"><h2>Measurements</h2><ObsTable rows={d.vitals} /></section>
      <section className="block">
        <h2>Family and lifestyle</h2>
        <ul className="plain">{[...d.familyHistory, ...d.socialHistory].map(x => <li key={x}><span>{x}</span></li>)}</ul>
      </section>
      <section className="block">
        <h2>Genetic markers</h2>
        <table className="kv"><tbody>
          {d.genetics.map(g => <tr key={g.rsid}><td>{g.gene}<div className="prev">{g.rsid}</div></td><td>{g.genotype}, {g.riskAlleles} risk {g.riskAlleles === 1 ? "copy" : "copies"}</td></tr>)}
        </tbody></table>
      </section>
      <section className="block">
        <h2>What the twin has learned</h2>
        <table className="kv num"><tbody>
          <tr><td>Insulin sensitivity</td><td>{fmt(d.twin.insulin_sensitivity_pct_typical)}% of typical</td></tr>
          <tr><td>Insulin response to food</td><td>{fmt(d.twin.secretion_pct_typical)}% of typical</td></tr>
          <tr><td>Resting glucose level</td><td>{fmt(d.twin.basal_glucose)} mg/dL</td></tr>
          <tr><td>Carbohydrate absorption half time</td><td>{fmt(d.twin.absorption_half_time_min)} min</td></tr>
          <tr><td>Fit error, first week</td><td>{fmt(d.twin.calibration_rmse_prior)} to {fmt(d.twin.calibration_rmse_fit)} mg/dL</td></tr>
        </tbody></table>
      </section>
      <section className="block">
        <h2>Data and consent</h2>
        <p className="muted">{d.device}. {d.consent}. Synthetic record, held out from model training.</p>
      </section>
    </div>
  );
}
