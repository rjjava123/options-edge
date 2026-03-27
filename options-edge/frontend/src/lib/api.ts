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
  setup_classifications: string[];
  direction: string;
  spread_type: string;
  short_strike: number;
  long_strike: number;
  expiration_date: string;
  entry_price: number;
  max_profit: number;
  max_loss: number;
  profit_target: number;
  stop_loss: number;
  confidence: number;
  reasoning: string;
  status: string;
  is_active: boolean;
  closed_at: string | null;
  daily_snapshots?: DailySnapshot[];
  system_score?: SystemScore | null;
  user_score?: UserScore | null;
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
  running: boolean;
  last_run: string | null;
  candidates_found: number | null;
}

// ─── Discovery ────────────────────────────────────────────────────────────────

export const discoveryApi = {
  getStatus: () => request<DiscoveryStatus>("/discovery/status"),
  runNow: () => request<{ job_id: string }>("/discovery/run", { method: "POST" }),
  getLatestTheses: (limit = 50) =>
    request<Thesis[]>(`/discovery/theses?limit=${limit}`),
};

// ─── Validation ───────────────────────────────────────────────────────────────

export const validationApi = {
  analyze: (ticker: string) =>
    request<Thesis>("/validation/analyze", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
};

// ─── Watchlist ────────────────────────────────────────────────────────────────

export const watchlistApi = {
  list: () => request<WatchlistItem[]>("/watchlist"),
  add: (ticker: string, notes?: string) =>
    request<WatchlistItem>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker, notes }),
    }),
  remove: (id: string) => request<void>(`/watchlist/${id}`, { method: "DELETE" }),
  getNews: (ticker: string) => request<NewsContext>(`/watchlist/${ticker}/news`),
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
    return request<Thesis[]>(`/theses?${qs}`);
  },
  get: (id: string) => request<Thesis>(`/theses/${id}`),
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
    request<UserScore>(`/theses/${id}/score`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  checkTrapDetection: (id: string) =>
    request<{ warnings: string[] }>(`/theses/${id}/trap-detection`),
  markActive: (id: string, active: boolean) =>
    request<Thesis>(`/theses/${id}/active`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: active }),
    }),
  close: (id: string, status: string) =>
    request<Thesis>(`/theses/${id}/close`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
};

// ─── Active Trades ────────────────────────────────────────────────────────────

export const activeTradesApi = {
  list: () => request<Thesis[]>("/active-trades"),
};
