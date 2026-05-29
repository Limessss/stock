import { api } from "./client";

export interface HealthData {
  status: string;
  app: string;
  version: string;
  data: {
    raw_dir: string;
    sh_day_files: number;
    sz_day_files: number;
    cache_dir: string;
    cache_files: number;
    stock_names: number;
  };
}

export async function fetchHealth(): Promise<HealthData> {
  const { data } = await api.get<HealthData>("/health");
  return data;
}
