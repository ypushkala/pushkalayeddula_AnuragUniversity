import { Link, useParams } from "react-router-dom";
import { api, fullTime } from "../api";
import { useLiveData } from "../live";

export function Note() {
  const { id = "" } = useParams();
  const { data: n } = useLiveData(() => api.note(id), [id]);
  if (!n) return <main className="sheet"><p className="empty">Preparing the clinical note.</p></main>;
  const sections: [keyof typeof n & ("S" | "O" | "A" | "P"), string][] = [
    ["S", "Subjective"], ["O", "Objective"], ["A", "Assessment (glucose forecast and heart risk)"], ["P", "Plan considerations"],
  ];
  return (
    <main className="sheet" id="main">
      <div className="sheet-tools no-print">
        <Link to={`/patient/${id}`}>Back to {n.patient.name}</Link>
        <button className="btn" onClick={() => window.print()}>Print</button>
        <a className="btn primary" href={`/api/patients/${id}/note.pdf`} target="_blank" rel="noreferrer">Download PDF</a>
      </div>
      <article className="note">
        <h1 style={{ fontSize: 22 }}>{n.patient.name}, {n.patient.age} {n.patient.gender === "male" ? "M" : "F"}</h1>
        <div className="small muted" style={{ marginTop: 4 }}>
          <span className="mono">{n.patient.id}</span> &middot; {n.problems.join(", ")} &middot; Summary, {fullTime(n.generated)} IST
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
    </main>
  );
}
