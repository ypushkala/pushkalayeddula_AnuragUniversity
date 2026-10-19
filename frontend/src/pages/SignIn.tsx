import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ROLE_NAMES, type Role } from "../api";
import { useLive, useLiveData } from "../live";

const SUGGEST: Record<Role, string> = { doctor: "Dr Rao", nurse: "Nurse Thomas", patient: "" };
const CAN: Record<Role, string> = {
  doctor: "Everything: mark any alert as seen, call and review, agree plans with patients, change consent on a patient's behalf.",
  nurse: "Mark glucose alerts as seen, call and check patients, log meals. Heart risk alerts and plans go to a doctor.",
  patient: "Your own page: what could help tonight, log a meal, choose what you share.",
};

/** Demo sign in. There are no passwords: a deployment would use the clinic's single sign on and keep these same roles. */
export function SignIn() {
  const { signIn } = useLive();
  const nav = useNavigate();
  const [q] = useSearchParams();
  const [role, setRole] = useState<Role>("doctor");
  const [name, setName] = useState(SUGGEST.doctor);
  const [pid, setPid] = useState("PTV-0001");
  const ward = useLiveData(() => api.ward(), []).data;
  const heroes = (ward?.patients ?? []).filter(p => p.hero);
  const go = () => {
    if (role === "patient") {
      const p = ward?.patients.find(x => x.id === pid);
      signIn({ role, name: p ? p.name.split(" ")[0] : "Patient", pid });
      nav(`/share/${pid}`);
    } else {
      signIn({ role, name: name.trim() || SUGGEST[role] });
      nav(q.get("next") || "/");
    }
  };
  return (
    <main className="signin" id="main">
      <h1>Prativimb</h1>
      <p className="muted">Remote monitoring for diabetes and heart risk. Synthetic patients only.</p>
      <fieldset className="roles">
        <legend>Sign in as</legend>
        {(Object.keys(ROLE_NAMES) as Role[]).map(r => (
          <label key={r} className={`role ${role === r ? "on" : ""}`}>
            <input type="radio" name="role" checked={role === r} onChange={() => { setRole(r); setName(SUGGEST[r]); }} />
            <span className="r-name">{ROLE_NAMES[r]}</span>
            <span className="small muted">{CAN[r]}</span>
          </label>
        ))}
      </fieldset>
      {role === "patient" ? (
        <label className="field">Which patient
          <select value={pid} onChange={e => setPid(e.target.value)}>
            {(heroes.length ? heroes : [{ id: "PTV-0001", name: "Ramesh Patil" }]).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      ) : (
        <label className="field">Your name, shown on what you do
          <input type="text" value={name} maxLength={40} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === "Enter" && go()} />
        </label>
      )}
      <button className="btn primary big-btn" onClick={go}>Continue</button>
      <p className="small muted">Demo sign in without a password. A real deployment would use the clinic's single sign on; the roles and what each may do stay the same, and the service checks them on every change.</p>
    </main>
  );
}
