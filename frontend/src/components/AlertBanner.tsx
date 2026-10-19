import { useState } from "react";
import { Link } from "react-router-dom";
import { api, hhmm, type AlertCard } from "../api";
import { useLive, useLiveData } from "../live";
import { MealEntry } from "./MealEntry";

const SNOOZE: [number, string][] = [[30, "30 min"], [60, "1 hour"], [120, "2 hours"], [240, "4 hours"]];
const ACKABLE = ["spike", "low", "cardio"];

function MarkSeen({ pid, cards, done }: { pid: string; cards: AlertCard[]; done: () => void }) {
  const { clinician, refresh } = useLive();
  const [snooze, setSnooze] = useState(60);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = () => {
    setBusy(true);
    Promise.all(cards.map(c => api.ack(pid, { kind: c.kind, by: clinician, snooze_minutes: snooze, note })))
      .then(() => { refresh(); done(); }).finally(() => setBusy(false));
  };
  return (
    <div className="banner-panel">
      <label>Keep quiet for{" "}
        <select value={snooze} onChange={e => setSnooze(+e.target.value)}>{SNOOZE.map(([m, l]) => <option key={m} value={m}>{l}</option>)}</select>
      </label>
      <input type="text" placeholder="Note, optional (for example: discussed a walk after dinner)" value={note} maxLength={280}
        onChange={e => setNote(e.target.value)} aria-label="Note" />
      <div className="row-actions">
        <button className="btn primary" disabled={busy} onClick={submit}>Mark as seen by {clinician}</button>
        <button className="btn" onClick={done}>Cancel</button>
      </div>
    </div>
  );
}

/** The patient's most important alert with everything you can do about it, visible on every tab. */
export function AlertBanner({ pid, first }: { pid: string; first: string }) {
  const fc = useLiveData(() => api.forecast(pid), [pid]).data;
  const [panel, setPanel] = useState<"seen" | "meal" | null>(null);
  if (!fc) return <div className="banner calm skeleton-block" style={{ height: 96 }} aria-busy="true" />;
  const cards = fc.alerts ?? [];
  const open = cards.filter(c => ACKABLE.includes(c.kind) && !c.ack);
  const main = open.find(c => c.tier === "alert") ?? open[0] ?? cards.find(c => c.tier !== "info") ?? cards[0];
  const others = cards.filter(c => c !== main && c.kind !== "event");
  const urgent = main && main.tier === "alert" && !main.ack;
  const toggle = (p: "seen" | "meal") => setPanel(x => (x === p ? null : p));
  return (
    <section className={`banner ${urgent ? "alert" : "calm"}`} aria-label="Alerts and actions" aria-live="polite">
      <div className="banner-text">
        <div className="b-title">{main ? main.title : "No alerts"}</div>
        <div className="b-detail">{main ? main.detail : `Glucose is expected to stay between 70 and 180 for the next 2 hours.`}</div>
        {main?.ack && <div className="ack">Seen by {main.ack.by} at {hhmm(main.ack.t!)}; quiet until {hhmm(main.ack.until_t!)}.</div>}
        {others.map(o => <div key={o.kind} className="b-more">Also: {o.title.toLowerCase()}{o.ack ? ` (seen by ${o.ack.by})` : ""}.</div>)}
        {main?.kind !== "event" && cards.some(c => c.kind === "event") && <div className="b-more">{cards.find(c => c.kind === "event")!.detail}</div>}
      </div>
      <div className="banner-actions">
        {open.length > 0 && <button className="btn" aria-expanded={panel === "seen"} onClick={() => toggle("seen")}>Mark as seen</button>}
        <Link className="btn primary" to={`/patient/${pid}/try`}>Try a change</Link>
        <button className="btn" aria-expanded={panel === "meal"} onClick={() => toggle("meal")}>Log a meal</button>
        <Link className="btn" to={`/share/${pid}`}>Share with {first}</Link>
      </div>
      {panel === "seen" && <MarkSeen pid={pid} cards={open} done={() => setPanel(null)} />}
      {panel === "meal" && (
        <div className="banner-panel">
          <p className="muted">Tell the glucose forecast about a meal. A planned meal replaces the usual one; an eaten meal is added to the log.</p>
          <MealEntry pid={pid} entries={fc.entries} />
        </div>
      )}
    </section>
  );
}
