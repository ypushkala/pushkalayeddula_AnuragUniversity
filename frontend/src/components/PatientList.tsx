import { NavLink } from "react-router-dom";
import { api, fmt, type WardRow } from "../api";
import { useLiveData } from "../live";

export function needsAttention(r: WardRow): boolean {
  const a = r.event_a;
  return Boolean((a && (a.tier === "alert" || a.low === "now" || a.low === "forecast")) || r.event_b.flag);
}

export function statusWord(r: WardRow): { text: string; alert: boolean } {
  const a = r.event_a;
  if (a?.low === "now") return { text: "Low glucose now", alert: true };
  if (a?.low === "forecast") return { text: "Low glucose likely", alert: true };
  if (a?.tier === "alert") return { text: "High glucose likely", alert: true };
  if (r.event_b.flag) return { text: "Raised heart risk", alert: true };
  if (a?.tier === "watch") return { text: "Glucose may go high", alert: false };
  return { text: "", alert: false };
}

/** The patients needing attention, in ward order, plus the one on screen. Used for the side list and next or previous. */
export function useQueue(currentId: string) {
  const { data } = useLiveData(() => api.ward(), []);
  const rows = data?.patients ?? [];
  const queue = rows.filter(r => needsAttention(r) || r.id === currentId);
  const i = queue.findIndex(r => r.id === currentId);
  return { queue, loaded: Boolean(data), prev: i > 0 ? queue[i - 1] : undefined, next: i >= 0 && i < queue.length - 1 ? queue[i + 1] : undefined };
}

export function PatientList({ currentId }: { currentId: string }) {
  const { queue, loaded } = useQueue(currentId);
  return (
    <nav className="plist" aria-label="Patients needing attention">
      <div className="plist-head">Needs attention</div>
      {!loaded && <div className="skeleton-block" style={{ height: 300 }} />}
      <ul>
        {queue.map(r => {
          const s = statusWord(r);
          return (
            <li key={r.id}>
              <NavLink to={`/patient/${r.id}`} className={({ isActive }) => (isActive || r.id === currentId ? "active" : "")}>
                <span className="pl-name">{r.name}</span>
                <span className={`pl-status ${s.alert ? "alert-text" : "muted"}`}>
                  {s.alert && <span className="mark solid" />}{s.text}{r.glucose !== null ? `, ${fmt(r.glucose)}` : ""}
                </span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
