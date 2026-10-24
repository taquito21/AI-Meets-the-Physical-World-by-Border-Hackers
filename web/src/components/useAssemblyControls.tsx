import { useState } from "react";
import type { Component } from "../api";
import { ExplodeControl } from "./ExplodeControl";

// Shared viewer state for every page that shows an assembly: explode, articulation (door) and framing.
export function useAssemblyControls(components: Component[] | undefined, selectedId: string | null) {
  const [explode, setExplode] = useState(0);
  const [articulation, setArticulation] = useState(0);
  const [focus, setFocus] = useState<{ id: string | null; key: number }>({ id: null, key: 0 });
  const articulated = components?.find((c) => c.articulation);
  const fit = () => setFocus((f) => ({ id: selectedId, key: f.key + 1 }));

  const viewerProps = { explode, articulation, focusId: focus.id, focusKey: focus.key };
  const controls = (
    <ExplodeControl value={explode} onChange={setExplode}
      articulationLabel={articulated ? articulated.articulation?.label ?? articulated.name : null}
      articulation={articulation} onArticulation={setArticulation}
      onFocus={fit} partSelected={!!selectedId} />
  );
  return { viewerProps, controls, setArticulation };
}
