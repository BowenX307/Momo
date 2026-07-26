/**
 * 内部工作看板(/internal)的 API 客户端。只给团队内部用,接口在 nginx 层
 * 挡了共享账号密码,这里不额外处理鉴权。
 */

import { API_BASE, YewneApiError } from "@/lib/api/yewne";

export type TodoStatus = "open" | "in_progress" | "done";
export type FeedbackKind = "bug" | "feature" | "other";
export type FeedbackStatus = "new" | "triaged" | "done";

export interface TodoItem {
  id: string;
  title: string;
  detail: string;
  status: TodoStatus;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface FeedbackItem {
  id: string;
  author_name: string;
  kind: FeedbackKind;
  content: string;
  status: FeedbackStatus;
  created_at: string;
  updated_at: string;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  baseUrl: string = API_BASE,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (err) {
    throw new YewneApiError(err instanceof Error ? err.message : "network error");
  }
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text().catch(() => undefined);
    }
    throw new YewneApiError(`HTTP ${res.status}`, res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function fetchTodos(baseUrl?: string): Promise<TodoItem[]> {
  return request<TodoItem[]>("/v1/workboard/todos", {}, baseUrl);
}

export function createTodo(
  payload: { title: string; detail?: string },
  baseUrl?: string,
): Promise<TodoItem> {
  return request<TodoItem>(
    "/v1/workboard/todos",
    { method: "POST", body: JSON.stringify(payload) },
    baseUrl,
  );
}

export function updateTodo(
  id: string,
  payload: Partial<{ title: string; detail: string; status: TodoStatus }>,
  baseUrl?: string,
): Promise<TodoItem> {
  return request<TodoItem>(
    `/v1/workboard/todos/${id}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    baseUrl,
  );
}

export function deleteTodo(id: string, baseUrl?: string): Promise<void> {
  return request<void>(`/v1/workboard/todos/${id}`, { method: "DELETE" }, baseUrl);
}

export function fetchFeedback(baseUrl?: string): Promise<FeedbackItem[]> {
  return request<FeedbackItem[]>("/v1/workboard/feedback", {}, baseUrl);
}

export function createFeedback(
  payload: { content: string; author_name?: string; kind?: FeedbackKind },
  baseUrl?: string,
): Promise<FeedbackItem> {
  return request<FeedbackItem>(
    "/v1/workboard/feedback",
    { method: "POST", body: JSON.stringify(payload) },
    baseUrl,
  );
}

export function updateFeedbackStatus(
  id: string,
  status: FeedbackStatus,
  baseUrl?: string,
): Promise<FeedbackItem> {
  return request<FeedbackItem>(
    `/v1/workboard/feedback/${id}`,
    { method: "PATCH", body: JSON.stringify({ status }) },
    baseUrl,
  );
}
