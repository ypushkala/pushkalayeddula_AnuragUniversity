import { useEffect, useState } from "react";
import { api, fmt, hhmm, minuteToDate, type MealEntryRec, type Session } from "../api";
import { useLive } from "../live";

const WHEN: [number, string][] = [[-60, "Eaten 1 h ago"], [-30, "Eaten 30 min ago"], [-15, "Eaten 15 min ago"], [0, "Eating now"],
  [30, "In 30 min"], [60, "In 1 h"], [90, "In 1 h 30 min"], [120, "In 2 h"], [180, "In 3 h"]];
const TYPICAL: Record<string, number> = { rice_meal: 90, roti_meal: 70, millet_meal: 60, idli_dosa: 55, poha_upma: 50,
  paratha: 55, biryani: 95, tea_snack: 20, iftar: 80, suhoor: 60, sabudana: 60, fruit: 25, sweets: 40, bread_tea: 45 };

/** Tell the glucose forecast about a meal: eaten ones join the log, planned ones replace the usual meal in the forecast. */
export function MealEntry({ pid, entries, as }: { pid: string; entries: MealEntryRec[] | undefined; as?: Session }) {
  const { refresh, toast } = useLive();
  const [types, setTypes] = useState<{ kind: string; label: string }[]>([]);
  const [when, setWhen] = useState(30);
  const [kind, setKind] = useState("rice_meal");
  const [carbs, setCarbs] = useState(90);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { api.mealTypes().then(setTypes).catch(() => {}); }, []);
  const label = types.find(t => t.kind === kind)?.label ?? kind;
  const submit = () => {
    setBusy(true);
    api.addMeal(pid, { minutes_from_now: when, carbs, kind, label }, as)
      .then(r => {
        const text = `${r.type === "planned" ? "Planned" : "Logged"} ${label.toLowerCase()} for ${hhmm(minuteToDate(r.minute))}. Forecast updated.`;
        setMsg(text); refresh();
        toast({ text, undo: () => api.removeMeal(pid, r.id, as) });
      })
      .catch(() => setMsg("Could not save the meal."))
      .finally(() => setBusy(false));
  };
  const remove = (e: MealEntryRec) => api.removeMeal(pid, e.id, as).then(refresh);
  return (
    <div className="meal-form">
      <div className="row2">
        <label className="small">When
          <select value={when} onChange={e => setWhen(+e.target.value)}>{WHEN.map(([m, l]) => <option key={m} value={m}>{l}</option>)}</select>
        </label>
        <label className="small">Carbohydrate, g
          <input type="number" min={5} max={250} step={5} value={carbs} onChange={e => setCarbs(+e.target.value)} />
        </label>
      </div>
      <label className="small">Food
        <select value={kind} onChange={e => { setKind(e.target.value); setCarbs(TYPICAL[e.target.value] ?? carbs); }}>
          {types.map(t => <option key={t.kind} value={t.kind}>{t.label}</option>)}
        </select>
      </label>
      <button className="btn primary" disabled={busy || carbs <= 0} onClick={submit}>Add meal</button>
      {msg && <div className="small muted" role="status">{msg}</div>}
      {entries && entries.length > 0 && (
        <table className="log num" style={{ marginTop: 8 }}>
          <tbody>
            {entries.map(e => (
              <tr key={e.id}>
                <td>{hhmm(e.t)}</td>
                <td>{e.label}, {fmt(e.carbs)} g <span className="muted">({e.type === "planned" ? "planned" : "eaten"}, {e.source === "patient" ? `logged by ${e.by}, the patient` : e.by})</span></td>
                <td style={{ width: 60, textAlign: "right" }}><button className="link-btn" onClick={() => remove(e)} aria-label={`Remove ${e.label}`}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
