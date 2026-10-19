import { BrowserRouter, Navigate, NavLink, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { DemoBar } from "./components/DemoBar";
import { Menu } from "./components/Disclosure";
import { GlobalSearch } from "./components/GlobalSearch";
import { LiveProvider, useLive } from "./live";
import { ModelCard } from "./pages/ModelCard";
import { Note } from "./pages/Note";
import { Patient, Record, Today } from "./pages/Patient";
import { Share } from "./pages/Share";
import { Ward } from "./pages/Ward";
import { WhatIf } from "./pages/WhatIf";

function Settings() {
  const { clinician, setClinician, theme, setTheme } = useLive();
  return (
    <Menu label="Settings">
      <label className="menu-field">Your name, used when you mark alerts as seen
        <input type="text" value={clinician} maxLength={40} onChange={e => setClinician(e.target.value)} />
      </label>
      <div className="menu-label">Appearance</div>
      <div className="menu-row">
        <button className={`btn ${theme === "light" ? "primary" : ""}`} onClick={() => setTheme("light")}>Light</button>
        <button className={`btn ${theme === "dark" ? "primary" : ""}`} onClick={() => setTheme("dark")}>Dark</button>
      </div>
      <div className="menu-label">Keyboard</div>
      <p className="menu-note">/ or Ctrl and K: find a patient. On the ward, j and k move and Enter opens. On a patient, Alt and the arrow keys go to the previous or next patient needing attention.</p>
    </Menu>
  );
}

// Old addresses keep working.
function ToTry() { const { id } = useParams(); return <Navigate to={`/patient/${id}/try`} replace />; }
function ToNote() { const { id } = useParams(); return <Navigate to={`/note/${id}`} replace />; }
function ToHeart() {
  const { id } = useParams();
  const [q] = useSearchParams();
  return <Navigate to={`/patient/${id}?heart=${q.get("end") ?? ""}`} replace />;
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
          <GlobalSearch />
          <Settings />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Ward />} />
          <Route path="/model" element={<ModelCard />} />
          <Route path="/patient/:id" element={<Patient />}>
            <Route index element={<Today />} />
            <Route path="try" element={<WhatIf />} />
            <Route path="record" element={<Record />} />
            <Route path="whatif" element={<ToTry />} />
            <Route path="cardio" element={<ToHeart />} />
            <Route path="note" element={<ToNote />} />
          </Route>
        </Routes>
      </main>
      <footer className="footer">
        <span>Synthetic data only. Decision support, not a diagnosis.</span>
        <span>Prativimb 1.3, MIT licence</span>
      </footer>
      <DemoBar />
    </>
  );
}

export default function App() {
  return (
    <LiveProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/share/:id" element={<Share />} />
          <Route path="/note/:id" element={<Note />} />
          <Route path="*" element={<Shell />} />
        </Routes>
      </BrowserRouter>
    </LiveProvider>
  );
}
