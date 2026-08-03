/**
 * 于你 Yewne 后端 API 客户端。
 *
 * Demo 阶段刻意只手抄一份与 `services/api` Pydantic 字段对齐的 TS 类型。
 * 等接口数 ≥3 个、且 mobile 端也要接入时，再统一抽到 `packages/shared-types`
 * 并把仓库正式改造成 pnpm workspace（届时本文件类型导入即可）。
 */

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
  /** AI 人格，默认 nini（妮妮）。切换人格时前端应重置会话。 */
  persona?: Persona;
  history?: HistoryMessage[];
}

export interface ChatDemoResponse {
  reply: string;
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
  /** 传了才会把这轮结束归档（ended_at/mood/letter 落库），配合 external_user_id 一起传。 */
  conversation_id?: string | null;
  external_user_id?: string;
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

export interface RoundSummary {
  conversation_id: string;
  persona: Persona;
  mood?: AftercareMood | null;
  letter?: string | null;
  created_at: string;
  ended_at: string;
}

export interface RoundMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

/** 调 /v1/conversation/rounds：列出该用户已结束归档的历史轮次，最新在前。 */
export async function fetchRounds(
  externalUserId: string,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<RoundSummary[]> {
  const base = options.baseUrl ?? API_BASE;
  const url = `${base}/v1/conversation/rounds?external_user_id=${encodeURIComponent(externalUserId)}`;
  const res = await fetch(url, { signal: options.signal });
  if (!res.ok) throw new YewneApiError(`HTTP ${res.status}`, res.status);
  return (await res.json()) as RoundSummary[];
}

/** 调 /v1/conversation/rounds/{id}/messages：某一轮的完整消息（只读回看）。 */
export async function fetchRoundMessages(
  conversationId: string,
  externalUserId: string,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<RoundMessage[]> {
  const base = options.baseUrl ?? API_BASE;
  const url = `${base}/v1/conversation/rounds/${conversationId}/messages?external_user_id=${encodeURIComponent(externalUserId)}`;
  const res = await fetch(url, { signal: options.signal });
  if (!res.ok) throw new YewneApiError(`HTTP ${res.status}`, res.status);
  return (await res.json()) as RoundMessage[];
}

export interface SendCodeResponse {
  ok: boolean;
}

export interface VerifyCodeResponse {
  token: string;
  /** 登录后应使用的匿名标识；手机号已绑过老账号时会是老账号的，前端要用这个覆盖本地存储 */
  external_user_id: string;
  expires_in_seconds: number;
}

export interface MeResponse {
  external_user_id: string;
  phone_number?: string | null;
  /** 有没有设过密码；前端据此显示「设置密码」还是「修改密码」。 */
  has_password?: boolean;
  consent_version?: string | null;
}

export interface AuthApiErrorBody {
  code: string;
  message: string;
}

/** 验证码用途。为登录发的码不能拿去重置密码，后端按用途分开存。 */
export type CodePurpose = "login" | "reset";

type AuthRequestOptions = { signal?: AbortSignal; baseUrl?: string };

/** /v1/auth/* 的公共调用：POST JSON，非 2xx 抛 YewneApiError(body 为 {code, message})。 */
async function postAuth<T>(
  path: string,
  payload: Record<string, unknown>,
  options: AuthRequestOptions & { token?: string } = {},
): Promise<T> {
  const base = options.baseUrl ?? API_BASE;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  const res = await fetch(`${base}/v1/auth/${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal: options.signal,
  });

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    // 204 之类没有响应体的情况走这里，不算错。
    body = undefined;
  }
  if (!res.ok) throw new YewneApiError(`HTTP ${res.status}`, res.status, unwrapDetail(body));
  return body as T;
}

/** FastAPI 把错误包在 detail 里：{"detail": {"code","message"}}。
 * 调用方只关心 {code, message}，在这里拆掉，省得每个 errorMessage() 都写 body.detail.code。
 * 422 的 detail 是数组（pydantic 校验错误），那种保持原样交给兜底文案。 */
function unwrapDetail(body: unknown): unknown {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) return detail;
  }
  return body;
}

/** 调 /v1/auth/send-code。失败时 err.body 是 {code, message}，code 取值：
 * cooldown(发送太频繁) / daily_limit(今日上限) / sms_failed(短信服务出错)。 */
export async function fetchSendCode(
  phoneNumber: string,
  options: AuthRequestOptions & { purpose?: CodePurpose } = {},
): Promise<SendCodeResponse> {
  return postAuth<SendCodeResponse>(
    "send-code",
    { phone_number: phoneNumber, purpose: options.purpose ?? "login" },
    options,
  );
}

/** 调 /v1/auth/verify-code。失败时 err.body 的 code 取值：
 * invalid_code / terms_required。 */
export async function fetchVerifyCode(
  phoneNumber: string,
  code: string,
  externalUserId: string,
  agreedToTerms: boolean,
  options: AuthRequestOptions = {},
): Promise<VerifyCodeResponse> {
  return postAuth<VerifyCodeResponse>(
    "verify-code",
    {
      phone_number: phoneNumber,
      code,
      external_user_id: externalUserId,
      agreed_to_terms: agreedToTerms,
    },
    options,
  );
}

/** 调 /v1/auth/login-password。失败时 err.body 的 code 取值：
 * invalid_credentials(手机号或密码不对——注意后端故意不区分"没注册"和"密码错")
 * / too_many_attempts(失败次数过多被锁) / terms_required。 */
export async function fetchLoginPassword(
  phoneNumber: string,
  password: string,
  externalUserId: string,
  agreedToTerms: boolean,
  options: AuthRequestOptions = {},
): Promise<VerifyCodeResponse> {
  return postAuth<VerifyCodeResponse>(
    "login-password",
    {
      phone_number: phoneNumber,
      password,
      external_user_id: externalUserId,
      agreed_to_terms: agreedToTerms,
    },
    options,
  );
}

/** 调 /v1/auth/set-password（需登录态）。首次设置 currentPassword 传 null。
 * 失败时 err.body 的 code 取值：invalid_credentials(旧密码不对) / unauthorized。 */
export async function fetchSetPassword(
  token: string,
  currentPassword: string | null,
  newPassword: string,
  options: AuthRequestOptions = {},
): Promise<void> {
  await postAuth<void>(
    "set-password",
    { current_password: currentPassword, new_password: newPassword },
    { ...options, token },
  );
}

/** 调 /v1/auth/reset-password。重置成功后直接返回 token（顺手登录，省一步）。 */
export async function fetchResetPassword(
  phoneNumber: string,
  code: string,
  newPassword: string,
  externalUserId: string,
  agreedToTerms: boolean,
  options: AuthRequestOptions = {},
): Promise<VerifyCodeResponse> {
  return postAuth<VerifyCodeResponse>(
    "reset-password",
    {
      phone_number: phoneNumber,
      code,
      new_password: newPassword,
      external_user_id: externalUserId,
      agreed_to_terms: agreedToTerms,
    },
    options,
  );
}

/** 调 /v1/auth/logout。 */
export async function fetchLogout(
  token: string,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<void> {
  const base = options.baseUrl ?? API_BASE;
  await fetch(`${base}/v1/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
    signal: options.signal,
  });
}

/** 调 /v1/auth/me；token 失效/过期时返回 null，不抛错(调用方按"未登录"处理)。 */
export async function fetchMe(
  token: string,
  options: { signal?: AbortSignal; baseUrl?: string } = {},
): Promise<MeResponse | null> {
  const base = options.baseUrl ?? API_BASE;
  try {
    const res = await fetch(`${base}/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: options.signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as MeResponse;
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
