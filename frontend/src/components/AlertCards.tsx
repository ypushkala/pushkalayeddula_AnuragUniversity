import { useState } from "react";
import { api, hhmm, type AlertCard, type Driver } from "../api";
import { useLive } from "../live";
import { FactorBars } from "./FactorBars";

const SNOOZE: [number, string][] = [[30, "30 min"], [60, "1 h"], [120, "2 h"], [240, "4 h"]];

function AckControl({ pid, card }: { pid: string; card: AlertCard }) {
  const { clinician, refresh } = useLive();
  const [open, setOpen] = useState(false);
  const [snooze, setSnooze] = useState(60);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  if (!["spike", "low", "cardio"].includes(card.kind)) return null;
  if (card.ack) {
    return (
      <div className="ack">
        Seen by {card.ack.by} at {hhmm(card.ack.t!)}; quiet until {hhmm(card.ack.until_t!)}.
        {card.ack.note && <> &ldquo;{card.ack.note}&rdquo;</>}
      </div>
    );
  }
  if (!open) return <button className="btn small-btn" onClick={() => setOpen(true)}>Mark as seen</button>;
  const submit = () => {
    setBusy(true);
    api.ack(pid, { kind: card.kind, by: clinician, snooze_minutes: snooze, note }).then(() => { setOpen(false); refresh(); })
      .finally(() => setBusy(false));
  };
  return (
    <div className="ack-form">
      <label className="small">Quiet for
        <select value={snooze} onChange={e => setSnooze(+e.target.value)} aria-label="Snooze period">
          {SNOOZE.map(([m, l]) => <option key={m} value={m}>{l}</option>)}
        </select>
      </label>
      <input type="text" placeholder="Note (optional)" value={note} maxLength={280} onChange={e => setNote(e.target.value)}
        aria-label="Acknowledgement note" />
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn primary" disabled={busy} onClick={submit}>Mark as seen by {clinician}</button>
        <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

export function AlertCards({ pid, cards, drivers }: { pid: string; cards: AlertCard[] | undefined; drivers?: Driver[] }) {
  if (!cards) return <div className="skeleton-block" style={{ height: 96 }} aria-busy="true" />;
  return (
    <div aria-live="polite">
      {cards.length ? cards.map((a, i) => (
        <div key={`${a.kind}-${i}`} className={`card ${a.ack ? "acked" : a.tier}`}>
          <div className="t">{a.title}</div>
          <div className="d">{a.detail}</div>
          {(a.reason || (a.kind === "spike" && drivers)) && (
            <details className="why">
              <summary>Why?</summary>
              {a.reason && <p className="r">{a.reason}</p>}
              {a.kind === "spike" && drivers && (
                <>
                  <FactorBars drivers={drivers} />
                  <p className="small muted">mg/dL each factor adds to or takes off the expected peak.</p>
                </>
              )}
            </details>
          )}
          <AckControl pid={pid} card={a} />
        </div>
      )) : <div className="empty">No alerts. Glucose expected to stay between 70 and 180 for the next 2 hours.</div>}
    </div>
  );
}
