import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, dayToDate, dayMonth, fmt, glu, gluAbs, gluUnit, hhmm, minuteToDate, T, type WardRow, type WardWhatIf } from "../api";
import { Hint } from "../components/Hint";
import { GROUP_NAMES, needsAttention, patientLink } from "../components/PatientList";
import { SkeletonRows } from "../components/Skeleton";
import { Sparkline } from "../components/Sparkline";
import { store, stored, useLive, useLiveData } from "../live";

type Filter = "attention" | "all" | "story";

export function trendWord(d30: number | null | undefined): string {
  if (d30 === null || d30 === undefined || !isFinite(d30)) return "";
  if (d30 <= -20) return "falling fast";
  if (d30 <= -6) return "falling";
  if (d30 >= 20) return "rising fast";
  if (d30 >= 6) return "rising";
  return "steady";
}


function GlucoseNext({ r }: { r: WardRow }) {
  const a = r.event_a;
  if (!a) return <span className="flag quiet">No recent reading</span>;
  const acked = a.ack ?? a.low_ack;
  let main;
  if (r.sharing_paused.includes("cgm")) return <span className="flag quiet">Glucose sharing withdrawn</span>;
  if (a.low === "now") main = <span className={`flag ${a.low_ack ? "acked" : "alert"}`}><span className="mark solid" />Low glucose now</span>;
  else if (a.low === "forecast") main = <span className={`flag ${a.low_ack ? "acked" : "alert"}`}><span className="mark solid" />Low glucose likely within the hour</span>;
  else if (a.tier === "alert") main = <span className={`flag ${a.ack ? "acked" : "alert"}`}><span className={`mark ${a.ack ? "" : "solid"}`} />High glucose likely by {hhmm(minuteToDate(a.cross_minute!))}, peak {glu(a.peak)}</span>;
  else if (a.tier === "watch") main = <span className="flag watch"><span className="mark" />Glucose may go high, peak {glu(a.peak)}{a.calibrating ? " (first week)" : ""}</span>;
  else if (a.tier === "high") main = <span className="flag quiet">Above range now</span>;
  else if (a.artefact) main = <span className="flag quiet">Low reading, probably the sensor</span>;
  else main = <span className="flag quiet">In range</span>;
  const why = a.tier === "alert" ? a.reason : a.low ? a.low_reason : "";
  return <div>{main}{why && <div className="sub why-line">{T(why)}</div>}{acked && <div className="sub">Seen by {acked.by}</div>}</div>;
}

function Heart({ r }: { r: WardRow }) {
  const b = r.event_b;
  if (b.post_event) return <span className="flag quiet">Event on {b.event_minute !== undefined ? dayMonth(minuteToDate(b.event_minute)) : ""}</span>;
  if (b.paused) return <span className="flag quiet">Wearable sharing withdrawn</span>;
  if (b.risk === null) return <span className="flag quiet">No data</span>;
  if (b.flag) return (
    <div>
      <span className={`flag ${b.ack ? "acked" : "alert"}`}><span className={`mark ${b.ack ? "" : "solid"}`} />Raised</span>
      <div className="sub">{fmt(b.risk * 100)}% in 3 days{b.flag_since !== null && b.flag_since !== undefined ? `, since ${dayMonth(dayToDate(b.flag_since))}` : ""}</div>
      {b.reason && <div className="sub why-line">{b.reason}</div>}
      {b.ack && <div className="sub">Seen by {b.ack.by}</div>}
    </div>
  );
  return <span className="flag quiet">Normal</span>;
}

/** Alert keys a clinician has to know about. Acknowledged ones do not count as new. */
function alertKeys(rows: WardRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    if (r.event_a?.tier === "alert" && !r.event_a.ack) out[`${r.id}:spike`] = r.name;
    if ((r.event_a?.low === "now" || r.event_a?.low === "forecast") && !r.event_a.low_ack) out[`${r.id}:low`] = r.name;
    if (r.event_b.flag && !r.event_b.ack) out[`${r.id}:cardio`] = r.name;
  }
  return out;
}

function SinceLastLooked({ rows, now }: { rows: WardRow[]; now: string }) {
  const current = alertKeys(rows);
  const [open, setOpen] = useState(false);
  const [snap, setSnap] = useState<{ t: string; keys: Record<string, string> } | null>(() => {
    try { return JSON.parse(stored("prativimb-ward-seen", "null")); } catch { return null; }
  });
  const markSeen = () => {
    const s = { t: now, keys: current };
    store("prativimb-ward-seen", JSON.stringify(s));
    setSnap(s);
    setOpen(false);
  };
  useEffect(() => { if (!snap) markSeen(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!snap) return null;
  const added = Object.keys(current).filter(k => !(k in snap.keys));
  const resolved = Object.keys(snap.keys).filter(k => !(k in current));
  if (!added.length && !resolved.length) return <p className="since quiet">Nothing new since you last looked at {hhmm(snap.t)}.</p>;
  const names = (keys: string[], src: Record<string, string>) => [...new Set(keys.map(k => src[k]))].join(", ");
  return (
    <div className="since" role="status">
      <span>
        Since {hhmm(snap.t)}: {added.length > 0 && <b className="alert-text">{added.length} new {added.length === 1 ? "alert" : "alerts"}</b>}
        {added.length > 0 && resolved.length > 0 && ", "}
        {resolved.length > 0 && <>{resolved.length} settled</>}.
      </span>
      <button className="link-btn" onClick={() => setOpen(o => !o)} aria-expanded={open}>{open ? "Hide names" : "Show names"}</button>
      <button className="link-btn" onClick={markSeen}>Mark as seen</button>
      {open && (
        <div className="since-detail">
          {added.length > 0 && <p><b>New:</b> {names(added, current)}</p>}
          {resolved.length > 0 && <p><b>Settled or acknowledged:</b> {names(resolved, snap.keys)}</p>}
        </div>
      )}
    </div>
  );
}

/** If tonight's likely high patients made a change: every change added up across them, and each patient's own best change. */
function WardWhatIfPanel({ count }: { count: number }) {
  const { can, refresh, toast } = useLive();
  const [watch, setWatch] = useState(false);
  const [res, setRes] = useState<WardWhatIf | null>(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const load = (w: boolean) => { setWatch(w); setBusy(true); api.wardWhatIf(w).then(setRes).finally(() => setBusy(false)); };
  const send = () => {
    setSending(true);
    api.wardNudge("own_best", watch).then(r => {
      refresh();
      toast({ text: `Sent ${r.sent.length} ${r.sent.length === 1 ? "message" : "messages"}${r.skipped.length ? `; ${r.skipped.length} already had one tonight` : ""}.`,
        undo: () => Promise.all(r.sent.map(x => api.removeMessage(x.pid, x.id))) });
    }).catch(e => toast({ text: e.message, error: true })).finally(() => setSending(false));
  };
  const top = res?.levers[0];
  return (
    <details className="disclosure ward-whatif" onToggle={e => { if ((e.target as HTMLDetailsElement).open && !res) load(false); }}>
      <summary><span className="d-title">If tonight's {count} likely high patients made a change</span>
        <span className="d-hint">{res ? `up to ${fmt(res.own_best.hours_saved, 1)} fewer hours above 180 in all` : "each patient's own forecast, added up"}</span></summary>
      <div className="d-body">
        <label className="check inline-left"><input type="checkbox" checked={watch} onChange={e => load(e.target.checked)} />
          Include the patients whose glucose may go high</label>
        {busy && <p className="empty">Running every change through each patient's forecast.</p>}
        {res && !busy && (
          <>
            <p className="lead">If each patient made the change that helps them most: about <b>{fmt(res.own_best.hours_saved, 1)} fewer hours above 180</b>
              {" "}across {res.patients.length} patients tonight{top ? `, against ${fmt(top.hours_saved, 1)} if everyone did the best single change (${top.label.toLowerCase()})` : ""}.</p>
            <div className="two">
              <table className="log num ww-table">
                <thead><tr><th scope="col">Same change for everyone</th><th scope="col">Hours above 180 saved</th><th scope="col">Peaks lower by</th></tr></thead>
                <tbody>
                  <tr className="own"><td>Each patient's own best change</td><td>{fmt(res.own_best.hours_saved, 1)}</td><td>{gluAbs(res.own_best.mean_peak_drop)} {gluUnit()}</td></tr>
                  {res.levers.map(l => <tr key={l.label}><td>{l.label}</td><td>{fmt(l.hours_saved, 1)}</td><td>{gluAbs(l.mean_peak_drop)} {gluUnit()}</td></tr>)}
                </tbody>
              </table>
              <table className="log num ww-table">
                <thead><tr><th scope="col">Patient</th><th scope="col">What helps them most</th><th scope="col">Saves</th></tr></thead>
                <tbody>{res.patients.map(p => (
                  <tr key={p.pid}><td><Link to={`/patient/${p.pid}/try`}>{p.name}</Link></td><td>{p.best}</td>
                    <td>{fmt(p.best_hours_saved * 60)} min, peak {glu(p.peak)} to {glu(p.by_lever[p.best].peak_after)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            {can("act") && (
              <div className="agree">
                <button className="btn primary" disabled={sending} onClick={send}>Message each patient their best change</button>
                <span className="small muted">Goes to each patient's phone in their language, with the numbers above. Patients messaged in the last 6 hours are skipped.</span>
              </div>
            )}
          </>
        )}
      </div>
    </details>
  );
}

export function Ward() {
  const { clock } = useLive();
  const { data, error } = useLiveData(() => api.ward(), []);
  const [typical, setTypical] = useState<Record<string, number> | null>(null);
  useEffect(() => { api.modelCard().then(m => setTypical(m.followup?.alert_load?.by_hour_of_200 ?? null)).catch(() => {}); }, []);
  const [filter, setFilter] = useState<Filter>(() => (stored("prativimb-ward-filter", "attention") as Filter));
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const body = useRef<HTMLTableSectionElement>(null);
  const byKeyboard = useRef(false);
  const nav = useNavigate();
  const choose = (f: Filter) => { setFilter(f); store("prativimb-ward-filter", f); };

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.patients.filter(r => {
      if (needle) return `${r.name} ${r.id}`.toLowerCase().includes(needle);
      if (filter === "attention") return needsAttention(r);
      if (filter === "story") return r.hero;
      return true;
    });
  }, [data, filter, q]);

  // Keyboard: j and k move, Enter opens, slash searches.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON" || tag === "SUMMARY") {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); byKeyboard.current = true; setCursor(c => Math.min(c + 1, rows.length - 1)); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); byKeyboard.current = true; setCursor(c => Math.max(c - 1, 0)); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows]);
  useEffect(() => {
    if (!byKeyboard.current) return;
    byKeyboard.current = false;
    (body.current?.querySelectorAll("tr.row")[cursor] as HTMLElement | undefined)?.focus();
  }, [cursor]);
  useEffect(() => setCursor(0), [filter, q]);
  useEffect(() => {
    const save = () => store("prativimb-ward-scroll", String(window.scrollY));
    window.addEventListener("scroll", save, { passive: true });
    return () => window.removeEventListener("scroll", save);
  }, []);
  const restored = useRef(false);
  useEffect(() => {
    if (!data || restored.current) return;
    restored.current = true;
    const y = Number(stored("prativimb-ward-scroll", "0"));
    if (y > 0) window.requestAnimationFrame(() => window.scrollTo(0, y));
  }, [data]);

  if (error) return <p className="empty">Could not reach the Prativimb service ({error}). Is the API running on port 8000?</p>;
  const p = data?.patients ?? [];
  const counts = { attention: p.filter(needsAttention).length, all: p.length, story: p.filter(r => r.hero).length };
  const labels: Record<Filter, string> = { attention: "Needs attention", all: "All patients", story: "Demo patients" };
  const stale = (r: WardRow) => {
    if (!r.last_sync || !clock) return null;
    const mins = Math.round((new Date(clock.now).getTime() - new Date(r.last_sync).getTime()) / 60000);
    return mins > 30 ? `no reading for ${mins} min` : null;
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Ward</h1>
          <div className="meta">{counts.all || 200} patients on remote monitoring{clock && <>, as of {hhmm(clock.now)}</>}</div>
          {data && clock && typical && (() => {
            const hour = Number(new Date(clock.now).toLocaleString("en-GB", { hour: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }));
            const t = typical[String(hour)];
            return t !== undefined ? <div className="meta muted">{counts.attention} need attention now; on a typical day at this hour a ward like this has about {fmt(t)}.</div> : null;
          })()}
          {data?.patients[0]?.calibrating && <div className="meta notice-inline">First week of monitoring (day {data.patients[0].calibrating} of 7): the glucose forecast is still learning, so possible highs are not pushed.</div>}
        </div>
      </div>
      {data && clock && <SinceLastLooked rows={data.patients} now={clock.now} />}
      <div className="segmented big" role="tablist" aria-label="Which patients to show">
        {(Object.keys(labels) as Filter[]).map(f => (
          <button key={f} role="tab" aria-selected={filter === f && !q} className={filter === f && !q ? "on" : ""} onClick={() => { setQ(""); choose(f); }}>
            {labels[f]} <span className="count">{data ? counts[f] : ""}</span>
          </button>
        ))}
      </div>
      {data && counts.attention > 0 && <WardWhatIfPanel count={p.filter(r => r.group === "high").length} />}
      <Hint id="ward">Grouped by urgency: lows first, then likely highs, then heart risk. The grey line under each alert says why. Press n to open the next alert nobody has seen.</Hint>
      <table className="ward">
        <thead>
          <tr>
            <th scope="col">Patient</th>
            <th scope="col" className="r">Glucose now, {gluUnit()}</th>
            <th scope="col">Glucose forecast, next 2 hours</th>
            <th scope="col">Heart risk</th>
            <th scope="col" className="hide-md">Last 24 hours</th>
          </tr>
        </thead>
        {!data ? <SkeletonRows cols={5} /> : (
          <tbody ref={body}>
            {rows.map((r, i) => (
              <Fragment key={r.id}>
              {!q && filter !== "story" && r.group !== rows[i - 1]?.group && (
                <tr className="group-row"><th colSpan={5} scope="colgroup">{r.group ? GROUP_NAMES[r.group] : "No alerts"}{" "}
                  <span className="muted">{rows.filter(x => x.group === r.group).length}</span></th></tr>
              )}
              <tr className={`row ${i === cursor ? "cursor" : ""}`} onClick={() => nav(patientLink(r))} tabIndex={0}
                onFocus={() => setCursor(i)} onKeyDown={e => e.key === "Enter" && nav(patientLink(r))}
                aria-label={`${r.name}, open`}>
                <td>
                  <div className="name">{r.name}{r.twin_fit === "drifting" && <span className="tag" title="The twin's recent error is clearly worse than in its first week of use">Twin needs refit</span>}</div>
                  <div className="sub">{r.age} {r.sex}{r.problems.length ? `, ${r.problems.slice(0, 2).join(", ")}` : ""}</div>
                </td>
                <td className="r">
                  <div className="glucose-now num">{glu(r.glucose)}</div>
                  <div className="sub">{stale(r) ?? trendWord(r.trend30)}</div>
                </td>
                <td className="c-flag"><GlucoseNext r={r} /></td>
                <td className="c-cv" data-label="Heart risk"><Heart r={r} /></td>
                <td className="hide-md"><Sparkline values={r.sparkline} /></td>
              </tr>
              </Fragment>
            ))}
          </tbody>
        )}
      </table>
      {data && !rows.length && <p className="empty">{q ? "No patient matches that name or ID." : "Nobody needs attention right now."}</p>}
    </>
  );
}
