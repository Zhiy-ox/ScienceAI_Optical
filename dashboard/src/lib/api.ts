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
  interrupt?: {
    type?: string;
    message?: string;
    plan?: Record<string, unknown>;
    verified_gaps?: Record<string, unknown>[];
  } | null;
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
  stream?: boolean;
  hitl_gates?: string[];
}

export interface StreamEvent {
  event: "progress" | "node" | "interrupt" | "done" | "error";
  stage?: string;
  msg?: string;
  status?: string;
  node?: string;
  count?: number;
  cost_so_far?: number;
  message?: string;
  // interrupt payload
  type?: string;
  plan?: Record<string, unknown>;
  verified_gaps?: Record<string, unknown>[];
}

export interface ResumeRequest {
  action: "approve" | "edit" | "reject";
  plan?: Record<string, unknown>;
  verified_gaps?: Record<string, unknown>[];
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

export interface NodeMetric {
  node: string;
  duration_s: number;
  status?: string | null;
}

export interface NodeAggregate {
  node: string;
  calls: number;
  total_s: number;
}

export interface TraceResponse {
  session_id: string;
  status: string;
  node_count: number;
  total_duration_s: number;
  by_node: NodeAggregate[];
  trace: NodeMetric[];
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

  // Per-node execution trace (timing) from the graph's observability layer.
  getTrace: (sessionId: string) =>
    fetchJSON<TraceResponse>(`/research/${sessionId}/trace`),

  // Zotero
  listZoteroCollections: () =>
    fetchJSON<ZoteroCollection[]>("/zotero/collections"),

  // Streaming (SSE). Returns an unsubscribe function.
  streamSession: (
    sessionId: string,
    onEvent: (ev: StreamEvent) => void,
    onError?: (err: Event) => void,
  ): (() => void) => {
    const url = `${API_BASE}/research/${sessionId}/stream`;
    const es = new EventSource(url);

    const handle = (type: StreamEvent["event"]) => (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ event: type, ...data });
      } catch {
        /* ignore malformed frame */
      }
      if (type === "done" || type === "error") {
        es.close();
      }
    };

    es.addEventListener("progress", handle("progress") as EventListener);
    es.addEventListener("node", handle("node") as EventListener);
    es.addEventListener("interrupt", handle("interrupt") as EventListener);
    es.addEventListener("done", handle("done") as EventListener);
    es.addEventListener("error", handle("error") as EventListener);
    es.onerror = (err) => {
      if (onError) onError(err);
      es.close();
    };

    return () => es.close();
  },

  // Resume an interrupted session at a HITL gate. POST returns an SSE stream;
  // parsed via fetch + ReadableStream (EventSource cannot POST).
  resumeSession: async (
    sessionId: string,
    body: ResumeRequest,
    onEvent: (ev: StreamEvent) => void,
  ): Promise<void> => {
    const res = await fetch(`${API_BASE}/research/${sessionId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => "");
      throw new Error(`Resume ${res.status}: ${text}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        try {
          onEvent({ event: event as StreamEvent["event"], ...JSON.parse(data) });
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  },
};
