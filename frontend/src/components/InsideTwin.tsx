import { useEffect, useMemo, useRef, useState } from "react";
import { api, glu, gluUnit, hhmm, type Inside, type InsideSeries, type WhatIfReq } from "../api";

const W = 470, Hh = 300;

function Diagram({ s, i, max, title }: { s: InsideSeries; i: number; max: Record<string, number>; title: string }) {
  const f = (k: keyof InsideSeries) => Math.max(0, Math.min(1, s[k][i] / (max[k] || 1)));
  const g = s.G[i];
  const gFill = Math.max(0, Math.min(1, (g - 40) / 310));
  const box = (x: number, y: number, w: number, h: number, frac: number, label: string, value: string, key: string) => (
    <g key={key}>
      <rect x={x} y={y} width={w} height={h} rx={6} className="in-box" />
      <rect x={x + 1} y={y + h - (h - 2) * frac - 1} width={w - 2} height={(h - 2) * frac} rx={5} className="in-fill" />
      <text x={x + 8} y={y + 18} className="in-label">{label}</text>
      <text x={x + 8} y={y + h - 8} className="in-value">{value}</text>
    </g>
  );
  const flow = (x1: number, y1: number, x2: number, y2: number, frac: number, key: string) => (
    <line key={key} x1={x1} y1={y1} x2={x2} y2={y2} className="in-flow" strokeWidth={1 + 9 * frac} markerEnd="url(#arrow)" />
  );
  return (
    <figure className="in-fig">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${Hh}`} role="img" aria-label={`${title}: glucose ${glu(g)} ${gluUnit()}`}>
        <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" className="in-arrow" /></marker></defs>
        {box(10, 20, 120, 80, f("stomach_g"), "Stomach", `${Math.round(s.stomach_g[i])} g`, "st")}
        {box(10, 150, 120, 80, f("gut_g"), "Gut", `${Math.round(s.gut_g[i])} g`, "gut")}
        {flow(70, 104, 70, 144, f("stomach_g"), "f1")}
        {box(185, 60, 110, 150, gFill, "Blood glucose", `${glu(g)} ${gluUnit()}`, "bl")}
        {flow(134, 190, 180, 160, f("into_blood"), "f2")}
        <text x={136} y={212} className="in-small">into the blood</text>
        {box(350, 60, 110, 90, f("out_of_blood"), "Muscle and organs", "taking glucose up", "mu")}
        {flow(299, 120, 345, 110, f("out_of_blood"), "f3")}
        {box(185, 232, 110, 56, f("action"), "Insulin action", "", "ia")}
        {flow(240, 230, 330, 150, f("action"), "f4")}
        {box(350, 205, 110, 56, f("activity"), "Walking", s.activity[i] > 0.2 ? "now" : "", "wa")}
        {flow(405, 202, 405, 156, f("activity"), "f5")}
      </svg>
    </figure>
  );
}

/** The twin's insides over the next 6 hours: food moving from stomach to gut to blood, insulin acting, a walk pulling glucose into muscle. */
export function InsideTwin({ pid, req, label }: { pid: string; req: WhatIfReq; label: string }) {
  const [data, setData] = useState<Inside | null>(null);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<number>();
  useEffect(() => { setData(null); api.inside(pid, req).then(d => { setData(d); setI(0); }); }, [pid, JSON.stringify(req)]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing || !data) return;
    timer.current = window.setInterval(() => setI(x => { if (x >= data.times.length - 1) { setPlaying(false); return x; } return x + 1; }), 140);
    return () => window.clearInterval(timer.current);
  }, [playing, data]);
  const max = useMemo(() => {
    if (!data) return {};
    const m: Record<string, number> = {};
    for (const k of Object.keys(data.usual) as (keyof InsideSeries)[]) m[k] = Math.max(...data.usual[k], ...data.change[k]);
    m.activity = Math.max(1, m.activity);
    return m;
  }, [data]);
  if (!data) return <p className="empty">Loading the twin's insides.</p>;
  if (!data.available) return null;
  const line = (arr: number[]) => arr.map((v, j) => `${(j / (arr.length - 1)) * 100},${100 - ((v - 40) / 310) * 100}`).join(" ");
  const u = data.usual, c = data.change;
  const story = () => {
    const parts = [];
    if (u.stomach_g[i] > 5) parts.push("the meal is still in the stomach");
    else if (u.gut_g[i] > 5) parts.push("the meal is being absorbed from the gut");
    if (c.activity[i] > 0.2) parts.push("with the change, walking muscles are pulling glucose out of the blood");
    if (c.stomach_g[i] + c.gut_g[i] < u.stomach_g[i] + u.gut_g[i] - 10) parts.push("with the change, less food is waiting to be absorbed");
    return parts.length ? parts.join("; ") + "." : "Glucose is settling.";
  };
  return (
    <div className="inside">
      <div className="in-controls">
        <button className="btn primary" onClick={() => { if (i >= data.times.length - 1) setI(0); setPlaying(p => !p); }}>{playing ? "Pause" : "Play"}</button>
        <input type="range" min={0} max={data.times.length - 1} value={i} onChange={e => { setPlaying(false); setI(+e.target.value); }}
          aria-label="Time" />
        <span className="num in-time">{hhmm(data.times[i])}</span>
      </div>
      <p className="in-story">{hhmm(data.times[i])}: {story()} Glucose {glu(u.G[i])} usually, {glu(c.G[i])} with {label.toLowerCase()}.</p>
      <div className="in-pair">
        <Diagram s={u} i={i} max={max} title="Usual plan" />
        <Diagram s={c} i={i} max={max} title={`With ${label.toLowerCase()}`} />
      </div>
      <svg className="in-spark" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <polyline points={line(u.G)} className="in-line usual" />
        <polyline points={line(c.G)} className="in-line change" />
        <line x1={(i / (data.times.length - 1)) * 100} x2={(i / (data.times.length - 1)) * 100} y1={0} y2={100} className="in-now" />
      </svg>
      <p className="small muted">These are the twin's own internal states (the Bergman model in prativimb/twin/bergman.py), not measurements.
        Bar heights are scaled to the largest value in either plan.</p>
    </div>
  );
}
