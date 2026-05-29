import { api } from "./client";

export interface LlmConfigPublic {
  base_url: string;
  model: string;
  timeout: number;
  api_key_masked: string;
  configured: boolean;
}

export interface LlmConfigUpdate {
  base_url: string;
  model: string;
  timeout: number;
  api_key?: string;
}

export interface LlmTestResponse {
  ok: boolean;
  latency_ms: number;
  model: string;
  reply: string;
}

export async function getLlmSettings(): Promise<LlmConfigPublic> {
  const { data } = await api.get<LlmConfigPublic>("/settings/llm");
  return data;
}

export async function updateLlmSettings(body: LlmConfigUpdate): Promise<LlmConfigPublic> {
  const { data } = await api.put<LlmConfigPublic>("/settings/llm", body);
  return data;
}

export async function testLlmSettings(): Promise<LlmTestResponse> {
  const { data } = await api.post<LlmTestResponse>("/settings/llm/test");
  return data;
}
