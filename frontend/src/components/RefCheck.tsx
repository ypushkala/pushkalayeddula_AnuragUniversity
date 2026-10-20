import * as Plot from "@observablehq/plot";
import { useState } from "react";
import { api, glu, gluAbs, gluTick, gluUnit, hhmm, T, type RefCheck as Ref, type WhatIfReq } from "../api";
import { useLive } from "../live";
import { PlotFigure, baseStyle } from "./PlotFigure";

const sgn = (v: number) => `${v > 0.5 ? "+" : v < -0.5 ? "-" : ""}${gluAbs(v)}`;

/** The twin's answer next to the reference simulator's, for the same moment and change. */
export function RefCheck({ pid, req, label }: { pid: string; req: WhatIfReq; label: string }) {
  const { palette: p } = useLive();
  const [res, setRes] = useState<Ref | null>(null);
  const [busy, setBusy] = useState(false);
  const [asked, setAsked] = useState("");
  const key = JSON.stringify(req);
  const run = () => { setBusy(true); setAsked(key); api.reference(pid, req).then(setRes).finally(() => setBusy(false)); };
  const stale = res && asked !== key;
  const spec = () => {
    if (!res?.available) return { marks: [] };
    const rows = res.times.map((t, i) => ({ t: new Date(t), b: res.reference.baseline[i], a: res.reference.scenario[i] }));
    const ymax = Math.max(250, ...res.reference.baseline, ...res.reference.scenario) + 10;
    return {
      height: 220, marginLeft: 50, marginRight: 20, marginTop: 16, marginBottom: 26, style: baseStyle(p.ink3),
      x: { type: "time" as const, tickFormat: (v: Date) => hhmm(v), ticks: 5, label: null },
      y: { domain: [60, ymax], ticks: [70, 180, 250].filter(v => v < ymax), label: gluUnit(), labelAnchor: "top" as const, tickFormat: gluTick },
      marks: [
        Plot.rect([0], { x1: rows[0].t, x2: rows[rows.length - 1].t, y1: 70, y2: 180, fill: p.band }),
        Plot.lineY(rows, { x: "t", y: "b", stroke: p.grey, strokeWidth: 2 }),
        Plot.lineY(rows, { x: "t", y: "a", stroke: p.accent, strokeWidth: 2.4 }),
        Plot.tip(rows, Plot.pointerX({ x: "t", y: "a", fill: p.paper, stroke: p.ruleStrong,
          title: (r: any) => `${hhmm(r.t)}  usual ${glu(r.b)}, with the change ${glu(r.a)}` })),
      ],
    };
  };
  return (
    <section className="refcheck" aria-label="Check against the reference simulator">
      <div className="refcheck-head">
        <div>
          <h3>Is the forecast right about this change?</h3>
          <p className="small muted">Synthetic patients come from a richer simulator than the twin. Re-running it with the same change shows what
            would really have happened to this patient: something no real clinic can see.</p>
        </div>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Re-running the reference" : res && !stale ? "Check again" : "Check against the reference simulator"}</button>
      </div>
      {res && !res.available && <p className="notice">{res.reason}</p>}
      {res?.available && (
        <div className={stale ? "stale" : ""}>
          <div className="refcheck-nums num">
            <div><div className="label">Forecast says</div><div className="big-num">{sgn(res.twin.peak)}</div><div className="small muted">{gluUnit()} at the peak</div></div>
            <div><div className="label">Reference simulator</div><div className="big-num">{sgn(res.reference.delta.peak)}</div><div className="small muted">{gluUnit()} at the peak</div></div>
            <div><div className="label">Time above {gluTick(180)}</div><div className="pair">{res.twin.tar_min > 0 ? "+" : ""}{res.twin.tar_min} <span className="arrow">and</span> {res.reference.delta.tar_min > 0 ? "+" : ""}{res.reference.delta.tar_min} min</div>
              <div className="small muted">forecast and reference</div></div>
          </div>
          <p className={res.agree ? "" : "alert-text"}>{res.agree
            ? `They agree on what ${label.toLowerCase()} does, within ${gluAbs(Math.abs(res.twin.peak - res.reference.delta.peak))} ${gluUnit()}.`
            : `They disagree: the forecast and the reference point different ways. Treat this change with caution for this patient.`}</p>
          {res.actual_meal && res.assumed_meal && (
            <p className="small muted">{T(`The forecast assumed the usual meal at ${res.assumed_meal.time}, about ${Math.round(res.assumed_meal.carbs)} g. In the simulation the patient actually ate at ${res.actual_meal.time}, about ${Math.round(res.actual_meal.carbs)} g.`)}</p>
          )}
          <div className="legend"><span><i style={{ borderColor: p.grey }} />Reference, usual</span><span><i style={{ borderColor: p.accent }} />Reference, with the change</span></div>
          <PlotFigure spec={spec} ariaLabel="Reference simulator, usual against the change" />
          <p className="small muted">{res.note} Window: {Math.round(res.window_min / 60 * 10) / 10} hours (the recorded data ends at midnight). Across 316 moments in
            40 test patients the forecast got the direction right 76% of the time; see About the model.</p>
        </div>
      )}
    </section>
  );
}
