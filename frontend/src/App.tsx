import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api, dayMonth, hhmm } from "./api";
import { Menu } from "./components/Disclosure";
import { LiveProvider, useLive } from "./live";
import { Cardio } from "./pages/Cardio";
import { ModelCard } from "./pages/ModelCard";
import { Note } from "./pages/Note";
import { Overview, Patient, Record } from "./pages/Patient";
import { Share } from "./pages/Share";
import { Ward } from "./pages/Ward";
import { WhatIf } from "./pages/WhatIf";

const JUMPS: [string, string][] = [
  ["17:30, before iftar", "2026-03-15T17:30:00+05:30"],
  ["18:00, iftar approaching", "2026-03-15T18:00:00+05:30"],
  ["19:45, demo start", "2026-03-15T19:45:00+05:30"],
];

/** The time and a play button stay visible; speed and jumps live in a small menu. */
function ClockControl() {
  const { clock, connected, refreshClock } = useLive();
  if (!clock) return <div className="clock muted">Connecting</div>;
  const set = (body: Parameters<typeof api.setClock>[0]) => api.setClock(body).then(refreshClock);
  return (
    <div className="clock">
      <span title={connected ? "Live replay connected" : "Replay disconnected"} className={`dot-live ${connected && !clock.paused ? "" : "off"}`} />
      <span className="clock-time">{dayMonth(clock.now)}, {hhmm(clock.now)}</span>
      <button className="btn" onClick={() => set({ paused: !clock.paused })} aria-label={clock.paused ? "Play replay" : "Pause replay"}>
        {clock.paused ? "Play" : "Pause"}
      </button>
      <Menu label="Replay">
        <div className="menu-label">Speed</div>
        <div className="menu-row">
          {[1, 10, 60, 300].map(s => (
            <button key={s} className={`btn ${clock.speed === s ? "primary" : ""}`} onClick={() => set({ speed: s })}>{s}x</button>
          ))}
        </div>
        <div className="menu-label">Jump to 15 March</div>
        {JUMPS.map(([l, v]) => <button key={v} className="menu-item" onClick={() => set({ at: v })}>{l}</button>)}
        <p className="menu-note">The demo replays synthetic data as if it were arriving now.</p>
      </Menu>
    </div>
  );
}

function Settings() {
  const { clinician, setClinician, theme, setTheme } = useLive();
  return (
    <Menu label="Settings">
      <label className="menu-field">Your name, for acknowledgements
        <input type="text" value={clinician} maxLength={40} onChange={e => setClinician(e.target.value)} />
      </label>
      <div className="menu-label">Appearance</div>
      <div className="menu-row">
        <button className={`btn ${theme === "light" ? "primary" : ""}`} onClick={() => setTheme("light")}>Light</button>
        <button className={`btn ${theme === "dark" ? "primary" : ""}`} onClick={() => setTheme("dark")}>Dark</button>
      </div>
      <div className="menu-label">Keyboard, on the ward list</div>
      <p className="menu-note">j and k move between patients, Enter opens one, / jumps to search.</p>
    </Menu>
  );
}

function Shell() {
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="masthead">
        <div className="brand">
          <span className="brand-name">Prativimb</span>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Ward</NavLink>
            <NavLink to="/model">About the model</NavLink>
          </nav>
        </div>
        <div className="mast-tools">
          <ClockControl />
          <Settings />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Ward />} />
          <Route path="/model" element={<ModelCard />} />
          <Route path="/patient/:id" element={<Patient />}>
            <Route index element={<Overview />} />
            <Route path="whatif" element={<WhatIf />} />
            <Route path="cardio" element={<Cardio />} />
            <Route path="record" element={<Record />} />
            <Route path="note" element={<Note />} />
          </Route>
        </Routes>
      </main>
      <footer className="footer">
        <span>Synthetic data only. Decision support, not a diagnosis.</span>
        <span>Prativimb 1.2, MIT licence</span>
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
