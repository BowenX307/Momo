# 于你 Yewne — 开发者说明

> 项目原名 uni / MOMO,因商标注册于 2026-07 更名为**于你 Yewne**(仓库目录名仍为 momo)。

## 仓库目录

```
momo/
├── apps/
│   ├── mobile/          # 手机 App（React Native + Expo）
│   └── web/             # 网站抢先体验页（Next.js）
├── services/
│   └── api/             # 后端 API（Python + FastAPI）
├── packages/
│   └── shared-types/    # 前后端共用的 TypeScript 类型（逐步充实）
└── docs/                # 项目文档（非工程说明多在这里）
```

**mobile / web 是客户端**，**api 是服务端**；它们通过 **HTTP + JSON** 对话。

---

## 安装


| 工具                 | 作用（用人话）                                                                                                                                                                    |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Homebrew**       | Mac 上用一条命令装其它软件，官网：[https://brew.sh](https://brew.sh)                                                                                                                      |
| **Node.js**        | 跑 JavaScript/TypeScript 前端；官网 LTS 或用 `fnm` / `nvm` 管理多版本。                                                                                                                  |
| **pnpm**           | **包管理器**：下载 `apps/mobile`、`apps/web` 依赖，比默认 `npm` 省磁盘、速度快。安装见：[https://pnpm.io/installation](https://pnpm.io/installation)                                                 |
| **Python 3.12+**   | 跑后端；若已装系统 Python，仍建议用 **uv** 隔离本项目环境（见下文）。                                                                                                                                 |
| **uv**             | **Python 依赖与虚拟环境管理**：一条命令装好后端库、创建独立环境，避免搞乱系统 Python。安装见：[https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/) |
| **Docker Desktop** | 可选。用于通过根目录 `compose.yaml` 统一启动 PostgreSQL；只测试聊天且关闭 persistence 时无需安装。                                                                                                        |
| **Git**            | 版本控制；与 GitHub 同步代码。                                                                                                                                                        |
| **编辑器**            | 推荐 VS Code 或 Cursor；装 TypeScript、Python、ESLint 等插件会更顺手。                                                                                                                    |


---

## 作用简述

### 前端：Node、pnpm、Expo / Next.js

- **Node.js**：执行 JavaScript/TypeScript 的运行时。前端工具链（打包、开发服务器）都跑在 Node 上。
- **pnpm**：**只负责「装依赖 + 跑脚本」**（例如 `pnpm install`、`pnpm start`）。依赖列表在各子项目的 `package.json` 里。
- **Expo**：在 `**apps/mobile`** 里。**React Native** 做原生界面；Expo 提供开发服务器、热更新、与模拟器/真机通信的脚手架。你改手机 App 时主要在这一目录活动。
- **Next.js**：在 `**apps/web`** 里。用 **React** 做网页，Next 负责路由、本地开发服务器、构建上线版本。抢先体验页跑在这里。

### 后端：Python、uv、FastAPI、`/docs`

- **Python**：后端语言；业务逻辑、接数据库、调 LLM 等最终都在这里执行。
- **uv**：在 `**services/api`** 里执行 `uv sync` 会按 `pyproject.toml` 安装依赖，并管理**独立虚拟环境**，避免和别的项目冲突。
- **FastAPI**：**Web 框架**：把「某个 URL + HTTP 方法」映射到 Python 函数，自动校验入参、生成 **OpenAPI** 文档。入口在 `services/api/app/main.py`。
- `**/docs`**：后端本地跑起来后，浏览器打开 **[http://localhost:8000/docs](http://localhost:8000/docs)** 是 **Swagger UI**，可试请求、看字段说明。前后端对齐接口时很有用。

### 数据库 Postgres 与 Redis

- **Postgres**：关系型数据库，当前保存匿名用户、聊天会话和消息。
- **Redis**：内存数据库，常做缓存、队列、会话（规划中）。

持久化由 `PERSISTENCE_ENABLED` 控制：

- `false`：完全跳过 PostgreSQL，未安装数据库也能聊天。
- `true`：保存用户、会话和消息，需要可用的 PostgreSQL，并先执行 Alembic migration。

---

## 本地怎么跑起来（复制命令即可）

### 1. 克隆仓库（第一次）

```bash
git clone <你的 GitHub 仓库 HTTPS 或 SSH 地址>
cd momo
```

### 2. 后端 `services/api`

```bash
cd services/api
cp .env.example .env
# 按需编辑 .env（API Key 等秘钥不要提交进 Git）
uv sync
uv run uvicorn app.main:app --reload
```

- 默认：**[http://localhost:8000](http://localhost:8000)**
- 健康检查：**[http://localhost:8000/health](http://localhost:8000/health)**
- 接口文档：**[http://localhost:8000/docs](http://localhost:8000/docs)**

只测试聊天、不保存数据时，保持：

```env
PERSISTENCE_ENABLED=false
```

## 使用 Docker 运行 PostgreSQL

安装 Docker Desktop 后，不需要再单独安装 PostgreSQL。

### 1. 启动数据库

```bash
# 仓库根目录
docker compose up -d db
docker compose ps
```

看到状态为 `healthy` 后继续。

### 2. 配置后端

```bash
cd services/api
cp .env.example .env
```

确认 `.env` 中有：

```env
PERSISTENCE_ENABLED=true
DATABASE_URL=postgresql+psycopg://yewne:yewne_dev_password@localhost:5432/yewne_dev
```

安装依赖、创建表并启动后端：

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### 3. 检查连接

```bash
curl http://127.0.0.1:8000/health
```

响应中的 `persistence_enabled` 和 `database_connected` 都应为 `true`。

浏览器一次打开到关闭视为一个会话。一个会话内部可以有多次问答；每位匿名用户在 PostgreSQL 中最多保留最近 7 个会话，创建第 8 个会话时会删除最早的会话及其消息。单条消息最多 2000 个字符。

### 4. 查看数据

```bash
docker compose exec db psql -U yewne -d yewne_dev
```

```sql
\dt
SELECT id, user_id, created_at FROM conversations ORDER BY created_at DESC;
SELECT role, content, created_at FROM messages ORDER BY created_at DESC LIMIT 20;
\q
```

### 5. 停止或重启

```bash
docker compose stop db
docker compose start db
docker compose down
```

以上命令不会删除数据。只有确定要清空本地数据库时才执行：

```bash
docker compose down -v
```

### 常见问题

- **端口 5432 被占用**：关闭本机 PostgreSQL，或把 Docker 端口和 `DATABASE_URL` 一起改成 `5433`。
- **聊天正常但没有数据**：检查 `PERSISTENCE_ENABLED=true`、`database_connected=true`，以及前端请求是否带有 `external_user_id`。
- **提示表不存在**：在 `services/api` 中执行 `uv run alembic upgrade head`。
- **不保存聊天数据**：设置 `PERSISTENCE_ENABLED=false`，不需要启动 PostgreSQL。

后端质量检查（改 Python 时建议跑）：

```bash
cd services/api
uv run ruff format .
uv run mypy app
uv run pytest
```

### 3. 手机 App `apps/mobile`

另开一个终端：

```bash
cd apps/mobile
pnpm install
pnpm start
```

终端里按 `**i**` 打开 **iOS 模拟器**；或用手机 **Expo Go** 扫终端里的二维码。

### 4. 抢先体验页 `apps/web`

再开一个终端：

```bash
cd apps/web
pnpm install
pnpm dev
```

浏览器打开 **[http://localhost:3000](http://localhost:3000)**。

---

## GitHub 协作方式

1. **主分支**（一般是 `main`）保持稳定；日常开发在**自己的分支**，例如 `feat/your-name-short-desc`。
2. 改完 → **commit** → **push** 到你的分支 → 在 GitHub 上开 **Pull Request**。
3. **项目负责人**审核后合并；合并前可能会要求你小改或补跑测试。

---

## 文件


| 你想做…         | 优先看的目录                                   |
| ------------ | ---------------------------------------- |
| 手机界面与交互      | `apps/mobile/`                           |
| 官网 / 落地页     | `apps/web/`                              |
| 接口、鉴权、和模型打交道 | `services/api/app/`（按 `domain/` 等业务文件夹找） |
| 前后端共用的类型名、枚举 | `packages/shared-types/`                 |


---

## 技术栈一览（对照用）


| 层级    | 技术                                                   |
| ----- | ---------------------------------------------------- |
| 移动端   | React Native（Expo）、TypeScript、Zustand、TanStack Query |
| 网页    | Next.js、React、TypeScript、Tailwind CSS                |
| 后端    | Python 3.12、FastAPI、Pydantic、uvicorn                 |
| 数据与缓存 | Postgres、Redis（环境与配置已预留，业务接入进行中）                     |
| LLM   | 通过配置接入（如 DeepSeek / 豆包）；秘钥只放 `.env`                  |
