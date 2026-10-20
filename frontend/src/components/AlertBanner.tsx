import { useState } from "react";
import { Link } from "react-router-dom";
import { api, hhmm, T, type AlertCard } from "../api";
import { useLive, useLiveData } from "../live";
import { LEVER_KEY } from "../pages/Share";
import { MealEntry } from "./MealEntry";

const SNOOZE: [number, string][] = [[30, "30 min"], [60, "1 hour"], [120, "2 hours"], [240, "4 hours"]];
const ACKABLE = ["spike", "low", "cardio"];
const KIND_NAMES: Record<string, string> = { spike: "High glucose", low: "Low glucose", cardio: "Heart risk" };
type Panel = "seen" | "meal" | "call" | "review" | "check" | null;

function MarkSeen({ pid, cards, done }: { pid: string; cards: AlertCard[]; done: () => void }) {
  const { clinician, refresh, toast, can } = useLive();
  const allowed = (c: AlertCard) => (c.kind === "cardio" ? can("ack-heart") : can("ack"));
  const [pick, setPick] = useState<string[]>(() => cards.filter(allowed).map(c => c.kind));
  const [snooze, setSnooze] = useState(60);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = () => {
    setBusy(true);
    Promise.all(pick.map(kind => api.ack(pid, { kind, snooze_minutes: snooze, note })))
      .then(acks => {
        refresh(); done();
        toast({ text: `Marked ${pick.map(k => KIND_NAMES[k].toLowerCase()).join(" and ")} as seen.`,
          undo: () => Promise.all(acks.map(a => api.unack(pid, a.id))) });
      })
      .catch(e => toast({ text: e.message, error: true }))
      .finally(() => setBusy(false));
  };
  return (
    <div className="banner-panel">
      {cards.length > 1 && (
        <fieldset className="pick">
          <legend>Which alerts</legend>
          {cards.map(c => (
            <label key={c.kind} className={allowed(c) ? "" : "muted"}>
              <input type="checkbox" checked={pick.includes(c.kind)} disabled={!allowed(c)}
                onChange={e => setPick(p => (e.target.checked ? [...p, c.kind] : p.filter(k => k !== c.kind)))} />
              {T(c.title)}{!allowed(c) && " (a doctor reviews heart risk)"}
            </label>
          ))}
        </fieldset>
      )}
      <label>Keep quiet for{" "}
        <select value={snooze} onChange={e => setSnooze(+e.target.value)}>{SNOOZE.map(([m, l]) => <option key={m} value={m}>{l}</option>)}</select>
      </label>
      <input type="text" placeholder="Note, optional (for example: discussed a walk after dinner)" value={note} maxLength={280}
        onChange={e => setNote(e.target.value)} aria-label="Note" />
      <div className="row-actions">
        <button className="btn primary" disabled={busy || !pick.length} onClick={submit}>Mark as seen by {clinician}</button>
        <button className="btn" onClick={done}>Cancel</button>
      </div>
    </div>
  );
}

const OUTCOMES: Record<"call" | "review" | "check", { label: string; options: string[]; note: string; button: string; done: string }> = {
  call: { label: "What happened", options: ["Spoke to the patient, no symptoms", "Spoke to the patient, symptoms reported and advised to attend",
    "Spoke to a family member", "Could not reach, will try again"], note: "Note, optional", button: "Record the call", done: "Recorded the call." },
  review: { label: "When", options: ["Today", "Tomorrow", "Within 3 days", "Within a week"], note: "With whom or where, optional (for example: cardiology clinic)",
    button: "Book the review", done: "Review booked." },
  check: { label: "What you found", options: ["Fingerstick confirms low, treated with 15 g fast sugar", "Fingerstick normal, probably the sensor",
    "Patient eating now", "Could not reach, will try again"], note: "Fingerstick reading or note, optional", button: "Record the check", done: "Recorded the check." },
};

function ActionPanel({ pid, kind, alert, done }: { pid: string; kind: "call" | "review" | "check"; alert: string; done: () => void }) {
  const { refresh, toast } = useLive();
  const o = OUTCOMES[kind];
  const [outcome, setOutcome] = useState(o.options[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = () => {
    setBusy(true);
    api.action(pid, { kind, outcome: kind === "review" ? `Review ${outcome.toLowerCase()}` : outcome, note,
      alert: ACKABLE.includes(alert) ? alert : "" })
      .then(a => { refresh(); done(); toast({ text: o.done, undo: () => api.undoAction(pid, a.id) }); })
      .catch(e => toast({ text: e.message, error: true }))
      .finally(() => setBusy(false));
  };
  return (
    <div className="banner-panel">
      <label>{o.label}{" "}
        <select value={outcome} onChange={e => setOutcome(e.target.value)}>{o.options.map(x => <option key={x}>{x}</option>)}</select>
      </label>
      <input type="text" placeholder={o.note} value={note} maxLength={280} onChange={e => setNote(e.target.value)} aria-label={o.note} />
      <div className="row-actions">
        <button className="btn primary" disabled={busy} onClick={submit}>{o.button}</button>
        <button className="btn" onClick={done}>Cancel</button>
      </div>
    </div>
  );
}

/** The patient's most important alert with what you can do about it, on every tab. The first action fits the alert. */
export function AlertBanner({ pid, first }: { pid: string; first: string }) {
  const { can, refresh, toast } = useLive();
  const fc = useLiveData(() => api.forecast(pid), [pid]).data;
  const msgs = useLiveData(() => api.messages(pid), [pid]).data;
  const lastReply = (msgs ?? []).filter(m => m.from === "patient").slice(-1)[0];
  const lastNudge = (msgs ?? []).filter(m => m.key === "nudge").slice(-1)[0];
  const REPLY: Record<string, string> = { will_walk: "will walk after dinner", walked: "walked 15 minutes", not_today: "not today" };
  const [panel, setPanel] = useState<Panel>(null);
  if (!fc) return <div className="banner calm skeleton-block" style={{ height: 96 }} aria-busy="true" />;
  const cards = fc.alerts ?? [];
  const open = cards.filter(c => ACKABLE.includes(c.kind) && !c.ack);
  const main = open.find(c => c.kind === "low") ?? open.find(c => c.tier === "alert") ?? open[0]
    ?? cards.find(c => c.tier !== "info") ?? cards.find(c => c.kind === "event") ?? cards[0];
  const others = cards.filter(c => c !== main);
  const urgent = main && main.tier === "alert" && !main.ack;
  const toggle = (p: Panel) => setPanel(x => (x === p ? null : p));
  const kind = main?.kind ?? "none";

  const btn = (p: Exclude<Panel, null>, label: string, primary = false) => (
    <button key={p} className={`btn ${primary ? "primary" : ""}`} aria-expanded={panel === p} onClick={() => toggle(p)}>{label}</button>
  );
  const tryLink = (primary: boolean) => <Link key="try" className={`btn ${primary ? "primary" : ""}`} to={`/patient/${pid}/try`}>Try a change</Link>;
  const seen = open.length > 0 && can("ack") ? btn("seen", "Mark as seen") : null;
  const act = can("act");
  let actions: (JSX.Element | null)[];
  if (kind === "low") actions = [act ? btn("check", "Check the patient now", true) : null, act ? btn("call", "Call the patient") : null, seen, btn("meal", "Log a meal")];
  else if (kind === "cardio") actions = [act ? btn("call", "Call the patient", true) : null, act ? btn("review", "Book a review") : null, seen];
  else if (kind === "event") actions = [act ? btn("review", "Book a review", true) : null, act ? btn("call", "Call the patient") : null];
  else if (kind === "spike") actions = [tryLink(true), seen, btn("meal", "Log a meal"), act ? btn("call", "Call the patient") : null];
  else actions = [tryLink(true), btn("meal", "Log a meal"), seen];
  actions.push(<Link key="share" className="btn" to={`/share/${pid}`}>Share with {first}</Link>,
    <Link key="note" className="btn" to={`/note/${pid}`}>Clinical note</Link>);

  const nudge = () => {
    if (!fc.available) return;
    api.levers(pid).then(lv => {
      const walk = lv.levers.find(l => l.request.walk_minutes === 15 && !l.request.swap) ?? lv.levers[0];
      return api.addMessage(pid, { key: "nudge", params: { peak: Math.round(fc.status.peak), after: Math.round(fc.status.peak + walk.peak), lever: LEVER_KEY(walk.request) } });
    }).then(m => { refresh(); toast({ text: `Message sent to ${first}'s phone.`, undo: () => api.removeMessage(pid, m.id) }); })
      .catch(e => toast({ text: e.message, error: true }));
  };
  const alsoLink = (c: AlertCard) => (c.kind === "cardio" || c.kind === "event" ? `/patient/${pid}?heart=`
    : c.kind === "calibrating" ? `/patient/${pid}/record#learned` : `/patient/${pid}`);
  return (
    <section className={`banner ${urgent ? "alert" : "calm"}`} aria-label="Alerts and actions" aria-live="polite">
      <div className="banner-text">
        <div className="b-title">{main ? T(main.title) : fc.available ? "No alerts" : "No forecast"}</div>
        <div className="b-detail">{main ? T(main.detail) : fc.available ? T(`Glucose ${Math.round(fc.status.glucose)} now; expected to stay between 70 and 180 for the next 2 hours.`) : fc.reason}</div>
        {main?.ack && <div className="ack">Seen by {main.ack.by} at {hhmm(main.ack.t!)}; quiet until {hhmm(main.ack.until_t!)}.{main.ack.note && ` "${main.ack.note}"`}</div>}
        {lastNudge && !lastReply && <div className="b-more">Message sent to {first}'s phone at {hhmm(lastNudge.t)}; no reply yet.</div>}
        {lastReply && <div className="b-reply">{first} replied at {hhmm(lastReply.t)}: {REPLY[lastReply.key] ?? lastReply.text}.</div>}
        {others.map(o => (
          <div key={o.kind} className="b-more">Also: <Link to={alsoLink(o)}>{T(o.title).toLowerCase()}</Link>{o.ack ? ` (seen by ${o.ack.by})` : ""}.</div>
        ))}
      </div>
      <div className="banner-actions">{actions}
        {(kind === "spike" || fc.status?.tier === "watch") && can("act") && !lastNudge &&
          <button className="link-small link-btn" onClick={nudge}>Message {first} a walk suggestion</button>}
        <Link className="link-small" to={`/phone/${pid}`}>{first}'s phone (demo)</Link></div>
      {panel === "seen" && <MarkSeen pid={pid} cards={open} done={() => setPanel(null)} />}
      {(panel === "call" || panel === "review" || panel === "check") && (
        <ActionPanel pid={pid} kind={panel} alert={kind} done={() => setPanel(null)} />
      )}
      {panel === "meal" && (
        <div className="banner-panel">
          <p className="muted">Tell the glucose forecast about a meal. A planned meal replaces the usual one; an eaten meal is added to the log.</p>
          <MealEntry pid={pid} entries={fc.entries} />
        </div>
      )}
    </section>
  );
}
