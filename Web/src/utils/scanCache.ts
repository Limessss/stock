import type { ScanResponse } from "@/api/scan";

export const SCAN_PAGE_QUERY_KEY = ["scan", "page"] as const;

const SESSION_KEY = "stockmodel:scan-page";

export interface ScanPageCache {
  strategyName: string;
  params: Record<string, unknown>;
  targetDate: string | null;
  limit: number;
  maxCodes: number | null;
  debugMode: boolean;
  result: ScanResponse;
}

export function loadScanPageCache(): ScanPageCache | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ScanPageCache;
  } catch {
    return null;
  }
}

export function saveScanPageCache(cache: ScanPageCache): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(cache));
}

export function clearScanPageCache(): void {
  sessionStorage.removeItem(SESSION_KEY);
}
