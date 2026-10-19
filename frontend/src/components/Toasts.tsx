import { useLive } from "../live";

/** Short confirmations at the bottom of the screen. Anything that changes the record offers Undo for 10 seconds. */
export function Toasts() {
  const { toasts, dismiss, refresh, toast } = useLive();
  if (!toasts.length) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.error ? "error" : ""}`}>
          <span>{t.text}</span>
          {t.undo && (
            <button className="link-btn" onClick={() => {
              dismiss(t.id);
              Promise.resolve(t.undo!()).then(() => { refresh(); toast({ text: "Undone." }); })
                .catch(e => toast({ text: `Could not undo: ${e.message ?? e}`, error: true }));
            }}>Undo</button>
          )}
          <button className="toast-x" aria-label="Dismiss" onClick={() => dismiss(t.id)}>Close</button>
        </div>
      ))}
    </div>
  );
}
