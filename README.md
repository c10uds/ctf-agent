# AIxCTF 自动解题系统

基于 OpenCode 多 Agent 能力的 CTF 自动解题系统，面向 AIxCTF 平台，只做 pwn 和 web。

## 架构

```
用户 ⇄ CTF-Customer（默认 agent，聊天/汇报/接收指令）
         │  写入 state/REQUESTS.md 或 Task 调起
         ▼
      CTF-Master（总指挥：全局状态、派发任务、管理环境与提交）
         │  Task 并行派发
         ▼
      CTF-Sliver × N（单题解题：本地分析 → 远程打 → 报告 flag）
```

- 角色提示词在 `prompts/`，agent 与 MCP 配置在 `opencode.json`，共享协议在 `AGENTS.md`。
- 协作通过 `state/` 下的状态文件完成，互不越权（详见 AGENTS.md）。

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
opencode run --agent ctf-master "$(cat prompts/kickoff-master.md)"
```

**终端 2 —— 用户接口（与 CTF-Customer 聊天、看进度、下指令）：**

```bash
opencode        # 默认 agent 即 ctf-customer
```

单终端用法：直接运行 `opencode`，与 ctf-customer 对话让它用 Task 调起 ctf-master（调起期间该会话会等待 Master 跑完一轮才返回）。TUI 内可用 Tab 切换 agent、`@ctf-sliver` 手动点名子代理。

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
| `RUN_ONCE` | 否 | 设为 `1` 时只跑一轮；默认每轮结束后 120s 自动重启 Master（断点续打、检查新题） |
| `MASTER_RESTART_DELAY` | 否 | 重启间隔秒数，默认 120 |

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

- Master 每轮跑完会自动重启续打（状态在 `state/`、`notes/`、`work/` 文件里，重启不丢进度）；如需跨容器持久化，挂载 `-v ctf-state:/app/state`。
- 容器内用的是 `docker/opencode.json`（Linux 版：无 `cmd /c` 包装，Chrome 无头 + no-sandbox），与本地 Windows 的 `opencode.json` 是两份，**改 agent 定义时两份要同步改**。
- Chrome 以 `--headless --no-sandbox` 运行（容器内 root 的必要姿势）；Ghidra 12.1.4 已内置并通过 `GHIDRA_INSTALL_DIR=/opt/ghidra` 提供给 pyghidra-mcp。

## 与系统交互

- 对 Customer 说："现在进度如何" / "优先做 web 第 8 题" / "授权查看第 12 题提示"（会告知 80% 扣分后果）/ "pwn 并行数提到 5 个"。
- 所有指令进入 `state/REQUESTS.md`，Master 每轮主循环开始时执行。
- 想看原始状态：直接翻 `state/SCOREBOARD.md`、`state/ENVIRONMENTS.md`、`notes/`。

## 排错

- `opencode mcp list` / `opencode debug config`：检查 MCP 与配置加载情况。
- ghidra MCP 首次启动慢（JVM + 依赖下载，超时已放宽到 180s）；确认 `GHIDRA_INSTALL_DIR` 正确。
- chrome MCP 需要本机安装 Chrome；Windows 下配置已用 `cmd /c` 包装 npx。
- 平台 MCP 401/403：检查 `TEAM_AGENT_KEY` 是否已 export 到启动 opencode 的同一个 shell。
