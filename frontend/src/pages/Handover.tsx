import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fullTime, glu, hhmm, T } from "../api";
import { GROUP_NAMES } from "../components/PatientList";
import { SkeletonBlock } from "../components/Skeleton";
import { useLive, useLiveData } from "../live";

/** End of shift: what was done and by whom, what is still open, and the notes left. Printable and copyable. */
export function Handover() {
  const { clinician, toast } = useLive();
  const [hours, setHours] = useState(12);
  const { data } = useLiveData(() => api.handover(hours), [hours]);
  if (!data) return <SkeletonBlock height={300} label="Preparing the handover" />;
  const text = [
    `Handover, ${fullTime(data.from)} to ${fullTime(data.to)}, from ${clinician}`,
    "", `Still open (${data.open.length}):`,
    ...data.open.map(o => `- ${o.name}: ${GROUP_NAMES[o.group]}${o.reason ? ` (${T(o.reason)})` : ""}`),
    "", `Seen but still active (${data.seen_still_active.length}):`,
    ...data.seen_still_active.map(o => `- ${o.name}: ${GROUP_NAMES[o.group]}`),
    "", `Done this shift (${data.done.length}):`,
    ...data.done.map(d => `- ${hhmm(d.t)} ${d.name}: ${d.what} (${d.who})${d.note ? `. ${T(d.note)}` : ""}`),
  ].join("\n");
  const copy = () => navigator.clipboard?.writeText(text).then(() => toast({ text: "Handover copied." })).catch(() => toast({ text: "Could not copy.", error: true }));
  const List = ({ items, empty }: { items: typeof data.open; empty: string }) => items.length ? (
    <ul className="handover-list">
      {items.map(o => (
        <li key={o.pid + o.group}><Link to={`/patient/${o.pid}${o.group === "heart" ? "?heart=" : ""}`}>{o.name}</Link>
          <span className={o.group === "watch" ? "muted" : "alert-text"}> {GROUP_NAMES[o.group]}</span>
          {o.glucose !== null && <span className="muted">, glucose {glu(o.glucose)}</span>}
          {o.reason && <span className="muted">, {T(o.reason)}</span>}</li>
      ))}
    </ul>
  ) : <p className="empty">{empty}</p>;
  return (
    <div className="handover">
      <div className="page-head">
        <div>
          <h1>Shift handover</h1>
          <div className="meta">{fullTime(data.from)} to {fullTime(data.to)}</div>
        </div>
        <div className="row-actions no-print">
          <label className="small">Shift length{" "}
            <select value={hours} onChange={e => setHours(+e.target.value)}>{[6, 8, 12, 24].map(h => <option key={h} value={h}>{h} hours</option>)}</select>
          </label>
          <button className="btn" onClick={copy}>Copy as text</button>
          <button className="btn primary" onClick={() => window.print()}>Print</button>
        </div>
      </div>
      <section><h2>Still open <span className="muted">{data.open.length}</span></h2><List items={data.open} empty="Nothing open." /></section>
      <section><h2>Seen but still active <span className="muted">{data.seen_still_active.length}</span></h2>
        <List items={data.seen_still_active} empty="None." /></section>
      <section>
        <h2>Done this shift <span className="muted">{data.done.length}</span></h2>
        {data.done.length ? (
          <table className="log num handover-done">
            <thead><tr><th scope="col">Time</th><th scope="col">Patient</th><th scope="col">What</th><th scope="col">Who</th><th scope="col">Note</th></tr></thead>
            <tbody>{data.done.map((d, i) => (
              <tr key={i}><td>{hhmm(d.t)}</td><td><Link to={`/patient/${d.pid}`}>{d.name}</Link></td><td>{T(d.what)}</td><td>{d.who}</td><td>{T(d.note)}</td></tr>
            ))}</tbody>
          </table>
        ) : <p className="empty">Nothing recorded in the last {hours} hours. Actions taken from a patient's banner appear here.</p>}
      </section>
    </div>
  );
}
