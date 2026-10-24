// Typed REST client. All workflow rules live on the server; the client only renders state.

export type ItemStatus = "pending" | "evidence_submitted" | "more_evidence_requested" | "passed" | "failed" | "not_applicable";
export type ComponentStatus = "not_inspected" | "in_progress" | "pending" | "accepted" | "finding";
export type EvidenceType = "photo" | "manual_confirmation" | "photo_and_manual_confirmation";

export interface Component {
  id: string;
  part_number: string;
  name: string;
  quantity: number;
  category: string | null;
  material: string | null;
  description: string | null;
  model_node_ids: string[];
  explosion: { direction: [number, number, number]; distance: number };
  documents: string[];
  specs: { label: string; value: string; demo_value?: boolean }[];
  inspection_type: string | null;
  articulation: { type: "hinge"; label?: string; pivot: [number, number, number]; axis: [number, number, number]; angle_deg: number } | null;
}

export interface Requirement {
  requirement_id: string;
  component_id: string;
  title: string;
  instructions: string;
  evidence_type: EvidenceType;
  required: boolean;
  acceptance_criteria: string[];
  photo_guidance?: string | null;
  visual_limitations: string[];
  inspection_points: string[];
  possible_findings: string[];
  risks: string[];
  recommended_actions: string[];
  human_review_required: boolean;
}

export interface DemoEvidence {
  id: string; requirement_id: string; caption: string | null; source: string | null; url: string;
  has_precomputed_assessment: boolean; precomputed_model: string | null; precomputed_at: string | null;
}

export interface DocumentRef { id: string; title: string; type: string; path: string; url: string }

export interface Revision {
  id: string;
  revision: string;
  product_model_id: string;
  product_name: string;
  product_description: string | null;
  manufacturer: string;
  engineering_package_id: string;
  package_version: string;
  content_hash: string;
  manifest: Record<string, any>;
  procedure: Record<string, any>;
  components: Component[];
  requirements: Requirement[];
  assembly_url: string | null; // null: asset without a 3D model (inspected from the component list)
  bom_url: string;
  documents: DocumentRef[];
  industry: string;
  asset_category: string | null;
  demo_evidence: DemoEvidence[];
}

export interface ProductSummary {
  id: string;
  revision: string;
  product_id: string;
  product_name: string;
  description: string | null;
  manufacturer: string;
  package_id: string;
  component_count: number;
  requirement_count: number;
  demonstration_package: boolean;
  industry: string;
  asset_category: string | null;
  demo_evidence_count: number;
  has_3d: boolean;
  instances: { serial_number: string; metadata: Record<string, string>; last_inspection_status: string | null; last_inspection_mode: string | null }[];
}

export interface AssessmentResult {
  summary: string;
  correct_area_visible: "yes" | "no" | "uncertain";
  image_quality: "good" | "acceptable" | "poor";
  evidence_sufficient: boolean;
  observations: string[];
  conditions_for_human_review: string[];
  missing_information: string[];
  recommended_action: "accept_for_human_review" | "retake_photo" | "flag_for_human_review";
  retake_guidance: string;
  uncertainty: "low" | "medium" | "high";
  limitations: string[];
}

export interface Assessment {
  id: string;
  evidence_id: string;
  provider: string;
  model: string | null;
  status: "completed" | "unavailable" | "failed" | "refused";
  result: AssessmentResult | null;
  error: string | null;
  latency_ms: number;
  created_at: string;
  origin?: "live" | "precomputed";
  captured_at?: string | null;
}

export interface ImageChecks { width: number; height: number; brightness: number; sharpness: number; issues: string[]; passed: boolean }

export interface Evidence {
  id: string;
  kind: string;
  url: string;
  note: string | null;
  submitted_by: string;
  created_at: string;
  image_checks?: ImageChecks | null;
  assessment?: Assessment | null;
  finding_id?: string | null;
}

export interface Item {
  id: string;
  requirement_id: string;
  component_id: string;
  requirement_snapshot: Omit<Requirement, "requirement_id" | "component_id"> & Record<string, any>;
  required: boolean;
  status: ItemStatus;
  status_reason: string | null;
  observation: string | null;
  manual_confirmed: boolean;
  override_note: string | null;
  decided_by: string | null;
  updated_at: string;
  evidence: Evidence[];
}

export interface CorrectiveAction { id: string; status: string; assigned_to: string | null; description: string | null; recorded_by: string | null; verified_by: string | null }

export interface Finding {
  id: string;
  inspection_id: string;
  product_instance_id: string;
  component_id: string;
  requirement_id: string | null;
  inspection_item_id: string | null;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  status: string;
  assigned_to: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  component_name?: string;
  part_number?: string;
  mode?: "live" | "demo";
  corrective_action: CorrectiveAction | null;
  evidence: Evidence[];
}

export interface Issue { item_id?: string; requirement_id?: string; component_id?: string; finding_id?: string; title?: string; reason: string }

export interface ActivityEvent { id: string; entity_type: string; entity_id: string; event_type: string; actor: string | null; metadata: Record<string, any>; created_at: string }

export interface InspectionState {
  inspection: {
    id: string; product_instance_id: string; product_revision_id: string; procedure_id: string; inspector: string;
    mode: "live" | "demo";
    status: "in_progress" | "submitted" | "changes_requested" | "approved" | "rejected";
    started_at: string; submitted_at: string | null; decided_at: string | null; updated_at: string;
  };
  instance: { id: string; serial_number: string; metadata: Record<string, string> };
  revision_id: string;
  items: Item[];
  findings: Finding[];
  reviews: { id: string; reviewer: string; decision: string; comments: string | null; item_ids: string[]; created_at: string }[];
  activity: ActivityEvent[];
  component_status: Record<string, ComponentStatus>;
  progress: { total: number; done: number; required_total: number; required_done: number };
  readiness: { ready: boolean; blocking: Issue[]; warnings: Issue[] };
}

export interface InspectionListRow {
  id: string; status: string; inspector: string; serial_number: string; product_name: string; revision: string;
  started_at: string; submitted_at: string | null; updated_at: string; open_findings: number; product_revision_id: string;
  mode: "live" | "demo"; industry: string; asset_category: string | null;
}

export interface Dashboard {
  industries: string[];
  filter: string;
  totals: Record<"inspections" | "live" | "demo" | "pending" | "requires_review" | "approved" | "components_inspected"
    | "components_total" | "findings" | "open_findings", number>;
  by_industry: Record<string, number>;
  by_asset: Record<string, number>;
  by_status: Record<string, number>;
  findings_by_severity: Record<string, number>;
  recent: InspectionListRow[];
}

export interface PackageSummary {
  package_dir: string; package_id: string; product_id: string; product_name: string; manufacturer: string;
  engineering_revision: string; demonstration_package: boolean; ok: boolean; errors: string[]; warnings: string[];
  content_hash: string; stats: Record<string, number>; files: Record<string, any>;
  loaded: boolean; loaded_at: string | null; loaded_matches_disk: boolean;
}

export interface Health { status: string; version: string; app_label: string; storage?: "persistent" | "ephemeral"; ai: { provider: string; available: boolean; detail: string } }

export class ApiError extends Error {
  constructor(public status: number, message: string, public issues: Issue[] = []) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check the network connection.");
  }
  const body = await res.json().catch(() => null);
  if (res.status === 413 && !body) {
    throw new ApiError(413, "The photo is too large to upload. Try again, or use a lower camera resolution.");
  }
  if (!res.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `Request failed (${res.status})`;
    const issues: Issue[] = body?.issues ?? (detail?.errors ?? []).map((e: string) => ({ reason: e }));
    throw new ApiError(res.status, message, issues);
  }
  return body as T;
}

// Phone photos are often 3-12 MB; hosted functions cap request bodies (4.5 MB on Vercel). Downscale on the
// device to what the server keeps anyway (1568 px JPEG). Falls back to the original file if decoding fails.
async function decodeImage(file: File): Promise<{ source: CanvasImageSource; width: number; height: number; close?: () => void }> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    return { source: bmp, width: bmp.width, height: bmp.height, close: () => bmp.close() };
  } catch {
    // Older Safari rejects the options bag; an <img> applies EXIF orientation in current browsers.
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return { source: img, width: img.naturalWidth, height: img.naturalHeight };
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

async function prepareImage(file: File): Promise<Blob> {
  const MAX = 1568;
  try {
    const { source, width, height, close } = await decodeImage(file);
    const scale = Math.min(1, MAX / Math.max(width, height));
    if (scale === 1 && file.size < 2_000_000 && file.type === "image/jpeg") {
      close?.();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    canvas.getContext("2d")!.drawImage(source, 0, 0, canvas.width, canvas.height);
    close?.();
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.88));
    return blob ?? file;
  } catch {
    return file; // the server still validates and reports unsupported or oversized files
  }
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  health: () => request<Health>("/api/health"),
  products: () => request<ProductSummary[]>("/api/products"),
  revision: (id: string) => request<Revision>(`/api/revisions/${encodeURIComponent(id)}`),
  passport: (serial: string) => request<any>(`/api/instances/${encodeURIComponent(serial)}`),
  packages: () => request<PackageSummary[]>("/api/packages"),
  loadPackage: (dir: string, actor: string) => request<any>(`/api/packages/${encodeURIComponent(dir)}/load`, json("POST", { actor })),
  startInspection: (serial_number: string, inspector: string, mode: "live" | "demo" = "live") =>
    request<{ inspection_id: string; resumed: boolean; state: InspectionState }>("/api/inspections", json("POST", { serial_number, inspector, mode })),
  inspections: (status?: string, industry?: string) => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (industry) q.set("industry", industry);
    return request<InspectionListRow[]>(`/api/inspections${q.toString() ? `?${q}` : ""}`);
  },
  dashboard: (industry?: string) => request<Dashboard>(`/api/dashboard${industry ? `?industry=${encodeURIComponent(industry)}` : ""}`),
  useDemoEvidence: (id: string, itemId: string, demo_id: string, actor: string, live_ai: boolean) =>
    request<{ evidence_id: string; assessment: Assessment | null; state: InspectionState }>(
      `/api/inspections/${id}/items/${itemId}/demo-evidence`, json("POST", { demo_id, actor, live_ai })),
  inspection: (id: string) => request<InspectionState>(`/api/inspections/${id}`),
  decide: (id: string, itemId: string, body: Record<string, unknown>) =>
    request<InspectionState>(`/api/inspections/${id}/items/${itemId}/decision`, json("POST", body)),
  submit: (id: string, actor: string) => request<InspectionState>(`/api/inspections/${id}/submit`, json("POST", { actor })),
  review: (id: string, body: Record<string, unknown>) => request<InspectionState>(`/api/inspections/${id}/review`, json("POST", body)),
  uploadEvidence: async (id: string, itemId: string, file: File, actor: string, note: string) => {
    const fd = new FormData();
    fd.append("file", await prepareImage(file), "photo.jpg");
    fd.append("actor", actor);
    if (note) fd.append("note", note);
    return request<{ evidence_id: string; image_checks: ImageChecks; assessment: Assessment | null; state: InspectionState }>(
      `/api/inspections/${id}/items/${itemId}/evidence`, { method: "POST", body: fd });
  },
  reassess: (evidenceId: string) => request<Assessment>(`/api/evidence/${evidenceId}/assess`, { method: "POST" }),
  findings: (status?: string) => request<Finding[]>(`/api/findings${status ? `?status=${status}` : ""}`),
  transitionFinding: (id: string, body: Record<string, unknown>) => request<any>(`/api/findings/${id}/transition`, json("POST", body)),
  findingEvidence: async (id: string, file: File, actor: string, kind: "corrective_before" | "corrective_after", note: string) => {
    const fd = new FormData();
    fd.append("file", await prepareImage(file), "photo.jpg");
    fd.append("actor", actor);
    fd.append("kind", kind);
    if (note) fd.append("note", note);
    return request<any>(`/api/findings/${id}/evidence`, { method: "POST", body: fd });
  },
  activity: () => request<ActivityEvent[]>("/api/activity"),
};
