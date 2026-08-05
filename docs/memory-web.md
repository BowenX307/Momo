# 于你 Yewne Web 记忆接口说明

本文面向 Web 前端开发，说明如何读取记忆状态、开启或关闭一段会话的记忆，以及后续聊天如何使用记忆。页面布局和具体交互样式由前端决定。

## 工作流程

```text
用户结束一段登录后的对话
  -> 会话进入 closed 状态
  -> 前端读取往期会话及其 memory_status
  -> 用户主动选择是否记住该会话
  -> 后端生成并保存摘要
  -> 后续聊天自动加载已启用且 ready 的摘要
```

前端不保存摘要，也不需要在聊天请求中传入记忆。后端根据登录 token 自动查找当前用户可用的记忆，并注入模型上下文。

## 前端封装

所有请求和类型都在：

```text
apps/web/lib/api/yewne.ts
```

页面代码应调用这里导出的函数，不要自行拼接接口 URL 或读取登录 token：

```ts
import {
  fetchRounds,
  updateRoundMemory,
  YewneApiError,
  type MemorySelectionResponse,
  type MemoryStatus,
  type RoundSummary,
} from "@/lib/api/yewne";
```

```ts
export type MemoryStatus = "pending" | "ready" | "failed" | "stale";

export interface MemorySelectionResponse {
  conversation_id: string;
  include_in_memory: boolean;
  memory_status: MemoryStatus | null;
}
```

`updateRoundMemory()` 会自动使用 `yewne:auth-token`，添加 `Authorization: Bearer <token>`，并把非 2xx 响应包装为 `YewneApiError`。

## 读取往期会话

前端调用：

```ts
const rounds = await fetchRounds(externalUserId);
```

对应接口：

```http
GET /v1/conversation/rounds?external_user_id={externalUserId}
Authorization: Bearer <token>
```

每个会话包含：

```json
{
  "conversation_id": "6c28eb25-5e7e-48fe-bad3-24780...",
  "persona": "nini",
  "status": "closed",
  "close_reason": "user_end",
  "include_in_memory": true,
  "memory_status": "ready",
  "created_at": "2026-08-05T10:00:00+00:00",
  "ended_at": "2026-08-05T10:20:00+00:00"
}
```

登录请求以 token 对应的用户身份为准。即使查询参数中的 `external_user_id` 与 token 不一致，后端也只返回 token 所属用户的数据。

## 开启或关闭记忆

### 开启

```ts
const result = await updateRoundMemory(conversationId, true);
```

### 关闭

```ts
const result = await updateRoundMemory(conversationId, false);
```

对应接口：

```http
PATCH /v1/conversation/rounds/{conversationId}/memory
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "enabled": true
}
```

响应示例：

```json
{
  "conversation_id": "6c28eb25-5e7e-48fe-bad3-24780...",
  "include_in_memory": true,
  "memory_status": "ready"
}
```

当前摘要生成在 PATCH 请求内同步完成，请求可能持续数秒。前端应防止同一会话被重复提交，并支持通过 `AbortSignal` 取消本地等待：

```ts
const controller = new AbortController();

await updateRoundMemory(conversationId, true, {
  signal: controller.signal,
});
```

取消浏览器请求不保证服务端同时终止摘要生成，之后应重新调用 `fetchRounds()` 获取服务端最终状态。

## 状态含义

| `include_in_memory` | `memory_status` | 含义 |
|---|---|---|
| `false` | `null` | 从未生成过摘要 |
| `true` | `pending` | 正在生成摘要，暂时不会注入聊天 |
| `true` | `ready` | 摘要可用，后续聊天会自动使用 |
| `true` | `failed` | 摘要生成失败，不会注入聊天；可再次开启重试 |
| `true` | `stale` | 预留状态：原会话内容变化后，摘要需要重新生成 |
| `false` | `ready` | 摘要仍保留，但已停用，不会注入聊天 |

关闭记忆只会把 `include_in_memory` 改为 `false`，不会删除已经生成的摘要。再次开启时，如果摘要仍然有效，后端会直接复用。

只有同时满足以下条件的摘要才会进入后续聊天：

```text
include_in_memory = true
memory_status = ready
会话未被删除
```

## 错误处理

`updateRoundMemory()` 失败时会抛出 `YewneApiError`：

```ts
try {
  await updateRoundMemory(conversationId, true);
} catch (error) {
  if (error instanceof YewneApiError) {
    console.log(error.status, error.body);
  }
}
```

| HTTP 状态 | 含义 | 前端处理建议 |
|---|---|---|
| `401` | 未登录或 token 已失效 | 引导重新登录 |
| `403` | 用户尚未同意数据协议 | 回到协议确认流程 |
| `404` | 会话不存在或不属于当前用户 | 刷新会话列表 |
| `409` | 会话仍在进行，尚未关闭 | 不允许开启记忆 |
| `422` | 请求参数格式错误 | 记录错误并检查调用代码 |

摘要供应商调用失败不会返回 HTTP 500。接口会正常返回 200，但 `memory_status` 为 `failed`，前端应按业务失败处理。

## 后续聊天

记忆开启后，原有聊天调用保持不变：

```ts
await fetchChatDemo({
  user_text: input,
  external_user_id: externalUserId,
  conversation_id: conversationId,
  persona,
  history,
});
```

前端不要新增 `memory`、`memory_context` 或摘要字段。后端会根据请求中的登录 token 自动读取该用户所有已启用且状态为 `ready` 的记忆。

## 本地联调

本地前端默认使用 `http://127.0.0.1:8000`。后端 CORS 需要允许：

```env
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

联调顺序：

1. 登录并勾选数据协议。
2. 完成一段对话并结束该轮，使会话状态变为 `closed`。
3. 调用 `fetchRounds()` 获取 `conversation_id`。
4. 调用 `updateRoundMemory(conversationId, true)`。
5. 确认响应为 `include_in_memory: true` 和 `memory_status: ready`。
6. 开始一段新会话，验证模型能够在相关问题中参考旧会话摘要。

## 当前边界

- 记忆只属于登录并同意数据协议的用户，游客不保存也不加载记忆。
- 用户必须主动选择会话，系统不会默认把所有会话加入记忆。
- 当前免费用户最多保留 7 个有效会话。
- 摘要由后端保存到 PostgreSQL，前端 localStorage 只负责当前浏览器会话续接，不是长期记忆来源。
- 前端页面中的开关位置、文案、加载效果和错误提示不属于本接口文件的职责。
