/**
 * 于你 Yewne 后端 API 客户端。
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

export const PERSONAS = ["youyou", "nini"] as const;
export type Persona = (typeof PERSONAS)[number];

export type SafetyFlag =
  | "ok"
  | "empty_input"
  | "input_too_long"
  | "crisis_keyword"
  | "aliyun_keyword"
  | "blocked_keyword"
  | "illegal_keyword"
  | "low_quality_keyword"
  | "hate_discrimination_keyword";

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatDemoRequest {
  user_text: string;
  /** 浏览器生成并长期保存的匿名用户标识；用于后端关联会话。 */
  external_user_id?: string;
  /** 第一轮为空，后续轮次传回后端返回的会话 ID。 */
  conversation_id?: string | null;
  /** 可选：每个会话第一句留空，让后端自动分类；后续轮把响应里的 scene 传回，
   * 避免每轮都跑一次分类（多 1 次 LLM 调用）。 */
  scene?: Scene | null;
  /** AI 人格，默认 nini（妮妮）。切换人格时前端应重置会话。 */
  persona?: Persona;
  history?: HistoryMessage[];
}

export interface ChatDemoResponse {
  reply: string;
  scene: Scene;
  safety_flag: SafetyFlag;
  is_mock: boolean;
  request_id: string;
  conversation_id?: string | null;
  /** true 表示原本走真模型但调用失败已降级到 Mock */
  degraded: boolean;
  /** 音频与文字一起返回，省去第二次请求；空串时前端降级浏览器朗读 */
  audio_base64: string;
  audio_content_type: string;
  audio_is_mock: boolean;
  /** 用户输入的情绪标签；空串表示未检测到 */
  emotion?: string;
  /** 小人该播的反应动画，据本句回答判定；空串=无（判定失败），前端回落 Idle。
   * youyou: 开心|伤心|疑惑|肯定|否定  nini: 开心|伤心|疑惑|关心 */
  reaction?: string;
}

export interface HealthResponse {
  status: string;
  env: string;
  persistence_enabled?: boolean;
  database_connected?: boolean | null;
  llm_provider: "mock" | "deepseek";
  llm_is_mock: boolean;
  stt_provider?: "mock" | "whisper";
  stt_is_mock?: boolean;
  tts_provider?: "mock" | "minimax" | "siliconflow" | "doubao";
  tts_is_mock?: boolean;
}

export interface SynthesizeRequest {
  text: string;
  scene?: Scene | null;
}

export interface SynthesizeResponse {
  audio_base64: string;
  content_type: string;
  is_mock: boolean;
  request_id: string;
}

export interface TranscribeResponse {
  text: string;
  language: string;
  is_mock: boolean;
  request_id: string;
}

export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class YewneApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "YewneApiError";
  }
}

/** 调用 /v1/chat/demo。失败抛 YewneApiError，调用方决定如何在 UI 表达。 */
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
    throw new YewneApiError(
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
    throw new YewneApiError(`HTTP ${res.status}`, res.status, body);
  }

  return (await res.json()) as ChatDemoResponse;
}

export type AftercareMood = "down" | "anxious" | "calm";

export interface AftercareRequest {
  persona: Persona;
  history?: HistoryMessage[];
}

export interface AftercareResponse {
  /** 由场景映射的情绪档,决定拍立得正面照片 */
  mood: AftercareMood;
  /** @deprecated 与 letter 内容相同,留作兼容 */
  quote: string;
  /** 回信正文(12 场景回信小精灵产出,≤100 字,可含 \n 分段) */
  letter: string;
  /** 判定的场景键(blank_entry…withdrawal / safety_override),空串=判定失败 */
  scene: string;
  is_mock: boolean;
}

/** 调 /v1/aftercare/generate：据对话判情绪档 + 现写金句（拍立得背面）。 */
export async function fetchAftercare(
  payload: AftercareRequest,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<AftercareResponse> {
  const base = options.baseUrl ?? API_BASE;
  const res = await fetch(`${base}/v1/aftercare/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: options.signal,
  });
  if (!res.ok) {
    throw new YewneApiError(`HTTP ${res.status}`, res.status);
  }
  return (await res.json()) as AftercareResponse;
}

/** 上传音频到 /v1/speech/transcribe，返回转写文本。 */
export async function fetchTranscribe(
  audio: Blob,
  options: { signal?: AbortSignal; baseUrl?: string; filename?: string } = {},
): Promise<TranscribeResponse> {
  const base = options.baseUrl ?? API_BASE;
  const form = new FormData();
  form.append("audio", audio, options.filename ?? "clip.webm");

  let res: Response;
  try {
    res = await fetch(`${base}/v1/speech/transcribe`, {
      method: "POST",
      body: form,
      signal: options.signal,
    });
  } catch (err) {
    throw new YewneApiError(
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
    throw new YewneApiError(`HTTP ${res.status}`, res.status, body);
  }

  return (await res.json()) as TranscribeResponse;
}

/** 把于你回复合成为语音（MP3 base64）。 */
export async function fetchSynthesize(
  payload: SynthesizeRequest,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<SynthesizeResponse> {
  const base = options.baseUrl ?? API_BASE;
  let res: Response;
  try {
    res = await fetch(`${base}/v1/speech/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
  } catch (err) {
    throw new YewneApiError(
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
    throw new YewneApiError(`HTTP ${res.status}`, res.status, body);
  }

  return (await res.json()) as SynthesizeResponse;
}

export interface StreamAudioEvent {
  type: "audio";
  index: number;
  /** 该句对应的文字，前端用它随语音逐句显示。旧后端可能不带此字段。 */
  text?: string;
  audio_base64: string;
  content_type: string;
  is_mock: boolean;
}

export interface StreamDoneEvent {
  type: "done";
  reply: string;
  scene: Scene;
  safety_flag: SafetyFlag;
  is_mock: boolean;
  request_id: string;
  conversation_id?: string | null;
  degraded: boolean;
  emotion?: string;
}

/** 调 /v1/chat/demo/stream（SSE）。audio 事件先于 done 事件到达。 */
export async function fetchChatDemoStream(
  payload: ChatDemoRequest,
  callbacks: {
    onAudio?: (event: StreamAudioEvent) => void;
    onDone: (event: StreamDoneEvent) => void;
  },
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<void> {
  const base = options.baseUrl ?? API_BASE;
  let res: Response;
  try {
    res = await fetch(`${base}/v1/chat/demo/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
  } catch (err) {
    throw new YewneApiError(err instanceof Error ? err.message : "network error");
  }

  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { body = await res.text().catch(() => undefined); }
    throw new YewneApiError(`HTTP ${res.status}`, res.status, body);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (!data) continue;
      try {
        const ev = JSON.parse(data) as StreamAudioEvent | StreamDoneEvent;
        if (ev.type === "audio") callbacks.onAudio?.(ev);
        else if (ev.type === "done") callbacks.onDone(ev);
      } catch { /* skip malformed lines */ }
    }
  }
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
  const rest = { ...payload };
  delete rest.history;
  const json = JSON.stringify(rest);
  return [
    `curl -X POST ${baseUrl}/v1/chat/demo \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${json.replace(/'/g, "'\\''")}'`,
  ].join("\n");
}
