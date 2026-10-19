import * as Plot from "@observablehq/plot";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, dayMonth, dayToDate, fmt, fullTime } from "../api";
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

  const s = v.summary;
  return (
    <>
      <div className="page-head" style={{ marginBottom: 10 }}>
        <div>
          <h2>Seven days ending {dayMonth(dayToDate(v.end_day))}</h2>
          <div className="meta">
            Rolling seven day window of wearable data, compared with this patient's own earlier baseline.
            {v.event && <> <span className="alert-text">Event recorded {fullTime(v.event.time)}: {v.event.description}.</span></>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }} className="no-print">
          <button className="btn" onClick={() => setEnd(Math.max(12, v.end_day - 1))}>Previous day</button>
          <button className="btn" onClick={() => setEnd(Math.min(lastComplete, v.end_day + 1))} disabled={v.end_day >= lastComplete}>Next day</button>
          <button className="btn" onClick={() => setEnd(undefined)}>Latest</button>
        </div>
      </div>
      <div className="stats num">
        <div className="stat"><div className="label">Risk, window end</div>
          <div className="v">{v.risk !== null ? `${fmt(v.risk * 100, 1)}%` : "n/a"}</div>
          <div className="d">{v.risk === null ? "after event, not scored" : v.flag ? <span className="alert-text">flagged</span> : "below threshold"}</div></div>
        <div className="stat"><div className="label">Flag threshold</div><div className="v">{fmt(v.threshold * 100, 1)}%</div><div className="d">95% specificity</div></div>
        <div className="stat"><div className="label">Status now</div>
          <div className="v" style={{ fontSize: 15, paddingTop: 5 }}>{s.post_event ? "Post event" : s.flag ? "Flagged" : "Not flagged"}</div>
          <div className="d">{s.flag_since !== null && s.flag_since !== undefined ? `since ${dayMonth(dayToDate(s.flag_since))}` : ""}</div></div>
      </div>
      <div className="two">
        <div>
          <div className="chart-title"><h2>Daily wearable measures</h2>
            <div className="heat-key">
              <span>Deviation from own baseline, in the adverse direction:</span>
              {[0.5, 1.2, 2, 3].map(z => <span key={z} className="sw" style={shade(z)} />)}
              <span>more</span>
            </div>
          </div>
          <table className="heat num">
            <thead>
              <tr><th>Measure</th>{v.dates.map(d => <th key={d}>{dayMonth(d)}</th>)}<th>Baseline</th></tr>
            </thead>
            <tbody>
              {ROWS.map(r => {
                const m = byKey[r.key];
                if (!m) return null;
                const f = (x: number | null) => (x === null ? "" : fmt(x * (r.scale ?? 1), r.digits));
                return (
                  <tr key={r.key}>
                    <td className="metric">{r.name}{r.unit && <span className="muted">, {r.unit}</span>}</td>
                    {m.values.map((x, i) => <td key={i} style={shade(m.adverse_z[i])} title={m.adverse_z[i] !== null ? `${fmt(m.adverse_z[i], 1)} SD adverse` : ""}>{f(x)}</td>)}
                    <td className="base">{f(m.baseline)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="chart-title" style={{ marginTop: 18 }}><h2>Sleep architecture</h2>
            <div className="legend">
              {Object.entries(stageColor).map(([k, c]) => <span key={k}><i className="band" style={{ background: c, outline: k === "Awake" ? `1px solid ${p.rule}` : undefined }} />{k}</span>)}
            </div>
          </div>
          <TableView title="Sleep stages per night" columns={["Night", "Deep, min", "REM, min", "Core, min", "Awake, min"]}
            rows={v.dates.map((d, i) => [dayMonth(d), fmt(byKey.deep_min?.values[i]), fmt(byKey.rem_min?.values[i]),
              fmt(byKey.core_min?.values[i]), fmt(byKey.awake_min?.values[i])])}>
            <PlotFigure spec={sleepSpec} ariaLabel="Sleep stages per night" />
          </TableView>
        </div>
        <div>
          <div className="chart-title"><h2>Risk trajectory</h2>
            <div className="legend"><span><i style={{ borderColor: p.accent }} />Ensemble risk</span><span><i className="dot" style={{ background: p.alert }} />Flagged day</span></div>
          </div>
          <TableView title="Daily cardiovascular risk" columns={["Window ending", "Risk of event in 3 days", "Flagged"]}
            rows={traj.map(t => [dayMonth(t.d), t.risk === null ? "after event" : `${fmt(t.risk * 100, 1)}%`, t.flag ? "yes" : ""])}>
            <PlotFigure spec={trajSpec} ariaLabel="Daily cardiovascular risk" />
          </TableView>
          <div className="block" style={{ marginTop: 14 }}>
            <span className="label">Top contributing factors, window ending {dayMonth(dayToDate(v.end_day))}</span>
            {v.factors.length ? (
              <ul className="plain">
                {v.factors.map(f => <li key={f.factor}><span>{f.text}</span></li>)}
              </ul>
            ) : <div className="empty">No factor raises risk for this window.</div>}
            <p className="small muted" style={{ marginTop: 8 }}>
              Ensemble of an isolation forest and a personal baseline z score (both unsupervised) with a LightGBM classifier
              trained on synthetic labelled episodes, combined by logistic regression. Factors come from SHAP values of the
              classifier, worded against the patient's own baseline.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
