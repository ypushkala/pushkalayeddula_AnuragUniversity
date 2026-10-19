import { api, hhmm, minuteToDate } from "../api";
import { useLiveData } from "../live";

const VERB: Record<string, string> = { alert_acknowledged: "acknowledged", meal_added: "added a meal", meal_removed: "removed a meal" };

export function Activity({ pid }: { pid: string }) {
  const { data } = useLiveData(() => api.audit(pid), [pid]);
  if (!data) return null;
  if (!data.length) return <div className="empty">No actions recorded for this patient.</div>;
  return (
    <table className="log num">
      <tbody>
        {data.slice(0, 12).map((r, i) => (
          <tr key={i}>
            <td>{r.minute !== undefined ? hhmm(minuteToDate(r.minute)) : ""}</td>
            <td>
              {r.action === "meal_removed" ? r.removed_by : r.by} {VERB[r.action] ?? r.action}
              {r.action === "alert_acknowledged" && <> the {r.kind} alert{r.note ? `: ${r.note}` : ""}</>}
              {r.action.startsWith("meal") && <>: {r.label}, {r.carbs} g</>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
