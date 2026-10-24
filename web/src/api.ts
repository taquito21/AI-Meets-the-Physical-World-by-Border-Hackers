// Typed REST client. Every access rule lives on the server; the client only renders what it returns.
import { accessToken } from "./supabase";

export type TaskStatus = "pending" | "passed" | "failed" | "flagged";
export type UserClass = "employer" | "employee";

export interface Person { id: string; username: string; user_class: UserClass }
export interface Me extends Person { company_id: string; company: { id: string; name: string } }
export type Counts = Record<TaskStatus | "total", number>;

// One selectable part of a 3D model (from the model's parts list).
export interface Part {
  id: string;
  name: string;
  part_number?: string;
  quantity?: number;
  category?: string;
  material?: string;
  description?: string;
  model_node_ids: string[];
  explosion?: { direction: [number, number, number]; distance: number };
  articulation?: { type: "hinge"; label?: string; pivot: [number, number, number]; axis: [number, number, number]; angle_deg: number } | null;
  specs?: { label: string; value: string; demo_value?: boolean }[];
  inspection_type?: string;
}

export interface MediaItem {
  id: string;
  title: string;
  kind: "model_3d" | "document" | "image";
  url: string | null; // short-lived signed link
  metadata: { filename?: string; parts?: Part[] };
  created_at: string;
  chunks?: number; // documents: searchable chunks (media library only)
  indexing?: { indexed: boolean; chunks?: number; error?: string } | null; // right after upload
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

export interface ImageChecks { width: number; height: number; brightness: number; sharpness: number; issues: string[]; passed: boolean }

export interface Assessment {
  status?: "completed" | "unavailable" | "failed" | "refused";
  provider?: string;
  model?: string | null;
  result?: AssessmentResult | null;
  error?: string | null;
  latency_ms?: number;
  image_checks?: ImageChecks | null;
}

export interface Evidence {
  id: string;
  task_id: string;
  created_by: Person | null;
  text: string | null;
  photo_url: string | null;
  ai_assessment: Assessment | null;
  created_at: string;
}

export interface Task {
  id: string;
  position: number;
  description: string;
  status: TaskStatus;
  updated_at: string;
  evidence: Evidence[];
  media: (MediaItem & { node_ids: string[] })[];
}

export interface JobSummary { id: string; title: string; created_at: string; assigned_to: Person | null; counts: Counts }
export interface Job extends JobSummary { tasks: Task[] }

export interface NewJob {
  title: string;
  assigned_to: string;
  tasks: { description: string; media: { media_id: string; node_ids: string[] }[] }[];
}

export interface AskResult {
  answer: string;
  sources: { n: number; media_id: string; title: string; page: number | null; cited_text: string }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Called when the server rejects the login (expired or revoked); the session provider signs out.
let onUnauthorized: () => void = () => undefined;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken().catch(() => null);
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check the network connection.");
  }
  const body = await res.json().catch(() => null);
  if (res.status === 401) onUnauthorized();
  if (res.status === 413 && !body) throw new ApiError(413, "The file is too large to upload.");
  if (!res.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ") : `Request failed (${res.status})`;
    throw new ApiError(res.status, message);
  }
  return body as T;
}

// Phone photos are often 3-12 MB; hosted functions cap request bodies (4.5 MB on Vercel). Downscale on the
// device to what the server keeps anyway (1568 px JPEG). Falls back to the original file if decoding fails.
async function prepareImage(file: File): Promise<Blob> {
  const MAX = 1568;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, MAX / Math.max(bmp.width, bmp.height));
    if (scale === 1 && file.size < 2_000_000 && file.type === "image/jpeg") {
      bmp.close();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close();
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
  me: () => request<Me>("/api/me"),
  users: () => request<(Person & { company_id: string })[]>("/api/users"),
  jobs: () => request<JobSummary[]>("/api/jobs"),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (body: NewJob) => request<Job>("/api/jobs", json("POST", body)),
  deleteJob: (id: string) => request<{ deleted: string }>(`/api/jobs/${id}`, { method: "DELETE" }),
  setStatus: (taskId: string, status: TaskStatus) => request<Job>(`/api/tasks/${taskId}/status`, json("POST", { status })),
  addEvidence: async (taskId: string, text: string, file: File | null) => {
    const fd = new FormData();
    if (file) fd.append("file", await prepareImage(file), "photo.jpg");
    if (text.trim()) fd.append("text", text.trim());
    return request<Job>(`/api/tasks/${taskId}/evidence`, { method: "POST", body: fd });
  },
  reassess: (evidenceId: string) => request<Job>(`/api/evidence/${evidenceId}/assess`, { method: "POST" }),
  media: () => request<MediaItem[]>("/api/media"),
  uploadMedia: (file: File, title: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (title.trim()) fd.append("title", title.trim());
    return request<MediaItem>("/api/media", { method: "POST", body: fd });
  },
  deleteMedia: (id: string) => request<{ deleted: string }>(`/api/media/${id}`, { method: "DELETE" }),
  ask: (question: string) => request<AskResult>("/api/ask", json("POST", { question })),
};
