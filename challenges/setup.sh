#!/usr/bin/env bash
# 一键准备本地评测环境：编译 5 道 pwn + 装平台依赖。
# 注意：web 题在 docker 里跑（platform 会自动构建 ctf-web-runner 镜像）。
set -euo pipefail
cd "$(dirname "$0")"

bash pwn/build_all.sh

python3 -m pip install -q -r platform/requirements.txt
echo "完成。启动平台：python3 challenges/platform/fake_platform.py --port 8080"
