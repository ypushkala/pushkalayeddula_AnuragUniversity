import type { ReactNode } from "react";
import { useLive } from "../live";

/** A one line explanation shown the first few times, until someone clicks Got it. Settings can show them again. */
export function Hint({ id, children }: { id: string; children: ReactNode }) {
  const { hintSeen, seeHint } = useLive();
  if (hintSeen(id)) return null;
  return (
    <p className="hint">
      <span className="hint-tag">Tip</span><span>{children}</span>
      <button className="link-btn" onClick={() => seeHint(id)}>Got it</button>
    </p>
  );
}
