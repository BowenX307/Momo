# MOMO Web 记忆设计

## 目标

Web 版对话在刷新页面后不丢失上下文。用户回来继续说，MOMO 还记得上一次聊到哪里。

---

## 现状

`page.tsx` 里已有 `history` state，每轮把最近 20 条消息传给后端 LLM。  
问题：纯 React state，刷新即清零。

---

## 方案：localStorage 持久化

不需要数据库，不需要用户登录，前端改动约 40 行。

### 存什么

```ts
interface PersistedSession {
  history: HistoryMessage[];   // 最近 10 轮对话（20 条消息）
  scene: Scene | null;         // 已锁定的场景分类
  turns: ConvTurn[];           // 用于页面气泡展示的对话记录
  savedAt: number;             // 时间戳，用于过期判断
}
```

key 固定为 `momo:session`。

### 读写时机

| 时机 | 操作 |
|---|---|
| 页面加载 | 读 localStorage，恢复 history / scene / turns |
| 每轮对话完成 | 把最新 history 写回 localStorage |
| 用户手动清空 | 删除 localStorage key，重置所有 state |
| 距上次对话超过 24h | 自动丢弃（避免带着很久以前的上下文） |

### 容量控制

- 保留最近 **10 轮**（20 条消息）
- 超出时从头部截断，保留最新的
- 单条消息过长（> 500 字）时截断存储，避免 localStorage 超限（5MB）

---

## 实现位置

所有持久化逻辑封装在一个独立文件：

```
apps/web/lib/session/persistSession.ts
```

对外暴露三个函数：

```ts
// 读取，页面加载时调用一次
function loadSession(): PersistedSession | null

// 写入，每轮对话后调用
function saveSession(session: PersistedSession): void

// 清空，用户主动重置时调用
function clearSession(): void
```

`page.tsx` 只调用这三个函数，不直接碰 localStorage。

---

## 过期策略

```ts
const SESSION_TTL_MS = 24 * 60 * 60 * 1000; // 24 小时

function loadSession(): PersistedSession | null {
  const raw = localStorage.getItem("momo:session");
  if (!raw) return null;
  const session = JSON.parse(raw) as PersistedSession;
  if (Date.now() - session.savedAt > SESSION_TTL_MS) {
    localStorage.removeItem("momo:session");
    return null;
  }
  return session;
}
```

---

## UI 变化

### 恢复提示

页面加载时若有历史记录，在输入框上方轻提示：

```
上次聊到这里 · 2小时前   [重新开始]
```

点「重新开始」调用 `clearSession()`，重置所有状态。

### 其他

- 历史气泡正常展示（已有），无需额外改动
- 无需新增设置页或开关，行为默认开启

---

## 后端影响

**零改动。**

`history` 依然是前端组装好传过去的数组，后端不感知存储层。

---

## 实现顺序

1. 新建 `apps/web/lib/session/persistSession.ts`，实现三个函数
2. `page.tsx` 加载时调用 `loadSession()`，恢复 state
3. 每轮对话完成后调用 `saveSession()`
4. 加「重新开始」按钮，调用 `clearSession()`
5. 加过期提示文字

预计改动量：`persistSession.ts` 约 60 行，`page.tsx` 约 20 行。

---

## 和 Mobile 长期记忆的关系

Web localStorage 是单设备、短期的临时方案。  
Mobile 长期记忆会用数据库 + 用户身份，两套体系独立，不冲突。  
未来如果 Web 也要跨设备同步，直接把 localStorage 换成 API 调用即可，`persistSession.ts` 的接口不需要变。
