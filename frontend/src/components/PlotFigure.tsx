import * as Plot from "@observablehq/plot";
import { useEffect, useRef, useState } from "react";

/** Renders an Observable Plot spec at the container's width; the spec function receives that width. */
export function PlotFigure({ spec, height, ariaLabel }: { spec: (width: number) => Plot.PlotOptions; height?: number; ariaLabel: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(entries => setWidth(Math.floor(entries[0].contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    if (!ref.current || width < 50) return;
    const el = Plot.plot({ width, height, ...spec(width) });
    el.setAttribute("aria-label", ariaLabel);
    el.setAttribute("role", "img");
    // The figure is one labelled image with a table twin; Plot's labels on inner groups are not valid ARIA there.
    el.querySelectorAll("[aria-label]").forEach(n => { if (n !== el) n.removeAttribute("aria-label"); });
    ref.current.replaceChildren(el);
    return () => el.remove();
  });
  return <div className="plot" ref={ref} />;
}

export const baseStyle = (ink3: string) => ({
  background: "transparent",
  color: ink3,
  fontFamily: "IBM Plex Sans, sans-serif",
  fontSize: "11px",
  overflow: "visible",
  fontVariantNumeric: "tabular-nums",
});
