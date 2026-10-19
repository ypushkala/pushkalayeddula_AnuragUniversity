import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { api, dayMonth, dayToDate, fmt, hhmm, minuteToDate, type Forecast, type Obs, type PatientDetail, type Timeline } from "../api";
import { Activity } from "../components/Activity";
import { AgpChart } from "../components/AgpChart";
import { AlertBanner } from "../components/AlertBanner";
import { Disclosure } from "../components/Disclosure";
import { FactorBars } from "../components/FactorBars";
import { ForecastChart } from "../components/ForecastChart";
import { PatientList, useQueue } from "../components/PatientList";
import { SkeletonBlock } from "../components/Skeleton";
import { TableView } from "../components/TableView";
import { useLiveData } from "../live";
import { HeartWeek } from "./Cardio";
import { trendWord } from "./Ward";

const LAB_NAMES: Record<string, string> = {
  hba1c: "HbA1c", fpg: "Fasting glucose", ldl: "LDL cholesterol", hdl: "HDL cholesterol", tg: "Triglycerides",
  tc: "Total cholesterol", creatinine: "Creatinine", egfr: "eGFR", sbp: "Systolic BP", dbp: "Diastolic BP",
  bmi: "BMI", weight: "Weight", waist: "Waist",
};

// Plain words for the header; the full coded list is on the Record tab.
const PLAIN: Record<string, string> = {
  "E11.9": "Type 2 diabetes", "R73.03": "Prediabetes", "I10": "High blood pressure", "E78.5": "High cholesterol",
  "E66.9": "Obesity", "Z82.49": "Family history of heart disease", "G47.26": "Night shift work", "F17.210": "Smoker",
};

export function usePatient() {
  return useOutletContext<{ detail: PatientDetail }>();
}

function PrevNext({ id }: { id: string }) {
  const { prev, next } = useQueue(id);
  const nav = useNavigate();
  // Alt plus left or right arrow steps through the patients needing attention.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      if (e.key === "ArrowRight" && next) nav(`/patient/${next.id}`);
      if (e.key === "ArrowLeft" && prev) nav(`/patient/${prev.id}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prev, next, nav]);
  return (
    <div className="prevnext" role="group" aria-label="Move between patients needing attention">
      {prev ? <Link className="btn" to={`/patient/${prev.id}`} title="Alt and left arrow">Previous: {prev.name.split(" ")[0]}</Link>
        : <span className="btn disabled" aria-disabled="true">Previous</span>}
      {next ? <Link className="btn" to={`/patient/${next.id}`} title="Alt and right arrow">Next: {next.name.split(" ")[0]}</Link>
        : <span className="btn disabled" aria-disabled="true">Next</span>}
    </div>
  );
}

export function Patient() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setDetail(null); api.patient(id).then(setDetail).catch(e => setErr(String(e))); window.scrollTo(0, 0); }, [id]);
  const p = detail?.patient;
  const problems = detail ? detail.conditions.map(c => PLAIN[c.code.code] ?? c.code.display) : [];
  return (
    <div className="patient-layout">
      <PatientList currentId={id} />
      <div className="patient-main">
        {err && <p className="empty">Patient not found ({err}).</p>}
        {!detail ? <SkeletonBlock height={160} label="Loading patient" /> : (
          <>
            <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Ward</Link><span aria-hidden="true"> / </span><span>{p!.name}</span></nav>
            <div className="patient-head">
              <div>
                <h1>{p!.name}</h1>
                <div className="facts">{p!.age} {p!.gender === "male" ? "M" : "F"}, {p!.city}. {problems.slice(0, 4).join(", ")}.</div>
                {detail.context.length > 0 && <div className="facts muted">{detail.context.join(". ")}.</div>}
              </div>
              <div className="head-actions">
                <PrevNext id={id} />
                <Link className="btn" to={`/note/${id}`}>Clinical note</Link>
              </div>
            </div>
            <AlertBanner pid={id} first={p!.name.split(" ")[0]} />
            <nav className="tabs" aria-label="Patient sections">
              <NavLink end to={`/patient/${id}`}>Today</NavLink>
              <NavLink to={`/patient/${id}/try`}>Try a change</NavLink>
              <NavLink to={`/patient/${id}/record`}>Record</NavLink>
            </nav>
            <Outlet context={{ detail }} />
          </>
        )}
      </div>
    </div>
  );
}

function Headline({ fc }: { fc: Forecast | null }) {
  if (!fc) return <SkeletonBlock height={70} label="Loading glucose forecast" />;
  if (!fc.available) return <p className="lead">No glucose reading in the last 30 minutes.</p>;
  const st = fc.status;
  const h120 = fc.horizons.find(h => h.h === 120);
  return (
    <div className="headline">
      <div className="now num"><span className="big">{fmt(st.glucose)}</span> mg/dL <span className="trend">{trendWord(st.trend30)}</span></div>
      {h120 && <p className="muted">Glucose forecast for {hhmm(fc.points[fc.points.length - 1].t)}: most likely {fmt(h120.mid)},
        very probably between {fmt(h120.lo)} and {fmt(h120.hi)}.</p>}
    </div>
  );
}

function stepsPreview(tl: Timeline | null): string {
  if (!tl) return "";
  const steps = tl.steps.slice(-36).reduce((a, s) => a + (s.v ?? 0), 0);
  const hr = tl.hr.filter(h => h.v !== null).slice(-6);
  const hrNow = hr.length ? hr.reduce((a, h) => a + (h.v as number), 0) / hr.length : null;
  return `${Math.round(steps).toLocaleString("en-IN")} steps in the last 3 hours${hrNow ? `, heart rate ${fmt(hrNow)} now` : ""}`;
}

export function Today() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const tl = useLiveData(() => api.timeline(id, 12), [id]).data;
  const fc = useLiveData(() => api.forecast(id), [id]).data;
  const heart = useLiveData(() => api.cardio(id), [id]).data;
  const heartEnd = params.get("heart") ? Number(params.get("heart")) : undefined;

  let heartTitle = "Heart risk";
  if (heart) {
    const s = heart.summary;
    heartTitle = s.post_event ? `Heart risk: event recorded${s.event_minute !== undefined ? ` on ${dayMonth(minuteToDate(s.event_minute))}` : ""}`
      : s.flag ? `Heart risk: raised, ${fmt((s.risk ?? 0) * 100)}% within 3 days${s.flag_since !== null && s.flag_since !== undefined ? `, since ${dayMonth(dayToDate(s.flag_since))}` : ""}`
      : `Heart risk: normal this week`;
  }
  const heartOpen = Boolean(heartEnd !== undefined || heart?.summary.flag || heart?.summary.post_event);

  return (
    <div className="today">
      <section aria-label="Glucose">
        <Headline fc={fc} />
        {tl ? (
          <TableView title="Glucose, last 12 hours and forecast"
            columns={["Time", "Measured, mg/dL", "Forecast, mg/dL", "Likely range"]}
            rows={[...tl.cgm.filter((_, i) => i % 3 === 0).map(r => [hhmm(r.t), fmt(r.v), "", ""]),
                   ...(fc?.available ? fc.points.filter((_, i) => i % 3 === 0).map(p => [hhmm(p.t), "", fmt(p.mid), `${fmt(p.lo)} to ${fmt(p.hi)}`]) : [])]}>
            <ForecastChart tl={tl} fc={fc} stepsPreview={stepsPreview(tl)} />
          </TableView>
        ) : <SkeletonBlock height={420} label="Loading glucose" />}
      </section>
      {fc?.explanation && (
        <section className="why-block" aria-label="Why the forecast says this">
          <h2>Why the glucose forecast says this</h2>
          <p className="lead-reason">{fc.explanation.sentence}</p>
          <FactorBars drivers={fc.explanation.drivers} />
          <p className="small muted">How many mg/dL each factor adds to or takes off the expected peak.</p>
        </section>
      )}
      {heart && (
        <Disclosure title={heartTitle} hint="seven days of heart rate, heart rate variability, sleep and steps" open={heartOpen}>
          <HeartWeek id={id} initialEnd={heartEnd} />
        </Disclosure>
      )}
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
  const { id = "" } = useParams();
  const { detail: d } = usePatient();
  const agp = useLiveData(() => api.agp(id), [id]).data;
  const log = useLiveData(() => api.alertLog(id), [id]).data;
  const year = (s: string | null) => (s ? new Date(s).getFullYear() : "");
  const logPreview = log ? (log.length ? `${log.length} alert ${log.length === 1 ? "check" : "checks"} in the last 6 hours, latest at ${hhmm(log[log.length - 1].t)}` : "No alerts in the last 6 hours") : "";
  return (
    <>
      <Disclosure title="Two week glucose pattern" open
        hint={agp ? `${fmt(agp.metrics.tir)}% of the time in range, average ${fmt(agp.metrics.mean)} mg/dL` : ""}>
        {agp ? <AgpChart agp={agp} /> : <SkeletonBlock height={300} label="Loading pattern" />}
      </Disclosure>
      <Disclosure title="History" hint={logPreview}>
        <div className="two">
          <div>
            <h3>Alerts in the last 6 hours</h3>
            {log && log.length ? (
              <table className="log num">
                <tbody>
                  {log.slice().reverse().map(e => (
                    <tr key={e.t}>
                      <td>{hhmm(e.t)}</td>
                      <td>
                        {e.low === "now" && <span className="alert-text">Low glucose, {fmt(e.glucose)}. </span>}
                        {e.low === "forecast" && <span>Low glucose likely within the hour. </span>}
                        {e.tier === "alert" && <span className="alert-text">High glucose likely by {e.cross_time}, peak {fmt(e.peak)}.</span>}
                        {e.tier === "watch" && <span className="ink2">Glucose may go high, peak {fmt(e.peak)}.</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="empty">{log ? "None." : "Loading."}</p>}
          </div>
          <div><h3>Actions by the care team</h3><Activity pid={id} /></div>
        </div>
      </Disclosure>
      <div className="record" style={{ marginTop: 18 }}>
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
          <h2>What the glucose forecast has learned</h2>
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
    </>
  );
}
