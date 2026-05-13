const BASE = "";

export interface Run {
  id: string;
  service_name: string;
  model: string | null;
  start_time: number;
  end_time: number | null;
  total_cost_usd: number;
  total_tokens: number;
  status: string;
}

export interface Span {
  id: string;
  run_id: string;
  name: string;
  parent_id: string | null;
  start_time: number;
  end_time: number;
  latency_ms: number;
  attributes: Record<string, unknown>;
  error: string | null;
  children: Span[];
}

export interface Alert {
  id: string;
  run_id: string;
  rule_name: string;
  severity: string;
  message: string;
  fired_at: number;
}

export interface NodeCost {
  node_name: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  call_count: number;
}

export interface CostResponse {
  run_id: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  breakdown: NodeCost[];
}

export interface PaginatedRuns {
  items: Run[];
  total: number;
  limit: number;
  offset: number;
}

export interface RegressionPoint {
  bucket: string;
  service_name: string;
  run_count: number;
  avg_latency_ms: number | null;
  max_latency_ms: number | null;
  avg_cost_usd: number | null;
  avg_tokens: number | null;
  error_rate: number;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  runs: {
    list: (params?: {
      limit?: number;
      offset?: number;
      service_name?: string;
      model?: string;
      since?: number;
      until?: number;
    }) => {
      const q = new URLSearchParams();
      if (params?.limit)        q.set("limit",        String(params.limit));
      if (params?.offset)       q.set("offset",       String(params.offset));
      if (params?.service_name) q.set("service_name", params.service_name);
      if (params?.model)        q.set("model",        params.model);
      if (params?.since)        q.set("since",        String(params.since));
      if (params?.until)        q.set("until",        String(params.until));
      return get<PaginatedRuns>(`/api/runs?${q}`);
    },
    get:    (id: string)  => get<Run>(`/api/runs/${id}`),
    spans:  (id: string)  => get<Span[]>(`/api/runs/${id}/spans`),
    cost:   (id: string)  => get<CostResponse>(`/api/runs/${id}/cost`),
  },
  alerts: {
    list: (params?: { limit?: number; run_id?: string }) => {
      const q = new URLSearchParams();
      if (params?.limit)  q.set("limit",  String(params.limit));
      if (params?.run_id) q.set("run_id", params.run_id);
      return get<Alert[]>(`/api/alerts?${q}`);
    },
  },
  regression: {
    get: (params?: {
      service_name?: string;
      bucket?: string;
      since?: number;
      until?: number;
      limit?: number;
    }) => {
      const q = new URLSearchParams();
      if (params?.service_name) q.set("service_name", params.service_name);
      if (params?.bucket)       q.set("bucket",       params.bucket);
      if (params?.since)        q.set("since",        String(params.since));
      if (params?.until)        q.set("until",        String(params.until));
      if (params?.limit)        q.set("limit",        String(params.limit));
      return get<RegressionPoint[]>(`/api/regression?${q}`);
    },
  },
};
