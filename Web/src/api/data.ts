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

export interface TdxSyncStatus {
  running: boolean;
  stage: string;
  done: number;
  total: number;
  unit: "bytes" | "files" | string;
  progress_pct: number;
  elapsed_seconds: number;
  error: string | null;
  remote_time: string;
  remote_size: string;
  downloaded: boolean;
  extracted: number;
  updated: number;
  skipped: number;
  failed: number;
  last_raw_date: string;
  raw_dir: string;
  download_path: string;
  source_url: string;
  gbbq_downloaded: boolean;
  gbbq_events: number;
  gbbq_updated_at: string;
  gbbq_source_url: string;
  gbbq_download_path: string;
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

export async function getTdxSyncStatus(): Promise<TdxSyncStatus> {
  const { data } = await api.get<TdxSyncStatus>("/data/tdx-sync/status");
  return data;
}

export async function startTdxSync(forceDownload = false): Promise<TdxSyncStatus> {
  const { data } = await api.post<TdxSyncStatus>("/data/tdx-sync", {
    force_download: forceDownload,
  });
  return data;
}
