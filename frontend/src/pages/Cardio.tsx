import * as Plot from "@observablehq/plot";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, dayMonth, dayToDate, fmt, fullTime } from "../api";
import { Disclosure } from "../components/Disclosure";
import { PlotFigure, baseStyle } from "../components/PlotFigure";
import { TableView } from "../components/TableView";
import { useLive, useLiveData } from "../live";

const ROWS: { key: string; name: string; unit: string; digits: number; scale?: number }[] = [
  { key: "rhr", name: "Resting heart rate", unit: "bpm", digits: 0 },
  { key: "rmssd", name: "HRV, RMSSD", unit: "ms", digits: 0 },
  { key: "sleep_h", name: "Total sleep", unit: "h", digits: 1 },
  { key: "deep_min", name: "Deep sleep", unit: "min", digits: 0 },
  { key: "rem_min", name: "REM sleep", unit: "min", digits: 0 },
  { key: "awakenings", name: "Awakenings", unit: "", digits: 0 },
  { key: "efficiency", name: "Sleep efficiency", unit: "%", digits: 0, scale: 100 },
  { key: "steps", name: "Steps", unit: "", digits: 0 },
];

export function Cardio() {
  const { id = "" } = useParams();
  const { palette: p, clock } = useLive();
  const [params] = useSearchParams();
  const [end, setEnd] = useState<number | undefined>(params.get("end") ? Number(params.get("end")) : undefined);
  const { data: v } = useLiveData(() => api.cardio(id, end), [id, end]);
  if (!v) return <p className="empty">Loading wearable week.</p>;
  const lastComplete = clock ? Math.floor(clock.minute / 1440) - 1 : v.end_day;
  const byKey = Object.fromEntries(v.metrics.map(m => [m.metric, m]));

  const shade = (z: number | null) => {
    if (z === null || !isFinite(z) || z <= 0.25) return { background: "transparent", color: "var(--ink)" };
    // Four ordinal steps that skip the mid greys, where neither dark nor light text reaches 4.5:1.
    const mix = z < 1 ? 15 : z < 2 ? 30 : z < 3 ? 70 : 82;
    return { background: `color-mix(in srgb, var(--ink) ${mix}%, var(--paper))`, color: mix >= 70 ? "var(--paper)" : "var(--ink)" };
  };

  const sleepRows = v.dates.flatMap((d, i) => [
    { date: dayMonth(d), stage: "Deep", min: byKey.deep_min?.values[i] ?? 0 },
    { date: dayMonth(d), stage: "REM", min: byKey.rem_min?.values[i] ?? 0 },
    { date: dayMonth(d), stage: "Core", min: byKey.core_min?.values[i] ?? 0 },
    { date: dayMonth(d), stage: "Awake", min: byKey.awake_min?.values[i] ?? 0 },
  ]).map(r => ({ ...r, h: (r.min ?? 0) / 60 }));
  const stageColor = { Deep: p.accent, REM: p.ink3, Core: p.ruleStrong, Awake: p.paper2 };

  const sleepSpec = () => ({
    height: 200, marginLeft: 36, marginRight: 8, marginTop: 14, marginBottom: 26, style: baseStyle(p.ink3),
    x: { domain: v.dates.map(d => dayMonth(d)), label: null, padding: 0.35 },
    y: { label: "hours", labelAnchor: "top" as const, grid: true, ticks: 4 },
    color: { domain: ["Deep", "REM", "Core", "Awake"], range: [stageColor.Deep, stageColor.REM, stageColor.Core, stageColor.Awake] },
    marks: [
      Plot.barY(sleepRows, { x: "date", y: "h", fill: "stage", order: ["Deep", "REM", "Core", "Awake"], insetTop: 1, insetBottom: 1,
        stroke: p.paper, strokeWidth: 1 }),
      Plot.ruleY([0], { stroke: p.ruleStrong }),
      Plot.tip(sleepRows, Plot.pointer({ x: "date", y: "h", fill: p.paper, stroke: p.ruleStrong,
        title: (r: any) => `${r.date}  ${r.stage} ${fmt(r.min)} min` })),
    ],
  });

  const traj = v.trajectory.map(t => ({ ...t, d: new Date(t.date) }));
  const pre = traj.filter(t => !t.post_event && t.risk !== null);
  const ymax = Math.max(0.2, ...pre.map(t => t.risk as number)) * 1.15;
  const trajSpec = () => ({
    height: 200, marginLeft: 40, marginRight: 20, marginTop: 16, marginBottom: 26, style: baseStyle(p.ink3),
    x: { type: "time" as const, tickFormat: (d: Date) => dayMonth(d), ticks: 6, label: null },
    y: { domain: [0, ymax], label: "risk of event in 3 days", labelAnchor: "top" as const, tickFormat: (x: number) => `${Math.round(x * 100)}%`, grid: true, ticks: 4 },
    marks: [
      Plot.rect([0], { x1: dayToDate(v.end_day - 6), x2: new Date(dayToDate(v.end_day).getTime() + 86400e3), y1: 0, y2: ymax, fill: p.band }),
      Plot.ruleY([v.threshold], { stroke: p.ink3 }),
      Plot.text([v.threshold], { x: pre.length ? pre[0].d : new Date(), y: (t: number) => t, text: () => "flag threshold", dy: -7, textAnchor: "start", fill: p.ink3 }),
      Plot.lineY(pre, { x: "d", y: "risk", stroke: p.accent, strokeWidth: 2 }),
      Plot.dot(pre.filter(t => t.flag), { x: "d", y: "risk", r: 3.5, fill: p.alert, stroke: p.paper, strokeWidth: 1.5 }),
      ...(v.event ? [
        Plot.ruleX([new Date(v.event.time)], { stroke: p.alert, strokeWidth: 1.2 }),
        Plot.text([new Date(v.event.time)], { x: (d: Date) => d, y: ymax, text: () => "event", dx: 4, dy: 6, textAnchor: "start", fill: p.alert }),
      ] : []),
      Plot.tip(pre, Plot.pointerX({ x: "d", y: "risk", fill: p.paper, stroke: p.ruleStrong,
        title: (t: any) => `${dayMonth(t.d)}  ${fmt((t.risk as number) * 100, 1)}%${t.flag ? ", flagged" : ""}` })),
    ],
  });

  // Describe the week on screen, not today: a past week can be flagged even if an event has happened since.
  const status = v.risk === null ? "After the recorded event; risk is not scored for this week."
    : v.flag ? `Raised risk of a heart event within 3 days (${fmt(v.risk * 100)}%).`
    : "No sign of raised risk this week.";
  return (
    <>
      <div className="wi-head">
        <div>
          <h2>Heart health, week ending {dayMonth(dayToDate(v.end_day))}</h2>
          <p className={`lead ${v.flag ? "alert-text" : ""}`}>{status}</p>
          {v.event && <p className="alert-text">Event recorded {fullTime(v.event.time)}: {v.event.description}.</p>}
          {v.factors.length > 0 && v.flag && (
            <ul className="reasons">{v.factors.slice(0, 3).map(f => <li key={f.factor}>{f.text}</li>)}</ul>
          )}
        </div>
        <div className="week-nav no-print" role="group" aria-label="Change week">
          <button className="btn" onClick={() => setEnd(Math.max(12, v.end_day - 1))}>Earlier</button>
          <button className="btn" onClick={() => setEnd(Math.min(lastComplete, v.end_day + 1))} disabled={v.end_day >= lastComplete}>Later</button>
          <button className="btn" onClick={() => setEnd(undefined)}>This week</button>
        </div>
      </div>
      <div className="two">
        <div>
          <div className="chart-title"><h3>Risk, day by day</h3>
            <div className="legend"><span><i style={{ borderColor: p.accent }} />Risk</span><span><i className="dot" style={{ background: p.alert }} />Flagged</span></div>
          </div>
          <TableView title="Daily cardiovascular risk" columns={["Week ending", "Risk of event in 3 days", "Flagged"]}
            rows={traj.map(t => [dayMonth(t.d), t.risk === null ? "after event" : `${fmt(t.risk * 100, 1)}%`, t.flag ? "yes" : ""])}>
            <PlotFigure spec={trajSpec} ariaLabel="Daily cardiovascular risk" />
          </TableView>
        </div>
        <div>
          <div className="chart-title"><h3>This week against usual</h3></div>
          <div className="heat-key">
            <span>Darker means further from usual, in the worrying direction</span>
            {[0.5, 1.2, 2, 3].map(z => <span key={z} className="sw" style={shade(z)} />)}
          </div>
          <table className="heat num">
            <thead>
              <tr><th>Measure</th>{v.dates.map(d => <th key={d}>{dayMonth(d)}</th>)}<th>Usual</th></tr>
            </thead>
            <tbody>
              {ROWS.map(r => {
                const m = byKey[r.key];
                if (!m) return null;
                const f = (x: number | null) => (x === null ? "" : fmt(x * (r.scale ?? 1), r.digits));
                return (
                  <tr key={r.key}>
                    <td className="metric">{r.name}{r.unit && <span className="muted">, {r.unit}</span>}</td>
                    {m.values.map((x, i) => <td key={i} style={shade(m.adverse_z[i])} title={m.adverse_z[i] !== null ? `${fmt(m.adverse_z[i], 1)} SD from usual` : ""}>{f(x)}</td>)}
                    <td className="base">{f(m.baseline)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <Disclosure title="Sleep stages, night by night">
        <div className="legend">
          {Object.entries(stageColor).map(([k, c]) => <span key={k}><i className="band" style={{ background: c, outline: k === "Awake" ? `1px solid ${p.rule}` : undefined }} />{k}</span>)}
        </div>
        <TableView title="Sleep stages per night" columns={["Night", "Deep, min", "REM, min", "Core, min", "Awake, min"]}
          rows={v.dates.map((d, i) => [dayMonth(d), fmt(byKey.deep_min?.values[i]), fmt(byKey.rem_min?.values[i]),
            fmt(byKey.core_min?.values[i]), fmt(byKey.awake_min?.values[i])])}>
          <PlotFigure spec={sleepSpec} ariaLabel="Sleep stages per night" />
        </TableView>
      </Disclosure>
      <Disclosure title="How this is worked out">
        <p className="muted">Seven days of resting heart rate, heart rate variability, sleep and steps are compared with this
          patient's own earlier weeks. Two methods look for anything unusual and a third has learned the pattern that comes
          before an event; together they give the risk. A flag is raised above {fmt(v.threshold * 100, 1)}%, a level that
          keeps false flags to about 1 in 20 patient days.</p>
      </Disclosure>
    </>
  );
}
