import { api } from "./client";

export interface TuningBacktestConfig {
  start_date: string;
  end_date: string;
  val_start_date?: string | null;
  val_end_date?: string | null;
  take_profit?: number;
  stop_loss?: number;
  max_hold?: number;
  split_tp?: number | null;
  max_codes?: number | null;
  num_workers?: number | null;
  engine?: "legacy" | "vectorbt";
  initial_capital?: number;
  position_pct?: number;
  max_concurrent?: number;
  t_plus_1?: boolean;
}

export interface TuningAdviseRequest {
  strategy: string;
  params: Record<string, unknown>;
  goal?: string;
  task_id?: string | null;
  summary?: Record<string, unknown> | null;
  backtest_config?: TuningBacktestConfig;
}

export interface TuningAdviseResponse {
  analysis: string;
  suggested_params: Record<string, unknown>;
  suggested_trade_params: Record<string, unknown>;
  changes: Array<{ key: string; from?: unknown; to?: unknown; reason?: string }>;
  trade_changes: Array<{ key: string; from?: unknown; to?: unknown; reason?: string }>;
  risks: string[];
}

export interface TuningSessionCreate {
  strategy: string;
  goal?: string;
  objective?: string;
  params: Record<string, unknown>;
  backtest_config: TuningBacktestConfig;
  max_iterations?: number;
}

export interface TuningTrial {
  id: string;
  iteration: number;
  params: Record<string, unknown>;
  summary: Record<string, unknown> | null;
  score: number | null;
  llm_analysis: string | null;
  elapsed_seconds: number | null;
}

export interface TuningSession {
  id: string;
  strategy_name: string;
  goal: string;
  objective: string;
  backtest_config: Record<string, unknown>;
  max_iterations: number;
  status: string;
  error: string | null;
  best_trial_id: string | null;
  created_at: string;
  finished_at: string | null;
  trials: TuningTrial[];
}

export interface TuningVerifyResponse {
  verdict: string;
  meets_goal: boolean;
  analysis: string;
  comparison: string;
  highlights: string[];
  risks: string[];
  suggested_params: Record<string, unknown> | null;
  suggested_trade_params: Record<string, unknown> | null;
}

export interface TuningQuickBacktestResponse {
  summary: Record<string, unknown>;
  score: number;
  elapsed_seconds: number;
}

export async function tuningAdvise(req: TuningAdviseRequest): Promise<TuningAdviseResponse> {
  const { data } = await api.post<TuningAdviseResponse>("/tuning/advise", req);
  return data;
}

export async function tuningQuickBacktest(req: {
  strategy: string;
  params: Record<string, unknown>;
  backtest_config: TuningBacktestConfig;
  objective?: string;
}): Promise<TuningQuickBacktestResponse> {
  const { data } = await api.post<TuningQuickBacktestResponse>("/tuning/quick-backtest", req, {
    timeout: 600_000,
  });
  return data;
}

export async function tuningVerify(req: {
  strategy: string;
  suggested_params: Record<string, unknown>;
  trade_params: Record<string, unknown>;
  verify_summary: Record<string, unknown>;
  goal?: string;
  baseline_summary?: Record<string, unknown> | null;
  prior_analysis?: string;
}): Promise<TuningVerifyResponse> {
  const { data } = await api.post<TuningVerifyResponse>("/tuning/verify", req, {
    timeout: 120_000,
  });
  return data;
}

export async function startTuningSession(req: TuningSessionCreate): Promise<{ session_id: string; status: string }> {
  const { data } = await api.post<{ session_id: string; status: string }>("/tuning/sessions", req);
  return data;
}

export async function getTuningSession(sessionId: string): Promise<TuningSession> {
  const { data } = await api.get<TuningSession>(`/tuning/sessions/${sessionId}`);
  return data;
}

export async function applyTuningSession(sessionId: string): Promise<{ ok: boolean; strategy: string; params: Record<string, unknown> }> {
  const { data } = await api.post<{ ok: boolean; strategy: string; params: Record<string, unknown> }>(
    `/tuning/sessions/${sessionId}/apply`
  );
  return data;
}
