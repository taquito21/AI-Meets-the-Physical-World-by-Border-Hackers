// Developer page: renders an assembly at a fixed large size so demonstration images can be captured from the
// canvas (window.__captureRender()). Images produced here are 3D renders and must be labelled as such.
import { useEffect } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import AssemblyViewer from "../components/AssemblyViewer";
import { useAsync } from "../components/ui";

declare global {
  interface Window { __captureRender?: () => string | null }
}

export default function Render() {
  const { revisionId = "" } = useParams();
  const [q] = useSearchParams();
  const { data: rev } = useAsync(() => api.revision(revisionId), [revisionId]);
  const width = Number(q.get("w") ?? 1600);
  const height = Number(q.get("h") ?? 1200);
  const cam = (q.get("cam") ?? "0,0.45,3").split(",").map(Number) as [number, number, number];

  useEffect(() => {
    window.__captureRender = () => document.querySelector<HTMLCanvasElement>(".render-stage canvas")?.toDataURL("image/jpeg", 0.92) ?? null;
    return () => { delete window.__captureRender; };
  }, []);

  if (!rev || !rev.assembly_url) return null;
  return (
    <div className="render-stage" style={{ width, height }}>
      <AssemblyViewer className="render-viewer" assemblyUrl={rev.assembly_url} components={rev.components}
        selectedId={null} onSelect={() => undefined} explode={Number(q.get("explode") ?? 0)}
        articulation={Number(q.get("door") ?? 0)} focusId={q.get("focus")} focusKey={q.get("focus") ? 1 : 0}
        cameraPosition={cam} margin={Number(q.get("margin") ?? 1.7)} preserveDrawingBuffer />
    </div>
  );
}
