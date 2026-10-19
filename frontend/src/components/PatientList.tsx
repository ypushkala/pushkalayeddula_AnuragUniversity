import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, glu, type Group, type WardRow } from "../api";
import { useLiveData } from "../live";

export const GROUP_NAMES: Record<Group, string> = {
  low: "Low glucose", high: "High glucose likely", heart: "Raised heart risk", watch: "Glucose may go high",
};
export const URGENT: Group[] = ["low", "high", "heart"];

export function needsAttention(r: WardRow): boolean {
  return r.group !== null && URGENT.includes(r.group);
}

export function statusWord(r: WardRow): { text: string; alert: boolean } {
  const a = r.event_a;
  if (r.group === "low") return { text: a?.low === "now" ? "Low glucose now" : "Low glucose likely", alert: !r.seen };
  if (r.group === "high") return { text: "High glucose likely", alert: !r.seen };
  if (r.group === "heart") return { text: "Raised heart risk", alert: !r.seen };
  if (r.group === "watch") return { text: "Glucose may go high", alert: false };
  return { text: "", alert: false };
}

/** Where a ward row should open: the heart section for a heart alert, the top of Today otherwise. */
export function patientLink(r: WardRow): string {
  return r.group === "heart" || r.event_b.post_event ? `/patient/${r.id}?heart=` : `/patient/${r.id}`;
}

/** The patients needing attention, most urgent first, plus the one on screen. Used for the side list and next or previous. */
export function useQueue(currentId: string) {
  const { data } = useLiveData(() => api.ward(), []);
  const rows = data?.patients ?? [];
  const queue = rows.filter(r => needsAttention(r) || r.id === currentId);
  const watch = rows.filter(r => r.group === "watch" && r.id !== currentId);
  const i = queue.findIndex(r => r.id === currentId);
  return { rows, queue, watch, loaded: Boolean(data), prev: i > 0 ? queue[i - 1] : undefined,
    next: i >= 0 && i < queue.length - 1 ? queue[i + 1] : undefined };
}

/** The next patient with an alert nobody has marked as seen, after the current one. */
export function nextUnseen(rows: WardRow[], currentId?: string): WardRow | undefined {
  const open = rows.filter(r => needsAttention(r) && !r.seen);
  if (!open.length) return undefined;
  const i = rows.findIndex(r => r.id === currentId);
  return open.find(r => rows.indexOf(r) > i && r.id !== currentId) ?? open.find(r => r.id !== currentId);
}

function Row({ r, currentId }: { r: WardRow; currentId: string }) {
  const s = statusWord(r);
  return (
    <li>
      <NavLink to={patientLink(r)} className={() => (r.id === currentId ? "active" : "")} aria-current={r.id === currentId ? "page" : undefined}>
        <span className="pl-name">{r.name}</span>
        <span className={`pl-status ${s.alert ? "alert-text" : "muted"}`}>
          {s.alert && <span className="mark solid" />}{s.text}{r.glucose !== null ? `, ${glu(r.glucose)}` : ""}{r.seen ? ", seen" : ""}
        </span>
      </NavLink>
    </li>
  );
}

export function PatientList({ currentId }: { currentId: string }) {
  const { queue, watch, loaded } = useQueue(currentId);
  const box = useRef<HTMLElement>(null);
  const [more, setMore] = useState(false);
  const urgent = queue.filter(needsAttention);
  const pos = urgent.findIndex(r => r.id === currentId);
  // The list scrolls; a fade at the bottom shows there is more.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const check = () => setMore(el.scrollTop + el.clientHeight < el.scrollHeight - 4);
    check();
    el.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => { el.removeEventListener("scroll", check); window.removeEventListener("resize", check); };
  }, [queue.length, watch.length]);
  useEffect(() => {
    box.current?.querySelector("a.active")?.scrollIntoView({ block: "nearest" });
  }, [currentId, loaded]);
  return (
    <div className={`plist-wrap ${more ? "more" : ""}`}>
      <nav className="plist" aria-label="Patients needing attention" ref={box}>
        <div className="plist-head">
          <span>Needs attention</span>
          {loaded && <span className="plist-count">{pos >= 0 ? `${pos + 1} of ${urgent.length}` : urgent.length}</span>}
        </div>
        {!loaded && <div className="skeleton-block" style={{ height: 300 }} />}
        {URGENT.map(g => {
          const rs = queue.filter(r => r.group === g);
          if (!rs.length) return null;
          return (
            <section key={g} aria-label={GROUP_NAMES[g]}>
              <div className="plist-group">{GROUP_NAMES[g]} <span className="muted">{rs.length}</span></div>
              <ul>{rs.map(r => <Row key={r.id} r={r} currentId={currentId} />)}</ul>
            </section>
          );
        })}
        {queue.filter(r => !needsAttention(r)).length > 0 && (
          <ul>{queue.filter(r => !needsAttention(r)).map(r => <Row key={r.id} r={r} currentId={currentId} />)}</ul>
        )}
        {watch.length > 0 && (
          <details className="plist-watch">
            <summary>{GROUP_NAMES.watch} <span className="muted">{watch.length}</span></summary>
            <ul>{watch.map(r => <Row key={r.id} r={r} currentId={currentId} />)}</ul>
          </details>
        )}
        {loaded && !urgent.length && <p className="empty">Nobody needs attention right now.</p>}
      </nav>
      {more && <button className="plist-more link-btn" onClick={() => box.current?.scrollBy({ top: 240, behavior: "smooth" })}
        aria-label="Show more patients">More below</button>}
    </div>
  );
}
