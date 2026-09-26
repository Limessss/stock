import { api } from "./client";

export interface AiReviewSummary {
  id: string;
  trade_date: string;
  agent_name: string;
  model: string;
  title: string;
  summary: string;
  tags: string[];
  linked_codes: string[];
  data_sources: string[];
  data_cutoff: string | null;
  created_at: string;
}

export interface AiReviewDetail extends AiReviewSummary {
  content_markdown: string;
}

export interface ReviewFilters {
  start_date?: string;
  end_date?: string;
  agent_name?: string;
  q?: string;
  order: "asc" | "desc";
  page: number;
  page_size: number;
}

export interface ReviewInstructions {
  trade_date: string;
  prompt: string;
  connection: {
    server_name: string;
    transport: string;
    api_url: string;
    codex_config: string;
    claude_config: string;
    tools: string[];
  };
}

export async function listAiReviews(params: ReviewFilters) {
  const { data } = await api.get<{ items: AiReviewSummary[]; total: number; page: number; page_size: number }>("/ai-reviews", { params });
  return data;
}

export async function getAiReview(id: string) {
  const { data } = await api.get<AiReviewDetail>(`/ai-reviews/${encodeURIComponent(id)}`);
  return data;
}

export async function getAiReviewOverview() {
  const { data } = await api.get<{
    report_count: number; agent_count: number; latest_data_date: string | null;
    agents: { name: string; count: number }[];
  }>("/ai-reviews/overview");
  return data;
}

export async function getReviewInstructions(tradeDate: string) {
  const { data } = await api.get<ReviewInstructions>("/ai-reviews/instructions", { params: { trade_date: tradeDate } });
  return data;
}
