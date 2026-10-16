#!/usr/bin/env bash
# 一键准备本地评测环境：编译两道 pwn（含从当前系统拷 libc/ld）+ 装平台依赖。
set -euo pipefail
cd "$(dirname "$0")"

bash pwn/fmtstr/build.sh
bash pwn/noteheap/build.sh

python3 -m pip install -q -r platform/requirements.txt
echo "完成。启动平台：python3 challenges/platform/fake_platform.py --port 8080"
