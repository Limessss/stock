import { api } from "./client";

export interface CacheStats {
  total_files: number;
  total_rows: number;
  total_size_mb: number;
  last_updated: string;
}

export interface BuildStatus {
  running: boolean;
  done: number;
  total: number;
  progress_pct: number;
  elapsed_seconds: number;
  error: string | null;
  incremental?: boolean;
  updated?: number;
  skipped?: number;
  failed?: number;
}

export async function getCacheStats(): Promise<CacheStats> {
  const { data } = await api.get<CacheStats>("/data/stats");
  return data;
}

export async function startBuild(
  opts?: { codes?: string[]; incremental?: boolean }
): Promise<BuildStatus> {
  const { data } = await api.post<BuildStatus>("/data/build", {
    codes: opts?.codes ?? null,
    incremental: opts?.incremental ?? true,
  });
  return data;
}

export async function getBuildStatus(): Promise<BuildStatus> {
  const { data } = await api.get<BuildStatus>("/data/build/status");
  return data;
}
