interface Props { values: (number | null)[]; width?: number; height?: number }

const LO = 40, HI = 340;

export function Sparkline({ values, width = 132, height = 30 }: Props) {
  const n = values.length;
  if (!n) return null;
  const x = (i: number) => (i / Math.max(n - 1, 1)) * (width - 4) + 2;
  const y = (v: number) => height - 2 - ((Math.min(Math.max(v, LO), HI) - LO) / (HI - LO)) * (height - 4);
  const segs: string[] = [];
  let cur = "";
  values.forEach((v, i) => {
    if (v === null) { if (cur) segs.push(cur); cur = ""; return; }
    cur += `${cur ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  if (cur) segs.push(cur);
  let last = -1;
  for (let i = n - 1; i >= 0; i--) if (values[i] !== null) { last = i; break; }
  return (
    <svg width={width} height={height} role="img" aria-label="Glucose, last 24 hours" style={{ display: "block" }}>
      <rect x={0} y={y(180)} width={width} height={y(70) - y(180)} fill="var(--band)" />
      {segs.map((d, i) => <path key={i} d={d} fill="none" stroke="var(--ink-2)" strokeWidth={1.2} strokeLinejoin="round" />)}
      {last >= 0 && <circle cx={x(last)} cy={y(values[last] as number)} r={2.4} fill="var(--ink)" />}
    </svg>
  );
}
