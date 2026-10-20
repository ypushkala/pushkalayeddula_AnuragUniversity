import { api, fullTime, zoneName } from "../api";
import { useLive } from "../live";

const JUMPS: [string, string][] = [
  ["17 Feb, new patients", "2026-02-17T19:45:00+05:30"],
  ["17:30", "2026-03-15T17:30:00+05:30"],
  ["18:00", "2026-03-15T18:00:00+05:30"],
  ["19:45", "2026-03-15T19:45:00+05:30"],
  ["22:30", "2026-03-15T22:30:00+05:30"],
];

/** Demo controls live apart from the clinical tool, in a strip at the bottom of the screen. */
export function DemoBar() {
  const { clock, connected, refreshClock } = useLive();
  if (!clock) return null;
  const set = (body: Parameters<typeof api.setClock>[0]) => api.setClock(body).then(refreshClock);
  return (
    <aside className="demobar" aria-label="Demo replay controls">
      <span className="demo-tag">Demo replay</span>
      <span className="demo-time"><span className={`dot-live ${connected && !clock.paused ? "" : "off"}`} />{fullTime(clock.now)} {zoneName()}</span>
      <button className="btn" onClick={() => set({ paused: !clock.paused })}>{clock.paused ? "Play" : "Pause"}</button>
      <span className="demo-group hide-sm" role="group" aria-label="Speed">
        <span className="muted">Speed</span>
        {[1, 10, 60, 300].map(s => (
          <button key={s} className={`chip ${clock.speed === s ? "on" : ""}`} aria-pressed={clock.speed === s} onClick={() => set({ speed: s })}>{s}x</button>
        ))}
      </span>
      <span className="demo-group" role="group" aria-label="Jump to a time">
        <span className="muted hide-sm">Jump to</span>
        {JUMPS.map(([l, v]) => <button key={v} className="chip" onClick={() => set({ at: v })}>{l}</button>)}
      </span>
      <span className="demo-note hide-md">Synthetic patients, replayed as if live.</span>
    </aside>
  );
}
