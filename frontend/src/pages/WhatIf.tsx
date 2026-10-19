import * as Plot from "@observablehq/plot";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, fmt, hhmm, signed, type Lever, type WhatIf as WhatIfRes, type WhatIfReq } from "../api";
import { PlotFigure, baseStyle } from "../components/PlotFigure";
import { SkeletonBlock } from "../components/Skeleton";
import { TableView } from "../components/TableView";
import { useLive } from "../live";

const NEUTRAL = { walk_minutes: 0, swap: "none", shift_hours: 0, missed_dose: false, sleep_hours: null, night_shift: false };
const BASE: WhatIfReq = { ...NEUTRAL, scope: "next", horizon_h: 6 };
const SWAPS: Record<string, string> = {
  none: "As planned", millet: "Millets instead of white rice", brown_rice: "Brown rice instead of white rice",
  roti: "Roti instead of rice", half_portion: "Half the portion",
};
const PRESETS: { label: string; req: Partial<WhatIfReq> }[] = [
  { label: "15 min walk after the meal", req: { walk_minutes: 15 } },
  { label: "Millets instead of rice", req: { swap: "millet" } },
  { label: "Walk and millets", req: { walk_minutes: 15, swap: "millet" } },
  { label: "Meal 1 h earlier", req: { shift_hours: -1 } },
  { label: "Missed metformin", req: { missed_dose: true } },
];

function Delta({ v, unit, lowerIsBetter = true }: { v: number; unit: string; lowerIsBetter?: boolean }) {
  if (Math.abs(v) < 0.5) return <span className="muted">no change</span>;
  const better = lowerIsBetter ? v < 0 : v > 0;
  return <span className={better ? "better" : "worse"}>{signed(v)} {unit}</span>;
}

export function WhatIf() {
  const { id = "" } = useParams();
  const { palette: p, tick } = useLive();
  const [req, setReq] = useState<WhatIfReq>(BASE);
  const [res, setRes] = useState<WhatIfRes | null>(null);
  const [busy, setBusy] = useState(false);
  const [levers, setLevers] = useState<Lever[] | null>(null);
  const timer = useRef<number>();
  const day = req.horizon_h === 24;

  useEffect(() => {
    setLevers(null);
    api.levers(id, req.horizon_h, req.scope).then(r => setLevers(r.levers)).catch(() => setLevers([]));
  }, [id, req.horizon_h, req.scope, tick]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setBusy(true);
      api.whatif(id, req).then(setRes).finally(() => setBusy(false));
    }, 180);
  }, [id, req, tick]);

  const set = (patch: Partial<WhatIfReq>) => setReq(r => ({ ...r, ...patch }));
  const apply = (patch: Partial<WhatIfReq>) => setReq(r => ({ ...r, ...NEUTRAL, ...patch }));
  if (res && !res.available) return <p className="empty">No recent CGM reading, so the twin cannot start a simulation.</p>;

  const spec = () => {
    if (!res) return { marks: [] };
    const rows = res.times.map((t, i) => ({ t: new Date(t), base: res.baseline[i], alt: res.scenario[i] }));
    const ymax = Math.max(300, ...res.baseline, ...res.scenario) + 15;
    const bi = rows.reduce((b, r, i) => (r.base > rows[b].base ? i : b), 1);
    const ai = rows.reduce((b, r, i) => (r.alt > rows[b].alt ? i : b), 1);
    return {
      height: 330, marginLeft: 44, marginRight: 30, marginTop: 20, marginBottom: 26, style: baseStyle(p.ink3),
      x: { type: "time" as const, tickFormat: (v: Date) => hhmm(v), ticks: 7, label: null },
      y: { domain: [40, ymax], ticks: [70, 100, 140, 180, 250, 300, 350].filter(v => v < ymax), label: "mg/dL", labelAnchor: "top" as const },
      marks: [
        Plot.rect([0], { x1: rows[0].t, x2: rows[rows.length - 1].t, y1: 70, y2: 180, fill: p.band }),
        Plot.gridY({ stroke: p.rule, strokeOpacity: 1, ticks: [70, 180, 250] }),
        Plot.areaY(rows, { x: "t", y1: (r: any) => Math.min(r.base, r.alt), y2: (r: any) => Math.max(r.base, r.alt), fill: p.accent, fillOpacity: 0.1 }),
        Plot.lineY(rows, { x: "t", y: "base", stroke: p.grey, strokeWidth: 2 }),
        Plot.lineY(rows, { x: "t", y: "alt", stroke: p.accent, strokeWidth: 2.2 }),
        Plot.dot([rows[bi]], { x: "t", y: "base", r: 3.5, fill: p.grey, stroke: p.paper, strokeWidth: 2 }),
        Plot.dot([rows[ai]], { x: "t", y: "alt", r: 3.5, fill: p.accent, stroke: p.paper, strokeWidth: 2 }),
        Plot.text([rows[bi]], { x: "t", y: "base", text: (r: any) => `As planned ${fmt(r.base)}`, dy: -12, fill: p.ink2,
          stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" }),
        ...(Math.abs(rows[ai].alt - rows[bi].base) > 2
          ? [Plot.text([rows[ai]], { x: "t", y: "alt", text: (r: any) => `Scenario ${fmt(r.alt)}`, dy: 16, fill: p.ink,
              stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" })]
          : []),
        Plot.tip(rows, Plot.pointerX({ x: "t", y: "alt", fill: p.paper, stroke: p.ruleStrong,
          title: (r: any) => `${hhmm(r.t)}  as planned ${fmt(r.base)}, scenario ${fmt(r.alt)} mg/dL` })),
      ],
    };
  };

  const b = res?.baseline_summary, a = res?.scenario_summary;
  return (
    <div className="whatif">
      <aside>
        <h2>Change one thing</h2>
        <div className="segmented" role="radiogroup" aria-label="Horizon">
          <button role="radio" aria-checked={!day} className={!day ? "on" : ""} onClick={() => set({ horizon_h: 6, scope: "next" })}>Tonight, next meal</button>
          <button role="radio" aria-checked={day} className={day ? "on" : ""} onClick={() => set({ horizon_h: 24, scope: "all" })}>Next 24 h, every meal</button>
        </div>
        <p className="small muted" style={{ margin: "6px 0 6px" }}>
          {day ? "The twin re-simulates the next 24 hours with the change applied to every main meal (meal timing moves dinner only)."
               : "The twin re-simulates the next 6 hours from now."}
          {!day && res?.target_meal && <> Meal in question: about {fmt(res.target_meal.carbs)} g at {res.target_meal.time}.</>}
        </p>
        <div className="presets">
          {PRESETS.map(pr => <button key={pr.label} className="btn" onClick={() => apply(pr.req)}>{pr.label}</button>)}
          <button className="btn" onClick={() => apply({})}>Reset</button>
        </div>
        <div className="control">
          <label htmlFor="walk"><span>Walk after the meal</span><span>{req.walk_minutes ? `${req.walk_minutes} min` : "none"}</span></label>
          <input id="walk" type="range" min={0} max={45} step={5} value={req.walk_minutes} onChange={e => set({ walk_minutes: +e.target.value })} />
        </div>
        <div className="control">
          <label htmlFor="swap"><span>Carbohydrate</span><span /></label>
          <select id="swap" value={req.swap} onChange={e => set({ swap: e.target.value })}>
            {Object.entries(SWAPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="control">
          <label htmlFor="shift"><span>Meal timing</span><span>{req.shift_hours ? `${signed(req.shift_hours, 1)} h` : "as usual"}</span></label>
          <input id="shift" type="range" min={-3} max={2} step={0.5} value={req.shift_hours} onChange={e => set({ shift_hours: +e.target.value })} />
          {res?.target_meal && req.shift_hours !== 0 && <div className="small muted">Moves to {res.target_meal.new_time}; never earlier than now.</div>}
        </div>
        <div className="control">
          <label htmlFor="sleep"><span>Sleep, last 3 nights</span><span>{req.sleep_hours ? `${req.sleep_hours} h` : "as recorded"}</span></label>
          <input id="sleep" type="range" min={0} max={9} step={0.5} value={req.sleep_hours ?? 0}
            onChange={e => set({ sleep_hours: +e.target.value < 3 ? null : +e.target.value })} />
        </div>
        <div className="control">
          <label className="check"><input type="checkbox" checked={req.missed_dose} onChange={e => set({ missed_dose: e.target.checked })} />Missed metformin dose</label>
        </div>
        <div className="control">
          <label className="check"><input type="checkbox" checked={req.night_shift} onChange={e => set({ night_shift: e.target.checked })} />Working a night shift tonight</label>
        </div>
      </aside>
      <section>
        <div className="chart-title">
          <h2>Next {day ? "24" : "6"} hours: as planned against the scenario</h2>
          <div className="legend">
            <span><i style={{ borderColor: p.grey }} />As planned</span>
            <span><i style={{ borderColor: p.accent }} />Scenario</span>
            <span><i className="band" style={{ background: p.band, outline: `1px solid ${p.rule}` }} />70 to 180</span>
            {busy && <span>Simulating</span>}
          </div>
        </div>
        <div style={{ opacity: busy ? 0.6 : 1, transition: "opacity 120ms" }}>
          {res ? (
            <TableView title="As planned against the scenario" columns={["Time", "As planned, mg/dL", "Scenario, mg/dL"]}
              rows={res.times.map((t, i) => [hhmm(t), fmt(res.baseline[i]), fmt(res.scenario[i])]).filter((_, i) => i % (day ? 6 : 3) === 0)}>
              <PlotFigure spec={spec} ariaLabel="Baseline and counterfactual glucose" />
            </TableView>
          ) : <SkeletonBlock height={330} label="Simulating" />}
        </div>
        {b && a && res && (
          <table className="compare num">
            <thead><tr><th /><th>As planned</th><th>Scenario</th><th>Change</th></tr></thead>
            <tbody>
              <tr><td>Peak glucose</td><td>{fmt(b.peak)} at {b.peak_time}</td><td>{fmt(a.peak)} at {a.peak_time}</td><td><Delta v={res.delta.peak} unit="mg/dL" /></td></tr>
              <tr><td>Time above 180</td><td>{b.tar_min} min</td><td>{a.tar_min} min</td><td><Delta v={res.delta.tar_min} unit="min" /></td></tr>
              <tr><td>Time below 70</td><td>{b.tbr_min} min</td><td>{a.tbr_min} min</td><td><Delta v={a.tbr_min - b.tbr_min} unit="min" /></td></tr>
              <tr><td>Mean glucose</td><td>{fmt(b.mean)}</td><td>{fmt(a.mean)}</td><td><Delta v={res.delta.mean} unit="mg/dL" /></td></tr>
              <tr><td>Time in range</td><td>{fmt(b.tir_pct)}%</td><td>{fmt(a.tir_pct)}%</td><td><Delta v={res.delta.tir_pct} unit="points" lowerIsBetter={false} /></td></tr>
              <tr><td>Area above 180</td><td>{fmt(b.auc_above_180)}</td><td>{fmt(a.auc_above_180)}</td><td><Delta v={res.delta.auc_above_180} unit="mg/dL h" /></td></tr>
            </tbody>
          </table>
        )}
        <h2 style={{ marginTop: 24 }}>Levers for this patient, ranked</h2>
        <p className="small muted" style={{ margin: "4px 0 6px" }}>
          The twin tries each change on its own. Ranked by {day ? "area above 180 over 24 hours" : "the change in peak"}. Select a row to show it above.
        </p>
        {levers ? (
          <table className="compare num levers">
            <thead><tr><th>Change</th><th>Peak</th><th>Time above 180</th>{day && <th>Area above 180</th>}</tr></thead>
            <tbody>
              {levers.map(l => (
                <tr key={l.label} className="row" tabIndex={0} onClick={() => apply(l.request)}
                  onKeyDown={e => e.key === "Enter" && apply(l.request)} aria-label={`Apply: ${l.label}`}>
                  <td>{l.label}</td>
                  <td><Delta v={l.peak} unit="mg/dL" /></td>
                  <td><Delta v={l.tar_min} unit="min" /></td>
                  {day && <td><Delta v={l.auc_above_180} unit="mg/dL h" /></td>}
                </tr>
              ))}
            </tbody>
          </table>
        ) : <SkeletonBlock height={260} label="Ranking levers" />}
        <p className="small muted" style={{ marginTop: 12, maxWidth: 720 }}>
          {res?.note} Solver: {res?.solver}. The twin has learned this patient's insulin sensitivity, absorption and
          response to walking from the calibration week; effects of foods use published absorption speeds. Treat results
          as a conversation aid, not a prescription.
        </p>
      </section>
    </div>
  );
}
