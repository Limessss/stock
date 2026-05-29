import { api } from "./client";

export interface StrategyParamSchema {
  type: string;
  default: unknown;
}

export interface StrategyInfo {
  name: string;
  label: string;
  code_label?: string;
  description?: string;
  code_description?: string;
  param_count?: number;
  params_schema: Record<string, StrategyParamSchema>;
  has_custom_defaults?: boolean;
  has_custom_meta?: boolean;
  is_default?: boolean;
}

export interface StrategyDetail extends StrategyInfo {
  features: string[];
  tier_rules: string[];
  default_params: Record<string, unknown>;
  code_defaults: Record<string, unknown>;
}

export interface StrategiesResponse {
  strategies: StrategyInfo[];
  default_strategy: string;
}

export async function fetchStrategies(): Promise<StrategiesResponse> {
  const { data } = await api.get<StrategiesResponse>("/strategies");
  return data;
}

/** 兼容旧调用：仅返回策略数组 */
export async function listStrategies(): Promise<StrategyInfo[]> {
  const { strategies } = await fetchStrategies();
  return strategies;
}

export async function getStrategyDetail(name: string): Promise<StrategyDetail> {
  const { data } = await api.get<StrategyDetail>(`/strategies/${name}`);
  return data;
}

export async function updateStrategyConfig(
  name: string,
  body: {
    label: string;
    description: string;
    is_default: boolean;
    params: Record<string, unknown>;
  }
): Promise<StrategyDetail> {
  const { data } = await api.put<StrategyDetail>(`/strategies/${name}`, body);
  return data;
}

export async function updateStrategyDefaults(
  name: string,
  params: Record<string, unknown>
): Promise<StrategyDetail> {
  const { data } = await api.put<StrategyDetail>(`/strategies/${name}/defaults`, { params });
  return data;
}

export async function resetStrategyDefaults(name: string): Promise<StrategyDetail> {
  const { data } = await api.delete<StrategyDetail>(`/strategies/${name}/defaults`);
  return data;
}

export async function resetStrategyMeta(name: string): Promise<StrategyDetail> {
  const { data } = await api.delete<StrategyDetail>(`/strategies/${name}/meta`);
  return data;
}
