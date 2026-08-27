import { api } from "./client";

export interface SentimentMarket {
  sh_change_pct: number | null;
  up_count: number | null;
  down_count: number | null;
  flat_count: number | null;
  limit_up_count: number | null;
  limit_down_count: number | null;
  broken_board_count: number | null;
  new_high_100_count: number | null;
  scanned_stock_count: number | null;
  total_amount: number | null;
  amount_change_pct: number | null;
}

export interface SentimentThemeItem {
  id: string;
  name: string;
  count: number | null;
  rank: number;
  stage: string;
  source: string;
  manual_override: boolean;
}

export interface SentimentStockItem {
  code: string;
  name: string;
  themes: string[];
  source: string;
}

export interface SentimentLadderItem {
  id: string;
  code: string;
  name: string;
  board_count: number;
  board_type: string;
  limit_time: number | null;
  reason: string;
  themes: string[];
  is_major_first_board: boolean;
  source: string;
}

export interface SentimentNegativeFeedbackItem {
  code: string;
  name: string;
  recent_max_board: number;
  recent_board_date: string;
  board_type: string;
  themes: string[];
  source: string;
}

export interface SentimentFeedbackItem {
  id: string;
  feedback_type: string;
  content: string;
  linked_codes: string[];
  linked_themes: string[];
  source: string;
  confirmed: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface SentimentDay {
  trade_date: string;
  market: SentimentMarket;
  limit_up_themes: SentimentThemeItem[];
  new_high_themes: SentimentThemeItem[];
  strong_sectors: SentimentThemeItem[];
  weak_sectors: SentimentThemeItem[];
  new_high_stocks: SentimentStockItem[];
  ladder: {
    max_board: number;
    three_board_count: number;
    items: SentimentLadderItem[];
  };
  negative_feedback: SentimentNegativeFeedbackItem[];
  sync_status: {
    local_complete: boolean;
    external_complete: boolean;
    external_status: string;
    external_configured: boolean;
    sync_error: string;
    updated_at: string;
  };
}

export interface SentimentSyncResponse {
  trade_date: string;
  local_complete: boolean;
  external_status: string;
  local_cached: boolean;
  configured: boolean;
  network_requests: number;
  statuses: Record<string, string>;
}

export interface IntervalGainItem {
  rank: number;
  code: string;
  name: string;
  start_close: number;
  end_close: number;
  gain_pct: number;
}

export interface IntervalGainResponse {
  start_date: string;
  end_date: string;
  days: number;
  total_candidates: number;
  scanned_stocks: number;
  source: string;
  cache_hit: boolean;
  generated_at: string;
  items: IntervalGainItem[];
}

export async function fetchSentimentMatrix(
  limit = 20,
  end?: string
): Promise<SentimentDay[]> {
  const { data } = await api.get<{ items: SentimentDay[] }>("/sentiment/matrix", {
    params: { limit, end },
  });
  return data.items;
}

export async function fetchSentimentDay(tradeDate: string): Promise<SentimentDay | null> {
  const response = await api.get<SentimentDay>(`/sentiment/${tradeDate}`, {
    validateStatus: (status) => (status >= 200 && status < 300) || status === 404,
  });
  return response.status === 404 ? null : response.data;
}

export async function fetchIntervalGains(params: {
  start?: string;
  end?: string;
  days: number;
  limit: number;
}): Promise<IntervalGainResponse> {
  const { data } = await api.get<IntervalGainResponse>("/sentiment/interval-gains", { params });
  return data;
}

export async function syncSentimentDay(
  tradeDate: string,
  force = false
): Promise<SentimentSyncResponse> {
  const { data } = await api.post<SentimentSyncResponse>(`/sentiment/${tradeDate}/sync`, {
    force,
  });
  return data;
}

export async function updateMajorFirstBoards(
  tradeDate: string,
  codes: string[]
): Promise<SentimentDay> {
  const { data } = await api.put<SentimentDay>(
    `/sentiment/${tradeDate}/major-first-boards`,
    { codes }
  );
  return data;
}

export async function createSentimentFeedback(
  tradeDate: string,
  payload: { content: string; linked_codes: string[]; linked_themes: string[] }
): Promise<SentimentFeedbackItem> {
  const { data } = await api.post<SentimentFeedbackItem>(
    `/sentiment/${tradeDate}/feedback`,
    payload
  );
  return data;
}

export async function deleteSentimentFeedback(id: string): Promise<void> {
  await api.delete(`/sentiment/feedback/${id}`);
}
