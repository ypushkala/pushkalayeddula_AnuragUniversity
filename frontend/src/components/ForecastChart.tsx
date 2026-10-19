import * as Plot from "@observablehq/plot";
import type { Forecast, Timeline } from "../api";
import { fmt, hhmm } from "../api";
import { useLive } from "../live";
import { PlotFigure, baseStyle } from "./PlotFigure";

const M = { marginLeft: 70, marginRight: 64 };
const d = (s: string) => new Date(s);

export function ForecastChart({ tl, fc, stepsPreview }: { tl: Timeline; fc: Forecast | null; stepsPreview?: string }) {
  const { palette: p } = useLive();
  const x0 = d(tl.start);
  const now = d(tl.now);
  const pts = fc?.available ? fc.points : [];
  const x1 = pts.length ? d(pts[pts.length - 1].t) : new Date(now.getTime() + 2 * 3600e3);
  const cgm = tl.cgm.map(r => ({ t: d(r.t), v: r.v }));
  const fpts = pts.map(r => ({ ...r, t: d(r.t) }));
  const ymax = Math.max(300, ...cgm.map(r => r.v ?? 0), ...fpts.map(r => r.hi)) + 10;
  const st = fc?.available ? fc.status : null;
  const peakIdx = fpts.length ? fpts.reduce((b, r, i) => (r.mid > fpts[b].mid ? i : b), 1) : -1;
  const xScale = { type: "time" as const, domain: [x0, x1], tickFormat: (v: Date) => hhmm(v), ticks: 8, label: null };

  const main = () => ({
    ...M, height: 330, marginTop: 20, marginBottom: 26, style: baseStyle(p.ink3),
    x: xScale,
    y: { domain: [40, ymax], ticks: [70, 100, 140, 180, 250, 300, 350].filter(v => v < ymax), label: "mg/dL", labelAnchor: "top" as const },
    marks: [
      Plot.rect([0], { x1: x0, x2: x1, y1: 70, y2: 180, fill: p.band }),
      Plot.gridY({ stroke: p.rule, strokeOpacity: 1, ticks: [70, 180, 250] }),
      Plot.areaY(fpts, { x: "t", y1: "lo", y2: "hi", fill: p.accent, fillOpacity: 0.14, curve: "monotone-x" }),
      Plot.lineY(fpts, { x: "t", y: "mid", stroke: p.accent, strokeWidth: 2, curve: "monotone-x" }),
      Plot.lineY(cgm, { x: "t", y: "v", stroke: p.ink, strokeWidth: 1.6 }),
      Plot.ruleX([now], { stroke: p.ink3, strokeWidth: 1 }),
      Plot.text([now], { x: (v: Date) => v, y: ymax, text: () => `now ${hhmm(now)}`, dy: -8, fill: p.ink3, fontSize: 12.5 }),
      ...(st?.tier === "alert" && st.cross_minute
        ? [Plot.dot(fpts.filter(r => r.mid >= 180).slice(0, 1), { x: "t", y: 180, r: 4, fill: p.alert, stroke: p.paper, strokeWidth: 2 })]
        : []),
      ...(peakIdx > 0
        ? [Plot.text([fpts[peakIdx]], { x: "t", y: "mid", text: (r: any) => `${fmt(r.mid)} at ${hhmm(r.t)}`, dy: -12,
            fill: p.ink, fontSize: 13, fontWeight: 500, stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" })]
        : []),
      Plot.text([180], { x: x1, y: (v: number) => v, text: () => "180", dx: 6, textAnchor: "start", fill: p.ink3 }),
      Plot.text([70], { x: x1, y: (v: number) => v, text: () => "70", dx: 6, textAnchor: "start", fill: p.ink3 }),
      Plot.tip(cgm.filter(r => r.v !== null), Plot.pointerX({ x: "t", y: "v", fill: p.paper, stroke: p.ruleStrong,
        title: (r: any) => `${hhmm(r.t)}  ${fmt(r.v)} mg/dL` })),
      Plot.tip(fpts, Plot.pointerX({ x: "t", y: "mid", fill: p.paper, stroke: p.ruleStrong,
        title: (r: any) => `${hhmm(r.t)} forecast ${fmt(r.mid)} (90%: ${fmt(r.lo)} to ${fmt(r.hi)})` })),
    ],
  });

  const stageFill: Record<string, string> = { deep: p.accent, rem: p.ink3, core: p.ruleStrong, awake: p.paper2 };
  const planned = (fc?.entries ?? []).filter(e => e.type === "planned").map(e => ({ ...e, t: d(e.t) }));
  const lanes = () => ({
    ...M, height: 92, marginTop: 4, marginBottom: 4, style: baseStyle(p.ink3),
    x: { ...xScale, axis: null },
    y: { domain: ["Meals", "Medicine", "Sleep"], label: null, tickSize: 0, padding: 0.25 },
    marks: [
      Plot.ruleX([now], { stroke: p.ink3 }),
      Plot.barX(tl.sleep.map(s => ({ ...s, a: d(s.start), b: d(s.end) })), { x1: "a", x2: "b", y: () => "Sleep", fill: (s: any) => stageFill[s.stage], insetTop: 2, insetBottom: 2 }),
      Plot.tickX(tl.meals.map(m => ({ ...m, t: d(m.t) })), { x: "t", y: () => "Meals", stroke: p.ink2, strokeWidth: 1.5 }),
      Plot.text(tl.meals.map(m => ({ ...m, t: d(m.t) })), { x: "t", y: () => "Meals", text: (m: any) => `${fmt(m.carbs)} g`, dx: 4, textAnchor: "start", fill: p.ink2, fontSize: 12.5 }),
      Plot.dot(tl.doses.filter(x => x.drug === "metformin" || !x.taken).map(x => ({ ...x, t: d(x.t) })),
        { x: "t", y: () => "Medicine", r: 3.5, fill: (x: any) => (x.taken ? p.ink2 : p.paper), stroke: p.ink2, strokeWidth: 1.4 }),
      Plot.text(tl.doses.filter(x => !x.taken).map(x => ({ ...x, t: d(x.t) })), { x: "t", y: () => "Medicine", text: (x: any) => `${x.drug} missed`, dx: 7, textAnchor: "start", fill: p.ink, fontSize: 12.5 }),
      Plot.dot(planned, { x: "t", y: () => "Meals", r: 4, fill: p.paper, stroke: p.accent, strokeWidth: 1.6 }),
      Plot.text(planned, { x: "t", y: () => "Meals", text: (m: any) => `planned ${Math.round(m.carbs)} g`, dx: 7, textAnchor: "start", fill: p.ink2, fontSize: 12.5 }),
      Plot.tip(tl.meals.map(m => ({ ...m, t: d(m.t) })), Plot.pointerX({ x: "t", y: () => "Meals", fill: p.paper, stroke: p.ruleStrong,
        title: (m: any) => `${hhmm(m.t)}  ${m.description}, about ${fmt(m.carbs)} g` })),
    ],
  });

  const steps = () => ({
    ...M, height: 52, marginTop: 4, marginBottom: 4, style: baseStyle(p.ink3),
    x: { ...xScale, axis: null },
    y: { label: null, ticks: 2, tickFormat: (v: number) => (v ? `${v}` : "") },
    marks: [
      Plot.rectY(tl.steps.filter(s => (s.v ?? 0) > 0).map(s => ({ a: d(s.t), b: new Date(d(s.t).getTime() + 5 * 60e3), v: s.v })),
        { x1: "a", x2: "b", y: "v", fill: p.grey, insetLeft: 0.5, insetRight: 0.5 }),
      Plot.ruleY([0], { stroke: p.rule }),
      Plot.ruleX([now], { stroke: p.ink3 }),
    ],
  });

  const hr = () => ({
    ...M, height: 58, marginTop: 6, marginBottom: 22, style: baseStyle(p.ink3),
    x: xScale,
    y: { label: null, ticks: 2, nice: true },
    marks: [
      Plot.lineY(tl.hr.map(h => ({ t: d(h.t), v: h.v })), { x: "t", y: "v", stroke: p.ink2, strokeWidth: 1.1 }),
      Plot.ruleX([now], { stroke: p.ink3 }),
    ],
  });

  return (
    <div>
      <div className="chart-title">
        <h2>Glucose, last 12 hours and forecast for the next 2</h2>
        <div className="legend">
          <span><i style={{ borderColor: p.ink }} />Measured</span>
          <span><i style={{ borderColor: p.accent }} />Forecast</span>
          <span><i className="band" style={{ background: p.accent, opacity: 0.3 }} />Likely range</span>
          <span><i className="band" style={{ background: p.band, outline: `1px solid ${p.rule}` }} />Target, 70 to 180</span>
        </div>
      </div>
      <PlotFigure spec={main} ariaLabel="Glucose history and forecast" />
      <p className="small muted band-note">The shaded band holds 9 in 10 future readings. A red dot marks a likely rise above 180.</p>
      <div className="label" style={{ margin: "8px 0 0" }}>Meals, medicines and sleep</div>
      <PlotFigure spec={lanes} ariaLabel="Meals, medication doses and sleep stages" />
      <div className="legend" style={{ margin: "0 0 2px 44px" }}>
        <span><i className="dot" style={{ background: p.ink2 }} />Dose taken</span>
        <span><i className="dot" style={{ border: `1.4px solid ${p.ink2}` }} />Dose missed</span>
        <span><i className="band" style={{ background: p.accent }} />Deep</span>
        <span><i className="band" style={{ background: p.ink3 }} />REM</span>
        <span><i className="band" style={{ background: p.ruleStrong }} />Core</span>
        <span><i className="dot" style={{ border: `1.6px solid ${p.accent}` }} />Planned meal</span>
      </div>
      <details className="disclosure inline">
        <summary><span className="d-title">Steps and heart rate</span>{stepsPreview && <span className="d-hint">{stepsPreview}</span>}</summary>
        <div className="d-body">
          <div className="label">Steps per 5 minutes</div>
          <PlotFigure spec={steps} ariaLabel="Steps" />
          <div className="label">Heart rate, beats per minute</div>
          <PlotFigure spec={hr} ariaLabel="Heart rate" />
        </div>
      </details>
    </div>
  );
}
