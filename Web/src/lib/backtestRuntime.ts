import dayjs, { type Dayjs } from "dayjs";

/** 与回测页一致的运行时配置（不含策略名/策略参数/任务名） */
export interface BacktestRuntimeState {
  startDate: Dayjs;
  endDate: Dayjs;
  takeProfit: number;
  stopLoss: number;
  maxHold: number;
  splitTp: number | null;
  debugMode: boolean;
  maxCodes: number | null;
  numWorkers: number | null;
  engine: "legacy" | "vectorbt";
  initialCapital: number;
  positionPct: number;
  maxConcurrent: number;
  tPlus1: boolean;
}

export const DEFAULT_BACKTEST_RUNTIME: BacktestRuntimeState = {
  startDate: dayjs("2026-01-01"),
  endDate: dayjs("2026-05-28"),
  takeProfit: 0.2,
  stopLoss: 0.07,
  maxHold: 20,
  splitTp: null,
  debugMode: false,
  maxCodes: 200,
  numWorkers: 8,
  engine: "legacy",
  initialCapital: 1_000_000,
  positionPct: 1.0,
  maxConcurrent: 1,
  tPlus1: true,
};

/** 转为 API 请求体（回测页 createBacktest / AI 调参 quick-backtest 共用） */
export function toBacktestApiPayload(rt: BacktestRuntimeState) {
  return {
    start_date: rt.startDate.format("YYYY-MM-DD"),
    end_date: rt.endDate.format("YYYY-MM-DD"),
    take_profit: rt.takeProfit,
    stop_loss: rt.stopLoss,
    max_hold: rt.maxHold,
    split_tp: rt.splitTp,
    max_codes: rt.debugMode ? rt.maxCodes : null,
    num_workers: rt.numWorkers ?? 8,
    engine: rt.engine,
    initial_capital: rt.initialCapital,
    position_pct: rt.positionPct,
    max_concurrent: rt.maxConcurrent,
    t_plus_1: rt.tPlus1,
  };
}

export function backtestScopeLabel(rt: BacktestRuntimeState): string {
  if (rt.debugMode && rt.maxCodes) {
    return `调试模式 · 前 ${rt.maxCodes} 只`;
  }
  return "全市场";
}

/** 从历史回测任务同步可对齐的字段（max_codes/并行度等任务表未持久化则保留当前值） */
export function tradeParamsFromRuntime(rt: BacktestRuntimeState) {
  return {
    take_profit: rt.takeProfit,
    stop_loss: rt.stopLoss,
    max_hold: rt.maxHold,
    split_tp: rt.splitTp,
    position_pct: rt.positionPct,
    max_concurrent: rt.maxConcurrent,
  };
}

export function applyTradeParamsToRuntime(
  rt: BacktestRuntimeState,
  tp: Record<string, unknown>
): BacktestRuntimeState {
  return {
    ...rt,
    takeProfit: tp.take_profit != null ? Number(tp.take_profit) : rt.takeProfit,
    stopLoss: tp.stop_loss != null ? Number(tp.stop_loss) : rt.stopLoss,
    maxHold: tp.max_hold != null ? Number(tp.max_hold) : rt.maxHold,
    splitTp:
      tp.split_tp === null || tp.split_tp === undefined
        ? rt.splitTp
        : tp.split_tp === "" || Number(tp.split_tp) <= 0
          ? null
          : Number(tp.split_tp),
    positionPct: tp.position_pct != null ? Number(tp.position_pct) : rt.positionPct,
    maxConcurrent: tp.max_concurrent != null ? Number(tp.max_concurrent) : rt.maxConcurrent,
  };
}

export const TRADE_PARAM_LABELS: Record<string, string> = {
  take_profit: "止盈",
  stop_loss: "止损",
  max_hold: "最长持有(日)",
  split_tp: "分批止盈",
  position_pct: "单笔仓位",
  max_concurrent: "最大持仓",
};

export function formatTradeParamValue(key: string, val: unknown): string {
  if (val == null || val === "") return "—";
  if (key === "take_profit" || key === "stop_loss" || key === "split_tp" || key === "position_pct") {
    const n = Number(val);
    if (Number.isNaN(n)) return String(val);
    if (key === "position_pct") return `${(n * 100).toFixed(0)}%`;
    return `${(n * 100).toFixed(1)}%`;
  }
  return String(val);
}

/** 从历史回测任务同步可对齐的字段（max_codes/并行度等任务表未持久化则保留当前值） */
export function runtimeFromBacktestTask(
  task: {
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
  },
  prev: BacktestRuntimeState = DEFAULT_BACKTEST_RUNTIME
): BacktestRuntimeState {
  return {
    ...prev,
    startDate: dayjs(task.start_date),
    endDate: dayjs(task.end_date),
    takeProfit: task.take_profit,
    stopLoss: task.stop_loss,
    maxHold: task.max_hold,
    splitTp: task.split_tp,
    initialCapital: task.initial_capital,
    positionPct: task.position_pct,
    maxConcurrent: task.max_concurrent,
    tPlus1: task.t_plus_1,
  };
}
