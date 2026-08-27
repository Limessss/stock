import { api } from "./client";

export interface GannPoint {
  time: string;
  value: number;
}

export interface GannAnchor {
  date: string;
  price: number;
  kind: string;
  reason: string;
}

export interface GannLine {
  label: string;
  color: string;
  direction: "up" | "down";
  points: GannPoint[];
}

export interface GannResponse {
  code: string;
  name: string;
  window_bars: number;
  price_scale: number;
  note: string;
  anchors: {
    up: GannAnchor | null;
    down: GannAnchor | null;
  };
  calibration: {
    up_ref: GannAnchor | null;
    down_ref: GannAnchor | null;
  };
  lines: GannLine[];
}

export async function getGannAnalysis(
  code: string,
  opts: {
    lastN?: number;
    swingHalf?: number;
    minMovePct?: number;
    upAnchorDate?: string;
    downAnchorDate?: string;
  } = {}
): Promise<GannResponse> {
  const { data } = await api.get<GannResponse>(`/gann/${code}`, {
    params: {
      last_n: opts.lastN ?? 250,
      ...(opts.swingHalf != null ? { swing_half: opts.swingHalf } : {}),
      ...(opts.minMovePct != null ? { min_move_pct: opts.minMovePct } : {}),
      ...(opts.upAnchorDate ? { up_anchor_date: opts.upAnchorDate } : {}),
      ...(opts.downAnchorDate ? { down_anchor_date: opts.downAnchorDate } : {}),
    },
  });
  return data;
}
