import type { Driver } from "../api";
import { gluAbs, gluUnit, prefs, T } from "../api";

const sg = (v: number) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${prefs.units === "mmol" ? gluAbs(v) : Math.abs(v).toFixed(0)}`;

/** Diverging bars of what each factor adds to the predicted peak, in the chosen units. Pushing up in ink, pulling down in the accent. */
export function FactorBars({ drivers }: { drivers: Driver[] }) {
  const shown = drivers.filter(d => Math.abs(d.mgdl) >= 1).slice(0, 7);
  const max = Math.max(10, ...shown.map(d => Math.abs(d.mgdl)));
  return (
    <table className="factors">
      <tbody>
        {shown.map(d => {
          const w = (Math.abs(d.mgdl) / max) * 50;
          return (
            <tr key={d.category} title={`Physiology model ${sg(d.twin)} ${gluUnit()}, learned correction ${sg(d.learned)} ${gluUnit()}`}>
              <td className="txt">{T(d.text[0].toUpperCase() + d.text.slice(1))}</td>
              <td>
                <div className="bar-track">
                  <div className="bar-axis" />
                  <div className={`bar ${d.mgdl >= 0 ? "up" : "down"}`}
                    style={d.mgdl >= 0 ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />
                </div>
              </td>
              <td className="val num">{sg(d.mgdl)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
