# MOMO 


## 这个项目是什么

**MOMO** 是一个面向中文用户的情绪陪伴 AI App。

不是心理治疗，不是泛聊机器人——**只做"有人在"这件事**：用户说出心情，MOMO 用温暖但不油腻的语言接住，帮 ta 命名情绪、打断内耗循环、在孤独时陪着。

现在处于 **Demo 阶段**：核心链路跑通（前端↔后端↔DeepSeek LLM），数据库和多账号体系还没接进来。

---

## 仓库结构（三分钟版）

```
momo/
├── apps/web/          # Next.js 网页 Demo（你改前端在这里）
├── apps/mobile/       # React Native App（移动端，暂时最低优先）
├── services/api/      # FastAPI 后端（你改 AI 回答/接口在这里）
├── packages/          # 前后端共用类型（目前很小）
└── docs/              # 文档（就是这里）
```

**你最常去的两个地方：**

| 想改什么 | 去哪里 |
|---|---|
| AI 的回答语气/逻辑 | `services/api/app/llm/deepseek.py`（system prompt 在这里） |
| 新增/修改接口字段 | `services/api/app/domain/conversation/schemas.py` |
| 接口编排逻辑（safety→LLM→返回） | `services/api/app/domain/conversation/service.py` |
| 危机关键词/安全规则 | `services/api/app/domain/safety/rules.py` |
| Demo 页面 UI | `apps/web/app/demo/page.tsx` |
| 前端 API 类型/请求封装 | `apps/web/lib/api/momo.ts` |

---

## 本地跑起来（复制粘贴即可）

### 前提：装好这些工具

- **Node.js**（LTS 版）+ **pnpm**：`npm install -g pnpm`
- **Python 3.12+** + **uv**：`curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Git**

### 第一步：克隆仓库

```bash
git clone <GitHub 仓库地址>
cd momo
```

### 第二步：启动后端

```bash
cd services/api
cp .env.example .env
# 用编辑器打开 .env，填入 DEEPSEEK_API_KEY（问项目负责人要）
uv sync
uv run uvicorn app.main:app --reload
```

后端跑在 **http://localhost:8000**
- 接口文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

> **没有 API Key？** 不填 key 也能跑，会自动降级到 Mock 模式，AI 回复是固定模板，能测前后端通路。

### 第三步：启动前端 Demo 页

另开一个终端：

```bash
cd apps/web
pnpm install
pnpm dev
```

浏览器打开 **http://localhost:3000/demo**

---

## 这条请求是怎么走的

```
用户输入 → 前端 POST /v1/chat/demo
         → 安全层（safety/rules.py）：检查危机关键词
             命中 → 直接返回固定降级文案，不进 LLM
             通过 → DeepSeek LLM（带 system prompt + 历史上下文）
                      成功 → 返回 AI 回复
                      失败 → 降级到 MockProvider，reply 照常返回，degraded=true
```

**5 个场景**（scene 字段）：`late_night` / `rumination` / `relationship` / `stress` / `loneliness`

每个场景有独立的 system prompt 指令，告诉 MOMO 这个场景下优先做什么。

---

## 改代码的流程

1. **从 `main` 拉一个自己的分支**：`git checkout -b feat/你的名字-简短描述`
2. 改代码
3. 后端改完先跑测试：`cd services/api && uv run pytest`
4. `git add` → `git commit` → `git push`
5. 在 GitHub 上开 **Pull Request**，指派项目负责人 review

> **原则**：不直接 push main。哪怕是一行改动，也开 PR。

---

## 几条重要的红线（不能违反）

1. **不在 AI 回复里出现** "治疗""诊断""药物""急救"等医疗措辞
2. **不给用户列行动清单**（"你应该做 A/B/C"）——先陪，后建议
3. **危机表达**（自杀/自残/想死）必须走 safety 层固定文案，不进 LLM
4. **API Key 绝对不提交进 Git**——只放 `.env`，已在 `.gitignore`

---

## 遇到问题？

- 后端报错先看终端日志（structlog 格式，JSON key 很清晰）
- 接口字段不匹配先看 http://localhost:8000/docs
- 不确定的事情直接问团队群
