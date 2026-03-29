const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Thesis {
  id: string;
  ticker: string;
  created_at: string;
  flow_type: string;
  setup_classifications?: string[];
  direction: string;
  spread_type: string;
  short_strike?: number;
  long_strike?: number;
  expiration_date?: string;
  entry_price?: number;
  max_profit?: number;
  max_loss?: number;
  profit_target?: number;
  stop_loss?: number;
  confidence: number;
  reasoning?: string;
  status?: string;
  is_active?: boolean;
  closed_at?: string | null;
  daily_snapshots?: DailySnapshot[];
  system_score?: SystemScore | null;
  user_score?: UserScore | null;
  state_snapshot?: Record<string, unknown>;
}

export interface DailySnapshot {
  id: string;
  thesis_id: string;
  snapshot_date: string;
  underlying_close: number;
  spread_mark: number;
  pnl_dollars: number;
  pnl_percent: number;
  exit_condition_met: string | null;
}

export interface SystemScore {
  id: string;
  thesis_id: string;
  profitable_at_close_date: boolean;
  hit_profit_target: boolean;
  days_to_profit_target: number | null;
  max_favorable_excursion: number;
  max_adverse_excursion: number;
  final_pnl: number;
}

export interface UserScore {
  id: string;
  thesis_id: string;
  score: number;
  direction_correct: boolean | null;
  structure_appropriate: boolean | null;
  timing_good: boolean | null;
  notes: string | null;
  scored_at: string;
}

export interface WatchlistItem {
  id: string;
  ticker: string;
  added_at: string;
  notes: string | null;
}

export interface NewsContext {
  ticker: string;
  headlines: { title: string; url: string; published: string }[];
  narrative: string;
}

export interface DiscoveryStatus {
  is_running: boolean;
  last_scan: string | null;
}

export interface DiscoveryResults {
  count: number;
  theses: Thesis[];
}

// ─── SSE Event Types ─────────────────────────────────────────────────────────

export interface SSENodeStart {
  node: string;
}

export interface SSENodeComplete {
  node: string;
  summary: Record<string, unknown>;
}

export interface SSENodeError {
  node: string;
  error: string;
}

export interface SSEProgress {
  eventType: string;
  data: SSENodeStart | SSENodeComplete | SSENodeError | Thesis | { message: string } | { ticker: string };
}

// ─── Discovery ────────────────────────────────────────────────────────────────

export const discoveryApi = {
  getStatus: () => request<DiscoveryStatus>("/api/discovery/status"),
  runNow: () =>
    request<{ message: string; status: string }>("/api/discovery/run", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  getResults: () => request<DiscoveryResults>("/api/discovery/results"),
};

// ─── Validation (SSE stream) ─────────────────────────────────────────────────

export const validationApi = {
  /**
   * Streams SSE events from the analysis graph for a single ticker.
   * The caller provides an `onEvent` callback that receives each parsed event.
   * Returns a promise that resolves when the stream ends.
   */
  analyzeStream: async (
    ticker: string,
    onEvent: (eventType: string, data: Record<string, unknown>) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const res = await fetch(`${BASE_URL}/api/validate/${encodeURIComponent(ticker)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API ${res.status}: ${text}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No readable stream in response");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer — format: "event: <type>\ndata: <json>\n\n"
      const parts = buffer.split("\n\n");
      // Keep the last (possibly incomplete) chunk in the buffer
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed) continue;

        let eventType = "message";
        let dataStr = "";

        for (const line of trimmed.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.slice(6);
          }
        }

        if (dataStr) {
          try {
            const data = JSON.parse(dataStr);
            onEvent(eventType, data);
          } catch {
            // Skip malformed JSON
          }
        }
      }
    }
  },
};

// ─── Watchlist ────────────────────────────────────────────────────────────────

export const watchlistApi = {
  list: () => request<WatchlistItem[]>("/api/watchlist/"),
  add: (ticker: string, notes?: string) =>
    request<WatchlistItem>("/api/watchlist/", {
      method: "POST",
      body: JSON.stringify({ ticker, notes }),
    }),
  remove: (ticker: string) =>
    request<void>(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  refreshNews: (ticker: string) =>
    request<NewsContext>(`/api/watchlist/${encodeURIComponent(ticker)}/refresh`, {
      method: "POST",
    }),
};

// ─── Theses ───────────────────────────────────────────────────────────────────

export const thesesApi = {
  list: (params?: {
    ticker?: string;
    status?: string;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.ticker) qs.set("ticker", params.ticker);
    if (params?.status) qs.set("status", params.status);
    if (params?.is_active !== undefined) qs.set("is_active", String(params.is_active));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return request<Thesis[]>(`/api/theses/?${qs}`);
  },
  get: (id: string) => request<Thesis>(`/api/theses/${id}`),
  submitUserScore: (
    id: string,
    payload: {
      score: number;
      direction_correct?: boolean;
      structure_appropriate?: boolean;
      timing_good?: boolean;
      notes?: string;
    }
  ) =>
    request<UserScore>(`/api/theses/${id}/score`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  checkTrapDetection: (id: string) =>
    request<{ warnings: string[] }>(`/api/theses/${id}/trap-check`),
  toggleActive: (id: string, active: boolean) =>
    request<Thesis>(`/api/theses/${id}/activate`, {
      method: "POST",
      body: JSON.stringify({ is_active: active }),
    }),
  close: (id: string, status: string) =>
    request<Thesis>(`/api/theses/${id}/close`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
};

// ─── Active Trades ────────────────────────────────────────────────────────────

export const activeTradesApi = {
  list: () => request<Thesis[]>("/api/active-trades/"),
  getAlerts: (thesisId: string) =>
    request<{ alerts: string[] }>(`/api/active-trades/${thesisId}/alerts`),
};
