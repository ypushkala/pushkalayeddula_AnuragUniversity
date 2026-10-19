import { dayMonth, fmt, hhmm, T, type History } from "../api";

export function trackRecord(h: History | null, first: string, lead = true): string {
  if (!h) return "Loading";
  const s = h.summary;
  if (!s.alerts && !s.lows) return `No alerts for ${first} in the last ${h.days} days`;
  const parts = [];
  if (s.alerts) parts.push(`${s.alerts} high glucose ${s.alerts === 1 ? "alert" : "alerts"}, ${s.happened} of ${s.decided} came true`
    + (s.median_lead !== null ? `, median warning ${fmt(s.median_lead)} min` : ""));
  if (s.lows) parts.push(`${s.lows} low glucose, ${s.lows_happened} confirmed`);
  return lead ? `Last ${h.days} days: ${parts.join("; ")}` : parts.join("; ");
}

const RESULT: Record<string, string> = { happened: "Came true", "did not happen": "Did not happen", pending: "Too early to tell" };

/** Each alert in the last week: what the forecast said, what the glucose did, and what the care team did about it. */
export function EarlierAlerts({ h, first }: { h: History; first: string }) {
  const s = h.summary;
  return (
    <div className="earlier">
      <div className="earlier-summary">
        <div><div className="label">High glucose alerts</div><div className="big-num">{s.alerts}</div></div>
        <div><div className="label">Came true</div><div className="big-num">{s.decided ? `${fmt((s.rate ?? 0) * 100)}%` : "n/a"}</div>
          <div className="small muted">{s.happened} of {s.decided}</div></div>
        <div><div className="label">Median warning</div><div className="big-num">{s.median_lead !== null ? `${fmt(s.median_lead)} min` : "n/a"}</div></div>
        <div><div className="label">Highs with no alert</div><div className="big-num">{s.missed}</div>
          <div className="small muted">rose above 180 with no confident alert in the 2 h before</div></div>
      </div>
      <p className="small muted">The forecast for {first} was fitted on the first week and is not refitted since; this is how it has done on the days after.
        Each alert counts once, from when it was first raised.</p>
      {h.episodes.length ? (
        <table className="episodes">
          <thead><tr><th scope="col">Raised</th><th scope="col">The forecast said</th><th scope="col">What happened</th><th scope="col">What the team did</th></tr></thead>
          <tbody>
            {h.episodes.map(e => (
              <tr key={`${e.kind}-${e.start}`}>
                <td className="num">{dayMonth(e.start)} {hhmm(e.start)}</td>
                <td>{T(e.said)}</td>
                <td><span className={`res ${e.result === "happened" ? "yes" : e.result === "pending" ? "wait" : "no"}`}>{RESULT[e.result]}</span>
                  <div className="small muted">{T(e.what_happened)}</div></td>
                <td className="small">{e.done.length ? e.done.map(d => <div key={d}>{T(d)}</div>) : <span className="muted">Nothing recorded</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="empty">No alerts in the last {h.days} days.</p>}
    </div>
  );
}
