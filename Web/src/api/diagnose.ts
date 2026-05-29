import { api } from "./client";

export interface DiagnoseRule {
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  value: unknown;
  threshold: unknown;
  note: string;
}

export interface DiagnoseResponse {
  code: string;
  name: string;
  strategy: string;
  strategy_label: string;
  date: string;
  close: number;
  final_status: "pass" | "fail";
  score: number | null;
  indicators: Record<string, number | null>;
  rules: DiagnoseRule[];
}

export interface KlineCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  change_pct?: number | null;
  amount?: number | null;
}

export interface KlineMaPoint {
  time: string;
  value: number;
}

export interface KlineVolumePoint {
  time: string;
  value: number;
  color: string;
}

export interface KlineResponse {
  code: string;
  name: string;
  candles: KlineCandle[];
  volume: KlineVolumePoint[];
  ma5: KlineMaPoint[];
  ma10: KlineMaPoint[];
  ma20: KlineMaPoint[];
  ma60: KlineMaPoint[];
}

export async function getDiagnose(
  code: string,
  opts: {
    date?: string;
    strategy?: string;
    params?: Record<string, unknown>;
  } = {}
): Promise<DiagnoseResponse> {
  const { data } = await api.get<DiagnoseResponse>(`/diagnose/${code}`, {
    params: {
      ...(opts.date ? { date: opts.date } : {}),
      ...(opts.strategy ? { strategy: opts.strategy } : {}),
      ...(opts.params && Object.keys(opts.params).length > 0
        ? { params: JSON.stringify(opts.params) }
        : {}),
    },
  });
  return data;
}

export async function getKline(
  code: string,
  opts: {
    lastN?: number;
    endDate?: string;
    minDate?: string;
    centerDate?: string;
    maxDate?: string;
  } = {}
): Promise<KlineResponse> {
  const { data } = await api.get<KlineResponse>(`/kline/${code}`, {
    params: {
      last_n: opts.lastN ?? 300,
      ...(opts.endDate ? { end_date: opts.endDate } : {}),
      ...(opts.minDate ? { min_date: opts.minDate } : {}),
      ...(opts.centerDate ? { center_date: opts.centerDate } : {}),
      ...(opts.maxDate ? { max_date: opts.maxDate } : {}),
    },
  });
  return data;
}
