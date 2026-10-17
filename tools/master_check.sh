#!/usr/bin/env bash
# CTF-Master 每轮只读快照：一次性执行、立即返回、不等待、不循环、不修改任何文件。
# 用法：bash tools/master_check.sh
set -u
cd /app 2>/dev/null || exit 1

echo "=== 1. 环境申请 state/env-requests/ ==="
found=0
for f in state/env-requests/*.req; do
  [ -f "$f" ] || continue
  found=1
  id=$(basename "$f" .req)
  waited=$(( $(date +%s) - $(stat -c %Y "$f") ))
  echo "--- <id=$id> 已等待 ${waited}s ---"
  cat "$f"
done
[ "$found" = 0 ] && echo "(无)"

echo
echo "=== 2. 环境台账 state/ENVIRONMENTS.md ==="
cat state/ENVIRONMENTS.md 2>/dev/null || echo "(缺失)"

echo
echo "=== 3. worker 进程与最新报告 ==="
for d in work/*/; do
  [ -d "$d" ] || continue
  id=$(basename "$d")
  pid=$(cat "$d/worker.pid" 2>/dev/null || true)
  if [ -n "$pid" ] && ps -p "$pid" >/dev/null 2>&1; then
    state_ps="ALIVE pid=$pid etime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')"
  elif [ -n "$pid" ]; then
    state_ps="DEAD pid=$pid"
  else
    state_ps="NO-PID"
  fi
  sb=$(awk -F'|' -v id="$id" '$2+0==id {gsub(/^[ \t]+|[ \t]+$/,"",$7); print $7}' state/SCOREBOARD.md 2>/dev/null)
  echo "--- work/$id [${state_ps}] scoreboard=${sb:-?} ---"
  if [ -f "$d/run.log" ]; then
    rep=$(grep -A8 '===WORKER-REPORT===' "$d/run.log" 2>/dev/null | tail -10)
    if [ -n "$rep" ]; then echo "$rep"; else echo "(无 WORKER-REPORT)"; fi
  else
    echo "(无 run.log)"
  fi
done

echo
echo "=== 4. SCOREBOARD 概览 ==="
if [ -f state/SCOREBOARD.md ]; then
  awk -F'|' 'NR>2 && $2 ~ /^ *[0-9]+ *$/ {
      gsub(/^[ \t]+|[ \t]+$/,"",$2); gsub(/^[ \t]+|[ \t]+$/,"",$3);
      gsub(/^[ \t]+|[ \t]+$/,"",$4); gsub(/^[ \t]+|[ \t]+$/,"",$7);
      gsub(/^[ \t]+|[ \t]+$/,"",$9);
      printf "id=%-3s %-18s %-4s %-10s %s\n", $2, $3, $4, $7, $9 }' state/SCOREBOARD.md
else
  echo "(缺失)"
fi
