/**
 * MOMO 后端 API 客户端。
 *
 * Demo 阶段刻意只手抄一份与 `services/api` Pydantic 字段对齐的 TS 类型。
 * 等接口数 ≥3 个、且 mobile 端也要接入时，再统一抽到 `packages/shared-types`
 * 并把仓库正式改造成 pnpm workspace（届时本文件类型导入即可）。
 */

export const SCENES = [
  "late_night",
  "rumination",
  "relationship",
  "stress",
  "loneliness",
] as const;

export type Scene = (typeof SCENES)[number];

export type SafetyFlag =
  | "ok"
  | "empty_input"
  | "input_too_long"
  | "crisis_keyword";

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatDemoRequest {
  user_text: string;
  /** 可选：每个会话第一句留空，让后端自动分类；后续轮把响应里的 scene 传回，
   * 避免每轮都跑一次分类（多 1 次 LLM 调用）。 */
  scene?: Scene | null;
  history?: HistoryMessage[];
}

export interface ChatDemoResponse {
  reply: string;
  scene: Scene;
  safety_flag: SafetyFlag;
  is_mock: boolean;
  request_id: string;
  /** true 表示原本走真模型但调用失败已降级到 Mock */
  degraded: boolean;
}

export interface HealthResponse {
  status: string;
  env: string;
  llm_provider: "mock" | "deepseek";
  llm_is_mock: boolean;
}

export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class MomoApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "MomoApiError";
  }
}

/** 调用 /v1/chat/demo。失败抛 MomoApiError，调用方决定如何在 UI 表达。 */
export async function fetchChatDemo(
  payload: ChatDemoRequest,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<ChatDemoResponse> {
  const base = options.baseUrl ?? API_BASE;
  let res: Response;
  try {
    res = await fetch(`${base}/v1/chat/demo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
  } catch (err) {
    throw new MomoApiError(
      err instanceof Error ? err.message : "network error",
    );
  }

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text().catch(() => undefined);
    }
    throw new MomoApiError(`HTTP ${res.status}`, res.status, body);
  }

  return (await res.json()) as ChatDemoResponse;
}

/** 调 /health 拿 provider 状态；失败时返回 null（前端按"未知"展示）。 */
export async function fetchHealth(
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<HealthResponse | null> {
  const base = options.baseUrl ?? API_BASE;
  try {
    const res = await fetch(`${base}/health`, { signal: options.signal });
    if (!res.ok) return null;
    return (await res.json()) as HealthResponse;
  } catch {
    return null;
  }
}

/** 拼一个等价的 curl 命令文本，用于调试面板"复制即可复刻"。history 不展示在 curl 里保持简洁。 */
export function buildCurl(payload: ChatDemoRequest, baseUrl: string = API_BASE): string {
  const { history: _history, ...rest } = payload;
  const json = JSON.stringify(rest);
  return [
    `curl -X POST ${baseUrl}/v1/chat/demo \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${json.replace(/'/g, "'\\''")}'`,
  ].join("\n");
}
