import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, dayToDate, dayMonth, fmt, hhmm, minuteToDate, signed, type WardRow } from "../api";
import { SkeletonRows } from "../components/Skeleton";
import { Sparkline } from "../components/Sparkline";
import { store, stored, useLive, useLiveData } from "../live";

type Filter = "all" | "alert" | "cardio" | "watch" | "story";

function glucoseFlag(r: WardRow) {
  const a = r.event_a;
  if (!a) return <span className="flag quiet">No recent reading</span>;
  const parts = [];
  if (a.artefact) parts.push(<span key="art" className="flag quiet">Low reading, probably sensor compression</span>);
  if (a.low === "now") parts.push(<span key="low" className={`flag ${a.low_ack ? "acked" : "alert"}`}><span className="mark solid" />Low now, {fmt(a.glucose)}</span>);
  else if (a.low === "forecast") parts.push(<span key="lowf" className={`flag ${a.low_ack ? "acked" : "alert"}`}><span className="mark solid" />Low likely within 60 min</span>);
  if (a.tier === "alert") parts.push(
    <span key="a" className={`flag ${a.ack ? "acked" : "alert"}`}><span className={`mark ${a.ack ? "" : "solid"}`} />
      Above 180 by {hhmm(minuteToDate(a.cross_minute!))}, peak {fmt(a.peak)}</span>);
  else if (a.tier === "watch") parts.push(<span key="w" className="flag watch"><span className="mark" />Watch: peak {fmt(a.peak)} at {hhmm(minuteToDate(a.peak_minute))}</span>);
  else if (a.tier === "high") parts.push(<span key="h" className="flag quiet">Above range now</span>);
  const ack = a.ack ?? a.low_ack;
  if (ack) parts.push(<span key="ack" className="sub">Acknowledged by {ack.by}, quiet until {hhmm(minuteToDate(ack.until))}</span>);
  if (!parts.length) return <span className="flag quiet">In range for 2 h</span>;
  return <div style={{ display: "grid", gap: 2 }}>{parts}</div>;
}

function cardioFlag(r: WardRow) {
  const b = r.event_b;
  if (b.post_event) return <span className="flag quiet">Event {b.event_minute !== undefined ? dayMonth(minuteToDate(b.event_minute)) : ""}</span>;
  if (b.risk === null) return <span className="flag quiet">n/a</span>;
  if (b.flag) return (
    <span className={`flag ${b.ack ? "acked" : "alert"}`}><span className={`mark ${b.ack ? "" : "solid"}`} />{fmt(b.risk * 100)}%
      {b.flag_since !== null && b.flag_since !== undefined ? `, since ${dayMonth(dayToDate(b.flag_since))}` : ""}</span>
  );
  return <span className="flag quiet num">{b.risk < 0.01 ? "<1" : fmt(b.risk * 100)}%</span>;
}

function sinceSync(last: string | null, now: string | undefined) {
  if (!last || !now) return "";
  const mins = Math.round((new Date(now).getTime() - new Date(last).getTime()) / 60000);
  return mins <= 0 ? "now" : `${mins} min ago`;
}

/** Alert keys the clinician has to know about. Acknowledged alerts do not count as new. */
function alertKeys(rows: WardRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    if (r.event_a?.tier === "alert" && !r.event_a.ack) out[`${r.id}:spike`] = r.name;
    if ((r.event_a?.low === "now" || r.event_a?.low === "forecast") && !r.event_a.low_ack) out[`${r.id}:low`] = r.name;
    if (r.event_b.flag && !r.event_b.ack) out[`${r.id}:cardio`] = r.name;
  }
  return out;
}

const KIND: Record<string, string> = { spike: "glucose alert", low: "low glucose", cardio: "cardiovascular flag" };

function SinceLastLooked({ rows, now }: { rows: WardRow[]; now: string }) {
  const current = alertKeys(rows);
  const [snap, setSnap] = useState<{ t: string; keys: Record<string, string> } | null>(() => {
    try { return JSON.parse(stored("prativimb-ward-seen", "null")); } catch { return null; }
  });
  const markSeen = () => {
    const s = { t: now, keys: current };
    store("prativimb-ward-seen", JSON.stringify(s));
    setSnap(s);
  };
  useEffect(() => { if (!snap) markSeen(); /* first visit: start from now */ }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!snap) return null;
  const added = Object.keys(current).filter(k => !(k in snap.keys));
  const resolved = Object.keys(snap.keys).filter(k => !(k in current));
  const describe = (keys: string[], names: Record<string, string>) => {
    const list = keys.slice(0, 4).map(k => `${names[k]} (${KIND[k.split(":")[1]]})`);
    return list.join(", ") + (keys.length > 4 ? ` and ${keys.length - 4} more` : "");
  };
  return (
    <div className="since" role="status">
      <span className="label">Since you last looked, {hhmm(snap.t)}</span>
      {!added.length && !resolved.length ? <span className="muted"> Nothing new.</span> : (
        <>
          {added.length > 0 && <span> <b className="alert-text">{added.length} new:</b> {describe(added, current)}.</span>}
          {resolved.length > 0 && <span> <b>{resolved.length} resolved or acknowledged:</b> {describe(resolved, snap.keys)}.</span>}
        </>
      )}
      <button className="link-btn" onClick={markSeen}>Mark all as seen</button>
    </div>
  );
}

export function Ward() {
  const { clock } = useLive();
  const { data, error } = useLiveData(() => api.ward(), []);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [compact, setCompact] = useState(() => stored("prativimb-density", "comfortable") === "compact");
  const [cursor, setCursor] = useState(0);
  const search = useRef<HTMLInputElement>(null);
  const byKeyboard = useRef(false);
  const body = useRef<HTMLTableSectionElement>(null);
  const nav = useNavigate();

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.patients.filter(r => {
      if (needle && !`${r.name} ${r.id}`.toLowerCase().includes(needle)) return false;
      if (filter === "alert") return r.event_a?.tier === "alert" || r.event_a?.low === "now" || r.event_a?.low === "forecast";
      if (filter === "cardio") return r.event_b.flag;
      if (filter === "watch") return r.event_a?.tier === "watch";
      if (filter === "story") return r.hero;
      return true;
    });
  }, [data, filter, q]);

  // Keyboard: j and k move, Enter opens, slash searches.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      if (e.key === "/") { e.preventDefault(); search.current?.focus(); }
      else if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); byKeyboard.current = true; setCursor(c => Math.min(c + 1, rows.length - 1)); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); byKeyboard.current = true; setCursor(c => Math.max(c - 1, 0)); }
      else if (e.key === "Enter" && rows[cursor]) nav(`/patient/${rows[cursor].id}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor, nav]);
  useEffect(() => {
    if (!byKeyboard.current) return;
    byKeyboard.current = false;
    (body.current?.children[cursor] as HTMLElement | undefined)?.focus();
  }, [cursor]);
  useEffect(() => setCursor(0), [filter, q]);

  if (error) return <p className="empty">Could not reach the twin service ({error}). Is the API running on port 8000?</p>;
  const p = data?.patients ?? [];
  const counts = {
    all: p.length,
    alert: p.filter(r => r.event_a?.tier === "alert" || r.event_a?.low === "now" || r.event_a?.low === "forecast").length,
    cardio: p.filter(r => r.event_b.flag).length,
    watch: p.filter(r => r.event_a?.tier === "watch").length,
    story: p.filter(r => r.hero).length,
  };
  const labels: Record<Filter, string> = { all: "All patients", alert: "Glucose alerts", cardio: "Cardiovascular flags", watch: "Watch", story: "Demo patients" };
  const toggleDensity = () => { setCompact(c => { store("prativimb-density", c ? "comfortable" : "compact"); return !c; }); };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Diabetes and cardiometabolic panel</h1>
          <div className="meta">
            Remote monitoring, {counts.all || 200} patients. Sorted by priority: glucose alerts, cardiovascular flags, then forecast peak.
            {clock && <> Data as of {hhmm(clock.now)} IST.</>}
          </div>
        </div>
        <div className="head-tools">
          <input ref={search} type="search" placeholder="Name or ID  ( / )" value={q} onChange={e => setQ(e.target.value)} aria-label="Search patients" />
          <button className="btn" onClick={toggleDensity} aria-pressed={compact}>{compact ? "Comfortable rows" : "Compact rows"}</button>
        </div>
      </div>
      {data && clock && <SinceLastLooked rows={data.patients} now={clock.now} />}
      <div className="filters" role="tablist" aria-label="Filter patients">
        {(Object.keys(labels) as Filter[]).map(f => (
          <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)} role="tab" aria-selected={filter === f}>
            {labels[f]}<span className="count num">{data ? counts[f] : ""}</span>
          </button>
        ))}
        <span className="kbd-hint muted small">Keys: j and k to move, Enter to open, / to search</span>
      </div>
      <table className={`ward ${compact ? "compact" : ""}`}>
        <thead>
          <tr>
            <th scope="col">Patient</th>
            <th scope="col" className="hide-sm">Age, sex</th>
            <th scope="col" className="hide-md">Problems</th>
            <th scope="col" className="r hide-sm">HbA1c</th>
            <th scope="col" className="r">Glucose</th>
            <th scope="col" className="hide-sm">Last 24 h</th>
            <th scope="col">Glucose, next 2 h</th>
            <th scope="col">CV risk, 3 days</th>
            <th scope="col" className="r hide-md">Last sync</th>
          </tr>
        </thead>
        {!data ? <SkeletonRows /> : (
          <tbody ref={body}>
            {rows.map((r, i) => (
              <tr key={r.id} className={`row ${i === cursor ? "cursor" : ""}`} onClick={() => nav(`/patient/${r.id}`)} tabIndex={0}
                onFocus={() => setCursor(i)} onKeyDown={e => e.key === "Enter" && nav(`/patient/${r.id}`)}
                aria-label={`${r.name}, open patient twin`}>
                <td><div className="name">{r.name}</div><div className="sub mono">{r.id}<span className="show-sm"> &middot; {r.age} {r.sex}</span></div></td>
                <td className="num hide-sm">{r.age} {r.sex}</td>
                <td className="small ink2 hide-md">{r.problems.join(", ") || "None recorded"}</td>
                <td className="r num hide-sm">{fmt(r.hba1c, 1)}%</td>
                <td className="r num c-glucose">
                  <div>{fmt(r.glucose)}</div>
                  <div className="sub">{r.trend30 !== null ? `${signed(r.trend30)} / 30 min` : ""}</div>
                </td>
                <td className="hide-sm"><Sparkline values={r.sparkline} /></td>
                <td className="c-flag">{glucoseFlag(r)}</td>
                <td className="c-cv" data-label="CV risk, 3 days">{cardioFlag(r)}</td>
                <td className="r num small hide-md">{r.last_sync ? hhmm(r.last_sync) : ""}<div className="sub">{sinceSync(r.last_sync, clock?.now)}</div></td>
              </tr>
            ))}
          </tbody>
        )}
      </table>
      {data && !rows.length && <p className="empty">No patients match.</p>}
    </>
  );
}
