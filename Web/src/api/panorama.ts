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

export interface PanoramaPresetRecord {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  instruments: PanoramaInstrumentRecord[];
  created_at: string;
  updated_at: string;
}

export interface PanoramaPresetCreate {
  name: string;
  start_date: string;
  end_date: string;
  instruments: PanoramaInstrumentRecord[];
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

export async function listPanoramaPresets(): Promise<PanoramaPresetRecord[]> {
  const { data } = await api.get<{ items: PanoramaPresetRecord[] }>("/sentiment/panorama/presets");
  return data.items;
}

export async function createPanoramaPreset(
  input: PanoramaPresetCreate
): Promise<PanoramaPresetRecord> {
  const { data } = await api.post<PanoramaPresetRecord>("/sentiment/panorama/presets", input);
  return data;
}

export async function updatePanoramaPreset(
  id: string,
  input: PanoramaPresetCreate
): Promise<PanoramaPresetRecord> {
  const { data } = await api.put<PanoramaPresetRecord>(`/sentiment/panorama/presets/${id}`, input);
  return data;
}

export async function deletePanoramaPreset(id: string): Promise<void> {
  await api.delete(`/sentiment/panorama/presets/${id}`);
}
