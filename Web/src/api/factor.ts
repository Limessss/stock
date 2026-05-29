import { api } from "./client";

export interface FactorICRow {
  field: string;
  label: string;
  ic_return: number | null;
  ic_max_up: number | null;
}

export interface QuantileRow {
  quantile: string;
  count: number;
  mean: number;
  median: number;
  win_rate: number;
  big_win_rate: number;
}

export interface FactorQuantile {
  field: string;
  label: string;
  quantiles: QuantileRow[];
}

export interface FactorAnalysisResponse {
  task_id: string;
  total_trades: number;
  ic: FactorICRow[];
  quantiles: FactorQuantile[];
}

export async function getFactorAnalysis(
  taskId: string,
  opts: { target?: "return_pct" | "max_up_pct"; quantileN?: number } = {}
): Promise<FactorAnalysisResponse> {
  const { data } = await api.get<FactorAnalysisResponse>("/factor/analysis", {
    params: {
      task_id: taskId,
      target: opts.target ?? "return_pct",
      quantile_n: opts.quantileN ?? 5,
    },
  });
  return data;
}
