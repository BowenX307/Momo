# MOMO

中文场景化 AI 情绪陪伴 App。

## 项目结构

```
momo/
├── apps/
│   ├── mobile/          # React Native (Expo) - 主 App
│   └── web/             # Next.js - 抢先体验页
├── services/
│   └── api/             # FastAPI 后端
├── packages/
│   └── shared-types/    # 前后端共享类型
└── docs/                # 项目文档
```

## 本地开发

### 前置要求
- Python 3.12（推荐用 `uv` 管理）
- Node.js 20+
- pnpm
- Docker Desktop（用于本地 Postgres + Redis，明天用）

### 启动后端
```bash
cd services/api
cp .env.example .env          # 第一次需要
uv sync                       # 安装依赖
uv run uvicorn app.main:app --reload
```

后端跑在 http://localhost:8000，文档在 http://localhost:8000/docs。

### 启动移动端
```bash
cd apps/mobile
pnpm install
pnpm start
```

按 `i` 启动 iOS 模拟器，或在手机用 Expo Go 扫码。

### 启动抢先体验页
```bash
cd apps/web
pnpm install
pnpm dev
```

跑在 http://localhost:3000。

## 技术栈

- **后端**：Python 3.12 + FastAPI + Pydantic + Postgres + Redis
- **移动端**：React Native (Expo) + TypeScript
- **抢先页**：Next.js + Tailwind
- **LLM**：DeepSeek（主）+ 豆包（备份）
- **部署**：阿里云 ECS + Docker

## 业务核心概念

- **场景**：用户进入时选择当前状态（深夜低落 / 情绪内耗 / 关系复盘 / 压力峰值 / 孤独陪伴）
- **人格卡**：MOMO 的稳定语气、边界、价值观
- **情景记忆**：结构化事件、情绪、触发点、回应偏好
- **回应强度**：轻回应 / 陪伴 / 复盘 / 建议 / 行动
- **聊后整理**：情绪命名 + 触发点 + 下一步轻动作
- **安全降级**：危机识别 + 现实支持引导

## 不做范围

不做医疗诊断；不做治疗承诺；不做未成年人主场景；不做角色扮演 / 剧情 / 擦边互动。

## 里程碑

- 7 月中：Beta MVP 候选版（核心对话 + 场景入口 + 基础记忆 + 聊后整理 + 安全边界）
- 7 月中-8 月中：公开 Beta，验证留存和付费意愿
- 8 月下旬：正式上线，赶在 9 月开学季前
