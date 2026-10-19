import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ROLE_NAMES, T, type WardRow } from "./api";
import { DemoBar } from "./components/DemoBar";
import { Menu } from "./components/Disclosure";
import { GlobalSearch } from "./components/GlobalSearch";
import { GROUP_NAMES, needsAttention, nextUnseen, patientLink } from "./components/PatientList";
import { Toasts } from "./components/Toasts";
import { LiveProvider, store, stored, useLive, useLiveData } from "./live";
import { Digest } from "./pages/Digest";
import { Handover } from "./pages/Handover";
import { ModelCard } from "./pages/ModelCard";
import { Note } from "./pages/Note";
import { Patient, Record, Today } from "./pages/Patient";
import { Share } from "./pages/Share";
import { SignIn } from "./pages/SignIn";
import { Ward } from "./pages/Ward";
import { WhatIf } from "./pages/WhatIf";

function Settings() {
  const { theme, setTheme, prefs, setPrefs, resetHints } = useLive();
  const choice = <K extends "units" | "tz" | "size">(k: K, opts: [string, string][]) => (
    <div className="menu-row" role="radiogroup">
      {opts.map(([v, l]) => (
        <button key={v} role="radio" aria-checked={prefs[k] === v} className={`btn ${prefs[k] === v ? "primary" : ""}`}
          onClick={() => setPrefs({ [k]: v } as never)}>{l}</button>
      ))}
    </div>
  );
  const notify = (on: boolean) => {
    if (on && "Notification" in window && Notification.permission !== "granted") {
      Notification.requestPermission().then(p => setPrefs({ notify: p === "granted" }));
    } else setPrefs({ notify: on });
  };
  return (
    <Menu label="Settings">
      <div className="menu-label">Glucose units</div>
      {choice("units", [["mgdl", "mg/dL"], ["mmol", "mmol/L"]])}
      <div className="menu-label">Times</div>
      {choice("tz", [["ist", "India time"], ["local", "This computer's time"]])}
      <div className="menu-label">Text size</div>
      {choice("size", [["normal", "Normal"], ["large", "Larger"]])}
      <div className="menu-label">Appearance</div>
      <div className="menu-row">
        <button className={`btn ${theme === "light" ? "primary" : ""}`} onClick={() => setTheme("light")}>Light</button>
        <button className={`btn ${theme === "dark" ? "primary" : ""}`} onClick={() => setTheme("dark")}>Dark</button>
      </div>
      <div className="menu-label">Notifications</div>
      <label className="menu-check"><input type="checkbox" checked={prefs.notify} onChange={e => notify(e.target.checked)} />
        Desktop notification for new confirmed alerts (lows, likely highs, raised heart risk). Possible highs stay in the app.</label>
      <div className="menu-label">Tips</div>
      <div className="menu-row">
        <button className="btn" onClick={() => setPrefs({ hints: !prefs.hints })}>{prefs.hints ? "Hide tips" : "Show tips"}</button>
        <button className="btn" onClick={resetHints}>Show all tips again</button>
      </div>
      <div className="menu-label">Keyboard</div>
      <p className="menu-note">/ or Ctrl and K: find a patient. n: next patient with an alert nobody has seen. On the ward, j and k move and Enter opens.
        On a patient, Alt and the arrow keys go to the previous or next patient needing attention.</p>
    </Menu>
  );
}

function UserMenu() {
  const { user, signOut } = useLive();
  const nav = useNavigate();
  if (!user) return null;
  return (
    <Menu label={user.name}>
      <div className="menu-label">Signed in as</div>
      <p className="menu-note"><b>{user.name}</b>, {ROLE_NAMES[user.role].toLowerCase()}</p>
      <p className="menu-note">{user.role === "nurse" ? "Nurses and health educators can mark glucose alerts as seen, call and check patients, and log meals. A doctor reviews heart risk alerts and agrees plans."
        : "Doctors can do everything here, including marking heart risk alerts as seen and agreeing plans."}</p>
      <button className="btn" onClick={() => { signOut(); nav("/signin"); }}>Sign out</button>
    </Menu>
  );
}

const alertKey = (r: WardRow) => (needsAttention(r) && !r.seen ? `${r.id}:${r.group}` : null);

/** New confirmed alerts since you last opened this list; optionally as desktop notifications. */
function Notifications() {
  const { prefs } = useLive();
  const { data } = useLiveData(() => api.ward(), []);
  const [seen, setSeen] = useState<string[]>(() => { try { return JSON.parse(stored("prativimb-notified", "[]")); } catch { return []; } });
  const announced = useRef<Set<string> | null>(null);
  const rows = (data?.patients ?? []).filter(r => alertKey(r));
  const fresh = rows.filter(r => !seen.includes(alertKey(r)!));
  useEffect(() => {
    if (!data) return;
    const keys = new Set(rows.map(r => alertKey(r)!));
    if (announced.current && prefs.notify && "Notification" in window && Notification.permission === "granted") {
      rows.filter(r => !announced.current!.has(alertKey(r)!)).slice(0, 3).forEach(r =>
        new Notification(`${GROUP_NAMES[r.group!]}: ${r.name}`, { body: T(r.event_a?.reason || r.event_b.reason || "Open Prativimb for details"), tag: alertKey(r)! }));
    }
    announced.current = keys;
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const markRead = () => { const k = rows.map(r => alertKey(r)!); setSeen(k); store("prativimb-notified", JSON.stringify(k)); };
  return (
    <details className="menu" onToggle={e => { if (!(e.target as HTMLDetailsElement).open) markRead(); }}>
      <summary className="btn">Alerts{fresh.length > 0 && <span className="badge" aria-label={`${fresh.length} new`}>{fresh.length}</span>}</summary>
      <div className="menu-panel wide">
        <div className="menu-label">{fresh.length ? "New since you last looked" : "Nothing new"}</div>
        <ul className="notif">
          {fresh.slice(0, 10).map(r => (
            <li key={r.id}><Link to={patientLink(r)}><b>{r.name}</b> <span className="alert-text">{GROUP_NAMES[r.group!]}</span>
              {(r.event_a?.reason || r.event_b.reason) && <span className="muted">, {T(r.event_a?.reason || r.event_b.reason || "")}</span>}</Link></li>
          ))}
        </ul>
        <p className="menu-note">{rows.length} open {rows.length === 1 ? "alert" : "alerts"} in all. Possible highs are not listed here; they stay on each patient's page.</p>
        <button className="btn" onClick={markRead}>Mark all as read</button>
      </div>
    </details>
  );
}

/** n anywhere: the next patient with an alert nobody has marked as seen. */
function NextUnseenKey() {
  const { data } = useLiveData(() => api.ward(), []);
  const nav = useNavigate();
  const loc = useLocation();
  const { toast } = useLive();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (e.key !== "n" || e.ctrlKey || e.metaKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      const current = loc.pathname.match(/^\/patient\/([^/]+)/)?.[1];
      const r = nextUnseen(data?.patients ?? [], current);
      if (r) nav(patientLink(r)); else toast({ text: "Every alert has been seen." });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [data, loc.pathname, nav, toast]);
  return null;
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
  const { user } = useLive();
  const loc = useLocation();
  if (!user) return <Navigate to={`/signin?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (user.role === "patient") return <Navigate to={`/share/${user.pid}`} replace />;
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="masthead">
        <div className="brand">
          <span className="brand-name">Prativimb</span>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Ward</NavLink>
            <NavLink to="/handover">Handover</NavLink>
            <NavLink to="/digest">Daily digest</NavLink>
            <NavLink to="/model">About the model</NavLink>
          </nav>
        </div>
        <div className="mast-tools">
          <GlobalSearch />
          <Notifications />
          <Settings />
          <UserMenu />
        </div>
      </header>
      <NextUnseenKey />
      <main id="main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Ward />} />
          <Route path="/handover" element={<Handover />} />
          <Route path="/digest" element={<Digest />} />
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
        <span>Prativimb 1.4, MIT licence</span>
      </footer>
      <DemoBar />
    </>
  );
}

function Prefs({ children }: { children: (key: string) => JSX.Element }) {
  const { prefs } = useLive();
  // Units and time zone are read while rendering, so a change re-renders everything from scratch.
  return children(`${prefs.units}-${prefs.tz}`);
}

export default function App() {
  return (
    <LiveProvider>
      <Prefs>{key => (
        <BrowserRouter key={key}>
          <Routes>
            <Route path="/signin" element={<SignIn />} />
            <Route path="/share/:id" element={<Share />} />
            <Route path="/note/:id" element={<Note />} />
            <Route path="*" element={<Shell />} />
          </Routes>
          <Toasts />
        </BrowserRouter>
      )}</Prefs>
    </LiveProvider>
  );
}
