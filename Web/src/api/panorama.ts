import { api } from "./client";

export type PanoramaInstrumentType = "index" | "stock";

export interface PanoramaInstrumentRecord {
  code: string;
  name: string;
  type: PanoramaInstrumentType;
}

export interface PanoramaConfigResponse {
  initialized: boolean;
  instruments: PanoramaInstrumentRecord[];
  updated_at: string | null;
}

export async function getPanoramaConfig(): Promise<PanoramaConfigResponse> {
  const { data } = await api.get<PanoramaConfigResponse>("/sentiment/panorama/config");
  return data;
}

export async function savePanoramaConfig(
  instruments: PanoramaInstrumentRecord[]
): Promise<PanoramaConfigResponse> {
  const { data } = await api.put<PanoramaConfigResponse>("/sentiment/panorama/config", {
    instruments,
  });
  return data;
}
