import { useState } from "react";
import { Link } from "react-router-dom";
import { api, dayMonth, fmt, glu, gluUnit, type Festival } from "../api";
import { SkeletonBlock } from "../components/Skeleton";
import { useLive, useLiveData } from "../live";

function FestivalBlock({ f }: { f: Festival }) {
  const { can, refresh, toast } = useLive();
  const [busy, setBusy] = useState(false);
  const send = (pids: string[]) => {
    setBusy(true);
    api.festivalNudge(f.key, pids).then(r => {
      refresh();
      toast({ text: `Sent ${r.sent.length} ${r.sent.length === 1 ? "message" : "messages"}${r.skipped.length ? `; ${r.skipped.length} already had one` : ""}.`,
        undo: () => Promise.all(r.sent.map(x => api.removeMessage(x.pid, x.id))) });
    }).catch(e => toast({ text: e.message, error: true })).finally(() => setBusy(false));
  };
  const callList = () => {
    const text = [`${f.name}, ${dayMonth(f.date)}: who to call first`,
      ...f.most_affected.map(r => `- ${r.name} (${r.festival_local}): about ${fmt(r.extra_hours_above * 60)} min more above 180; suggest ${f.tips[r.best].toLowerCase()} (saves about ${fmt(r.best_saved_hours * 60)} min)`)].join("\n");
    navigator.clipboard?.writeText(text).then(() => toast({ text: "Call list copied." })).catch(() => toast({ text: "Could not copy.", error: true }));
  };
  return (
    <section className="fest">
      <h2>{f.name} <span className="muted">{dayMonth(f.date)}</span></h2>
      <p className="muted">{f.about} {f.patients} patients {f.key === "new_year" ? "live where it is celebrated" : "said they keep it"}.</p>
      <p>Together about <b>{fmt(f.total_extra_hours)} more hours above 180</b> than on a usual day; if each made the change that helps them most,
        about {fmt(f.total_saved_hours)} hours fewer.</p>
      {f.most_affected.length ? (
        <>
          <table className="log num fest-table">
            <thead><tr><th scope="col">Patient</th><th scope="col">Festival here</th><th scope="col">Extra time above 180</th>
              <th scope="col">Highest, usual and festival day</th><th scope="col">What helps most</th>{can("act") && <th scope="col"><span className="visually-hidden">Message</span></th>}</tr></thead>
            <tbody>{f.most_affected.map(r => (
              <tr key={r.pid}>
                <td><Link to={`/patient/${r.pid}/try`}>{r.name}</Link></td>
                <td>{r.festival_local}<div className="sub muted">{r.dish}</div></td>
                <td>{fmt(r.extra_hours_above * 60)} min</td>
                <td>{glu(r.usual_peak)} and {glu(r.festival_peak)} {gluUnit()}</td>
                <td>{f.tips[r.best]}<div className="sub muted">{r.best_saved_hours > 0.05 ? `about ${fmt(r.best_saved_hours * 60)} min less above 180` : "little difference"}</div></td>
                {can("act") && <td><button className="link-btn" disabled={busy} onClick={() => send([r.pid])}>Message</button></td>}
              </tr>
            ))}</tbody>
          </table>
          <div className="row-actions">
            {can("act") && <button className="btn primary" disabled={busy} onClick={() => send([])}>Message these {f.most_affected.length} patients</button>}
            <button className="btn" onClick={callList}>Copy the call list</button>
          </div>
        </>
      ) : <p className="empty">Nobody is expected to go much higher than usual.</p>}
    </section>
  );
}

/** Coming festivals: each patient's twin replays the festival day against a usual day, so the team knows whom to call first. */
export function Festivals() {
  const { data } = useLiveData(() => api.festivals(), []);
  if (!data) return <SkeletonBlock height={320} label="Replaying the festival days for each patient, a few seconds" />;
  return (
    <div className="festivals">
      <div className="page-head">
        <div>
          <h1>Festival planner</h1>
          <div className="meta">Who to call before the next festivals. Each patient's glucose forecast replays the festival day against a usual day,
            and then the day again with each suggestion.</div>
        </div>
      </div>
      {!data.festivals.length && <p className="empty">No festivals in the next ten days.</p>}
      {data.festivals.map(f => <FestivalBlock key={f.key} f={f} />)}
      <p className="small muted">Festival menus are typical for the state and observance (puran poli for Gudi Padwa in Maharashtra, obbattu in Karnataka,
        bobbatlu in Telangana and Andhra Pradesh, sabudana on a Navratri fast, sheer khurma and biryani for Eid), not each family's. The forecast runs several
        days past the recorded data, where its absolute level drifts, so it compares days for the same patient rather than reading the level.
        Eid al-Fitr depends on the moon; Navratri lasts nine days and the first fast is shown. Messages go to each patient's phone in their language.</p>
    </div>
  );
}
