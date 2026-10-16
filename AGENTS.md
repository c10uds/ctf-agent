# AIxCTF 自动解题系统

本项目是一个基于 OpenCode 多 Agent 能力的 AIxCTF 比赛自动解题系统。任何在本项目内工作的 agent 都必须先阅读本文件，遵守其中的共享协议。

## 角色分工

| 角色 | 形态 | 职责 |
| --- | --- | --- |
| CTF-Customer | primary（本地默认 agent） | 与用户聊天、汇报进度、把用户指令写入 `state/REQUESTS.md` |
| CTF-Master | primary（容器内由 entrypoint 常驻拉起） | 维护全局状态、派发/续跑 worker 进程、统一仲裁动态环境、记账 flag 提交结果 |
| CTF-Worker | primary（每题一个独立进程，由 Master 用 `opencode run --agent ctf-worker` 拉起） | 单题解题：本地分析、写 exploit、远程攻击、自行提交 flag |

协作链路：**进程编排**——Master 通过后台进程派发 worker（不是 Task 子代理）：

```
用户 ⇄ CTF-Customer →（state/REQUESTS.md）→ CTF-Master
                                              │  cd work/<id>/ && nohup opencode run --agent ctf-worker ... > run.log &
                                              ▼
                                    CTF-Worker × N（每题一个目录、一个持续会话，-c 续跑）
```

## 题目范围与策略

- **只做 pwn 和 web**，其它分类一律跳过（SCOREBOARD 标 SKIP）。
- **pwn**：本地可解，**并行**派发多个 worker 做本地分析（默认最多 3 个，用户可在 REQUESTS.md 调整）；exploit 本地验证通过后申请环境：抢占 → 远程打 → worker 自行提交 flag → 归还环境。
- **web**：按 `current_score` **从低到高**串行解题（需全程持有环境）。
- 平台动态环境为稀缺资源：**默认任意时刻最多 1 个环境**（`ENV_LIMIT`），由 Master 统一仲裁。

## 环境申请与抢占协议

- worker **禁止**调用 `start_challenge`/`stop_challenge`（配置层禁用）。需要环境时：写申请文件 `state/env-requests/<id>.req`（challenge_id/category/type/requested_at）→ 输出 WORKER-REPORT → 结束本轮，**不原地等待**。
- Master 步骤级轮询 `env-requests/`（每做一两个动作查一次），批准后 `-c` 续跑 worker 并附连接信息，同时删除申请文件。
- 环境台账 `state/ENVIRONMENTS.md` 由 Master 维护（当前持有者、启动时间、用途）；队列真相以 `env-requests/` 目录为准。
- **抢占规则**：pwn 的 LOCAL_READY 申请优先于进行中的 web；web 被打断时先等其当前轮结束，超过 `ENV_PREEMPT_GRACE`（默认 300s）杀进程强收。
- **持有预算**：worker 持环境默认最长 `ENV_HOLD_BUDGET`（默认 600s），超时 Master 杀 worker、收环境、该题回 ANALYZING 重新排队。

## 平台 MCP（aixctf-challenge）使用规范

- 工具：`list_challenges` / `get_challenge` / `start_challenge` / `stop_challenge` / `view_hint` / `submit_flag`。
- `start_challenge`/`stop_challenge`/`view_hint`：**只有 Master**（customer/worker 已在配置层禁用）。
- `submit_flag`：worker 可以自行提交**本題** flag（先校验 `flag{}` 格式）；Master 保留兜底与记账职责。
- `view_hint` 会扣分（该题后续按 80% 结算），必须有用户在 REQUESTS.md 中的明确授权才可调用。
- **附件下载**：MCP 不传附件内容。先 `get_challenge` 拿 `attachments[].download_url`（相对路径），再用 curl 下载：
  ```bash
  curl -sSL -H "Authorization: Bearer $TEAM_AGENT_KEY" "$CHALLENGE_API_ENDPOINT<download_url>" -o <本地路径>
  ```
- Web 题入口：`start_challenge` 返回的 `url` + `headers`，所有请求必须携带这些 headers。
- Pwn 题入口：`start_challenge` 返回的 `tcp.host` / `tcp.port` / `tcp.handshake`。

## 其它 MCP

- **ghidra**（pyghidra-mcp，headless）：pwn 二进制反编译/符号/字符串/交叉引用分析。用 `import_binary` 导入后用 `binary_name` 引用。需要环境变量 `GHIDRA_INSTALL_DIR`（容器内已内置）。
- **chrome**（chrome-devtools-mcp）：web 题的浏览器交互（JS 渲染、前端调试）。需要自定义请求头的访问一律改用 curl/requests。

## 目录与状态文件协议

```
├── state/
│   ├── SCOREBOARD.md      # 题目总表，Master 维护
│   ├── ENVIRONMENTS.md    # 环境台账，Master 维护
│   ├── REQUESTS.md        # 用户指令队列，Customer 写入，Master 读取并标记完成
│   └── env-requests/      # 环境申请队列，worker 写 <id>.req，Master 批准后删除
├── work/<id>/             # 每题一个工作区（worker 的 cwd，会话按目录隔离）
│   ├── dispatch.md        # Master 写的任务书
│   ├── run.log            # worker 进程日志（Master 轮询解析 WORKER-REPORT）
│   ├── worker.pid         # worker 进程 pid
│   ├── notes.md           # worker 笔记（过程/发现/下一步）
│   ├── artifacts/         # 原始附件
│   └── output/            # 大输出文件
├── prompts/               # 三个角色的系统提示词 + kickoff
└── opencode.json          # agent 与 MCP 配置
```

- `SCOREBOARD.md` 状态枚举：`TODO / ANALYZING / LOCAL_READY / ENV_QUEUED / ATTACKING / SOLVED / BLOCKED / STUCK / SKIP`。
- 写入归属：SCOREBOARD/ENVIRONMENTS 只有 Master 写；REQUESTS 只有 Customer 写、Master 标记；env-requests 谁申请谁写、Master 删；work/<id>/ 归该题 worker。
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
| `GHIDRA_INSTALL_DIR` | Ghidra 安装目录（pyghidra-mcp 需要；容器内已内置） |

本地运行前需在 shell 中 export（见 README.md）；容器部署时由 `ctf.config.json` 提供。
