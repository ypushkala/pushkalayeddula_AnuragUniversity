import { Link } from "react-router-dom";
import { api, T } from "../api";
import { useLiveData } from "../live";

/** What missing information would narrow the forecast most, and roughly by how much. */
export function Sharpen({ pid }: { pid: string }) {
  const { data } = useLiveData(() => api.sharpen(pid), [pid]);
  if (!data || !data.items.length) return null;
  return (
    <section className="sharpen" aria-label="What would sharpen this forecast">
      <h3>What would sharpen this forecast</h3>
      <ul>
        {data.items.map(i => (
          <li key={i.kind}>
            <div>{T(i.text)}</div>
            <div className="small muted">{T(i.detail)}</div>
          </li>
        ))}
      </ul>
      <p className="small muted">Worked out by re-running the forecast with the meal's usual spread for this patient. An estimate, not a promise.
        {" "}<Link to={`/patient/${pid}/record#learned`}>How the forecast works</Link></p>
    </section>
  );
}
