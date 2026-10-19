import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api, dayMonth, fullTime, hhmm } from "./api";
import { LiveProvider, useLive } from "./live";
import { Cardio } from "./pages/Cardio";
import { ModelCard } from "./pages/ModelCard";
import { Note } from "./pages/Note";
import { Patient, TwinTab } from "./pages/Patient";
import { Share } from "./pages/Share";
import { Ward } from "./pages/Ward";
import { WhatIf } from "./pages/WhatIf";

const JUMPS: [string, string][] = [
  ["15 Mar 17:30", "2026-03-15T17:30:00+05:30"],
  ["15 Mar 18:00", "2026-03-15T18:00:00+05:30"],
  ["15 Mar 19:45", "2026-03-15T19:45:00+05:30"],
];

function ClockControl() {
  const { clock, connected, refreshClock } = useLive();
  if (!clock) return <div className="clock muted">Connecting</div>;
  const set = (body: Parameters<typeof api.setClock>[0]) => api.setClock(body).then(refreshClock);
  return (
    <div className="clock">
      <span title={connected ? "Replay stream connected" : "Stream disconnected"} className={`dot-live ${connected && !clock.paused ? "" : "off"}`} />
      <span className="clock-time"><span className="hide-sm">{fullTime(clock.now)}</span><span className="show-sm">{dayMonth(clock.now)} {hhmm(clock.now)}</span> IST</span>
      <span className="muted small">Replay {clock.paused ? "paused" : `${clock.speed}x`}</span>
      <button className="btn" onClick={() => set({ paused: !clock.paused })}>{clock.paused ? "Play" : "Pause"}</button>
      <select className="hide-sm" aria-label="Replay speed" value={clock.speed} onChange={e => set({ speed: +e.target.value })}>
        {[1, 10, 60, 300].map(s => <option key={s} value={s}>{s}x</option>)}
      </select>
      <select className="hide-sm" aria-label="Jump to time" value="" onChange={e => e.target.value && set({ at: e.target.value })}>
        <option value="">Jump to</option>
        {JUMPS.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );
}

function Clinician() {
  const { clinician, setClinician } = useLive();
  return (
    <label className="clinician small hide-sm">Signed in as{" "}
      <input type="text" value={clinician} maxLength={40} onChange={e => setClinician(e.target.value)} aria-label="Clinician name" />
    </label>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useLive();
  return <button className="btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "Light" : "Dark"}</button>;
}

function Shell() {
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="masthead">
        <div className="brand">
          <span className="brand-name">Prativimb</span>
          <span className="brand-sub">Patient twin</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Ward</NavLink>
          <NavLink to="/model">Model card</NavLink>
        </nav>
        <div className="mast-tools">
          <ClockControl />
          <Clinician />
          <ThemeToggle />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Ward />} />
          <Route path="/model" element={<ModelCard />} />
          <Route path="/patient/:id" element={<Patient />}>
            <Route index element={<TwinTab />} />
            <Route path="whatif" element={<WhatIf />} />
            <Route path="cardio" element={<Cardio />} />
            <Route path="note" element={<Note />} />
          </Route>
        </Routes>
      </main>
      <footer className="footer">
        <span>Synthetic data only. Decision support, not a diagnosis.</span>
        <span>Prativimb 1.0, MIT licence</span>
      </footer>
    </>
  );
}

export default function App() {
  return (
    <LiveProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/share/:id" element={<Share />} />
          <Route path="*" element={<Shell />} />
        </Routes>
      </BrowserRouter>
    </LiveProvider>
  );
}
