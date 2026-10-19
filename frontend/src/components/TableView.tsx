import { useState, type ReactNode } from "react";

/** Every chart has a table twin: values stay reachable without reading the graphic. */
export function TableView({ title, columns, rows, children }: {
  title: string; columns: string[]; rows: (string | number)[][]; children: ReactNode;
}) {
  const [table, setTable] = useState(false);
  return (
    <div>
      {table ? (
        <div className="table-scroll" tabIndex={0} role="region" aria-label={`${title}, table`}>
          <table className="data-table num">
            <caption className="sr-only">{title}</caption>
            <thead><tr>{columns.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : children}
      <button className="link-btn small" onClick={() => setTable(t => !t)} aria-pressed={table}>
        {table ? "Show as chart" : "Show as table"}
      </button>
    </div>
  );
}
