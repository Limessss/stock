import { api } from "./client";

export interface BacktestSummary {
  total_trades: number;
  win_rate: number;
  avg_return: number;
  median_return: number;
  big_win_rate: number;
  big_loss_rate: number;
  avg_hold_days: number;
  sharpe?: number;
  max_drawdown_pct?: number;
  calmar?: number;
  cagr_pct?: number;
  initial_capital?: number;
  total_profit?: number;
  final_capital?: number;
  signal_count?: number;
  skipped_count?: number;
  max_concurrent?: number;
}

export interface MonthlyReturn {
  year: number;
  month: number;
  return_pct: number;
}

export interface EquityPoint {
  date: string;
  nav: number;
}

export interface BacktestMetrics {
  sharpe: number;
  max_drawdown_pct: number;
  calmar: number;
  cagr_pct: number;
  monthly: MonthlyReturn[];
  equity_curve: EquityPoint[];
  initial_capital?: number;
  total_profit?: number;
  final_capital?: number;
}

export interface BacktestTask {
  id: string;
  name: string | null;
  strategy_name: string;
  strategy_params: Record<string, unknown>;
  start_date: string;
  end_date: string;
  take_profit: number;
  stop_loss: number;
  max_hold: number;
  split_tp: number | null;
  initial_capital: number;
  position_pct: number;
  max_concurrent: number;
  t_plus_1: boolean;
  status: "pending" | "running" | "done" | "error" | "cancelled";
  progress: number;
  total: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  summary: BacktestSummary | null;
  trade_count: number;
}

export interface BacktestTrade {
  code: string;
  name: string;
  signal_date: string;
  market: string;
  tier: string;
  score: number;
  breakout_pct: number;
  is_limit_up: boolean;
  vol_ratio: number;
  macd: number;
  dif: number;
  pullback_pct: number;
  ma_spread_pct: number;
  days_since_test: number;
  close_to_ma30: number;
  close_to_low60: number;
  body_ratio: number;
  day_change_pct: number;
  bull_ma_count: number;
  buy_price: number;
  buy_date: string;
  sell_price: number;
  sell_date: string;
  sell_reason: string;
  return_pct: number;
  max_up_pct: number;
  max_dn_pct: number;
  hold_days: number;
  quantity: number;
  buy_amount: number;
  sell_amount: number;
  profit_amount: number;
}

export interface LedgerRow {
  date: string;
  action: "buy" | "sell";
  code: string;
  name: string;
  signal_date: string;
  buy_date?: string | null;
  price: number;
  quantity: number;
  amount: number;
  profit_amount: number | null;
  sell_reason: string | null;
}

export interface LedgerPage {
  rows: LedgerRow[];
  total: number;
  page: number;
  page_size: number;
  initial_capital: number;
  total_profit: number;
  final_capital: number;
}

export interface BacktestRequest {
  name?: string | null;
  strategy: string;
  params: Record<string, unknown>;
  start_date: string;
  end_date: string;
  take_profit: number;
  stop_loss: number;
  max_hold: number;
  split_tp?: number | null;
  max_codes?: number | null;
  num_workers?: number | null;
  engine?: "legacy" | "vectorbt";
  initial_capital?: number;
  position_pct?: number;
  max_concurrent?: number;
  t_plus_1?: boolean;
}

export interface TradesPage {
  rows: BacktestTrade[];
  total: number;
  page: number;
  page_size: number;
}

export async function createBacktest(req: BacktestRequest): Promise<{ task_id: string }> {
  const { data } = await api.post<{ task_id: string }>("/backtest", req);
  return data;
}

export async function getBacktest(taskId: string): Promise<BacktestTask> {
  const { data } = await api.get<BacktestTask>(`/backtest/${taskId}`);
  return data;
}

export async function listBacktestHistory(limit = 50): Promise<BacktestTask[]> {
  const { data } = await api.get<{ tasks: BacktestTask[] }>("/backtest/history", {
    params: { limit },
  });
  return data.tasks;
}

export async function listBacktestTrades(
  taskId: string,
  opts: { page?: number; pageSize?: number; sortBy?: string; desc?: boolean } = {}
): Promise<TradesPage> {
  const { data } = await api.get<TradesPage>(`/backtest/${taskId}/trades`, {
    params: {
      page: opts.page ?? 1,
      page_size: opts.pageSize ?? 50,
      sort_by: opts.sortBy ?? "score",
      desc: opts.desc ?? true,
    },
  });
  return data;
}

export async function deleteBacktest(taskId: string): Promise<void> {
  await api.delete(`/backtest/${taskId}`);
}

export async function getBacktestMetrics(taskId: string): Promise<BacktestMetrics> {
  const { data } = await api.get<BacktestMetrics>(`/backtest/${taskId}/metrics`);
  return data;
}

export async function listBacktestLedger(
  taskId: string,
  opts: { page?: number; pageSize?: number } = {}
): Promise<LedgerPage> {
  const { data } = await api.get<LedgerPage>(`/backtest/${taskId}/ledger`, {
    params: {
      page: opts.page ?? 1,
      page_size: opts.pageSize ?? 100,
    },
  });
  return data;
}

export type WsMessage =
  | { type: "snapshot"; task_id: string; status: string; done: number; total: number; trade_count: number; summary: BacktestSummary | null; error: string | null; elapsed_seconds: number | null }
  | { type: "progress"; task_id: string; done: number; total: number; trade_count: number; elapsed_seconds: number }
  | { type: "done"; task_id: string; summary: BacktestSummary; trade_count: number; elapsed_seconds: number }
  | { type: "error"; task_id: string; error: string };

export function subscribeBacktest(
  taskId: string,
  onMessage: (m: WsMessage) => void,
  onClose?: () => void
): () => void {
  // Vite 代理 ws：开发模式下用 ws://localhost:5173/ws/...，proxy 自动转发
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/ws/backtest/${taskId}`;
  const ws = new WebSocket(url);

  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data) as WsMessage;
      onMessage(msg);
    } catch (e) {
      console.warn("invalid ws message", e);
    }
  });
  ws.addEventListener("close", () => onClose?.());

  return () => ws.close();
}
