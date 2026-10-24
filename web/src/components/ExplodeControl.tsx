import { DoorClosed, DoorOpen, Expand, RotateCcw, Shrink, ZoomIn } from "lucide-react";
import { t } from "../i18n";
import { STATUS_COLORS } from "./AssemblyViewer";

interface Props {
  value: number;
  onChange: (v: number) => void;
  articulationLabel?: string | null; // e.g. "Door" when the asset has a hinged part
  articulation?: number;
  onArticulation?: (v: number) => void;
  onFocus?: () => void; // frame the selected part (or the whole assembly)
  partSelected?: boolean; // "Zoom to part" instead of "Reset view"
}

export function ExplodeControl({ value, onChange, articulationLabel, articulation = 0, onArticulation, onFocus, partSelected }: Props) {
  // The hinge label comes from the package untranslated (e.g. "Door"), so it goes through the dictionary too.
  const part = articulationLabel ? t(articulationLabel).toLowerCase() : "";
  return (
    <div className="explode">
      {articulationLabel && onArticulation && (
        <button className="btn btn-small" onClick={() => onArticulation(articulation > 0.5 ? 0 : 1)}>
          {articulation > 0.5 ? <><DoorClosed aria-hidden />{t("Close {part}", { part })}</> : <><DoorOpen aria-hidden />{t("Open {part}", { part })}</>}
        </button>
      )}
      <button className="btn btn-small" onClick={() => onChange(value > 0.5 ? 0 : 1)}>
        {value > 0.5 ? <><Shrink aria-hidden />{t("Put back together")}</> : <><Expand aria-hidden />{t("Separate parts")}</>}
      </button>
      <input type="range" min={0} max={1} step={0.01} value={value} aria-label={t("How far apart the parts are")}
        onChange={(e) => onChange(parseFloat(e.target.value))} />
      {onFocus && (
        <button className="btn btn-small btn-ghost" onClick={onFocus}>
          {partSelected ? <><ZoomIn aria-hidden />{t("Zoom to part")}</> : <><RotateCcw aria-hidden />{t("Reset view")}</>}
        </button>
      )}
    </div>
  );
}

export function StatusLegend() {
  // English keys; translated when shown.
  const entries: [string, string][] = [
    ["Not checked yet", STATUS_COLORS.not_inspected],
    ["Selected", STATUS_COLORS.selected],
    ["In progress", STATUS_COLORS.pending],
    ["Done", STATUS_COLORS.accepted],
    ["Problem", STATUS_COLORS.finding],
  ];
  return (
    <div className="legend">
      {entries.map(([l, c]) => (
        <span key={l}><i style={{ background: c }} />{t(l)}</span>
      ))}
    </div>
  );
}
