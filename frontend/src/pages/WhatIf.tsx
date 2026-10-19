import * as Plot from "@observablehq/plot";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, fmt, hhmm, signed, type Lever, type WhatIf as WhatIfRes, type WhatIfReq } from "../api";
import { Disclosure } from "../components/Disclosure";
import { PlotFigure, baseStyle } from "../components/PlotFigure";
import { SkeletonBlock } from "../components/Skeleton";
import { TableView } from "../components/TableView";
import { useLive } from "../live";
import { usePatient } from "./Patient";

const NEUTRAL = { walk_minutes: 0, swap: "none", shift_hours: 0, missed_dose: false, sleep_hours: null, night_shift: false };
const SWAPS: Record<string, string> = {
  none: "As planned", millet: "Millets instead of white rice", brown_rice: "Brown rice instead of white rice",
  roti: "Roti instead of rice", half_portion: "Half the portion",
};
const same = (a: Partial<WhatIfReq>, b: Partial<WhatIfReq>) =>
  (Object.keys(NEUTRAL) as (keyof typeof NEUTRAL)[]).every(k => (a[k] ?? NEUTRAL[k]) === (b[k] ?? NEUTRAL[k]));

function Delta({ v, unit, lowerIsBetter = true }: { v: number; unit: string; lowerIsBetter?: boolean }) {
  if (Math.abs(v) < 0.5) return <span className="muted">no change</span>;
  const better = lowerIsBetter ? v < 0 : v > 0;
  return <span className={better ? "better" : "worse"}>{signed(v)} {unit}</span>;
}

function gainText(l: Lever, day: boolean): string {
  if (day) return `${fmt(-l.auc_above_180)} fewer glucose-hours above 180 over the day`;
  if (l.peak <= -1) return `Peak about ${fmt(-l.peak)} mg/dL lower`;
  if (l.peak >= 1) return `Peak about ${fmt(l.peak)} mg/dL higher`;
  return "Little change tonight";
}

export function WhatIf() {
  const { id = "" } = useParams();
  const { detail } = usePatient();
  const { palette: p, tick } = useLive();
  const [horizon, setHorizon] = useState<6 | 24>(6);
  const [req, setReq] = useState<WhatIfReq>({ ...NEUTRAL, scope: "next", horizon_h: 6 });
  const [res, setRes] = useState<WhatIfRes | null>(null);
  const [busy, setBusy] = useState(false);
  const [levers, setLevers] = useState<Lever[] | null>(null);
  const touched = useRef(false);
  const timer = useRef<number>();
  const day = horizon === 24;
  const first = detail.patient.name.split(" ")[0];

  useEffect(() => {
    setLevers(null);
    api.levers(id, horizon, day ? "all" : "next").then(r => {
      setLevers(r.levers);
      // Start on the most helpful change, so the chart shows something worth seeing.
      if (!touched.current && r.levers.length) setReq(q => ({ ...q, ...NEUTRAL, ...r.levers[0].request }));
    }).catch(() => setLevers([]));
  }, [id, horizon, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setBusy(true);
      api.whatif(id, req).then(setRes).finally(() => setBusy(false));
    }, 180);
  }, [id, req, tick]);

  const choose = (patch: Partial<WhatIfReq>) => { touched.current = true; setReq(r => ({ ...r, ...NEUTRAL, ...patch })); };
  const set = (patch: Partial<WhatIfReq>) => { touched.current = true; setReq(r => ({ ...r, ...patch })); };
  const switchHorizon = (h: 6 | 24) => { touched.current = false; setHorizon(h); setReq(r => ({ ...r, ...NEUTRAL, horizon_h: h, scope: h === 24 ? "all" : "next" })); };
  if (res && !res.available) return <p className="empty">No recent CGM reading, so the twin cannot run a simulation.</p>;

  const best = (levers ?? []).filter(l => (day ? l.auc_above_180 <= -20 : l.peak <= -5)).slice(0, 4);
  const chosen = (levers ?? []).find(l => same(l.request, req));

  const spec = () => {
    if (!res) return { marks: [] };
    const rows = res.times.map((t, i) => ({ t: new Date(t), base: res.baseline[i], alt: res.scenario[i] }));
    const ymax = Math.max(300, ...res.baseline, ...res.scenario) + 15;
    const bi = rows.reduce((b, r, i) => (r.base > rows[b].base ? i : b), 1);
    const ai = rows.reduce((b, r, i) => (r.alt > rows[b].alt ? i : b), 1);
    return {
      height: 360, marginLeft: 50, marginRight: 30, marginTop: 24, marginBottom: 28, style: baseStyle(p.ink3),
      x: { type: "time" as const, tickFormat: (v: Date) => hhmm(v), ticks: day ? 8 : 7, label: null },
      y: { domain: [40, ymax], ticks: [70, 180, 250, 300, 350].filter(v => v < ymax), label: "mg/dL", labelAnchor: "top" as const },
      marks: [
        Plot.rect([0], { x1: rows[0].t, x2: rows[rows.length - 1].t, y1: 70, y2: 180, fill: p.band }),
        Plot.gridY({ stroke: p.rule, strokeOpacity: 1, ticks: [70, 180, 250] }),
        Plot.areaY(rows, { x: "t", y1: (r: any) => Math.min(r.base, r.alt), y2: (r: any) => Math.max(r.base, r.alt), fill: p.accent, fillOpacity: 0.12 }),
        Plot.lineY(rows, { x: "t", y: "base", stroke: p.grey, strokeWidth: 2.2 }),
        Plot.lineY(rows, { x: "t", y: "alt", stroke: p.accent, strokeWidth: 2.6 }),
        Plot.dot([rows[bi]], { x: "t", y: "base", r: 4, fill: p.grey, stroke: p.paper, strokeWidth: 2 }),
        Plot.dot([rows[ai]], { x: "t", y: "alt", r: 4, fill: p.accent, stroke: p.paper, strokeWidth: 2 }),
        Plot.text([rows[bi]], { x: "t", y: "base", text: (r: any) => `Usual ${fmt(r.base)}`, dy: -14, fill: p.ink2, fontSize: 13,
          stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" }),
        ...(Math.abs(rows[ai].alt - rows[bi].base) > 2
          ? [Plot.text([rows[ai]], { x: "t", y: "alt", text: (r: any) => `With the change ${fmt(r.alt)}`, dy: 18, fill: p.ink, fontSize: 13,
              stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" })]
          : []),
        Plot.tip(rows, Plot.pointerX({ x: "t", y: "alt", fill: p.paper, stroke: p.ruleStrong,
          title: (r: any) => `${hhmm(r.t)}  usual ${fmt(r.base)}, with the change ${fmt(r.alt)} mg/dL` })),
      ],
    };
  };

  const b = res?.baseline_summary, a = res?.scenario_summary;
  return (
    <div className="whatif-simple">
      <div className="wi-head">
        <div>
          <h2>Try a change for {first}</h2>
          <p className="muted">The glucose forecast replays the {day ? "next 24 hours" : "next 6 hours"} with one change at a time.
            {!day && res?.target_meal && <> The next main meal is at {res.target_meal.time}, about {fmt(res.target_meal.carbs)} g carbohydrate.</>}</p>
        </div>
        <div className="segmented big" role="radiogroup" aria-label="Time span">
          <button role="radio" aria-checked={!day} className={!day ? "on" : ""} onClick={() => switchHorizon(6)}>Tonight</button>
          <button role="radio" aria-checked={day} className={day ? "on" : ""} onClick={() => switchHorizon(24)}>Next 24 hours, every meal</button>
        </div>
      </div>

      {levers ? (
        best.length ? (
          <ol className="lever-cards" aria-label={`Changes that would help ${first} most, best first`}>
            {best.map((l, i) => {
              const on = same(l.request, req);
              return (
                <li key={l.label}>
                  <button className={`lever-card ${on ? "on" : ""}`} aria-pressed={on} onClick={() => choose(l.request)}>
                    <span className="rank">{i + 1}</span>
                    <span className="what">{l.label}</span>
                    <span className="gain">{gainText(l, day)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : <p className="empty">No single change makes much difference for {first} {day ? "today" : "tonight"}.</p>
      ) : <SkeletonBlock height={110} label="Working out what helps" />}

      <div className="wi-result" style={{ opacity: busy ? 0.6 : 1 }}>
        <div className="wi-numbers num">
          <div><div className="label">Highest glucose</div>
            <div className="pair">{b ? fmt(b.peak) : ""} <span className="arrow">to</span> <b>{a ? fmt(a.peak) : ""}</b></div>
            <div className="small">{res && <Delta v={res.delta.peak} unit="mg/dL" />}</div></div>
          <div><div className="label">Time above 180</div>
            <div className="pair">{b ? b.tar_min : ""} <span className="arrow">to</span> <b>{a ? a.tar_min : ""}</b> min</div>
            <div className="small">{res && <Delta v={res.delta.tar_min} unit="min" />}</div></div>
          {chosen && <p className="wi-chosen">Showing: <b>{chosen.label.toLowerCase()}</b></p>}
        </div>
        <div className="legend"><span><i style={{ borderColor: p.grey }} />Usual plan</span><span><i style={{ borderColor: p.accent }} />With the change</span>
          <span><i className="band" style={{ background: p.band, outline: `1px solid ${p.rule}` }} />Target, 70 to 180</span></div>
        {res ? (
          <TableView title="Usual plan against the change" columns={["Time", "Usual, mg/dL", "With the change, mg/dL"]}
            rows={res.times.map((t, i) => [hhmm(t), fmt(res.baseline[i]), fmt(res.scenario[i])]).filter((_, i) => i % (day ? 6 : 3) === 0)}>
            <PlotFigure spec={spec} ariaLabel="Usual plan against the change" />
          </TableView>
        ) : <SkeletonBlock height={360} label="Simulating" />}
        {day && <p className="small muted">Beyond about 6 hours the forecast's absolute levels drift; compare the two lines rather than reading the level.</p>}
      </div>

      <Disclosure title="Build your own change" hint="walk, food, meal time, sleep, a missed dose, a night shift">
        <div className="controls-grid">
          <div className="control">
            <label htmlFor="walk"><span>Walk after the meal</span><span>{req.walk_minutes ? `${req.walk_minutes} min` : "none"}</span></label>
            <input id="walk" type="range" min={0} max={45} step={5} value={req.walk_minutes} onChange={e => set({ walk_minutes: +e.target.value })} />
          </div>
          <div className="control">
            <label htmlFor="swap"><span>Food</span><span /></label>
            <select id="swap" value={req.swap} onChange={e => set({ swap: e.target.value })}>
              {Object.entries(SWAPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div className="control">
            <label htmlFor="shift"><span>Meal time</span><span>{req.shift_hours ? `${signed(req.shift_hours, 1)} h` : "as usual"}</span></label>
            <input id="shift" type="range" min={-3} max={2} step={0.5} value={req.shift_hours} onChange={e => set({ shift_hours: +e.target.value })} />
          </div>
          <div className="control">
            <label htmlFor="sleep"><span>Sleep, last 3 nights</span><span>{req.sleep_hours ? `${req.sleep_hours} h` : "as recorded"}</span></label>
            <input id="sleep" type="range" min={0} max={9} step={0.5} value={req.sleep_hours ?? 0}
              onChange={e => set({ sleep_hours: +e.target.value < 3 ? null : +e.target.value })} />
          </div>
          <label className="check"><input type="checkbox" checked={req.missed_dose} onChange={e => set({ missed_dose: e.target.checked })} />Missed metformin dose</label>
          <label className="check"><input type="checkbox" checked={req.night_shift} onChange={e => set({ night_shift: e.target.checked })} />Working a night shift</label>
          <button className="btn" onClick={() => choose({})}>Clear changes</button>
        </div>
      </Disclosure>

      <Disclosure title="All changes, ranked" hint={levers ? `${levers.length} changes tried, best first` : ""}>
        {levers && (
          <table className="compare num levers">
            <thead><tr><th>Change</th><th>Highest glucose</th><th>Time above 180</th>{day && <th>Glucose-hours above 180</th>}</tr></thead>
            <tbody>
              {levers.map(l => (
                <tr key={l.label} className="row" tabIndex={0} onClick={() => choose(l.request)}
                  onKeyDown={e => e.key === "Enter" && choose(l.request)} aria-label={`Show: ${l.label}`}>
                  <td>{l.label}</td><td><Delta v={l.peak} unit="mg/dL" /></td><td><Delta v={l.tar_min} unit="min" /></td>
                  {day && <td><Delta v={l.auc_above_180} unit="" /></td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Disclosure>

      <Disclosure title="All numbers for this change" hint={res && a ? `time in range ${fmt(res.baseline_summary.tir_pct)}% to ${fmt(a.tir_pct)}%` : ""}>
        {b && a && res && (
          <table className="compare num">
            <thead><tr><th /><th>Usual</th><th>With the change</th><th>Difference</th></tr></thead>
            <tbody>
              <tr><td>Highest glucose</td><td>{fmt(b.peak)} at {b.peak_time}</td><td>{fmt(a.peak)} at {a.peak_time}</td><td><Delta v={res.delta.peak} unit="mg/dL" /></td></tr>
              <tr><td>Time above 180</td><td>{b.tar_min} min</td><td>{a.tar_min} min</td><td><Delta v={res.delta.tar_min} unit="min" /></td></tr>
              <tr><td>Time below 70</td><td>{b.tbr_min} min</td><td>{a.tbr_min} min</td><td><Delta v={a.tbr_min - b.tbr_min} unit="min" /></td></tr>
              <tr><td>Average glucose</td><td>{fmt(b.mean)}</td><td>{fmt(a.mean)}</td><td><Delta v={res.delta.mean} unit="mg/dL" /></td></tr>
              <tr><td>Time in range</td><td>{fmt(b.tir_pct)}%</td><td>{fmt(a.tir_pct)}%</td><td><Delta v={res.delta.tir_pct} unit="points" lowerIsBetter={false} /></td></tr>
            </tbody>
          </table>
        )}
        <p className="small muted" style={{ marginTop: 10 }}>{res?.note} Solver: {res?.solver}. A conversation aid, not a prescription.</p>
      </Disclosure>
    </div>
  );
}
