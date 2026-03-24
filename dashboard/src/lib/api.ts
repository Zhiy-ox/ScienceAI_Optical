/** API client for the Science AI backend. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface HealthResponse {
  status: string;
  version: string;
}

export interface SessionCreated {
  session_id: string;
  status: string;
  message: string;
}

export interface SessionStatus {
  session_id: string;
  status: string;
  cost_so_far: number;
}

export interface CostDetail {
  call_id: string;
  agent: string;
  model: string;
  reasoning_effort: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  timestamp: number;
}

export interface DetailedCostReport {
  session_id: string;
  total_usd: number;
  by_model: Record<string, number>;
  by_agent: Record<string, number>;
  call_count: number;
  cache_savings_estimate_usd: number;
  calls: CostDetail[];
}

export interface ResearchResult {
  session_id: string;
  status: string;
  plan: Record<string, unknown> | null;
  papers_found: number;
  triage_results: Record<string, unknown>[];
  knowledge_objects: Record<string, unknown>[];
  critiques: Record<string, unknown>[];
  gaps: Record<string, unknown>[];
  verified_gaps: Record<string, unknown>[];
  ideas: Record<string, unknown>[];
  experiment_plans: Record<string, unknown>[];
  report: Record<string, unknown> | null;
  cost_summary: {
    session_id: string;
    total_usd: number;
    by_model: Record<string, number>;
    call_count: number;
  } | null;
}

export interface StartResearchRequest {
  question: string;
  max_papers?: number;
  phase?: number;
  user_background?: string;
  source?: "web" | "zotero" | "both";
}

export interface SettingsResponse {
  openai_api_key: string;
  anthropic_api_key: string;
  google_api_key: string;
  zotero_library_id: string;
  zotero_api_key: string;
  zotero_library_type: string;
  cost_budget_usd: number;
  llm_backend: "api" | "cli";
}

export interface SettingsUpdate {
  openai_api_key?: string;
  anthropic_api_key?: string;
  google_api_key?: string;
  zotero_library_id?: string;
  zotero_api_key?: string;
  zotero_library_type?: string;
  cost_budget_usd?: number;
  llm_backend?: "api" | "cli";
}

export interface ProviderTestResult {
  provider: string;
  ok: boolean;
  message: string;
}

export interface SettingsTestResponse {
  results: ProviderTestResult[];
}

export interface SessionListItem {
  session_id: string;
  status: string;
  question: string;
  cost_so_far: number;
}

export interface ZoteroCollection {
  key: string;
  name: string;
  num_items: number;
}

export interface StepProgress {
  step_number: number;
  step_name: string;
  status: "running" | "done" | "skipped" | "failed";
  started_at: number;
  finished_at: number | null;
  duration_seconds: number;
  error: string | null;
}

export interface PipelineProgress {
  session_id: string;
  current_step: string | null;
  current_step_number: number | null;
  elapsed_seconds: number | null;
  steps: StepProgress[];
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchJSON<HealthResponse>("/health"),

  startResearch: (req: StartResearchRequest) =>
    fetchJSON<SessionCreated>("/research/start", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  getStatus: (sessionId: string) =>
    fetchJSON<SessionStatus>(`/research/${sessionId}/status`),

  getResults: (sessionId: string) =>
    fetchJSON<ResearchResult>(`/research/${sessionId}/results`),

  getCost: (sessionId: string) =>
    fetchJSON<DetailedCostReport>(`/research/${sessionId}/cost`),

  // Settings
  getSettings: () => fetchJSON<SettingsResponse>("/settings"),

  updateSettings: (data: SettingsUpdate) =>
    fetchJSON<SettingsResponse>("/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  testSettings: () =>
    fetchJSON<SettingsTestResponse>("/settings/test", { method: "POST" }),

  // Sessions
  listSessions: () => fetchJSON<SessionListItem[]>("/sessions"),

  getProgress: (sessionId: string) =>
    fetchJSON<PipelineProgress>(`/research/${sessionId}/progress`),

  // Zotero
  listZoteroCollections: () =>
    fetchJSON<ZoteroCollection[]>("/zotero/collections"),
};
