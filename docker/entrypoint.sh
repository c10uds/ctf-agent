#!/usr/bin/env bash
# AIxCTF 容器入口：启动即自动运行 CTF-Master 开始比赛
set -u
cd /app

if [ -f /app/ctf.config.json ]; then
  # 凭据来源 1：构建时打包进镜像的 ctf.config.json（优先级高）
  export TEAM_AGENT_KEY="$(python3 -c 'import json;print(json.load(open("/app/ctf.config.json"))["platform"]["team_agent_key"])')"
  export CHALLENGE_API_ENDPOINT="$(python3 -c 'import json;print(json.load(open("/app/ctf.config.json"))["platform"]["challenge_api_endpoint"])')"
  # 若配置了 gateway 段：启动 LLM 转发器（127.0.0.1:8787 ← 反向隧道 → 本地网关），并注入 opencode provider
  if python3 -c 'import json,sys;sys.exit(0 if json.load(open("/app/ctf.config.json")).get("gateway",{}).get("server_url") else 1)'; then
    GATEWAY_INJECT_CONFIG=/app/opencode.json nohup python3 /app/docker/llm-forwarder.py >/tmp/llm-forwarder.log 2>&1 &
    echo "[entrypoint] llm-forwarder 已启动（日志 /tmp/llm-forwarder.log）"
  elif [ -n "${OPENCODE_MODEL:-}" ]; then
    export OPENCODE_CONFIG_CONTENT="{\"model\": \"${OPENCODE_MODEL}\"}"
  fi
else
  # 凭据来源 2：环境变量 / 挂载的 .env
  if [ -f /app/.env ]; then set -a; source /app/.env; set +a; fi
  if [ -n "${OPENCODE_MODEL:-}" ]; then
    export OPENCODE_CONFIG_CONTENT="{\"model\": \"${OPENCODE_MODEL}\"}"
  fi
fi

: "${TEAM_AGENT_KEY:?TEAM_AGENT_KEY 未设置（提供 ctf.config.json 或注入环境变量）}"
: "${CHALLENGE_API_ENDPOINT:?CHALLENGE_API_ENDPOINT 未设置（提供 ctf.config.json 或注入环境变量）}"

mkdir -p state notes work

if [ "${RUN_ONCE:-0}" = "1" ]; then
  exec opencode run --agent ctf-master --auto "$(cat prompts/kickoff-master.md)"
fi

DELAY="${MASTER_RESTART_DELAY:-120}"
child=0
term() {
  echo "[entrypoint] 收到停止信号，退出"
  [ "$child" != "0" ] && kill -TERM "$child" 2>/dev/null
  exit 0
}
trap term TERM INT

echo "[entrypoint] AIxCTF 自动解题启动：每轮结束后 ${DELAY}s 重启 CTF-Master（断点续打/检查新题）"
while true; do
  echo "[entrypoint] $(date -Is) 启动 CTF-Master"
  opencode run --agent ctf-master --auto "$(cat prompts/kickoff-master.md)" &
  child=$!
  wait "$child"; rc=$?
  [ "$rc" -ne 0 ] && echo "[entrypoint] CTF-Master 异常退出（code=$rc）"
  echo "[entrypoint] 本轮结束，${DELAY}s 后开始下一轮"
  sleep "$DELAY" & child=$!
  wait "$child"
done
