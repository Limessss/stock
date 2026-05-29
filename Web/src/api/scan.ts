import { api } from "./client";

export type { StrategyInfo, StrategyParamSchema } from "./strategies";
export { listStrategies } from "./strategies";

export interface ScanRow {
  code: string;
  name: string;
  market: string;
  tier: string;
  date: string;
  close: number;
  score: number;
  breakout_pct: number;
  is_limit_up: boolean;
  washout_high: number;
  test_date: string | null;
  days_since_test: number;
  pullback_pct: number;
  vol_ratio: number;
  ma_spread_pct: number;
  macd: number;
  dif: number;
  close_to_ma30: number;
  day_change_pct: number;
  bull_ma_count: number;
}

export interface ScanResponse {
  rows: ScanRow[];
  total: number;
  scanned: number;
  took_ms: number;
  strategy?: string;
  target_date?: string;
  warning?: string;
}

export interface ScanRequest {
  strategy: string;
  params: Record<string, unknown>;
  target_date?: string | null;
  limit?: number | null;
  sort_by?: string;
  desc?: boolean;
  max_codes?: number | null;
}

export async function runScan(req: ScanRequest): Promise<ScanResponse> {
  const { data } = await api.post<ScanResponse>("/scan", req);
  return data;
}
