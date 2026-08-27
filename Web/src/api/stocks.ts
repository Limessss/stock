import { api } from "./client";

export interface StockSearchItem {
  code: string;
  name: string;
  market: string;
}

export async function searchStocks(
  q: string,
  limit = 15
): Promise<StockSearchItem[]> {
  const { data } = await api.get<StockSearchItem[]>("/stocks/search", {
    params: { q, limit },
  });
  return data;
}
