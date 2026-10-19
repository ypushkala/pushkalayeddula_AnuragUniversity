import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { api, dayMonth, dayToDate, fmt, glu, gluUnit, hhmm, minuteToDate, T, type Forecast, type Obs, type PatientDetail, type Timeline } from "../api";
import { Activity } from "../components/Activity";
import { AgpChart } from "../components/AgpChart";
import { AlertBanner } from "../components/AlertBanner";
import { ConsentPanel } from "../components/ConsentPanel";
import { Disclosure } from "../components/Disclosure";
import { EarlierAlerts, trackRecord } from "../components/EarlierAlerts";
import { Hint } from "../components/Hint";
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
            <div className="crumb-row">
              <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Ward</Link><span aria-hidden="true"> / </span><span>{p!.name}</span></nav>
              <PrevNext id={id} />
            </div>
            <div className="patient-head">
              <h1>{p!.name}</h1>
              <div className="facts">{p!.age} {p!.gender === "male" ? "M" : "F"}, {p!.city}. {problems.slice(0, 4).join(", ")}{problems.length ? "." : ""}</div>
              {detail.context.length > 0 && <div className="facts muted">{detail.context.join(". ")}.</div>}
              {detail.calibrating && <div className="facts muted">New patient: the glucose forecast is in its first week (day {detail.calibrating} of 7).</div>}
            </div>
            <Hint id="banner">The banner holds the most important alert and what you can do about it. Press n for the next patient with an alert nobody has seen.</Hint>
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
  if (!fc.available) return <p className="lead">{fc.reason ?? "No glucose reading in the last 30 minutes."}</p>;
  const st = fc.status;
  const h120 = fc.horizons.find(h => h.h === 120);
  return (
    <div className="headline">
      <div className="now num"><span className="big">{glu(st.glucose)}</span> {gluUnit()} <span className="trend">{trendWord(st.trend30)}</span></div>
      {h120 && <p className="muted">Glucose forecast for {hhmm(fc.points[fc.points.length - 1].t)}: most likely {glu(h120.mid)},
        very probably between {glu(h120.lo)} and {glu(h120.hi)}.</p>}
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
  const { detail } = usePatient();
  const [params] = useSearchParams();
  const tl = useLiveData(() => api.timeline(id, 12), [id]).data;
  const fc = useLiveData(() => api.forecast(id), [id]).data;
  const heart = useLiveData(() => api.cardio(id), [id]).data;
  const hist = useLiveData(() => api.history(id), [id]).data;
  const heartEnd = params.get("heart") ? Number(params.get("heart")) : undefined;
  const heartLink = params.has("heart");
  // A link to the heart section (from the ward or the banner) opens it and brings it into view.
  useEffect(() => {
    if (heartLink && heart) window.setTimeout(() => document.getElementById("heart")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }, [heartLink, Boolean(heart), id]);

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
            columns={["Time", `Measured, ${gluUnit()}`, `Forecast, ${gluUnit()}`, "Likely range"]}
            rows={[...tl.cgm.filter((_, i) => i % 3 === 0).map(r => [hhmm(r.t), glu(r.v), "", ""]),
                   ...(fc?.available ? fc.points.filter((_, i) => i % 3 === 0).map(p => [hhmm(p.t), "", glu(p.mid), `${glu(p.lo)} to ${glu(p.hi)}`]) : [])]}>
            <ForecastChart tl={tl} fc={fc} stepsPreview={stepsPreview(tl)} />
          </TableView>
        ) : <SkeletonBlock height={420} label="Loading glucose" />}
      </section>
      {fc?.explanation && (
        <section className="why-block" aria-label="Why the forecast says this">
          <h2>Why the glucose forecast says this</h2>
          <p className="lead-reason">{T(fc.explanation.sentence)}</p>
          <FactorBars drivers={fc.explanation.drivers} />
          <p className="small muted">How many {gluUnit()} each factor adds to or takes off the expected peak.</p>
          <p className="track">Track record for {detail.patient.name.split(" ")[0]} over the last {hist?.days ?? 7} days: {trackRecord(hist, detail.patient.name.split(" ")[0], false)}.{" "}
            <Link to={`/patient/${id}/record#earlier`}>Earlier alerts and what happened</Link></p>
        </section>
      )}
      {heart && (
        <div id="heart" className="anchor">
          <Disclosure title={heartTitle} hint="seven days of heart rate, heart rate variability, sleep and steps" open={heartOpen || heartLink} key={heartLink ? "link" : "plain"}>
            <HeartWeek id={id} initialEnd={heartEnd} />
          </Disclosure>
        </div>
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
  const { hash } = useLocation();
  const { detail: d } = usePatient();
  const first = d.patient.name.split(" ")[0];
  const agp = useLiveData(() => api.agp(id), [id]).data;
  const hist = useLiveData(() => api.history(id), [id]).data;
  const audit = useLiveData(() => api.audit(id), [id]).data;
  const year = (s: string | null) => (s ? new Date(s).getFullYear() : "");
  useEffect(() => {
    if (hash) window.setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }, [hash, Boolean(hist)]);
  const withheld = d.records_withheld;
  return (
    <>
      <div id="earlier" className="anchor">
        <Disclosure title="Earlier alerts and what happened" open hint={trackRecord(hist, first)}>
          {hist ? <EarlierAlerts h={hist} first={first} /> : <SkeletonBlock height={200} label="Loading earlier alerts" />}
        </Disclosure>
      </div>
      <Disclosure title="Two week glucose pattern" open
        hint={agp ? `${fmt(agp.metrics.tir)}% of the time in range, average ${glu(agp.metrics.mean)} ${gluUnit()}` : "Loading"}>
        {agp ? <AgpChart agp={agp} /> : <SkeletonBlock height={300} label="Loading pattern" />}
      </Disclosure>
      <Disclosure title="Actions by the care team" hint={audit ? (audit.length ? `${audit.length} recorded, latest by ${audit[0].removed_by ?? audit[0].by}` : "None recorded yet") : "Loading"}>
        <Activity pid={id} />
      </Disclosure>
      {withheld && <p className="notice">Health records are hidden: the patient has withdrawn sharing of ABDM records. Problems, medicines and lab results come back when sharing is granted again.</p>}
      <div className="record" style={{ marginTop: 18 }}>
        {!withheld && <>
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
        </>}
        <section className="block anchor" id="learned">
          <h2>What the glucose forecast has learned</h2>
          {d.calibrating ? (
            <p className="notice">Day {d.calibrating} of 7. Until the first week is over the forecast uses values estimated from the health record
              (HbA1c, BMI, age, medicines). Its ranges are wider and possible highs are shown, not pushed to the ward.</p>
          ) : null}
          <table className="kv num"><tbody>
            <tr><td>Insulin sensitivity</td><td>{fmt(d.twin.insulin_sensitivity_pct_typical)}% of typical</td></tr>
            <tr><td>Insulin response to food</td><td>{fmt(d.twin.secretion_pct_typical)}% of typical</td></tr>
            <tr><td>Resting glucose level</td><td>{glu(d.twin.basal_glucose)} {gluUnit()}</td></tr>
            <tr><td>Carbohydrate absorption half time</td><td>{fmt(d.twin.absorption_half_time_min)} min</td></tr>
            <tr><td>Typical error, record only</td><td>{glu(d.twin.calibration_rmse_prior)} {gluUnit()}</td></tr>
            <tr><td>Typical error after the first week</td><td>{glu(d.twin.calibration_rmse_fit)} {gluUnit()}</td></tr>
          </tbody></table>
          <details className="why">
            <summary>What a new patient sees in the first week</summary>
            <p className="small">On day one the forecast starts from the health record alone. Across all 200 patients its typical error during that
              week is about 28 mg/dL; after fitting to the first week of sensor and wearable data it falls to about 20. Until day 7 the
              Needs attention list does not show this patient's possible highs, lows are still flagged, and the banner says the forecast is still learning.</p>
          </details>
        </section>
        <section className="block">
          <h2>Data and consent</h2>
          <p className="small muted">ABHA {d.abha} (synthetic). Devices: {d.device} and a Dexcom G6. Synthetic record, held out from model training.</p>
          <ConsentPanel pid={id} />
        </section>
      </div>
    </>
  );
}
