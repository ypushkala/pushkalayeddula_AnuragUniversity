import type { ReactNode } from "react";

/** A section that starts closed (or open) and expands in place. Native details element, so it works with keyboard and screen readers. */
export function Disclosure({ title, hint, open = false, children }: { title: string; hint?: string; open?: boolean; children: ReactNode }) {
  return (
    <details className="disclosure" open={open}>
      <summary><span className="d-title">{title}</span>{hint && <span className="d-hint">{hint}</span>}</summary>
      <div className="d-body">{children}</div>
    </details>
  );
}

/** A small dropdown menu for secondary controls. */
export function Menu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="menu">
      <summary className="btn">{label}</summary>
      <div className="menu-panel">{children}</div>
    </details>
  );
}
