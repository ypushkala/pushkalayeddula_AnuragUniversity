import { useState } from "react";
import { api, type Parsed, type WhatIfReq } from "../api";

const EXAMPLES = ["What if he skips rice and walks after dinner for the next week?", "Half the portion and a 30 minute walk",
  "Dinner an hour earlier", "Millets instead of rice tomorrow"];

/** Ask in plain words; the question becomes the simulator's settings, shown for checking before anything runs. */
export function AskTwin({ first, onApply }: { first: string; onApply: (req: Partial<WhatIfReq>) => void }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Parsed | null>(null);
  const [busy, setBusy] = useState(false);
  const ask = (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    api.ask(text).then(r => { setRes(r); if (r.understood.length) onApply(r.request); }).finally(() => setBusy(false));
  };
  return (
    <section className="ask" aria-label="Ask in plain words">
      <form className="ask-row" onSubmit={e => { e.preventDefault(); ask(q); }}>
        <label htmlFor="ask" className="visually-hidden">Ask in plain words</label>
        <input id="ask" type="text" value={q} maxLength={400} placeholder={`Ask in plain words, for example: what if ${first} walks after dinner this week?`}
          onChange={e => setQ(e.target.value)} />
        <button className="btn primary" disabled={busy || !q.trim()}>Ask</button>
      </form>
      {!res && (
        <div className="ask-examples small">
          <span className="muted">Try:</span>
          {EXAMPLES.map(x => <button key={x} type="button" className="chip" onClick={() => { setQ(x); ask(x); }}>{x}</button>)}
        </div>
      )}
      {res && (
        <div className="ask-result small" role="status">
          {res.understood.length ? <>
            <span className="muted">Understood as:</span> {res.understood.map(u => <span key={u} className="chip static">{u}</span>)}
            <span className="muted"> for {res.request.horizon_h === 168 ? "the next 7 days" : res.request.horizon_h === 24 ? "the next 24 hours" : "tonight"}.</span>
          </> : <span>{res.unclear}</span>}
          <div className="muted">Read by: {res.parser}. The numbers below come from the forecast, not from the reader. Check the settings under Build your own change.</div>
        </div>
      )}
    </section>
  );
}
