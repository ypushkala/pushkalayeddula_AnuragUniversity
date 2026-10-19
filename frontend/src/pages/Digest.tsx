import { Link } from "react-router-dom";
import { api, fmt, T } from "../api";
import { SkeletonBlock } from "../components/Skeleton";
import { useLive, useLiveData } from "../live";

/** The morning summary of the day before, for email. Confirmed alerts are pushed as they happen; this is the overview. */
export function Digest() {
  const { toast } = useLive();
  const { data } = useLiveData(() => api.digest(), []);
  if (!data) return <SkeletonBlock height={300} label="Working through yesterday, a few seconds" />;
  const text = [
    `Prativimb daily digest, ${data.date}`,
    `${data.patients} patients. Time in range across the ward: ${fmt(data.tir)}%.`,
    `${data.alerts} high glucose alerts (${fmt(data.alerts_per_patient, 1)} per patient); ${data.alerts_happened} of ${data.alerts_total} came true.`,
    `${data.lows} low glucose alerts.`,
    `Raised heart risk: ${data.heart_flags.map(h => h.name).join(", ") || "none"}.`,
    `Most alerts: ${data.most_alerts.map(m => `${m.name} (${m.alerts} high, ${m.lows} low)`).join("; ")}.`,
    `Care team: ${data.actions.seen} alerts marked as seen, ${data.actions.actions} calls, checks or reviews, ${data.actions.meals} meals logged.`,
  ].join("\n");
  const copy = () => navigator.clipboard?.writeText(text).then(() => toast({ text: "Digest copied, ready to paste into an email." })).catch(() => toast({ text: "Could not copy.", error: true }));
  return (
    <div className="digest">
      <div className="page-head">
        <div><h1>Daily digest</h1><div className="meta">{data.date}, the day before the current time</div></div>
        <div className="row-actions no-print">
          <button className="btn" onClick={copy}>Copy for email</button>
          <a className="btn primary" href={`mailto:?subject=${encodeURIComponent(`Prativimb digest, ${data.date}`)}&body=${encodeURIComponent(text)}`}>Email</a>
        </div>
      </div>
      <p className="small muted">Sent each morning. Confirmed alerts (lows, likely highs, raised heart risk) reach you as they happen; possible highs stay in the app and are only counted here.</p>
      <div className="digest-nums num">
        <div><div className="label">Time in range, whole ward</div><div className="big-num">{fmt(data.tir)}%</div></div>
        <div><div className="label">High glucose alerts</div><div className="big-num">{data.alerts}</div>
          <div className="small muted">{fmt(data.alerts_per_patient, 1)} per patient; {data.alerts_happened} of {data.alerts_total} came true</div></div>
        <div><div className="label">Low glucose alerts</div><div className="big-num">{data.lows}</div></div>
        <div><div className="label">Raised heart risk</div><div className="big-num">{data.heart_flags.length}</div></div>
      </div>
      <div className="two">
        <section>
          <h2>Most alerts yesterday</h2>
          <table className="log num"><tbody>
            {data.most_alerts.map(m => <tr key={m.pid}><td><Link to={`/patient/${m.pid}/record#earlier`}>{m.name}</Link></td><td>{m.alerts} high, {m.lows} low</td></tr>)}
          </tbody></table>
        </section>
        <section>
          <h2>Raised heart risk</h2>
          {data.heart_flags.length ? <ul className="plain">{data.heart_flags.map(h => <li key={h.pid}><Link to={`/patient/${h.pid}?heart=`}>{h.name}</Link></li>)}</ul>
            : <p className="empty">None.</p>}
          <h2>Care team</h2>
          <p>{T(`${data.actions.seen} alerts marked as seen, ${data.actions.actions} calls, checks or reviews, ${data.actions.meals} meals logged.`)}</p>
        </section>
      </div>
    </div>
  );
}
