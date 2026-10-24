import { STATUS_COLORS } from "./AssemblyViewer";

interface Props {
  value: number;
  onChange: (v: number) => void;
  articulationLabel?: string | null; // e.g. "Door" when the asset has a hinged part
  articulation?: number;
  onArticulation?: (v: number) => void;
  onFocus?: () => void; // frame the selected part (or the whole assembly)
  focusLabel?: string;
}

export function ExplodeControl({ value, onChange, articulationLabel, articulation = 0, onArticulation, onFocus, focusLabel }: Props) {
  return (
    <div className="explode">
      {articulationLabel && onArticulation && (
        <button className="btn btn-small" onClick={() => onArticulation(articulation > 0.5 ? 0 : 1)}>
          {articulation > 0.5 ? `Close ${articulationLabel.toLowerCase()}` : `Open ${articulationLabel.toLowerCase()}`}
        </button>
      )}
      <button className="btn btn-small" onClick={() => onChange(value > 0.5 ? 0 : 1)}>
        {value > 0.5 ? "Assemble" : "Explode"}
      </button>
      <input type="range" min={0} max={1} step={0.01} value={value} aria-label="Explosion"
        onChange={(e) => onChange(parseFloat(e.target.value))} />
      {onFocus && <button className="btn btn-small btn-ghost" onClick={onFocus}>{focusLabel ?? "Fit"}</button>}
    </div>
  );
}

export function StatusLegend() {
  const entries: [string, string][] = [
    ["Pending", STATUS_COLORS.not_inspected],
    ["Selected", STATUS_COLORS.selected],
    ["In progress / requires review", STATUS_COLORS.pending],
    ["Inspected", STATUS_COLORS.accepted],
    ["Finding reported", STATUS_COLORS.finding],
  ];
  return (
    <div className="legend">
      {entries.map(([l, c]) => (
        <span key={l}><i style={{ background: c }} />{l}</span>
      ))}
    </div>
  );
}
