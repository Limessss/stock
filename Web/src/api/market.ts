import { api } from "./client";



export interface MarketIndexItem {

  code: string;

  name: string;

  open?: number | null;

  high?: number | null;

  low?: number | null;

  close: number | null;

  prev_close?: number | null;

  change_pct: number | null;

  change_amt: number | null;

  volume?: number | null;

  amount?: number | null;

}



export interface MarketOverview {

  requested_date: string;

  trade_date: string;

  is_non_trading_day: boolean;

  ready: boolean;

  indices: MarketIndexItem[];

  index_name: string;

  index_close: number | null;

  index_change_pct: number | null;

  index_change_amt: number | null;

  up_count: number | null;

  down_count: number | null;

  flat_count: number | null;

  total_amount: number | null;

  data_source?: string;

}



export interface MarketOverviewBatchResponse {

  items: Record<string, MarketOverview>;

  building: boolean;

}



export interface MarketSyncResponse {

  requested_date: string;

  trade_date: string;

  is_non_trading_day: boolean;

  complete: boolean;

  fetched: boolean;

  ready: boolean;

}



export interface MarketIndexKlineBar {

  trade_date: string;

  code: string;

  name: string;

  open: number | null;

  high: number | null;

  low: number | null;

  close: number | null;

  prev_close: number | null;

  change_amt: number | null;

  change_pct: number | null;

  volume: number | null;

  amount: number | null;

}



/** 打开网页时检查并同步当日（或非交易日上一交易日）行情入库 */

export async function syncMarketToday(date?: string): Promise<MarketSyncResponse> {

  const { data } = await api.post<MarketSyncResponse>("/market/sync", { date: date ?? null });

  return data;

}



export async function fetchMarketOverviews(

  dates: string[]

): Promise<MarketOverviewBatchResponse> {

  const unique = [...new Set(dates)].filter(Boolean);

  if (unique.length === 0) {

    return { items: {}, building: false };

  }

  const { data } = await api.post<MarketOverviewBatchResponse>(

    "/market/overview/batch",

    { dates: unique }

  );

  return data;

}



export async function fetchMarketOverview(date: string): Promise<MarketOverview> {

  const { data } = await api.get<MarketOverview>("/market/overview", {

    params: { date },

  });

  return data;

}



export async function fetchIndexKline(

  code: string,

  start?: string,

  end?: string

): Promise<MarketIndexKlineBar[]> {

  const { data } = await api.get<{ code: string; bars: MarketIndexKlineBar[] }>(

    `/market/index/${encodeURIComponent(code)}/kline`,

    { params: { start, end } }

  );

  return data.bars;

}

