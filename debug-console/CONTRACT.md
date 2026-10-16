# AIxCTF 调试控制台 —— 前后端接口契约

本文档是 debug-console 前端（`debug-console/web`）与本地服务端（`debug-console/server.py`）之间的唯一接口依据。容器侧 debug-agent 与 server 的协议也列在此处供参考。

## 角色与连接拓扑

```
浏览器 ──WS /ui──> 本地 debug-console server <──WS /agent── 容器内 debug-agent（反向连接）
浏览器 ──HTTP──> server 静态页 + /api/models
```

- server 监听 `0.0.0.0:8790`（可用 `DEBUG_PORT` 环境变量改）。
- 容器 agent 连接 `WS /agent?token=<token>`；浏览器连接 `WS /ui`（无鉴权，仅本机使用）。
- server 缓存最近一次 snapshot 与全部 activity，浏览器后连也能补齐数据。

## 浏览器 ↔ server（WS /ui）

### server → 浏览器

```jsonc
// 连接建立后立即推送
{"type": "status", "agent_connected": true, "agent_hostname": "ctf-01", "last_seen": 1730000000.0}

// 全量快照（容器状态变化时推送；浏览器连接时若有缓存也立即推送）
{"type": "snapshot", "payload": {
  "master": {"session_id": "ses_x", "status": "running", "last_activity": 1730000000.0},
  "challenges": [
    {"id": 8, "name": "demo-pwn", "category": "pwn", "score": 500, "current_score": 500, "status": "ANALYZING"}
  ],
  "slivers": [
    {"session_id": "ses_a", "challenge_id": 8, "status": "active", "title": "...", "last_activity": 1730000000.0}
  ],
  "scoreboard_md": "# 比赛记分板\n…原文…",
  "environments_md": "…原文…",
  "requests_md": "…原文…",
  "model": {"current": "oai-compat/gpt-4o-mini", "pending": null}
}}

// 某个 sliver/master 会话的活动记录（"API 请求记录"），增量批量推送
{"type": "activity", "session_id": "ses_a", "challenge_id": 8, "entries": [
  {"id": "msg_1.0", "ts": 1730000000.0, "kind": "tool", "tool": "bash", "title": "bash", "preview": "curl -sSL -H ...（恰好200字符截断）"},
  {"id": "msg_2.0", "ts": 1730000001.0, "kind": "text", "tool": null, "title": "回复", "preview": "我先分析…"},
  {"id": "msg_3.0", "ts": 1730000002.0, "kind": "reasoning", "tool": null, "title": "思考", "preview": "…"},
  {"id": "msg_4.0", "ts": 1730000003.0, "kind": "user", "tool": null, "title": "派发指令", "preview": "…"}
]}

// 客服回复
{"type": "chat_reply", "req_id": "r1", "text": "当前进度：……", "ts": 1730000000.0}

// 模型状态变化
{"type": "model_state", "current": "oai-compat/gpt-4o-mini", "pending": "oai-compat/gpt-4o"}

// 通用错误
{"type": "error", "message": "..."}
```

`kind` 枚举：`tool`（工具调用，重点展示）、`text`（模型回复）、`reasoning`（思考）、`user`（派发指令/用户消息）。
`preview` 固定为**前 200 个字符**的纯文本（工具调用为 `工具名 + 输入JSON` 的截断）。
`status` 枚举（slivers）：`active`（最近 120s 内有新活动）/ `idle` / `finished`。
`challenge.status` 沿用记分板：`TODO/ANALYZING/LOCAL_READY/ATTACKING/SOLVED/BLOCKED/STUCK/SKIP`。

### 浏览器 → server

```jsonc
{"type": "chat", "req_id": "r1", "text": "现在进度如何"}
{"type": "set_model", "base_url": "https://api.example.com/v1", "api_key": "sk-...", "model": "gpt-4o-mini"}
{"type": "restart_master"}
{"type": "get_activities", "session_id": "ses_a"}   // 拉取某会话全量活动（server 回 activity 消息）
```

## HTTP

- `GET /` → 前端页面（`static/index.html`）
- `GET /api/models?base_url=<url>&api_key=<key>` → 代理请求 `<base_url>/models`，返回 `{"models": ["gpt-4o", ...]}`；失败 `{"models": [], "error": "..."}`

## 容器 agent ↔ server（WS /agent?token=）

agent → server：`hello` / `snapshot` / `activity` / `chat_reply` / `model_state`（结构同上，hello 带 hostname）。
server → agent：`chat` / `set_model` / `restart_master`（结构同上）。
agent 行为约定：收到 `set_model` 后改写容器内 `/app/opencode.json` 的 provider+model，回复 `model_state{current: 旧值, pending: 新值}`；模型在下轮 Master 重启后生效。收到 `chat` 后转发给容器内 opencode serve 的 ctf-customer 会话，同步等待回复后回 `chat_reply`（可能耗时数十秒，前端需显示"正在输入"）。
