# AIxCTF 自动解题系统

本项目是一个基于 OpenCode 多 Agent 能力的 AIxCTF 比赛自动解题系统。任何在本项目内工作的 agent 都必须先阅读本文件，遵守其中的共享协议。

## 角色分工

| 角色 | 类型 | 职责 |
| --- | --- | --- |
| CTF-Customer | primary（默认 agent） | 与用户聊天、汇报进度、把用户指令写入 `state/REQUESTS.md` |
| CTF-Master | primary（也可被 Customer 以 Task 调起） | 维护全局状态、派发 ctf-sliver、统一管理动态环境与 flag 提交 |
| CTF-Sliver | subagent（hidden） | 单题解题执行单元：本地分析、写 exploit、产出 flag 或结构化报告 |

链式关系：用户 ⇄ CTF-Customer →（REQUESTS.md / Task）→ CTF-Master →（Task，可并行多个）→ CTF-Sliver。

## 题目范围与策略

- **只做 pwn 和 web**，其它分类一律跳过。
- **pwn**：本地可解，**并行**派发多个 sliver 做本地分析（默认最多 3 个并行，用户可在 REQUESTS.md 调整）；exploit 本地验证通过后再去**抢占环境**：开启环境 → 远程打 → 提交 flag → **立即归还环境**，然后再继续解其它题。若 pwn 题需要环境才能继续分析，也走"抢占-使用-归还"流程，绝不久占。
- **web**：按 `current_score` **从低到高**串行解题，一题一清（开环境 → 攻击 → 提交 → 还环境 → 下一题）。
- 平台动态环境资源有限：**任意时刻最多开启 1 个环境**，由 Master 统一仲裁。

## 平台 MCP（aixctf-challenge）使用规范

- 工具：`list_challenges` / `get_challenge` / `start_challenge` / `stop_challenge` / `view_hint` / `submit_flag`。
- **只有 CTF-Master** 可调用 `start_challenge` / `stop_challenge` / `submit_flag` / `view_hint`（已在配置层面对其它角色禁用）。
- `view_hint` 会扣分（该题后续按 80% 结算），必须有用户在 REQUESTS.md 中的明确授权才可调用。
- **附件下载**：MCP 不传附件内容。先 `get_challenge` 拿 `attachments[].download_url`（相对路径），再用 curl 下载：
  ```bash
  curl -sSL -H "Authorization: Bearer $TEAM_AGENT_KEY" "$CHALLENGE_API_ENDPOINT<download_url>" -o <本地路径>
  ```
- Web 题入口：`start_challenge` 返回的 `url` + `headers`，所有请求必须携带这些 headers。
- Pwn 题入口：`start_challenge` 返回的 `tcp.host` / `tcp.port` / `tcp.handshake`。

## 其它 MCP

- **ghidra**（pyghidra-mcp，headless）：pwn 二进制反编译/符号/字符串/交叉引用分析。用 `import_binary` 导入 `work/<id>/` 下的二进制后用 `binary_name` 引用。需要环境变量 `GHIDRA_INSTALL_DIR`。
- **chrome**（chrome-devtools-mcp）：web 题的浏览器交互（JS 渲染、前端调试）。需要自定义请求头的访问一律改用 curl/requests。

## 目录与状态文件协议

```
├── state/
│   ├── SCOREBOARD.md      # 题目总表，Master 维护，其它角色只读
│   ├── ENVIRONMENTS.md    # 动态环境登记，Master 维护，其它角色只读
│   └── REQUESTS.md        # 用户指令队列，Customer 写入，Master 读取并标记完成
├── notes/                 # 每题一份笔记：<id>-<题名>.md，sliver 写入
├── work/                  # 每题一个工作目录：work/<id>/（附件、exploit、临时文件）
├── prompts/               # 三个角色的系统提示词 + kickoff
└── opencode.json          # agent 与 MCP 配置
```

- `SCOREBOARD.md` 状态枚举：`TODO / ANALYZING / LOCAL_READY / ATTACKING / SOLVED / BLOCKED / STUCK / SKIP`。
- 所有角色对状态文件的写入遵循上表归属，越权写入会破坏多进程协作。
- 每个写操作保持**追加优先**，不要整表重写覆盖他人刚写的内容。

## 得分规则（来自平台文档）

- `get_challenge` 的 `current_score`：下一次正确提交可得分数；查看提示后按 80% 结算。
- 名次倍率：第 1 名 120%，第 2 名 110%，第 3 名 105%，4-10 名 100%，11-20 名 80%，21-35 名 60%，36-50 名 40%，51 名及以后 20%。
- 策略含义：**快比完美重要**——尽快提交拿到高名次倍率；hint 代价大，慎用。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `TEAM_AGENT_KEY` | 平台 Agent Key（Bearer Token），下载附件也要用 |
| `CHALLENGE_API_ENDPOINT` | 题目服务器 Agent API 端点（MCP 地址为其下 `/mcp`） |
| `GHIDRA_INSTALL_DIR` | Ghidra 安装目录（pyghidra-mcp 需要） |

启动 opencode 前必须在 shell 中 export 这三个变量（见 README.md）。
