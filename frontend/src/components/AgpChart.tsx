import * as Plot from "@observablehq/plot";
import type { Agp } from "../api";
import { fmt } from "../api";
import { useLive } from "../live";
import { PlotFigure, baseStyle } from "./PlotFigure";
import { TableView } from "./TableView";

const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:00`;

/** Ambulatory glucose profile: median, 25 to 75 and 5 to 95 percentiles by time of day. */
export function AgpChart({ agp }: { agp: Agp }) {
  const { palette: p } = useLive();
  const rows = agp.profile;
  const m = agp.metrics;
  const spec = () => ({
    height: 210, marginLeft: 44, marginRight: 64, marginTop: 10, marginBottom: 24, style: baseStyle(p.ink3),
    x: { domain: [0, 1440], ticks: [0, 180, 360, 540, 720, 900, 1080, 1260, 1440], tickFormat: (v: number) => hm(v % 1440), label: null },
    y: { domain: [40, Math.max(300, ...rows.map(r => r.p95)) + 10], ticks: [70, 180, 250], label: "mg/dL", labelAnchor: "top" as const },
    marks: [
      Plot.rect([0], { x1: 0, x2: 1440, y1: 70, y2: 180, fill: p.band }),
      Plot.gridY({ stroke: p.rule, strokeOpacity: 1, ticks: [70, 180, 250] }),
      Plot.areaY(rows, { x: "minute", y1: "p5", y2: "p95", fill: p.ink, fillOpacity: 0.07, curve: "basis" }),
      Plot.areaY(rows, { x: "minute", y1: "p25", y2: "p75", fill: p.ink, fillOpacity: 0.16, curve: "basis" }),
      Plot.lineY(rows, { x: "minute", y: "p50", stroke: p.ink, strokeWidth: 1.8, curve: "basis" }),
      Plot.text([180, 70], { x: 1440, y: (v: number) => v, text: (v: number) => `${v}`, dx: 6, textAnchor: "start", fill: p.ink3 }),
      Plot.tip(rows, Plot.pointerX({ x: "minute", y: "p50", fill: p.paper, stroke: p.ruleStrong,
        title: (r: any) => `${String(Math.floor(r.minute / 60)).padStart(2, "0")}:${String(r.minute % 60).padStart(2, "0")}  median ${fmt(r.p50)}, IQR ${fmt(r.p25)} to ${fmt(r.p75)}` })),
    ],
  });
  return (
    <div style={{ marginTop: 22 }}>
      <div className="chart-title">
        <h2>Ambulatory glucose profile, last {agp.days} days</h2>
        <div className="legend">
          <span><i style={{ borderColor: p.ink }} />Median</span>
          <span><i className="band" style={{ background: p.ink, opacity: 0.25 }} />25 to 75%</span>
          <span><i className="band" style={{ background: p.ink, opacity: 0.1 }} />5 to 95%</span>
        </div>
      </div>
      <TableView title="Ambulatory glucose profile" columns={["Time of day", "5%", "25%", "Median", "75%", "95%"]}
        rows={rows.filter(r => r.minute % 60 === 0).map(r => [hm(r.minute), fmt(r.p5), fmt(r.p25), fmt(r.p50), fmt(r.p75), fmt(r.p95)])}>
        <PlotFigure spec={spec} ariaLabel="Ambulatory glucose profile" />
      </TableView>
      <table className="kv num" style={{ marginTop: 6 }}>
        <tbody>
          <tr>
            <td>Time in range, 70 to 180</td><td><b>{fmt(m.tir)}%</b> <span className="muted small">target over 70%</span></td>
            <td style={{ paddingLeft: 28 }}>Mean glucose</td><td>{fmt(m.mean)} mg/dL</td>
          </tr>
          <tr>
            <td>Above 180 (above 250)</td><td>{fmt(m.tar)}% ({fmt(m.tar250)}%)</td>
            <td style={{ paddingLeft: 28 }}>GMI</td><td>{fmt(m.gmi, 1)}%</td>
          </tr>
          <tr>
            <td>Below 70 (below 54)</td><td>{fmt(m.tbr, 1)}% ({fmt(m.tbr54, 1)}%)</td>
            <td style={{ paddingLeft: 28 }}>Variability, CV</td><td>{fmt(m.cv)}% <span className="muted small">target 36% or less</span></td>
          </tr>
        </tbody>
      </table>
      <p className="small muted">CGM worn {fmt(agp.coverage)}% of the time. Metrics follow the international consensus on time in range (2019).</p>
    </div>
  );
}
