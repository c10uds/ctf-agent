# AIxCTF 自动解题系统

基于 OpenCode 多 Agent 能力的 CTF 自动解题系统，面向 AIxCTF 平台，只做 pwn 和 web。

## 架构

```
用户 ⇄ CTF-Customer（本地默认 agent，聊天/汇报/接收指令）
         │  写入 state/REQUESTS.md
         ▼
      CTF-Master（容器内常驻：全局状态、环境仲裁、进程调度）
         │  进程编排：cd work/<id>/ && nohup opencode run --agent ctf-worker ... &
         ▼
      CTF-Worker × N（每题一个目录、一个持续会话，-c 续跑；自行提交 flag）
```

- 进程编排而非 Task 子代理：worker 是独立 opencode 进程，每题一个 `work/<id>/` 目录，会话按目录隔离、`-c` 续跑保持上下文连续；Master 后台派发后靠轮询 `run.log`（`WORKER-REPORT` 状态块）掌握进度。
- 环境仲裁：worker 通过 `state/env-requests/<id>.req` 申请环境，Master 独占 start/stop，pwn 抢占 web、短借短还；被抢占的 web 题由 Master 代写 `.req`（附 `preempted_at`）重新入队，归还后**最高优先**拿回环境，不会被新题饿死（详见 AGENTS.md）。
- 角色提示词在 `prompts/`，agent 与 MCP 配置在 `opencode.json`，共享协议在 `AGENTS.md`。

## PWN 二进制分析归档

pwn worker 对每个要分析的二进制**分析一次、全部落盘**：先用 ghidra MCP `import_binary` 导入，再用 `tools/ghidra_export.py` 复用同一 Ghidra 工程逐函数反编译到 `work/<id>/analysis/<二进制>/`：

```
analysis/<二进制>/
├── INDEX.md        # sha256/文件清单/全函数表/高危导入/读取示例
├── metadata.txt    # 架构/位宽/endian/编译器/hash/入口点
├── functions.txt   # 地址 | 名称 | 大小 | 文件
├── strings.txt
├── imports.txt
└── src/<函数名>.c   # 每函数一文件，文件名=函数名（非法字符清洗、重名加地址后缀）
```

```bash
python3 tools/ghidra_export.py --binary main --binary-path artifacts/main --out work/42/analysis/main
```

之后一切阅读/检索都走本地文件（`read_file`/`grep`），**不把大段反编译经 MCP 灌进上下文**，上下文被重置（`-c` 续跑 / 容器重启）也不丢分析；ghidra MCP 保留用于语义搜索、调用图、读内存、改命名/注释等交互。**分析哪些二进制由 worker 自行判断**（至少主程序；libc/ld 等只在需要算偏移时才归档）。`tools/archive_challenge.sh <题目目录>` 做惰性辅助：解压附件并列出 ELF 候选，不自动归档。

## 安装准备

1. **OpenCode**：`npm i -g opencode-ai`，并配置好模型（`opencode auth login`）。
2. **Chrome**：安装 Chrome 浏览器（chrome-devtools-mcp 会自动启动它，首次运行 npx 会下载该 MCP 包）。
3. **Ghidra**（pwn 反编译用）：
   - 安装 JDK 21（注意：部分发行版的 openjdk 版本串会让 Ghidra 误判版本，推荐 Amazon Corretto / Eclipse Temurin）与 [Ghidra](https://ghidra-sre.org/)；
   - 设置 `GHIDRA_INSTALL_DIR` 指向 Ghidra 安装目录；
   - 首次运行时 `uvx pyghidra-mcp` 会自动下载依赖（需要 [uv](https://docs.astral.sh/uv/)）。
4. **凭据**：
   ```bash
   cp .env.example .env   # 填入 TEAM_AGENT_KEY / CHALLENGE_API_ENDPOINT / GHIDRA_INSTALL_DIR
   set -a; source .env; set +a   # Git Bash；PowerShell 请自行 setx 或 $env: 设置
   ```

## 启动（推荐双终端）

**终端 1 —— 总指挥（自动解题主循环）：**

```bash
opencode run --agent ctf-master --auto "$(cat prompts/kickoff-master.md)"
```

**终端 2 —— 用户接口（与 CTF-Customer 聊天、看进度、下指令）：**

```bash
opencode        # 默认 agent 即 ctf-customer
```

单终端用法：直接运行 `opencode` 与 ctf-customer 对话（它只读写状态文件，不调度）；Master 建议在独立终端跑。TUI 内可用 Tab 切换 agent。

## Docker 部署（平台评测）

镜像基于 `ubuntu:24.04`，内含 opencode、Chrome、Ghidra 12.1.4、pyghidra-mcp、pwntools 等完整工具链。**容器启动即自动运行 CTF-Master 开始比赛**（`docker/entrypoint.sh`）。

构建：

```bash
docker build -t ctf-agent .
```

构建期网络适配（默认即可在国内构建，全部为可选 ARG）：

| ARG | 默认值 | 说明 |
| --- | --- | --- |
| `APT_MIRROR` | `mirrors.huaweicloud.com` | apt 源（华为镜像）；置空恢复官方源： `--build-arg APT_MIRROR=` |
| `GHIDRA_PROXY` | 空（直连 GitHub） | GitHub 不可达时： `--build-arg GHIDRA_PROXY=https://ghfast.top/` |
| `GEM_SOURCE` | 空（rubygems.org） | rubygems 不可达时： `--build-arg GEM_SOURCE=https://mirrors.aliyun.com/rubygems/` |

如果 Docker 拉取镜像或构建下载仍被网络阻断，可走本机 7897 代理（Clash 等）：宿主机先 `docker pull docker.1ms.run/library/ubuntu:24.04 && docker tag docker.1ms.run/library/ubuntu:24.04 ubuntu:24.04` 解决基础镜像；构建内下载用 `--build-arg HTTPS_PROXY=http://host.docker.internal:7897 --build-arg HTTP_PROXY=http://host.docker.internal:7897`（这两个是 BuildKit 预定义 ARG，不会残留进镜像）。

平台启动容器时需要注入的环境变量：

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `TEAM_AGENT_KEY` | 是 | 平台 Agent Key |
| `CHALLENGE_API_ENDPOINT` | 是 | 题目服务器 Agent API 端点 |
| `OPENCODE_MODEL` | 否 | 指定模型，如 `anthropic/claude-sonnet-4-5` |
| 模型 provider 的 API Key | 是 | 如 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OPENCODE_API_KEY`，取决于所用 provider |
| `RUN_ONCE` | 否 | 设为 `1` 时只跑一轮全新会话后退出（调试用） |
| `MASTER_CONTINUE_ROUNDS` | 否 | 每个全新会话后的 `-c` 续跑次数，默认 5 |
| `MASTER_RESTART_DELAY` | 否 | 每大轮（全新会话开局）之间的间隔秒数，默认 120 |

### 推荐：配置文件 + 本地 LLM 网关模式（自包含镜像）

把平台凭据和网关回连地址写进 `ctf.config.json` 再构建，镜像完全自包含，平台无需注入任何变量：

```bash
cp ctf.config.example.json ctf.config.json   # 填 platform（平台凭据）+ gateway（你本机地址/token）
docker build -t ctf-agent .
```

> 注意：`ctf.config.json` 含密钥，会被打包进镜像，请勿上传公开仓库；它已被 `.gitignore` 排除。
> 未提供 `ctf.config.json` 时构建会报错——若仍想用环境变量模式，删除 Dockerfile 末尾的 `COPY ctf.config.json` 一行即可。

**LLM 网关（模型路由完全在本地，容器无感）**：

```
容器内 opencode ──> 127.0.0.1:8787（llm-forwarder）
                     │ 反向 WS 隧道（token 鉴权、断线重连、SSE 逐 chunk 转发）
                     ▼
              你本地的 gateway/gateway.py ──> 真实 OpenAI 兼容上游
```

容器内 opencode 的 provider 被转发器自动写成 `http://127.0.0.1:8787/v1`（模型占位 `gateway/auto`）。**切换模型/上游只改本地，容器和 agent 进程零改动、不重启，下一个请求即生效。**

本地启动网关：

```bash
pip install -r gateway/requirements.txt
python gateway/gateway.py --upstream https://api.example.com/v1 --key sk-xxx --model gpt-4o-mini --token <与 config 一致>
# 或用配置文件：cp gateway/gateway.config.example.json gateway/gateway.config.json 后编辑
python gateway/gateway.py --config gateway/gateway.config.json
```

- 网关会把请求里的模型重写为 `--model` 指定的真实模型，替换真实 key，并在控制台打印每条请求日志（模型、耗时、token、prompt/响应前 200 字符预览）。
- 想临时换模型：杀掉网关换个 `--model` 重启即可（容器侧无感）。
- `gateway/mock_upstream.py` 是不耗 key 的链路自测假上游：`python gateway/mock_upstream.py 9001`，网关 `--upstream http://127.0.0.1:9001/v1` 即可演练。
- 隧道断开期间容器内请求会收到 502 并自动重试恢复；网关另有本地直连端口 `http://127.0.0.1:8788/v1` 供本机程序使用（`--http-port 0` 可关）。

本地自测：

```bash
docker run --rm \
  -e TEAM_AGENT_KEY=xxx \
  -e CHALLENGE_API_ENDPOINT=https://xxx/api/challenge/v1/agent \
  -e OPENCODE_MODEL=anthropic/claude-sonnet-4-5 \
  -e ANTHROPIC_API_KEY=sk-xxx \
  ctf-agent
```

说明：

- Master 循环策略：**1 次全新会话（kickoff 指令）+ 5 次 `-c` 续跑（"继续答题"，保留上下文免冷启动对账）为一大轮**，之后丢弃上下文重新开局防止膨胀，大轮间隔 `MASTER_RESTART_DELAY` 秒；状态在 `state/`、`work/` 文件里，重启不丢进度。如需跨容器持久化，挂载 `-v ctf-state:/app/state -v ctf-work:/app/work`。
- 容器内用的是 `docker/opencode.json`（Linux 版：无 `cmd /c` 包装，Chrome 无头 + no-sandbox），与本地 Windows 的 `opencode.json` 是两份，**改 agent 定义时两份要同步改**。
- Chrome 以 `--headless --no-sandbox` 运行（容器内 root 的必要姿势）；Ghidra 12.1.4 已内置并通过 `GHIDRA_INSTALL_DIR=/opt/ghidra` 提供给 pyghidra-mcp。

## 观测面板（实时推流）

本地起一个 Web 面板，**实时**（SSE 推流，非轮询刷新）观测容器内正在发生的一切，并可直接与 ctf-customer 对话。

**数据通路**：容器内 `docker/llm-forwarder.py` 在同一条反向 WS 隧道上，除转发 LLM 外还上报事件
（LLM 请求/响应、`state/` 与 `work/` 文件变更、worker 进程与资源、环境队列），本地 `gateway` 维护
事件总线 + 环形缓冲 + JSONL 落盘，并以 SSE 广播给浏览器；Chat 走同一条隧道下行到容器内的 customer
会话（cwd `/app/customer`，与 Master 的 `/app` 会话隔离，故 `-c` 不会串上下文），一切操作仍由
customer 写 `state/REQUESTS.md`、由 Master 执行——**没有任何绕过 Master 的旁路**。

**启动**（本机）：

```bash
# 1) 构建前端（首次或改前端后；若 shell 有 NODE_ENV=production 需 --include=dev）
cd dashboard && npm install && npm run build && cd ..

# 2) 起网关 + 面板（同时是容器要连的隧道服务端）
python gateway/gateway.py --config gateway/gateway.config.json
#   面板地址 http://127.0.0.1:8791
```

**页面**：总览（容器指标 / worker 进程 / 最近 AI 活动）、题目（SCOREBOARD）、题目详情（AI 请求流 · notes.md · run.log · 进程）、Master 流、环境（台账 + 申请队列）、Chat（与 customer 对话，历史留存 `gateway/logs/chat.jsonl`）。

**请求归属**：每条 LLM 请求按发起进程的 cwd 精确判定 agent 与题号（worker → `work/<id>`、customer → `customer`、其余 → `master`），**零配置**，不用改 Master 的派发命令。

**配置 / 关闭**：`gateway.config.json` 的 `dashboard_port` / `dashboard_host` / `static` / `logs_dir`；`--dashboard-port 0` 可关闭面板。面板默认只绑 `127.0.0.1`。
容器侧可调 `CTF_WATCH_INTERVAL`（采集间隔秒，默认 1）与 `CTF_CUSTOMER_DIR`（customer 会话目录）。

**事件落盘**：`gateway/logs/<topic>.jsonl`（llm_req / llm_resp / chat / fs / proc / metrics / env / scoreboard），供事后复盘。

## 与系统交互

- 对 Customer 说："现在进度如何" / "优先做 web 第 8 题" / "授权查看第 12 题提示"（会告知 80% 扣分后果）/ "pwn 并行数提到 5 个"。
- 所有指令进入 `state/REQUESTS.md`，Master 每轮主循环开始时执行。
- 想看原始状态：直接翻 `state/SCOREBOARD.md`、`state/ENVIRONMENTS.md`、`state/env-requests/`（环境申请队列）、`work/<id>/notes.md`（各题笔记）与 `work/<id>/run.log`（worker 实时日志）。

## 排错

- `opencode mcp list` / `opencode debug config`：检查 MCP 与配置加载情况。
- ghidra MCP 首次启动慢（JVM + 依赖下载，超时已放宽到 180s）；确认 `GHIDRA_INSTALL_DIR` 正确。
- chrome MCP 需要本机安装 Chrome；Windows 下配置已用 `cmd /c` 包装 npx。
- 平台 MCP 401/403：检查 `TEAM_AGENT_KEY` 是否已 export 到启动 opencode 的同一个 shell。
