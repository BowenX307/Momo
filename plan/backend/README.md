# 后端计划（极简 Demo）

面向负责人：**后端**。时间目标：**下周五前**有一个「非常非常简单的 demo」——能演示「请求进 → 规则跑一遍 → 回复出」，不要求数据库、不要求完整业务。

---

## 1. 下周五的 Demo 建议长什么样（验收标准）

满足下面几条就算达标，前后端可以各跑各的、用 **Swagger `/docs`** 或 **curl** 演示即可。

| # | 验收项 | 说明 |
|---|--------|------|
| A | 服务可启动 | `uv run uvicorn app.main:app --reload`，`/health` 正常。 |
| B | 有一个「对话试玩」接口 | 例如 `POST /v1/chat/demo`：入参包含用户一句话（可选：场景 `scene` 枚举字符串）。 |
| C | 有结构化返回 | 返回 JSON：至少包含 `reply`（助手回复文本）；若有安全命中可加 `safety_flag` 等。 |
| D | 安全层占位 | 用户输入**先**过 `domain/safety` 再进 LLM；demo 阶段可以是「关键词列表 → 命中则固定降级文案、不调模型」。 |
| E | LLM 二选一即可 | **方案 1**：接好 **一个** provider（如 DeepSeek），用 `.env` 密钥，失败时有明确错误信息。**方案 2**：未接密钥时自动走 **mock 固定回复**，保证 demo 不断。 |

**刻意不做（下周五之后再说）**：Postgres、Redis、Alembic、用户登录、记忆持久化、完整人格卡与整理卡 pipeline。

---

## 2. 这段时间你应该做什么（推荐顺序）

### 阶段 A：定接口形状（半天）

1. 在 `packages/shared-types` 里（或先只在后端 Pydantic）定 **请求/响应模型**：字段名、场景枚举与前端口头对齐即可。
2. 在 `app/api/`（或 `app/domain/conversation/`）挂路由，**先在 `main.py` include_router**，保证 `/docs` 里能看到新接口。

### 阶段 B：安全占位（半天～1 天）

1. 实现 `domain/safety`：**纯函数**输入字符串 → 输出 `allow` / `fallback` + 可选原因码。
2. demo 规则示例：空输入、极短占位、危机相关关键词（用项目红线：**不医疗话术**，只做「建议联系身边信任的人 / 当地紧急电话」类固定模板）。
3. 所有后续 LLM 调用**禁止绕过**这一层（代码路径上强制先 `safety.check`）。

### 阶段 C：LLM 抽象 + 一条真链或 mock（1～2 天）

1. 在 `app/llm/` 定义接口：例如 `async def complete(messages: list[...]) -> str`（具体签名你定，但要 **async + httpx**）。
2. 实现 `DeepSeek`（或当前配置里的主模型）**一个**实现类；无 key 或 `ENV=dev` 时用 `MockProvider` 返回固定句。
3. `config` 里模型名、base URL 从环境变量读，**禁止**在业务文件里硬编码密钥。

### 阶段 D：拼对话 demo（半天～1 天）

1. `POST /v1/chat/demo`：组装 system prompt（极简：一两句角色 + 当前 `scene`），拼接 user message，调 `llm`。
2. 日志：用已有 `structlog` 打 `request_id`（可先用 UUID）、`scene`、是否 mock、是否 safety fallback（**不要打全量用户隐私原文到生产配置**；dev 可酌情）。

### 阶段 E：自测与交给前端（持续）

1. `uv run ruff format .`、`uv run mypy app`、`uv run pytest`（可先写 **1～2 个**接口测试：safety 命中、mock 回复）。
2. 把 **curl 示例** 或 `/docs` 截图发给前端；约定 base URL（本地 `http://127.0.0.1:8000`）。

---

## 3. 按日节奏（可按你本周实际工作日平移）

| 日 | 重点 |
|----|------|
| 1 | 路由 + Pydantic 入参出参 + `/docs` 可见；safety 函数骨架。 |
| 2 | safety 规则 + 单测；LLM 接口抽象 + MockProvider。 |
| 3 | 真 provider 接通（或决定 demo 仅用 mock）；`POST /v1/chat/demo` 打通。 |
| 4 | 错误处理、日志、与前端对齐字段；补测试。 |
| 5 | 缓冲：联调、修 CORS（若前端跨域）、文档一句话写进根 `README` 或本文件「Demo 调用方式」。 |

若只有 3 个工作日：**砍掉真 LLM**，只留 mock + safety，仍算有效 demo，下周五再换真模型。

---

## 4. 风险清单（提前知道就不慌）

- **密钥与计费**：DeepSeek 等 key 只放 `.env`；demo 别在公网暴露无鉴权接口太久，或只本机演示。
- **CORS**：前端若从浏览器打另一个端口，需在 `settings.cors_origins` 里加 `http://localhost:3000` 等（你已在 dev 用 `*`，一般可先不管）。
- **依赖模型升级**：先固定 `httpx` 超时与重试策略别搞太复杂，demo 超时 30s 内即可。

---

## 5. 与仓库约定的对齐点

见仓库根目录 `.cursorrules`：**异步 httpx**、**LLM 只走 `app/llm/`**、**用户与模型输出经 safety**。下周五 demo 宁可简单，也不要在 `router` 里直接 `import openai_sdk`。

---

## 6. Demo 之后（ backlog 占位，不必下周五完成）

- Postgres + SQLAlchemy / Alembic，用户与会话表。
- Redis 会话或限流。
- 正式 `conversation` / `memory` / `reflection` 领域拆分与 id 设计。
- 阿里云内容安全接入 production path。

若你下周五的「demo」还必须包含某一项（例如**一定要真模型**、或**一定要给前端一个固定 path**），在本文件末尾自己加一节「硬需求」，避免和前端期望打架。
