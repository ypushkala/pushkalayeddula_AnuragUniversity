import { api, fullTime, type ConsentRow, type Session } from "../api";
import { useLive, useLiveData } from "../live";

/** Each data source the service uses, with its consent, and a way to withdraw or grant it again (DPDP Act 2023). */
export function ConsentPanel({ pid, as, labels }: { pid: string; as?: Session;
  labels?: { granted: string; withdrawn: string; withdraw: string; grant: string; since: string } }) {
  const { can, refresh, toast } = useLive();
  const { data } = useLiveData(() => api.consent(pid), [pid]);
  const L = labels ?? { granted: "Shared", withdrawn: "Withdrawn", withdraw: "Withdraw", grant: "Share again", since: "since" };
  const allowed = Boolean(as) || can("consent");
  if (!data) return <p className="empty">Loading.</p>;
  const change = (c: ConsentRow, granted: boolean) =>
    api.setConsent(pid, { source: c.source, granted }, as)
      .then(() => { refresh(); toast({ text: `${c.name}: ${granted ? L.granted : L.withdrawn}.`, undo: () => api.setConsent(pid, { source: c.source, granted: !granted }, as) }); })
      .catch(e => toast({ text: e.message, error: true }));
  return (
    <ul className="consent">
      {data.map(c => (
        <li key={c.source}>
          <div>
            <div className="c-name">{c.name}</div>
            <div className="small muted">{c.what}</div>
            <div className={`small ${c.granted ? "" : "alert-text"}`}>{c.granted ? L.granted : L.withdrawn} {L.since} {fullTime(c.since)}{c.by !== "Enrolment" ? `, ${c.by}` : ""}</div>
          </div>
          {allowed && (c.granted
            ? <button className="btn" onClick={() => change(c, false)}>{L.withdraw}</button>
            : <button className="btn primary" onClick={() => change(c, true)}>{L.grant}</button>)}
        </li>
      ))}
    </ul>
  );
}
