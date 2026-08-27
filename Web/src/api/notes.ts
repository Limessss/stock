import { api } from "./client";

export interface NoteStockMention {
  code: string;
  name: string;
}

export interface NoteSummary {
  id: string;
  title: string;
  trade_date: string | null;
  tags: string[];
  linked_codes: string[];
  mentions?: NoteStockMention[];
  excerpt: string;
  created_at: string;
  updated_at: string;
}

export interface NoteDetail {
  id: string;
  title: string;
  content_html: string;
  trade_date: string | null;
  tags: string[];
  linked_codes: string[];
  created_at: string;
  updated_at: string;
}

export interface NoteListResponse {
  items: NoteSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface NoteCreatePayload {
  title: string;
  content_html: string;
  trade_date?: string | null;
  tags?: string[];
}

export interface NoteUpdatePayload {
  title?: string;
  content_html?: string;
  trade_date?: string | null;
  tags?: string[];
}

export async function listNotes(params?: {
  q?: string;
  tag?: string;
  code?: string;
  page?: number;
  page_size?: number;
}): Promise<NoteListResponse> {
  const { data } = await api.get<NoteListResponse>("/notes", { params });
  return data;
}

export async function listNoteTags(): Promise<string[]> {
  const { data } = await api.get<string[]>("/notes/tags");
  return data;
}

export async function getNote(id: string): Promise<NoteDetail> {
  const { data } = await api.get<NoteDetail>(`/notes/${id}`);
  return data;
}

export async function createNote(payload: NoteCreatePayload): Promise<NoteDetail> {
  const { data } = await api.post<NoteDetail>("/notes", payload);
  return data;
}

export async function updateNote(id: string, payload: NoteUpdatePayload): Promise<NoteDetail> {
  const { data } = await api.put<NoteDetail>(`/notes/${id}`, payload);
  return data;
}

export async function deleteNote(id: string): Promise<void> {
  await api.delete(`/notes/${id}`);
}
