import { Link } from "react-router-dom";
import { api, dayMonth, fmt, glu, gluUnit } from "../api";
import { SkeletonBlock } from "../components/Skeleton";
import { useLiveData } from "../live";

/** Coming festivals: each patient's twin replays the festival day against a usual day, so the team knows whom to call first. */
export function Festivals() {
  const { data } = useLiveData(() => api.festivals(), []);
  if (!data) return <SkeletonBlock height={320} label="Replaying the festival days for each patient, a few seconds" />;
  return (
    <div className="festivals">
      <div className="page-head">
        <div>
          <h1>Festival planner</h1>
          <div className="meta">Who to call before the next festivals. Each patient's glucose forecast replays the festival day against a usual day.</div>
        </div>
      </div>
      {!data.festivals.length && <p className="empty">No festivals in the next ten days.</p>}
      {data.festivals.map(f => (
        <section key={f.key} className="fest">
          <h2>{f.name} <span className="muted">{dayMonth(f.date)}</span></h2>
          <p className="muted">{f.about} {f.patients} patients {f.key === "ugadi" ? "in cities that celebrate it" : "who said they keep it"}; together about
            {" "}{fmt(f.total_extra_hours)} more hours above 180 than on a usual day.</p>
          <p><b>Suggest:</b> {f.suggest}</p>
          {f.most_affected.length ? (
            <table className="log num fest-table">
              <thead><tr><th scope="col">Patient</th><th scope="col">Extra time above 180</th><th scope="col">Highest, usual day</th><th scope="col">Highest, festival day</th></tr></thead>
              <tbody>{f.most_affected.map(r => (
                <tr key={r.pid}><td><Link to={`/patient/${r.pid}/try`}>{r.name}</Link></td><td>{fmt(r.extra_hours_above * 60)} min</td>
                  <td>{glu(r.usual_peak)} {gluUnit()}</td><td>{glu(r.festival_peak)} {gluUnit()}</td></tr>
              ))}</tbody>
            </table>
          ) : <p className="empty">Nobody is expected to go much higher than usual.</p>}
        </section>
      ))}
      <p className="small muted">Festival menus are typical for the region and observance, not each family's. The forecast runs several days past the recorded data,
        where its absolute level drifts, so it compares the festival day with a usual day for the same patient rather than reading the level. Eid al-Fitr depends on the moon.</p>
    </div>
  );
}
