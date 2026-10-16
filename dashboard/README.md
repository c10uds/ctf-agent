# AIxCTF 观测台（dashboard）

基于 [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin) 模板裁剪：保留 sidebar / layout /
shadcn/ui 组件与主题，删掉 demo 页与 Clerk 认证，接上 AIxCTF 的观测 API。

## 开发

```bash
npm install
npm run dev        # Vite dev server，/api 已 proxy 到本地 gateway(8791)
```

## 构建（由 gateway 托管）

```bash
npm run build      # 产出 dist/，gateway 用 --static dashboard/dist 托管
npm run typecheck  # tsc -b
```

> 注意：若 shell 里有 `NODE_ENV=production`，`npm install` 会跳过 devDependencies（没有 tsc / vite 插件）。
> 用 `NODE_ENV=development npm install --include=dev`。

## 页面

| 路由 | 内容 |
| --- | --- |
| `/` | 总览：容器指标、Worker 进程、最近 AI 活动、环境 |
| `/challenges` | 题目表（来自 state/SCOREBOARD.md） |
| `/challenges/$id` | 单题：AI 请求流 / notes.md / run.log / 进程 |
| `/master` | Master 的决策流（agent=master 的 AI 请求） |
| `/environments` | 环境台账 + 申请队列 |
| `/chat` | 与 ctf-customer 对话（操作仍由 customer 写 REQUESTS.md） |

## 数据来源（gateway 提供）

- `GET /api/snapshot`：首屏快照
- `GET /api/stream`：SSE 实时事件（`hello` / `metrics` / `proc` / `env` / `scoreboard` / `fs` /
  `llm_req` / `llm_resp` / `chat`，连接时另有一次 `snapshot` 与 `replay`）
- `GET /api/history?topic=&limit=`：历史查询
- `POST /api/chat {text}`：向容器内 customer 发消息

## 技术栈

Shadcn UI（Tailwind v4 + Radix）、Vite、TanStack Router、TypeScript、Zustand、Lucide Icons。
