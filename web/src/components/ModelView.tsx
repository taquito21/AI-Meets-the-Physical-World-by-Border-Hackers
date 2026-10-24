import { useMemo, useState } from "react";
import type { MediaItem, TaskStatus } from "../api";
import AssemblyViewer from "./AssemblyViewer";
import { TechSheet } from "./TechSheet";
import { useAssemblyControls } from "./useAssemblyControls";

// A 3D model with the parts a task is about tinted by the task's status. Tap a part for its technical sheet.
export function ModelView({ model, highlight = [], status = "pending" }:
  { model: MediaItem; highlight?: string[]; status?: TaskStatus }) {
  const parts = model.metadata.parts ?? [];
  const [selected, setSelected] = useState<string | null>(highlight.length === 1 ? highlight[0] : null);
  const tint = useMemo(() => Object.fromEntries(highlight.map((id) => [id, status])), [highlight, status]);
  const { viewerProps, controls } = useAssemblyControls(parts, selected);
  const part = parts.find((p) => p.id === selected);
  if (!model.url) return <div className="viewer-fallback">Model file unavailable.</div>;
  return (
    <div className="model-view">
      <AssemblyViewer assemblyUrl={model.url} components={parts} status={tint} selectedId={selected}
        onSelect={setSelected} {...viewerProps} />
      {controls}
      {highlight.length > 0 && (
        <div className="tiny muted pad">
          This task is about: {highlight.map((id) => parts.find((p) => p.id === id)?.name ?? id).join(", ")}
        </div>
      )}
      {part && <div className="pad"><TechSheet comp={part} /></div>}
    </div>
  );
}
