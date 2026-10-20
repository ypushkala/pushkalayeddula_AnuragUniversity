import * as Plot from "@observablehq/plot";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, dayMonth, fmt, glu, gluAbs, gluTick, gluUnit, hhmm, signed, T, type Horizon, type Lever, type PlanRec,
  type WhatIf as WhatIfRes, type WhatIfReq } from "../api";
import { AskTwin } from "../components/AskTwin";
import { Disclosure } from "../components/Disclosure";
import { InsideTwin } from "../components/InsideTwin";
import { RefCheck } from "../components/RefCheck";
import { Hint } from "../components/Hint";
import { PlotFigure, baseStyle } from "../components/PlotFigure";
import { SkeletonBlock } from "../components/Skeleton";
import { TableView } from "../components/TableView";
import { useLive, useLiveData } from "../live";
import { usePatient } from "./Patient";

const NEUTRAL = { walk_minutes: 0, swap: "none", shift_hours: 0, missed_dose: false, sleep_hours: null, night_shift: false,
  insulin_bolus_units: 0, insulin_basal_units: 0, metformin_shift_hours: 0 };
const SWAPS: Record<string, string> = {
  none: "As planned", millet: "Millets instead of white rice", brown_rice: "Brown rice instead of white rice",
  roti: "Roti instead of rice", half_portion: "Half the portion",
};
const SPANS: [Horizon, string][] = [[6, "Tonight"], [24, "Next 24 hours"], [168, "Next 7 days"]];
const same = (a: Partial<WhatIfReq>, b: Partial<WhatIfReq>) =>
  (Object.keys(NEUTRAL) as (keyof typeof NEUTRAL)[]).every(k => (a[k] ?? NEUTRAL[k]) === (b[k] ?? NEUTRAL[k]));

function Delta({ v, unit, lowerIsBetter = true, glucose = false }: { v: number; unit: string; lowerIsBetter?: boolean; glucose?: boolean }) {
  if (Math.abs(v) < 0.5) return <span className="muted">no change</span>;
  const better = lowerIsBetter ? v < 0 : v > 0;
  return <span className={better ? "better" : "worse"}>{v > 0 ? "+" : "-"}{glucose ? gluAbs(v) : fmt(Math.abs(v))} {unit}</span>;
}

function gainText(l: Lever, h: Horizon): string {
  if (h === 168) return l.tir_pct >= 0.5 ? `Time in range about ${fmt(l.tir_pct)} points higher over the week` : "Little change over the week";
  if (h === 24) return `${fmt(-l.auc_above_180)} fewer glucose-hours above 180 over the day`;
  if (l.peak <= -1) return `Peak about ${gluAbs(l.peak)} ${gluUnit()} lower`;
  if (l.peak >= 1) return `Peak about ${gluAbs(l.peak)} ${gluUnit()} higher`;
  return "Little change tonight";
}

function Plans({ pid, first }: { pid: string; first: string }) {
  const { can, refresh, toast } = useLive();
  const { data } = useLiveData(() => api.plans(pid), [pid]);
  if (!data || !data.length) return null;
  return (
    <section className="plans" aria-label={`Plans agreed with ${first}`}>
      <h3>Plans agreed with {first}</h3>
      <ul>
        {data.map((p: PlanRec) => (
          <li key={p.id}>
            <div className="plan-top">
              <b>{p.label}</b>
              <span className="small muted">agreed {dayMonth(p.t)} by {p.by}{p.predicted.tir_pct !== undefined ? `; expected about ${signed(p.predicted.tir_pct)} points of time in range` : ""}</span>
            </div>
            <div className={`plan-check ${p.check.complete ? "done" : ""}`}>
              {p.check.complete ? "One week check: " : `Check due ${dayMonth(p.check.due)}. So far: `}
              {T(p.check.verdict ?? "")}
              {p.check.adherence && <span className="small muted"> Followed: {p.check.adherence_how} {p.check.adherence}.</span>}
            </div>
            {can("plan") && (
              <button className="link-btn small" onClick={() => api.removePlan(pid, p.id).then(() => { refresh(); toast({ text: "Plan removed." }); })
                .catch(e => toast({ text: e.message, error: true }))}>Remove</button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function WhatIf() {
  const { id = "" } = useParams();
  const { detail } = usePatient();
  const { palette: p, tick, can, refresh, toast } = useLive();
  const [horizon, setHorizon] = useState<Horizon>(6);
  const [req, setReq] = useState<WhatIfReq>({ ...NEUTRAL, scope: "next", horizon_h: 6 });
  const [res, setRes] = useState<WhatIfRes | null>(null);
  const [busy, setBusy] = useState(false);
  const [levers, setLevers] = useState<Lever[] | null>(null);
  const [levels, setLevels] = useState(false);
  const touched = useRef(false);
  const timer = useRef<number>();
  const long = horizon > 6;
  const first = detail.patient.name.split(" ")[0];
  const t2d = detail.conditions.some(c => c.code.code.startsWith("E11"));
  const metformin = detail.medications.some(m => m.drugClass === "metformin");

  useEffect(() => {
    setLevers(null);
    api.levers(id, horizon, long ? "all" : "next").then(r => {
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
  const applyAsked = (r: Partial<WhatIfReq>) => {
    const h = (r.horizon_h ?? 6) as Horizon;
    touched.current = true;
    if (h !== horizon) { setHorizon(h); setRes(null); }
    setReq({ ...NEUTRAL, scope: h > 6 ? "all" : "next", ...r, horizon_h: h } as WhatIfReq);
  };
  const switchHorizon = (h: Horizon) => { touched.current = false; setHorizon(h); setRes(null); setReq(r => ({ ...r, ...NEUTRAL, horizon_h: h, scope: h > 6 ? "all" : "next" })); };
  if (res && !res.available) return <p className="empty">No recent glucose reading, so the forecast cannot replay a change.</p>;

  const best = (levers ?? []).filter(l => (horizon === 168 ? l.tir_pct >= 2 : horizon === 24 ? l.auc_above_180 <= -20 : l.peak <= -5)).slice(0, 4);
  const chosen = (levers ?? []).find(l => same(l.request, req));
  const isLifestyle = !req.insulin_bolus_units && !req.insulin_basal_units && !req.metformin_shift_hours && !req.missed_dose && !req.night_shift;

  const spec = () => {
    if (!res) return { marks: [] };
    const rows = res.times.map((t, i) => ({ t: new Date(t), base: res.baseline[i], alt: res.scenario[i], d: res.scenario[i] - res.baseline[i] }));
    const fmtX = (v: Date) => (horizon === 168 ? dayMonth(v) : hhmm(v));
    const common = { height: 360, marginLeft: 56, marginRight: 30, marginTop: 24, marginBottom: 28, style: baseStyle(p.ink3),
      x: { type: "time" as const, tickFormat: fmtX, ticks: horizon === 168 ? 7 : 8, label: null } };
    if (long && !levels) {
      // A week ahead the absolute level drifts, but the difference between the two runs is what the change does.
      const lo = Math.min(-20, ...rows.map(r => r.d)) - 5, hi = Math.max(20, ...rows.map(r => r.d)) + 5;
      return {
        ...common,
        y: { domain: [lo, hi], label: `Change against the usual plan, ${gluUnit()}`, labelAnchor: "top" as const, tickFormat: (v: number) => (v > 0 ? "+" : "") + gluTick(v) },
        marks: [
          Plot.ruleY([0], { stroke: p.ink3 }),
          Plot.areaY(rows, { x: "t", y1: 0, y2: "d", fill: p.accent, fillOpacity: 0.18 }),
          Plot.lineY(rows, { x: "t", y: "d", stroke: p.accent, strokeWidth: 2 }),
          Plot.tip(rows, Plot.pointerX({ x: "t", y: "d", fill: p.paper, stroke: p.ruleStrong,
            title: (r: any) => `${fmtX(r.t)} ${hhmm(r.t)}  ${r.d > 0 ? "+" : "-"}${gluAbs(r.d)} ${gluUnit()} against the usual plan` })),
        ],
      };
    }
    const ymax = Math.max(300, ...res.baseline, ...res.scenario) + 15;
    const bi = rows.reduce((b, r, i) => (r.base > rows[b].base ? i : b), 1);
    const ai = rows.reduce((b, r, i) => (r.alt > rows[b].alt ? i : b), 1);
    return {
      ...common,
      y: { domain: [40, ymax], ticks: [70, 180, 250, 300, 350].filter(v => v < ymax), label: gluUnit(), labelAnchor: "top" as const, tickFormat: gluTick },
      marks: [
        Plot.rect([0], { x1: rows[0].t, x2: rows[rows.length - 1].t, y1: 70, y2: 180, fill: p.band }),
        Plot.gridY({ stroke: p.rule, strokeOpacity: 1, ticks: [70, 180, 250] }),
        Plot.areaY(rows, { x: "t", y1: (r: any) => Math.min(r.base, r.alt), y2: (r: any) => Math.max(r.base, r.alt), fill: p.accent, fillOpacity: 0.12 }),
        Plot.lineY(rows, { x: "t", y: "base", stroke: p.grey, strokeWidth: 2.2 }),
        Plot.lineY(rows, { x: "t", y: "alt", stroke: p.accent, strokeWidth: 2.6 }),
        ...(long ? [] : [
          Plot.dot([rows[bi]], { x: "t", y: "base", r: 4, fill: p.grey, stroke: p.paper, strokeWidth: 2 }),
          Plot.dot([rows[ai]], { x: "t", y: "alt", r: 4, fill: p.accent, stroke: p.paper, strokeWidth: 2 }),
          Plot.text([rows[bi]], { x: "t", y: "base", text: (r: any) => `Usual ${glu(r.base)}`, dy: -14, fill: p.ink2, fontSize: 13,
            stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" }),
          ...(Math.abs(rows[ai].alt - rows[bi].base) > 2
            ? [Plot.text([rows[ai]], { x: "t", y: "alt", text: (r: any) => `With the change ${glu(r.alt)}`, dy: 18, fill: p.ink, fontSize: 13,
                stroke: p.paper, strokeWidth: 3, paintOrder: "stroke" })]
            : []),
        ]),
        Plot.tip(rows, Plot.pointerX({ x: "t", y: "alt", fill: p.paper, stroke: p.ruleStrong,
          title: (r: any) => `${hhmm(r.t)}  usual ${glu(r.base)}, with the change ${glu(r.alt)} ${gluUnit()}` })),
      ],
    };
  };

  const agree = () => {
    if (!res) return;
    const label = chosen?.label ?? "Custom change";
    api.addPlan(id, { label, request: { ...req, horizon_h: undefined } as Partial<WhatIfReq>,
      predicted: { tir_pct: res.delta.tir_pct, mean: res.delta.mean } })
      .then(pl => { refresh(); toast({ text: `Plan agreed: ${label}. A check is due in 7 days.`, undo: () => api.removePlan(id, pl.id) }); })
      .catch(e => toast({ text: e.message, error: true }));
  };

  const b = res?.baseline_summary, a = res?.scenario_summary;
  const span = horizon === 168 ? "next 7 days, at every main meal" : horizon === 24 ? "next 24 hours, at every main meal" : "next 6 hours";
  return (
    <div className="whatif-simple">
      <Plans pid={id} first={first} />
      <AskTwin first={first} onApply={applyAsked} />
      <div className="wi-head">
        <div>
          <h2>Try a change for {first}</h2>
          <p className="muted">The glucose forecast replays the {span} with one change at a time.
            {!long && res?.target_meal && <> The next main meal is at {T(res.target_meal.time)}, about {fmt(res.target_meal.carbs)} g carbohydrate.</>}</p>
        </div>
        <div className="segmented big" role="radiogroup" aria-label="Time span">
          {SPANS.map(([h, l]) => (
            <button key={h} role="radio" aria-checked={horizon === h} className={horizon === h ? "on" : ""} onClick={() => switchHorizon(h)}>{l}</button>
          ))}
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
                    <span className="gain">{T(gainText(l, horizon))}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : <p className="empty">No single change makes much difference for {first} {horizon === 168 ? "this week" : horizon === 24 ? "today" : "tonight"}.</p>
      ) : <SkeletonBlock height={110} label={horizon === 168 ? "Replaying a week for each change, a few seconds" : "Working out what helps"} />}

      <div className="wi-result" style={{ opacity: busy ? 0.6 : 1 }}>
        <div className="wi-numbers num">
          {!long ? <>
            <div><div className="label">Highest glucose</div>
              <div className="pair">{b ? glu(b.peak) : ""} <span className="arrow">to</span> <b>{a ? glu(a.peak) : ""}</b></div>
              <div className="small">{res && <Delta v={res.delta.peak} unit={gluUnit()} glucose />}</div></div>
            <div><div className="label">Time above {gluTick(180)}</div>
              <div className="pair">{b ? b.tar_min : ""} <span className="arrow">to</span> <b>{a ? a.tar_min : ""}</b> min</div>
              <div className="small">{res && <Delta v={res.delta.tar_min} unit="min" />}</div></div>
          </> : <>
            <div><div className="label">Time in range</div>
              <div className="pair">{b ? fmt(b.tir_pct) : ""}% <span className="arrow">to</span> <b>{a ? fmt(a.tir_pct) : ""}%</b></div>
              <div className="small">{res && <Delta v={res.delta.tir_pct} unit="points" lowerIsBetter={false} />}</div></div>
            <div><div className="label">Average glucose</div>
              <div className="pair">{b ? glu(b.mean) : ""} <span className="arrow">to</span> <b>{a ? glu(a.mean) : ""}</b></div>
              <div className="small">{res && <Delta v={res.delta.mean} unit={gluUnit()} glucose />}</div></div>
            {a && <div><div className="label">Lowest</div><div className="pair"><b>{glu(Math.min(...(res?.scenario ?? [a.mean])))}</b></div>
              <div className="small muted">{a.tbr_min ? `${a.tbr_min} min below ${gluTick(70)}` : `never below ${gluTick(70)}`}</div></div>}
          </>}
          {chosen && <p className="wi-chosen">Showing: <b>{chosen.label.toLowerCase()}</b></p>}
        </div>
        {long && <Hint id="difference">A day or a week ahead the forecast's level drifts, so this chart shows what the change does: below the line is lower glucose than the usual plan.</Hint>}
        <div className="legend">
          {long && !levels ? <span><i style={{ borderColor: p.accent }} />Change against the usual plan; below zero is lower glucose</span> : <>
            <span><i style={{ borderColor: p.grey }} />Usual plan</span><span><i style={{ borderColor: p.accent }} />With the change</span>
            <span><i className="band" style={{ background: p.band, outline: `1px solid ${p.rule}` }} />Target, {gluTick(70)} to {gluTick(180)}</span></>}
          {long && <label className="check inline"><input type="checkbox" checked={levels} onChange={e => setLevels(e.target.checked)} />Show levels instead</label>}
        </div>
        {res ? (
          <TableView title="Usual plan against the change" columns={["Time", `Usual, ${gluUnit()}`, `With the change, ${gluUnit()}`]}
            rows={res.times.map((t, i) => [`${horizon === 168 ? dayMonth(t) + " " : ""}${hhmm(t)}`, glu(res.baseline[i]), glu(res.scenario[i])])
              .filter((_, i) => i % (horizon === 168 ? 8 : long ? 6 : 3) === 0)}>
            <PlotFigure spec={spec} ariaLabel="Usual plan against the change" />
          </TableView>
        ) : <SkeletonBlock height={360} label="Simulating" />}
        {horizon === 168 && res && res.days.length > 0 && (
          <table className="compare num week-days">
            <thead><tr><th>Day</th>{res.days.map(d => <th key={d.day}>{d.day}</th>)}</tr></thead>
            <tbody>
              <tr><td>Time in range, change</td>{res.days.map(d => <td key={d.day}><Delta v={d.tir_change} unit="" lowerIsBetter={false} /></td>)}</tr>
              <tr><td>Average, change</td>{res.days.map(d => <td key={d.day}><Delta v={d.mean_change} unit="" glucose /></td>)}</tr>
            </tbody>
          </table>
        )}
        {horizon === 168 && can("plan") && res && isLifestyle && !same(req, {}) && (
          <div className="agree">
            <button className="btn primary" onClick={agree}>Agree this plan with {first}</button>
            <span className="small muted">Saved with what the forecast expects, and checked against what actually happens after a week.</span>
          </div>
        )}
      </div>

      {!long && res && !same(req, {}) && <RefCheck pid={id} req={req} label={chosen?.label ?? "this change"} />}

      {!long && (
        <Disclosure title="See inside the twin" hint="food, insulin and walking, minute by minute, usual against the change">
          <InsideTwin pid={id} req={req} label={chosen?.label ?? "the change"} />
        </Disclosure>
      )}

      <Disclosure title="Build your own change" hint={`walk, food, meal time, sleep, a missed dose, a night shift${t2d ? ", insulin" : ""}`}>
        <div className="controls-grid">
          <div className="control">
            <label htmlFor="walk"><span>Walk after {long ? "each main meal" : "the meal"}</span><span>{req.walk_minutes ? `${req.walk_minutes} min` : "none"}</span></label>
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
          {metformin && (
            <div className="control">
              <label htmlFor="met"><span>Evening metformin</span><span>{req.metformin_shift_hours ? `${signed(req.metformin_shift_hours, 1)} h` : "as usual"}</span></label>
              <input id="met" type="range" min={-3} max={3} step={0.5} value={req.metformin_shift_hours} onChange={e => set({ metformin_shift_hours: +e.target.value })} />
            </div>
          )}
          {t2d && <>
            <div className="control">
              <label htmlFor="bolus"><span>Mealtime insulin, with {long ? "each main meal" : "the next main meal"}</span><span>{req.insulin_bolus_units ? `${req.insulin_bolus_units} units` : "none"}</span></label>
              <input id="bolus" type="range" min={0} max={12} step={1} value={req.insulin_bolus_units} onChange={e => set({ insulin_bolus_units: +e.target.value })} />
            </div>
            <div className="control">
              <label htmlFor="basal"><span>Long acting insulin, per day</span><span>{req.insulin_basal_units ? `${req.insulin_basal_units} units` : "none"}</span></label>
              <input id="basal" type="range" min={0} max={30} step={2} value={req.insulin_basal_units} onChange={e => set({ insulin_basal_units: +e.target.value })} />
            </div>
          </>}
          <label className="check"><input type="checkbox" checked={req.missed_dose} onChange={e => set({ missed_dose: e.target.checked })} />Missed metformin dose</label>
          <label className="check"><input type="checkbox" checked={req.night_shift} onChange={e => set({ night_shift: e.target.checked })} />Working a night shift</label>
          <button className="btn" onClick={() => choose({})}>Clear changes</button>
        </div>
        {(req.insulin_bolus_units > 0 || req.insulin_basal_units > 0) && (
          <p className="notice">Insulin is simulated with typical insulin action, not {first}'s own, because nobody in this synthetic group uses insulin.
            Look at the lowest value first. Starting insulin is a prescribing decision this tool does not make.</p>
        )}
        {req.metformin_shift_hours !== 0 && res && Math.abs(res.delta.peak) < 2 && (
          <p className="notice">Moving the evening metformin makes almost no difference in the forecast: its effect lasts about 12 hours, so the timing of one dose barely changes the level.</p>
        )}
      </Disclosure>

      <Disclosure title="All changes, ranked" hint={levers ? `${levers.length} changes tried, best first` : "Loading"}>
        {levers && (
          <table className="compare num levers">
            <thead><tr><th>Change</th>{horizon === 168 ? <><th>Time in range</th><th>Average glucose</th></> : <><th>Highest glucose</th><th>Time above {gluTick(180)}</th></>}
              {horizon === 24 && <th>Glucose-hours above {gluTick(180)}</th>}</tr></thead>
            <tbody>
              {levers.map(l => (
                <tr key={l.label} className="row" tabIndex={0} onClick={() => choose(l.request)}
                  onKeyDown={e => e.key === "Enter" && choose(l.request)} aria-label={`Show: ${l.label}`}>
                  <td>{l.label}</td>
                  {horizon === 168 ? <><td><Delta v={l.tir_pct} unit="points" lowerIsBetter={false} /></td><td><Delta v={l.mean} unit={gluUnit()} glucose /></td></>
                    : <><td><Delta v={l.peak} unit={gluUnit()} glucose /></td><td><Delta v={l.tar_min} unit="min" /></td></>}
                  {horizon === 24 && <td><Delta v={l.auc_above_180} unit="" /></td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Disclosure>

      <Disclosure title="All numbers for this change" hint={res && a ? `time in range ${fmt(res.baseline_summary.tir_pct)}% to ${fmt(a.tir_pct)}%` : "Loading"}>
        {b && a && res && (
          <table className="compare num">
            <thead><tr><th /><th>Usual</th><th>With the change</th><th>Difference</th></tr></thead>
            <tbody>
              <tr><td>Highest glucose</td><td>{glu(b.peak)} at {b.peak_time}</td><td>{glu(a.peak)} at {a.peak_time}</td><td><Delta v={res.delta.peak} unit={gluUnit()} glucose /></td></tr>
              <tr><td>Time above {gluTick(180)}</td><td>{b.tar_min} min</td><td>{a.tar_min} min</td><td><Delta v={res.delta.tar_min} unit="min" /></td></tr>
              <tr><td>Time below {gluTick(70)}</td><td>{b.tbr_min} min</td><td>{a.tbr_min} min</td><td><Delta v={a.tbr_min - b.tbr_min} unit="min" /></td></tr>
              <tr><td>Average glucose</td><td>{glu(b.mean)}</td><td>{glu(a.mean)}</td><td><Delta v={res.delta.mean} unit={gluUnit()} glucose /></td></tr>
              <tr><td>Time in range</td><td>{fmt(b.tir_pct)}%</td><td>{fmt(a.tir_pct)}%</td><td><Delta v={res.delta.tir_pct} unit="points" lowerIsBetter={false} /></td></tr>
            </tbody>
          </table>
        )}
        <p className="small muted" style={{ marginTop: 10 }}>{T(res?.note ?? "")} Solver: {res?.solver}. A conversation aid, not a prescription.</p>
      </Disclosure>
    </div>
  );
}
