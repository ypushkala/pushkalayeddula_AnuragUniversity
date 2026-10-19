import { api, dayMonth, hhmm, minuteToDate, T } from "../api";
import { useLiveData } from "../live";

const VERB: Record<string, string> = {
  alert_acknowledged: "marked an alert as seen", acknowledgement_undone: "undid marking an alert as seen",
  meal_added: "added a meal", meal_removed: "removed a meal", action_call: "called the patient",
  action_review: "booked a review", action_check: "checked the patient", action_undone: "undid an action",
  plan_agreed: "agreed a plan", plan_removed: "removed a plan", consent_granted: "granted sharing", consent_withdrawn: "withdrew sharing",
};
const KINDS: Record<string, string> = { spike: "high glucose", low: "low glucose", cardio: "heart risk" };

/** Everything people did for this patient, newest first, from the audit log. */
export function Activity({ pid }: { pid: string }) {
  const { data } = useLiveData(() => api.audit(pid), [pid]);
  if (!data) return <p className="empty">Loading.</p>;
  if (!data.length) return <div className="empty">No actions recorded for this patient.</div>;
  return (
    <table className="log num">
      <tbody>
        {data.slice(0, 15).map((r: any, i) => (
          <tr key={i}>
            <td style={{ width: 110 }}>{r.minute !== undefined ? `${dayMonth(minuteToDate(r.minute))} ${hhmm(minuteToDate(r.minute))}` : ""}</td>
            <td>
              {r.removed_by ?? r.by} {VERB[r.action] ?? r.action.replace(/_/g, " ")}
              {r.action === "alert_acknowledged" && <> ({KINDS[r.kind] ?? r.kind}){r.note ? `: ${r.note}` : ""}</>}
              {r.action.startsWith("meal") && <>: {r.label}, {r.carbs} g{r.source === "patient" ? " (the patient)" : ""}</>}
              {r.action.startsWith("action_") && r.action !== "action_undone" && (r.outcome || r.note) && <>: {T([r.outcome, r.note].filter(Boolean).join(". "))}</>}
              {r.action.startsWith("plan") && <>: {r.label}</>}
              {r.action.startsWith("consent") && <>: {r.source}</>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
