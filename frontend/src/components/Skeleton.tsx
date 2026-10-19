/** Placeholders that hold the final layout, so nothing jumps when data arrives. */
export function SkeletonRows({ rows = 12, cols = 9 }: { rows?: number; cols?: number }) {
  return (
    <tbody aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i}>{Array.from({ length: cols }).map((__, j) => <td key={j}><span className="skeleton-line" style={{ width: `${40 + ((i * 7 + j * 13) % 50)}%` }} /></td>)}</tr>
      ))}
    </tbody>
  );
}

export function SkeletonBlock({ height, label }: { height: number; label: string }) {
  return <div className="skeleton-block" style={{ height }} role="status" aria-label={label} />;
}
