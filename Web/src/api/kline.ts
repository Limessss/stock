import { api } from "./client";

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

export interface KlineMacdBar {
  time: string;
  value: number;
  color: string;
}

export interface KlineMacdLine {
  time: string;
  value: number;
}

export interface KlineResponse {
  code: string;
  name: string;
  adjustment: "qfq" | "none";
  candles: KlineCandle[];
  volume: KlineVolumePoint[];
  macd?: KlineMacdBar[];
  dif?: KlineMacdLine[];
  dea?: KlineMacdLine[];
  ma5: KlineMaPoint[];
  ma10: KlineMaPoint[];
  ma20: KlineMaPoint[];
  ma60: KlineMaPoint[];
}

export async function getKline(
  code: string,
  opts: {
    lastN?: number;
    endDate?: string;
    minDate?: string;
    centerDate?: string;
    maxDate?: string;
    adjust?: "qfq" | "none";
  } = {}
): Promise<KlineResponse> {
  const { data } = await api.get<KlineResponse>(`/kline/${code}`, {
    params: {
      last_n: opts.lastN ?? 300,
      adjust: opts.adjust ?? "qfq",
      ...(opts.endDate ? { end_date: opts.endDate } : {}),
      ...(opts.minDate ? { min_date: opts.minDate } : {}),
      ...(opts.centerDate ? { center_date: opts.centerDate } : {}),
      ...(opts.maxDate ? { max_date: opts.maxDate } : {}),
    },
  });
  return data;
}
