// Reusable, product-agnostic 3D assembly viewer.
// Geometry comes from the model's GLB; part identity, explosion vectors and articulations (e.g. a hinged door)
// come from the model's parts list, keyed by stable part ids. Parts a task is about are tinted by its status.
import { Component as ReactComponent, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { Rotate3d } from "lucide-react";
import { Bounds, ContactShadows, Html, OrbitControls, useBounds, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { Part, TaskStatus } from "../api";
import { t } from "../i18n";

type Component = Part;
export type PartStatus = TaskStatus;

export const STATUS_COLORS: Record<PartStatus | "selected", string> = {
  pending: "#f59e0b",
  passed: "#16a34a",
  failed: "#dc2626",
  flagged: "#7c3aed",
  selected: "#2563eb",
};

interface ViewerProps {
  assemblyUrl: string;
  components: Component[];
  status?: Record<string, PartStatus>; // part id -> status tint (parts without an entry keep their colors)
  selectedId: string | null;
  onSelect: (componentId: string | null) => void;
  explode: number; // 0 = assembled, 1 = fully exploded (target; animated)
  articulation?: number; // 0 = closed, 1 = open (applies to components with an articulation)
  focusId?: string | null; // component to frame; null = whole assembly
  focusKey?: number; // bump to re-run framing
  cameraPosition?: [number, number, number];
  preserveDrawingBuffer?: boolean; // needed only to capture images from the canvas
  className?: string;
  margin?: number; // framing margin around the fitted assembly or part
  fallback?: ReactNode;
}

interface NodeEntry {
  mesh: THREE.Mesh;
  componentId: string;
  base: THREE.Vector3;
  baseQuat: THREE.Quaternion;
  offset: THREE.Vector3; // full-explosion offset in parent space
  hinge: { pivot: THREE.Vector3; axis: THREE.Vector3; angle: number } | null;
  baseColor: THREE.Color;
  material: THREE.MeshStandardMaterial;
}

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function Assembly({ assemblyUrl, components, status, selectedId, onSelect, explode, articulation = 0,
  focusId = null, focusKey = 0 }: ViewerProps) {
  const gltf = useGLTF(assemblyUrl);
  const scene = useMemo(() => gltf.scene.clone(true), [gltf]);
  const t = useRef(explode);
  const a = useRef(articulation);
  const bounds = useBounds();

  const nodes = useMemo(() => {
    const byNode = new Map<string, Component>();
    components.forEach((c) => c.model_node_ids.forEach((n) => byNode.set(n, c)));
    const entries: NodeEntry[] = [];
    scene.traverse((obj) => {
      const comp = byNode.get(obj.name);
      if (!comp || !(obj as THREE.Mesh).isMesh) return;
      const mesh = obj as THREE.Mesh;
      const material = (mesh.material as THREE.MeshStandardMaterial).clone();
      mesh.material = material;
      mesh.castShadow = true;
      const exp = comp.explosion ?? { direction: [0, 1, 0] as [number, number, number], distance: 0 };
      const dir = new THREE.Vector3(...exp.direction).normalize();
      const art = comp.articulation;
      entries.push({
        mesh, componentId: comp.id, base: mesh.position.clone(), baseQuat: mesh.quaternion.clone(),
        offset: dir.multiplyScalar(exp.distance),
        hinge: art ? { pivot: new THREE.Vector3(...art.pivot), axis: new THREE.Vector3(...art.axis).normalize(),
          angle: THREE.MathUtils.degToRad(art.angle_deg) } : null,
        baseColor: material.color.clone(), material,
      });
    });
    return entries;
  }, [scene, components]);

  // Release cloned materials and the pointer cursor when the viewer goes away.
  useEffect(() => () => {
    nodes.forEach((n) => n.material.dispose());
    document.body.style.cursor = "";
  }, [nodes]);

  // Frame one component (or the whole assembly) on request.
  useEffect(() => {
    if (!focusKey) return;
    const sel = focusId ? nodes.filter((n) => n.componentId === focusId) : [];
    if (sel.length) {
      const box = new THREE.Box3();
      sel.forEach((n) => box.expandByObject(n.mesh));
      bounds.refresh(box).clip().fit();
    } else {
      bounds.refresh().clip().fit();
    }
  }, [focusKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Status / selection tint. Colors reflect persisted backend state passed in via props.
  useEffect(() => {
    const tmp = new THREE.Color();
    for (const n of nodes) {
      const st = status?.[n.componentId];
      const selected = n.componentId === selectedId;
      n.material.color.copy(n.baseColor);
      n.material.emissive.set("#000000");
      n.material.emissiveIntensity = 1;
      if (st) {
        tmp.set(STATUS_COLORS[st]);
        n.material.color.lerp(tmp, 0.65);
        n.material.emissive.copy(tmp).multiplyScalar(0.18);
      }
      if (selected) {
        // The selected part is always clearly coloured; the rest of the assembly fades back.
        n.material.color.lerp(tmp.set(STATUS_COLORS.selected), 0.55);
        n.material.emissive.set(STATUS_COLORS.selected).multiplyScalar(0.45);
      }
      const faded = !!selectedId && !selected;
      n.material.transparent = faded;
      n.material.opacity = faded ? 0.4 : 1;
      n.material.depthWrite = !faded; // faded parts never hide the selected one
      n.material.needsUpdate = true;
    }
  }, [nodes, status, selectedId]);

  // Smooth interpolation of articulation (hinge rotation about its pivot) and explosion offsets.
  // Stored engineering data is untouched; only the rendered transforms change.
  const q = useMemo(() => new THREE.Quaternion(), []);
  const rel = useMemo(() => new THREE.Vector3(), []);
  useFrame((_, dt) => {
    const k = 1 - Math.exp(-dt * 8);
    t.current += (explode - t.current) * k;
    a.current += (articulation - a.current) * k;
    if (Math.abs(explode - t.current) < 1e-4) t.current = explode;
    if (Math.abs(articulation - a.current) < 1e-4) a.current = articulation;
    for (const n of nodes) {
      if (n.hinge) {
        q.setFromAxisAngle(n.hinge.axis, n.hinge.angle * a.current);
        rel.copy(n.base).sub(n.hinge.pivot).applyQuaternion(q);
        n.mesh.position.copy(n.hinge.pivot).add(rel);
        n.mesh.quaternion.copy(q).multiply(n.baseQuat);
      } else {
        n.mesh.position.copy(n.base);
      }
      n.mesh.position.addScaledVector(n.offset, t.current);
    }
  });

  const labelPos = useMemo(() => {
    if (!selectedId) return null;
    const sel = nodes.filter((n) => n.componentId === selectedId);
    return sel.length ? sel : null;
  }, [nodes, selectedId]);

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    if (e.delta > 6) return; // treat as orbit drag, not selection
    e.stopPropagation();
    const hit = nodes.find((n) => n.mesh === e.object);
    if (hit) onSelect(hit.componentId === selectedId ? null : hit.componentId);
  };

  const selectedComp = components.find((c) => c.id === selectedId);
  return (
    <group>
      <primitive
        object={scene}
        onClick={handleClick}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { document.body.style.cursor = ""; }}
      />
      {labelPos && selectedComp && <SelectedLabel nodes={labelPos} name={selectedComp.name} part={selectedComp.part_number ?? ""} />}
    </group>
  );
}

function SelectedLabel({ nodes, name, part }: { nodes: NodeEntry[]; name: string; part: string }) {
  const ref = useRef<THREE.Group>(null);
  const box = useMemo(() => new THREE.Box3(), []);
  const centre = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    if (!ref.current) return;
    box.makeEmpty();
    nodes.forEach((n) => box.expandByObject(n.mesh));
    box.getCenter(centre);
    ref.current.position.set(centre.x, box.max.y + 0.04, centre.z);
  });
  return (
    <group ref={ref}>
      <Html center zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
        <div className="viewer-label">{name}<span>{part}</span></div>
      </Html>
    </group>
  );
}

class ViewerBoundary extends ReactComponent<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export default function AssemblyViewer(props: ViewerProps) {
  // First-time gesture hint; it goes away as soon as the person touches the model.
  const [hint, setHint] = useState(!props.preserveDrawingBuffer);
  const fallback = props.fallback ?? (
    <div className="viewer-fallback">{t("The 3D view doesn't work on this device.")}</div>
  );
  if (!webglAvailable()) return <div className="viewer">{fallback}</div>;
  return (
    <div className={props.className ?? "viewer"} onPointerDown={() => setHint(false)}>
      {hint && <div className="viewer-hint"><Rotate3d aria-hidden />{t("Drag to turn · Pinch to zoom · Tap a part")}</div>}
      <ViewerBoundary fallback={fallback}>
        <Canvas shadows camera={{ position: props.cameraPosition ?? [1.3, 1.0, 1.5], fov: 40, near: 0.01, far: 50 }}
          dpr={[1, 2]} gl={{ preserveDrawingBuffer: !!props.preserveDrawingBuffer }}
          onPointerMissed={(e) => { if (e.type === "click") props.onSelect(null); }}>
          <color attach="background" args={["#eef2f7"]} />
          <hemisphereLight args={["#ffffff", "#8090a0", 1.1]} />
          <directionalLight position={[2, 4, 3]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]} />
          <directionalLight position={[-3, 2, -2]} intensity={0.5} />
          <Suspense fallback={<Html center><div className="viewer-loading">{t("Loading 3D model…")}</div></Html>}>
            <Bounds fit clip margin={props.margin ?? 1.7}>
              <Assembly {...props} />
            </Bounds>
            <ContactShadows position={[0, -0.001, 0]} opacity={0.35} scale={4} blur={2.2} far={1.5} />
          </Suspense>
          <OrbitControls makeDefault enableDamping minDistance={0.15} maxDistance={8} target={[0, 0.4, 0]} />
        </Canvas>
      </ViewerBoundary>
    </div>
  );
}
