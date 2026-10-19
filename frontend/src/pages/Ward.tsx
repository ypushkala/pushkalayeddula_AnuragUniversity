import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, dayToDate, dayMonth, fmt, hhmm, minuteToDate, signed, type WardRow } from "../api";
import { Sparkline } from "../components/Sparkline";
import { useLive, useLiveData } from "../live";

type Filter = "all" | "alert" | "cardio" | "watch" | "story";

function glucoseFlag(r: WardRow) {
  const a = r.event_a;
  if (!a) return <span className="flag quiet">No recent reading</span>;
  const parts = [];
  if (a.low === "now") parts.push(<span key="low" className="flag alert"><span className="mark solid" />Low now, {fmt(a.glucose)}</span>);
  else if (a.low === "forecast") parts.push(<span key="lowf" className="flag watch"><span className="mark" />Low by {hhmm(minuteToDate(a.low_minute!))}</span>);
  if (a.tier === "alert") parts.push(<span key="a" className="flag alert"><span className="mark solid" />Above 180 by {hhmm(minuteToDate(a.cross_minute!))}, peak {fmt(a.peak)}</span>);
  else if (a.tier === "watch") parts.push(<span key="w" className="flag watch"><span className="mark" />Watch: peak {fmt(a.peak)} at {hhmm(minuteToDate(a.peak_minute))}</span>);
  else if (a.tier === "high") parts.push(<span key="h" className="flag quiet">Above range now</span>);
  if (!parts.length) return <span className="flag quiet">In range for 2 h</span>;
  return <div style={{ display: "grid", gap: 2 }}>{parts}</div>;
}

function cardioFlag(r: WardRow) {
  const b = r.event_b;
  if (b.post_event) return <span className="flag quiet">Event {b.event_minute !== undefined ? dayMonth(minuteToDate(b.event_minute)) : ""}</span>;
  if (b.risk === null) return <span className="flag quiet">n/a</span>;
  if (b.flag) return (
    <span className="flag alert"><span className="mark solid" />{fmt(b.risk * 100)}%
      {b.flag_since !== null && b.flag_since !== undefined ? `, since ${dayMonth(dayToDate(b.flag_since))}` : ""}</span>
  );
  return <span className="flag quiet num">{b.risk < 0.01 ? "<1" : fmt(b.risk * 100)}%</span>;
}

function sinceSync(last: string | null, now: string | undefined) {
  if (!last || !now) return "";
  const mins = Math.round((new Date(now).getTime() - new Date(last).getTime()) / 60000);
  return mins <= 0 ? "now" : `${mins} min ago`;
}

export function Ward() {
  const { clock } = useLive();
  const { data, error } = useLiveData(() => api.ward(), []);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const nav = useNavigate();

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.patients.filter(r => {
      if (needle && !`${r.name} ${r.id}`.toLowerCase().includes(needle)) return false;
      if (filter === "alert") return r.event_a?.tier === "alert" || r.event_a?.low === "now";
      if (filter === "cardio") return r.event_b.flag;
      if (filter === "watch") return r.event_a?.tier === "watch" || r.event_a?.low === "forecast";
      if (filter === "story") return r.hero;
      return true;
    });
  }, [data, filter, q]);

  if (error) return <p className="empty">Could not reach the twin service ({error}). Is the API running on port 8000?</p>;
  if (!data) return <p className="empty">Loading ward.</p>;
  const p = data.patients;
  const counts = {
    all: p.length,
    alert: p.filter(r => r.event_a?.tier === "alert" || r.event_a?.low === "now").length,
    cardio: p.filter(r => r.event_b.flag).length,
    watch: p.filter(r => r.event_a?.tier === "watch" || r.event_a?.low === "forecast").length,
    story: p.filter(r => r.hero).length,
  };
  const labels: Record<Filter, string> = { all: "All patients", alert: "Glucose alerts", cardio: "Cardiovascular flags", watch: "Watch", story: "Demo patients" };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Diabetes and cardiometabolic panel</h1>
          <div className="meta">
            Remote monitoring, {counts.all} patients. Sorted by priority: glucose alerts, cardiovascular flags, then forecast peak.
            {clock && <> Data as of {hhmm(clock.now)} IST.</>}
          </div>
        </div>
        <input type="search" placeholder="Name or ID" value={q} onChange={e => setQ(e.target.value)} aria-label="Search patients" />
      </div>
      <div className="filters" role="tablist">
        {(Object.keys(labels) as Filter[]).map(f => (
          <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)} role="tab" aria-selected={filter === f}>
            {labels[f]}<span className="count num">{counts[f]}</span>
          </button>
        ))}
      </div>
      <table className="ward">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Age, sex</th>
            <th>Problems</th>
            <th className="r">HbA1c</th>
            <th className="r">Glucose</th>
            <th>Last 24 h</th>
            <th>Glucose, next 2 h</th>
            <th>CV risk, 3 days</th>
            <th className="r">Last sync</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className="row" onClick={() => nav(`/patient/${r.id}`)} tabIndex={0}
              onKeyDown={e => e.key === "Enter" && nav(`/patient/${r.id}`)}>
              <td><div className="name">{r.name}</div><div className="sub mono">{r.id}</div></td>
              <td className="num">{r.age} {r.sex}</td>
              <td className="small ink2">{r.problems.join(", ") || "None recorded"}</td>
              <td className="r num">{fmt(r.hba1c, 1)}%</td>
              <td className="r num">
                <div>{fmt(r.glucose)}</div>
                <div className="sub">{r.trend30 !== null ? `${signed(r.trend30)} / 30 min` : ""}</div>
              </td>
              <td><Sparkline values={r.sparkline} /></td>
              <td>{glucoseFlag(r)}</td>
              <td>{cardioFlag(r)}</td>
              <td className="r num small">{r.last_sync ? hhmm(r.last_sync) : ""}<div className="sub">{sinceSync(r.last_sync, clock?.now)}</div></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="empty">No patients match.</p>}
    </>
  );
}
