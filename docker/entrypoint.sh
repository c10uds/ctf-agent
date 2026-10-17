#!/usr/bin/env bash
# AIxCTF 容器入口：启动即自动运行 CTF-Master 开始比赛
# 循环策略：1 次全新会话 + 5 次 -c 续跑（保留上下文、省去冷启动对账），
# 然后丢弃上下文重新开局，防止上下文无限膨胀。
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

# customer 会话目录：cwd 与 Master 的 /app 不同，保证 opencode 会话隔离；
# 通过软链复用同一份 opencode 配置与 state/work，提示词里的相对路径一字不用改。
CUSTOMER_DIR="${CTF_CUSTOMER_DIR:-/app/customer}"
mkdir -p "$CUSTOMER_DIR"
ln -sfn /app/opencode.json "$CUSTOMER_DIR/opencode.json"
ln -sfn /app/state "$CUSTOMER_DIR/state"
ln -sfn /app/work "$CUSTOMER_DIR/work"

if [ "${RUN_ONCE:-0}" = "1" ]; then
  exec opencode run --agent ctf-master --auto "$(cat prompts/kickoff-master.md)"
fi

CONTINUE_ROUNDS="${MASTER_CONTINUE_ROUNDS:-5}"   # 每个全新会话后续跑次数
CONTINUE_DELAY="${MASTER_CONTINUE_DELAY:-30}"    # 每次 -c 续跑之间的间隔秒数（让 worker 有时间推进，避免 Master 空转烧 token）
DELAY="${MASTER_RESTART_DELAY:-120}"             # 每大轮（新会话开局）之间的间隔秒数

child=0
term() {
  echo "[entrypoint] 收到停止信号，退出"
  [ "$child" != "0" ] && kill -TERM "$child" 2>/dev/null
  exit 0
}
trap term TERM INT

run_master() {  # $1=消息  $2=continue 时续跑最近会话
  if [ "${2:-}" = "continue" ]; then
    opencode run --agent ctf-master --auto -c "$1" &
  else
    opencode run --agent ctf-master --auto "$1" &
  fi
  child=$!
  wait "$child"
  rc=$?
  [ "$rc" -ne 0 ] && echo "[entrypoint] CTF-Master 退出码 $rc"
  return 0
}

echo "[entrypoint] AIxCTF 自动解题启动：1 新会话 + ${CONTINUE_ROUNDS} 次续跑为一大轮，大轮间隔 ${DELAY}s"
while true; do
  echo "[entrypoint] $(date -Is) 开启全新 Master 会话"
  run_master "$(cat prompts/kickoff-master.md)"
  for i in $(seq 1 "$CONTINUE_ROUNDS"); do
    echo "[entrypoint] $(date -Is) 续跑 Master 会话（$i/$CONTINUE_ROUNDS）"
    run_master "继续答题" continue
    sleep "$CONTINUE_DELAY" & child=$!
    wait "$child"
  done
  echo "[entrypoint] 本大轮结束，${DELAY}s 后开新会话（重置上下文）"
  sleep "$DELAY" & child=$!
  wait "$child"
done
