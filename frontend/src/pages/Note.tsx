import { useParams } from "react-router-dom";
import { api, fullTime } from "../api";
import { useLiveData } from "../live";

export function Note() {
  const { id = "" } = useParams();
  const { data: n } = useLiveData(() => api.note(id), [id]);
  if (!n) return <p className="empty">Preparing note.</p>;
  const sections: [keyof typeof n & ("S" | "O" | "A" | "P"), string][] = [
    ["S", "Subjective"], ["O", "Objective"], ["A", "Assessment (twin findings)"], ["P", "Plan considerations"],
  ];
  return (
    <>
      <div className="no-print" style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginBottom: 10 }}>
        <button className="btn" onClick={() => window.print()}>Print</button>
        <a className="btn primary" href={`/api/patients/${id}/note.pdf`} target="_blank" rel="noreferrer">Download PDF</a>
      </div>
      <article className="note">
        <h1 style={{ fontSize: 22 }}>{n.patient.name}, {n.patient.age} {n.patient.gender === "male" ? "M" : "F"}</h1>
        <div className="small muted" style={{ marginTop: 4 }}>
          <span className="mono">{n.patient.id}</span> &middot; {n.problems.join(", ")} &middot; Twin summary, {fullTime(n.generated)} IST
        </div>
        <div className="small ink2" style={{ marginTop: 4 }}>Medications: {n.medications.join("; ")}</div>
        {sections.map(([k, title]) => (
          <section key={k}>
            <h2>{title}</h2>
            <ul>{n[k].map((line, i) => <li key={i}>{line}</li>)}</ul>
          </section>
        ))}
        <p className="disclaimer">{n.disclaimer}</p>
      </article>
    </>
  );
}
