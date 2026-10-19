import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useLiveData } from "../live";

/** Find any patient from anywhere. "/" or Ctrl+K focuses it; arrows choose; Enter opens. */
export function GlobalSearch() {
  const { data } = useLiveData(() => api.ward(), []);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n || !data) return [];
    return data.patients.filter(p => `${p.name} ${p.id}`.toLowerCase().includes(n)).slice(0, 8);
  }, [q, data]);
  useEffect(() => setPick(0), [q]);

  const go = (id: string) => { setQ(""); setOpen(false); input.current?.blur(); nav(`/patient/${id}`); };
  return (
    <div className="gsearch" role="search">
      <input ref={input} type="search" value={q} placeholder="Find a patient  ( / )" aria-label="Find a patient by name or ID"
        aria-expanded={open && results.length > 0} aria-controls="gsearch-list" role="combobox" aria-autocomplete="list"
        aria-activedescendant={results[pick] ? `gs-${results[pick].id}` : undefined}
        onChange={e => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={e => {
          if (e.key === "ArrowDown") { e.preventDefault(); setPick(p => Math.min(p + 1, results.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setPick(p => Math.max(p - 1, 0)); }
          else if (e.key === "Enter" && results[pick]) go(results[pick].id);
          else if (e.key === "Escape") { setQ(""); input.current?.blur(); }
        }} />
      {open && results.length > 0 && (
        <ul id="gsearch-list" role="listbox" className="gsearch-list">
          {results.map((p, i) => (
            <li key={p.id} id={`gs-${p.id}`} role="option" aria-selected={i === pick} className={i === pick ? "on" : ""}
              onMouseDown={e => { e.preventDefault(); go(p.id); }} onMouseEnter={() => setPick(i)}>
              <span>{p.name}</span><span className="muted">{p.age} {p.sex}, {p.id}</span>
            </li>
          ))}
        </ul>
      )}
      {open && q.trim() && data && !results.length && <div className="gsearch-list empty-row">No patient matches.</div>}
    </div>
  );
}
