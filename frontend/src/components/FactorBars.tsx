import type { Driver } from "../api";
import { signed } from "../api";

/** Diverging bars in mg/dL of predicted peak. Pushing up in ink, pulling down in the accent. */
export function FactorBars({ drivers }: { drivers: Driver[] }) {
  const shown = drivers.filter(d => Math.abs(d.mgdl) >= 1).slice(0, 7);
  const max = Math.max(10, ...shown.map(d => Math.abs(d.mgdl)));
  return (
    <table className="factors">
      <tbody>
        {shown.map(d => {
          const w = (Math.abs(d.mgdl) / max) * 50;
          return (
            <tr key={d.category} title={`Twin ${signed(d.twin)} mg/dL, learned correction ${signed(d.learned)} mg/dL`}>
              <td className="txt">{d.text[0].toUpperCase() + d.text.slice(1)}</td>
              <td>
                <div className="bar-track">
                  <div className="bar-axis" />
                  <div className={`bar ${d.mgdl >= 0 ? "up" : "down"}`}
                    style={d.mgdl >= 0 ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />
                </div>
              </td>
              <td className="val num">{signed(d.mgdl)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
